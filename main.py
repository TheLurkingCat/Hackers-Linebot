from ast import literal_eval
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
owners = set(literal_eval(environ['Owner']))
editors = set(literal_eval(environ['Admins']))
need_check = set(literal_eval(environ['Check']))
token = None
input_str = ''
isgroup = False
state = False

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
                label='查遊戲維基網址',
                text='貓 光炮'
            ),
            MessageAction(
                label='查遊戲內物品資料',
                text='貓 光炮 21'
            )
        ]
    )
)


def reply(x, check=None):
    """回復使用者，但是會先檢查"""
    if not isinstance(x, SendMessage):
        if x:
            # 如果在群組內發言而且沒有免檢查特權就檢查他
            if (check is not None or isgroup) and database.anti_spam(input_str, x):
                return
            x = TextSendMessage(x)
            bot_reply(token, x)
    else:
        bot_reply(token, x)


database = Database()
net = Net()


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

    global token, input_str, isgroup, state
    text = event.message.text
    token = event.reply_token
    # 透過某個群組喊話
    if (
            event.source.type == "group" and
            event.source.group_id == environ['TalkID']):

        bot.push_message(environ['GroupMain'],
                         TextSendMessage(text))

    if text == "我的ID" and event.source.type == "user":
        reply(event.source.user_id)

    if text == "群組ID" and event.source.type == "group":
        reply(event.source.group_id, 'check')

    # 管理指令們
    if event.source.user_id in owners:
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
    if text == 'Selftest':
        t = post('https://little-cat.herokuapp.com/').status_code
        if t == 401:
            reply('喵喵喵！')
        elif t == 500:
            reply('蹦蹦蹦！')
        else:
            reply(str(t))

    text_msg = text.split()
    if text_msg[0] == '貓':
        if state:
            return
        isgroup = True if event.source.type == "group" and event.source.group_id in need_check else False
        text_msg[1] = database.correct(text_msg[1])
        msg_length = len(text_msg)
        input_str = ' '.join(text_msg[1:])
        if msg_length == 2:
            if text_msg[1] == '群規':
                reply(database.get_rules())

            elif text_msg[1] == '執法者':
                reply(database.get_rules(-1))

            elif database.is_wiki_page(text_msg[1]):
                reply(net.get_uri(text_msg[1]))

            elif text_msg[1] == '使用說明':
                reply(user_guide)
            try:
                reply(database.get_username(text_msg[1]))
            except ValueError as e:
                reply(str(e))
        elif msg_length == 3:
            if text_msg[1] == '群規':
                try:
                    reply(database.get_rules(int(text_msg[2])))
                except ValueError:
                    pass
            elif database.is_wiki_page(text_msg[1]):
                reply(net.get_data(text_msg[1], int(text_msg[2])))

        elif msg_length == 4:
            if text_msg[3] == '圖片' and (event.source.type == "user" or event.source.user_id in editors):
                try:
                    reply(database.get_picture(text_msg[1], text_msg[2]))
                except ValueError as e:
                    reply(str(e))
            elif text_msg[2] == '對應':
                database.add_common_name(text_msg[1], text_msg[3])
        else:
            switch = ('計算時間', '計算經驗')
            try:
                search_type = switch.index(text_msg[1])
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

    elif text[0] == '貓' and event.source.user_id in editors:
        # Deprecated(未來會偏向用Excel更新)
        text_msg = text.split(text[1])
        text_msg = [x for x in text_msg if x]
        msg_length = len(text_msg)
        if msg_length == 3:
            if text_msg[2] == '退群':
                try:
                    database.delete_name(text_msg[1])
                except ValueError as e:
                    reply(str(e))
                else:
                    reply('成功刪除一筆資料')

        elif msg_length == 4:
            if text_msg[1] == '新增資料':
                try:
                    database.add_name(text_msg[2], text_msg[3])
                except ValueError as e:
                    reply(str(e))
                else:
                    reply('成功新增一筆資料')

            elif text_msg[1] == '更新資料':
                try:
                    database.update_name(text_msg[2], text_msg[3])
                except ValueError as e:
                    reply(str(e))
                else:
                    reply('成功更新一筆資料')


if __name__ == '__main__':
    # 取得當前運作的埠
    app.run(host='0.0.0.0', port=int(environ['PORT']))
