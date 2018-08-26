from os import environ

from flask import Flask, abort, request
from linebot.api import LineBotApi
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models.actions import MessageAction
from linebot.models.events import MessageEvent
from linebot.models.messages import TextMessage
from linebot.models.send_messages import SendMessage, TextSendMessage
from linebot.models.template import ButtonsTemplate, TemplateSendMessage
from linebot.webhook import WebhookHandler
from requests import post

from database import Database
from net import Net

app = Flask(__name__)
bot = LineBotApi(environ['ChannelAccessToken'])
bot_reply = bot.reply_message
handler = WebhookHandler(environ['ChannelSecret'])
database = Database()
net = Net()
owners = database.permission('owners')
admins = database.permission('admins')
need_check = database.permission('check')
token = None
text = ''
isgroup = False
state = False
group_id = None

user_guide = TemplateSendMessage(
    alt_text='電腦版無法顯示按紐，按鈕功能只是舉例，實際使用上請自行替換\n查群規: 貓 群規\n查名字: 貓 小貓貓\n查遊戲維基網址: 貓 光炮\n查遊戲內物品資料: 貓 光炮 21',
    template=ButtonsTemplate(
        text='簡單功能介紹',
        actions=[
            MessageAction(
                label='查群規',
                text='貓 群規'
            ),
            MessageAction(
                label='查名字',
                text='貓 小貓貓'
            ),
            MessageAction(
                label='查遊戲內物品資料',
                text='貓 光炮 21'
            ),
            MessageAction(
                label='查一段等級之間經驗',
                text='貓 計算經驗\n光炮 1 0 21\n守衛 3 20 21'
            )
        ]
    )
)


def reply(x, check=None):
    """回覆使用者，但是會先檢查"""
    global group_id, user_id

    # 如果在群組內發言而且沒有免檢查特權就檢查他

    if not isinstance(x, SendMessage):
        if x:
            if isgroup and database.anti_spam(text, x) and check is None:
                return
            x = TextSendMessage(x)
            try:
                bot_reply(token, x)
            except LineBotApiError as e:
                if "Invalid reply token" in str(e):
                    if group_id is None:
                        bot.push_message(user_id, x)
                    else:
                        bot.push_message(group_id, x)
    else:
        if isgroup and database.anti_spam(text, text) and check is None:
            return
        bot_reply(token, x)


@app.route("/", methods=['POST'])
def callback():
    """確認簽名正確後呼叫handler"""

    try:
        signature = request.headers['X-Line-Signature']
    except KeyError:
        abort(401)

    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """主控制器，沒什麼功能，類似一個switch去呼叫其他功能"""

    global token, isgroup, state, group_id, user_id, text
    user_id = event.source.user_id
    source = event.source.type
    text = event.message.text
    token = event.reply_token
    easy_switch = {'貓 群規': database.get_rules(
    ), "貓 執法者": database.get_rules(-1), "貓 使用說明": user_guide}

    if source == "group":
        group_id = event.source.group_id
    else:
        group_id = None
    # 透過某個群組喊話
    if (
            source == "group" and
            group_id == environ['TalkID']):

        bot.push_message(environ['GroupMain'],
                         TextSendMessage(text))

    if text == "我的ID" and source == "user":
        reply(user_id)

    if text == "群組ID" and source == "group":
        reply(group_id, 'nocheck')

    # 管理指令們
    if user_id in owners or group_id == environ['GroupManage']:
        if text == '關機':
            state = True
        elif text == '開機':
            state = False
        elif text == '解鎖':
            database.unlock()
        elif text == '封鎖清單':
            x = database.get_banned_list()
            x = TextSendMessage(x if x else 'None')
            bot_reply(token, x)

    # 連連看伺服器看看他有沒有活著
    if text == '連線測試' and user_id in owners:
        t = post('https://little-cat.herokuapp.com/').status_code
        if t == 401:
            reply('喵喵喵！', 'nocheck')
        elif t == 500:
            reply('蹦蹦蹦！', 'nocheck')
        else:
            reply(str(t), 'nocheck')

    if text in easy_switch:
        reply(easy_switch[text])

    text_msg = text.split()

    if text_msg[0] == '貓':
        if state:
            return
        isgroup = True if source == "group" and group_id in need_check else False
        if len(text_msg) > 1:
            quest_1 = database.correct(text_msg[1])
        msg_length = len(text_msg)
        if msg_length == 2:
            if database.is_wiki_page(quest_1):
                reply(net.get_uri(quest_1))
            elif quest_1 == '更新名單' and user_id in admins:
                reply('更新後有{}筆資料'.format(database.update_name()))
            try:
                reply(database.get_username(quest_1))
            except ValueError as e:
                reply(str(e))

        elif msg_length == 3:
            if quest_1 == '群規':
                try:
                    reply(database.get_rules(int(text_msg[2])))
                except ValueError:
                    pass
            elif database.is_wiki_page(quest_1):
                reply(net.get_data(quest_1, int(text_msg[2])))

        elif msg_length == 4:
            if text_msg[3] == '圖片' and (source == "user" or user_id in owners):
                try:
                    reply(database.get_picture(quest_1, text_msg[2]))
                except ValueError as e:
                    reply(str(e))
            elif text_msg[2] == '對應' and user_id in admins:
                database.add_common_name(quest_1, text_msg[3])
        else:
            switch = ('計算時間', '計算經驗')
            try:
                search_type = switch.index(quest_1)
            except ValueError:
                search_type = None

            if search_type is not None:
                total = 0
                tofind = text.split('\n')
                del tofind[0]

                for i, data in enumerate(tofind, 2):
                    data = data.split()
                    data[0] = database.correct(data[0])
                    if not database.is_wiki_page(data[0]):
                        continue
                    try:
                        data[1] = int(data[1])
                    except ValueError:
                        continue
                    try:
                        total += database.get_time_exp(*data, search_type, i)
                    except TypeError:
                        reply('錯誤: 第{}行參數不足！'.format(i))
                    except ValueError as e:
                        reply(str(e))
                if search_type:
                    reply('總共獲得：{} 經驗'.format(total))
                else:
                    hour, minute = divmod(total, 60)
                    day, hour = divmod(hour, 24)
                    reply('總共需要：{}天{}小時{}分鐘'.format(day, hour, minute))


if __name__ == '__main__':
    # 取得當前運作的埠
    app.run(host='0.0.0.0', port=int(environ['PORT']))
