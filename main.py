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


class Variables(object):
    """
    儲存基本變數用
    """
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
    user_id = None
    user_guide = TemplateSendMessage(
        alt_text='''電腦版無法顯示按紐，按鈕功能只是舉例，實際使用上請自行替換
                    查群規: 貓 群規
                    查名字: 貓 小貓貓
                    查遊戲維基網址: 貓 光炮
                    查遊戲內物品資料: 貓 光炮 21''',
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


def reply(output, check=None):
    """回覆使用者，但是會先檢查"""

    # 如果在群組內發言而且沒有免檢查特權就檢查他
    if not isinstance(output, SendMessage):
        if output:
            if Variables.isgroup and Variables.database.anti_spam(Variables.text, output) and check is None:
                return
            output = TextSendMessage(output)
            try:
                Variables.bot_reply(Variables.token, output)
            except LineBotApiError as error:
                if "Invalid reply token" in str(error):
                    if Variables.group_id is None:
                        Variables.bot.push_message(Variables.user_id, output)
                    else:
                        Variables.bot.push_message(Variables.group_id, output)
    else:
        if Variables.isgroup and Variables.database.anti_spam(Variables.text, Variables.text) and check is None:
            return
        Variables.bot_reply(Variables.token, output)


@Variables.app.route("/", methods=['POST'])
def callback():
    """確認簽名正確後呼叫handler"""

    try:
        signature = request.headers['X-Line-Signature']
    except KeyError:
        abort(401)

    body = request.get_data(as_text=True)

    try:
        Variables.handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@Variables.handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """主控制器，沒什麼功能，類似一個switch去呼叫其他功能"""

    Variables.user_id = event.source.user_id
    Variables.source = event.source.type
    Variables.text = event.message.text
    Variables.token = event.reply_token
    easy_switch = {'貓 群規': Variables.database.get_rules(
    ), "貓 執法者": Variables.database.get_rules(-1), "貓 使用說明": Variables.user_guide}

    Variables.group_id = event.source.group_id if Variables.source == "group" else None

    # 透過某個群組喊話
    if (
            Variables.source == "group" and
            Variables.group_id == environ['TalkID']):

        Variables.bot.push_message(environ['GroupMain'],
                                   TextSendMessage(Variables.text))

    if Variables.text == "我的ID" and Variables.source == "user":
        reply(Variables.user_id)

    # 管理指令們
    if Variables.user_id in Variables.admins or Variables.group_id == environ['GroupManage']:
        if Variables.text == '關機':
            state = True
        elif Variables.text == '開機':
            state = False
        elif Variables.text == '解鎖':
            Variables.database.unlock()
        elif Variables.text == "群組ID" and Variables.source == "group":
            reply(Variables.group_id, 'nocheck')
        elif Variables.text == '封鎖清單':
            banned = Variables.database.get_banned_list()
            output = TextSendMessage(banned if banned else 'None')
            Variables.bot_reply(Variables.token, output)

    # 連連看伺服器看看他有沒有活著
    if Variables.text == '連線測試' and Variables.user_id in Variables.owners:
        state = post('https://little-cat.herokuapp.com/').status_code
        if state == 401:
            reply('喵喵喵！', 'nocheck')
        elif state == 500:
            reply('蹦蹦蹦！', 'nocheck')
        else:
            reply(str(state), 'nocheck')

    if Variables.text in easy_switch:
        reply(easy_switch[Variables.text])

    text_msg = Variables.text.split()

    if text_msg[0] == '貓':
        if state:
            return
        Variables.isgroup = True if Variables.source == "group" and Variables.group_id in Variables.need_check else False
        if len(text_msg) > 1:
            quest_1 = Variables.database.correct(text_msg[1])
        msg_length = len(text_msg)
        if msg_length == 2:
            if Variables.database.is_wiki_page(quest_1):
                reply(Variables.net.get_uri(quest_1))
            elif quest_1 == '更新名單' and (Variables.user_id in Variables.admins or Variables.group_id == environ['GroupManage']):
                reply('更新後有{}筆資料'.format(Variables.database.update_name()))
            try:
                reply(Variables.database.get_username(quest_1))
            except ValueError as error:
                reply(str(error))

        elif msg_length == 3:
            if quest_1 == '群規':
                try:
                    reply(Variables.database.get_rules(int(text_msg[2])))
                except ValueError:
                    pass
            elif Variables.database.is_wiki_page(quest_1):
                reply(Variables.net.get_data(quest_1, int(text_msg[2])))

        elif msg_length == 4:
            if text_msg[3] == '圖片' and (Variables.source == "user" or Variables.user_id in Variables.owners):
                try:
                    reply(Variables.database.get_picture(quest_1, text_msg[2]))
                except ValueError as error:
                    reply(str(error))
            elif text_msg[2] == '對應' and (Variables.user_id in Variables.admins or Variables.group_id == environ['GroupManage']):
                Variables.database.add_common_name(quest_1, text_msg[3])
        else:
            switch = ('計算時間', '計算經驗')
            try:
                search_type = switch.index(quest_1)
            except ValueError:
                search_type = None

            if search_type is not None:
                total = 0
                tofind = Variables.text.split('\n')
                del tofind[0]

                for i, data in enumerate(tofind, 2):
                    data = data.split()
                    data[0] = Variables.database.correct(data[0])
                    if not Variables.database.is_wiki_page(data[0]):
                        continue
                    try:
                        data[1] = int(data[1])
                    except ValueError:
                        continue
                    try:
                        total += Variables.database.get_time_exp(
                            *data, search_type, i)
                    except TypeError:
                        reply('錯誤: 第{}行參數不足！'.format(i))
                    except ValueError as error:
                        reply(str(error))
                if search_type:
                    reply('總共獲得：{} 經驗'.format(total))
                else:
                    hour, minute = divmod(total, 60)
                    day, hour = divmod(hour, 24)
                    reply('總共需要：{}天{}小時{}分鐘'.format(day, hour, minute))


if __name__ == '__main__':
    # 取得當前運作的埠
    Variables.app.run(host='0.0.0.0', port=int(environ['PORT']))
