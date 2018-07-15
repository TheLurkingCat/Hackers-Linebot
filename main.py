from ast import literal_eval
from os import environ

from flask import Flask, abort, request
from linebot.api import LineBotApi
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models.events import MessageEvent
from linebot.models.messages import TextMessage
from linebot.models.send_messages import SendMessage, TextSendMessage
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
token = None
input_str = ''
isgroup = False
state = False


def reply(x):
    if not isinstance(x, SendMessage):
        if isgroup and database.anti_spam(input_str, x):
            return
        if x:
            x = TextSendMessage(x)
            bot_reply(token, x)
    else:
        bot_reply(token, x)


database = Database()
net = Net()


@app.route("/", methods=['POST'])
def callback():
    """Validate the signature and call the handler."""
    # get X-Line-Signature header value
    try:
        signature = request.headers['X-Line-Signature']
    except KeyError:
        abort(401)
    # get request body as text
    body = request.get_data(as_text=True)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """Main hadler of the message event."""
    global token, input_str, isgroup, state
    text = event.message.text
    token = event.reply_token
    if (
            event.source.type == "group" and
            event.source.group_id == environ['TalkID']):

        bot.push_message(environ['GroupMain'],
                         TextSendMessage(text))

    if text == "我的ID" and event.source.type == "user":
        reply(event.source.user_id)

    if event.source.user_id in owners:
        if text == '關機':
            state = True
        elif text == '開機':
            state = False
        elif text == '解鎖':
            database.unlock()
        elif text == '封鎖清單':
            bot_reply(token, TextSendMessage(database.get_banned_list()))
    if text == 'Selftest':
        t = post('https://little-cat.herokuapp.com/').status_code
        if t == 401:
            reply('Server is running！')
        elif t == 500:
            reply('Server crashed！')
        else:
            reply(str(t))
    text_msg = text.split()
    if text_msg[0] == '貓':
        if state:
            return
        isgroup = True if event.source.type == "group" and event.source.group_id == environ[
            'GroupMain'] else False
        text_msg[1] = database.correct(text_msg[1])
        msg_length = len(text_msg)
        input_str = text[2:]
        if msg_length == 2:
            if text_msg[1] == '群規':
                reply(database.get_rules())

            elif text_msg[1] == '執法者':
                reply(database.get_rules(-1))

            elif database.is_wiki_page(text_msg[1]):
                reply(net.get_uri(text_msg[1]))

            elif text_msg[1] == '使用說明':
                reply('請參閱記事本')

            reply(database.get_username(text_msg[1]))

        elif msg_length == 3:
            if text_msg[1] == '群規':
                reply(database.get_rules(int(text_msg[2])))

            elif database.is_wiki_page(text_msg[1]):
                reply(net.get_data(text_msg[1], int(text_msg[2])))

        elif msg_length == 4 and (event.source.type == "user" or event.source.user_id in editors):
            if text_msg[3] == '圖片':
                reply(database.get_picture(text_msg[1], text_msg[2]))
        else:
            switch = ('計算時間', '計算經驗')
            try:
                search_type = switch.index(text_msg[1])
            except ValueError:
                search_type = None
                reply('Error: Search type not support at line 1')
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
                        reply('Error：Not Enough Parameter at line {}！'.format(i))
                    except ValueError as e:
                        reply(str(e))
                if search_type:
                    reply('總共獲得：{} 經驗'.format(total))
                else:
                    hour, minute = divmod(total, 60)
                    day, hour = divmod(hour, 24)
                    reply('總共需要：{}天{}小時{}分鐘'.format(day, hour, minute))

    elif text[0] == '貓' and event.source.user_id in editors:
        text_msg = text.split(text[1])
        text_msg = [x for x in text_msg if x]
        msg_length = len(text_msg)
        if msg_length == 3:
            if text_msg[2] == '退群':
                database.delete_name(text_msg[1])
                reply('成功刪除一筆資料')

        elif msg_length == 4:
            if text_msg[1] == '新增資料':
                database.add_name(text_msg[2], text_msg[3])
                reply('成功新增一筆資料')

            elif text_msg[1] == '更新資料':
                database.update_name(text_msg[2], text_msg[3])
                reply('成功更新一筆資料')


if __name__ == '__main__':
    # To get the port of this program running on.
    app.run(host='0.0.0.0', port=int(environ['PORT']))
