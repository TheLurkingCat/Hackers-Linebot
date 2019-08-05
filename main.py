"""Web api and control panel of linebot"""
from hashlib import sha3_512
from os import environ

from flask import Flask, abort, request
from linebot.api import LineBotApi
from linebot.exceptions import InvalidSignatureError
from linebot.models.actions import MessageAction
from linebot.models.events import MessageEvent
from linebot.models.messages import TextMessage
from linebot.models.send_messages import SendMessage, TextSendMessage
from linebot.models.template import ButtonsTemplate, TemplateSendMessage
from linebot.webhook import WebhookHandler

from database import Database, generate_url

app = Flask(__name__)
bot = LineBotApi(environ['ChannelAccessToken'])
handler = WebhookHandler(environ['ChannelSecret'])
database = Database()


def reply(output, event):
    """回覆使用者，但是會先檢查"""
    # 如果在群組內發言而且沒有免檢查特權就檢查他
    group_check = database.group_data['permission']['check']
    need_check = event.source.user_id not in database.group_data[
        'permission']['no_check']
    if isinstance(output, SendMessage):
        bot.reply_message(event.reply_token, output)
    elif output:
        if (event.source.type == 'group' and
                need_check and
                event.source.group_id in group_check and
                database.is_banned(output)):
            return

        output = TextSendMessage(output)
        bot.reply_message(event.reply_token, output)


@app.route("/", methods=['GET'])
def panel():
    """網頁測試介面"""
    text = "This is test msg!"
    hashed = sha3_512(text.encode())
    return hashed.hexdigest()


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


def process_single_line(commands: list):
    """單行查詢
    Args:
        commands: 包含查詢內容的列表
    """
    user_guide = TemplateSendMessage(
        alt_text='''電腦版無法顯示按紐，按鈕功能只是舉例，實際使用上請自行替換
                查群規: 貓 群規
                查名字: 貓 小貓貓
                查遊戲維基網址: 貓 光炮
                查遊戲內物品資料: 貓 光炮 21''',
        template=ButtonsTemplate(
            text='簡單功能介紹',
            actions=[
                MessageAction(label='查群規', text='貓 群規'),
                MessageAction(label='查名字', text='貓 小貓貓'),
                MessageAction(label='查遊戲內物品資料', text='貓 光炮 21'),
                MessageAction(label='查一段等級之間經驗',
                              text='貓 計算經驗\n光炮 1 0 21\n守衛 3 20 21')
            ]
        )
    )

    if len(commands) == 1:
        if commands[0] == '群規':
            return database.get_rules()
        if commands[0] == '執法者':
            return database.group_data['admin']
        if commands[0] == '使用說明':
            return user_guide
        try:
            name = database.correct(commands[0])
        except ValueError:
            return ''
        else:
            return generate_url(name)

    if commands[0] == '群規':
        try:
            return database.get_rules(int(commands[1]))
        except ValueError as error:
            print(error)
        return ''

    if commands[1] == '圖片':
        try:
            name = database.correct(commands[0])
        except ValueError:
            pass
        if database.item_data[name]['type'] != 'node':
            return database.get_picture(name, 0)

    try:
        name = database.correct(commands[0])
        level = int(commands[1])
        database.verify_input(name, level, level)
    except ValueError as error:
        pass
    else:
        return database.item_data[name]['data'][level]['data_string']
    return ''


def process_multiple_line(commands: list, function) -> int:
    """
    Args:
        commands: 包含每筆數據的列表(二維)
        function: 提供計算時間或是經驗的函數
    """
    total_value = 0

    for line in commands:
        try:
            name = database.correct(line[0])
            number = int(line[1])
            level_from = int(line[2])
            level_to = int(line[3])
        except ValueError:
            continue

        try:
            total_value += function(name, level_from, level_to)
        except ValueError:
            continue
        else:
            total_value *= number
    return total_value


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """主控制器，沒什麼功能，類似一個switch去呼叫其他功能"""
    group_id = event.source.group_id if event.source.type == 'group' else "不在群組中"
    admins = database.group_data['permission']['admins']

    if event.message.text == "我的ID" and event.source.type == "user":
        reply(event.source.user_id, event)

    # 管理指令們
    if event.source.user_id in admins or group_id == environ['GroupManage']:
        if event.message.text == '解鎖':
            database.unlock()
        elif event.message.text == '貓 更新名單':
            reply('更新後有{}筆資料'.format(database.update_name()), event)
        elif event.message.text == "群組ID" and event.source.type == "group":
            reply(group_id, event)

    split_text = [x.split() for x in event.message.text.split('\n')]

    if split_text[0] and split_text[0][0] == '貓':
        if len(split_text) == 1:
            if len(split_text[0]) < 4:
                reply(process_single_line(split_text[0][1:]), event)
            elif len(split_text[0]) == 4:
                if (split_text[0][3] == '圖片' and
                        (event.source.type == "user" or event.source.user_id in admins)):
                    try:
                        picture = database.get_picture(
                            split_text[0][1], int(split_text[0][2]))
                    except ValueError:
                        pass
                    else:
                        reply(picture, event)

            reply(database.get_username(event.message.text[2:]), event)
        elif split_text[0][1] == '計算時間':
            total = process_multiple_line(split_text[1:], database.get_time)
            hour, minute = divmod(total, 60)
            day, hour = divmod(hour, 24)
            reply('總共需要：{}天{}小時{}分鐘'.format(day, hour, minute), event)
        elif split_text[0][1] == '計算經驗':
            total = process_multiple_line(
                split_text[1:], database.get_experience)
            reply('總共獲得：{} 經驗'.format(total), event)


if __name__ == '__main__':
    # 取得當前運作的埠
    app.run(host='0.0.0.0', port=int(environ['PORT']))
