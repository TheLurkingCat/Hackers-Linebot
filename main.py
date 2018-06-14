from ast import literal_eval
from os import environ

from flask import Flask, request, abort
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models.events import MessageEvent
from linebot.models.messages import TextMessage
from linebot.models.send_messages import ImageSendMessage, TextSendMessage, SendMessage
from linebot.api import LineBotApi
from linebot.webhook import WebhookHandler
import numpy
from pandas import read_html
from pymongo import MongoClient
from urllib.parse import quote

app = Flask(__name__)
bot = LineBotApi(environ['ChannelAccessToken'])
bot_reply = bot.reply_message
handler = WebhookHandler(environ['ChannelSecret'])
owners = set(literal_eval(environ['Owner']))
editors = set(literal_eval(environ['Admins']))
token = None


def reply(x):
    if not isinstance(x, SendMessage):
        x = TextSendMessage(x)
    bot_reply(token, x)


class DataBase(object):
    """Handles MongoDB requests
    Attributes:
        UserID: User name of mongodb.
        UserPassword: Password of the user.
        uri: Mongodb connect uri.
        db: The name of the database.
        collection: Defualt collection of database.
        data_table: Contains time_table and experience_table
    """

    def __init__(self):
        """Initial the connection"""
        self.UserID = environ['UserID']
        self.UserPassword = environ['UserPassword']
        self.uri = "mongodb://{}:{}@ds149743.mlab.com:49743/meow".format(
            self.UserID, self.UserPassword)
        self.db = MongoClient(self.uri)['meow']
        self.collection = self.db['name']
        time = self.db['time'].find_one({'_id': 0})
        experience = self.db['time'].find_one({'_id': 1})
        self.data_table = (time, experience)

    def add_name(self, gamename, linename):
        self.collection.insert_one({"gamename": gamename,
                                    "linename": linename})

    def delete_name(self, gamename):
        self.collection.delete_many({'gamename': gamename})

    def update_name(self, gamename, linename):
        self.collection.update_many({"gamename": gamename},
                                    {"$set": {"linename": linename}})

    def get_username(self, name):
        """Find out whether the name in database or not.
        Args:
            name: The name to be find.
        Returns:
            A string of name line-by-line.
        """
        names = []

        for documents in self.collection.find():
            if documents['linename'] == name:
                names.append(documents['gamename'])
            elif documents['gamename'] == name:
                names.append(documents['linename'])
            else:
                if self.levenshtein_distance(name, documents['linename']):
                    names.append('{}--->{}'.format(documents['linename'],
                                                   documents['gamename']))

                if self.levenshtein_distance(name, documents['gamename']):
                    names.append('{}--->{}'.format(documents['gamename'],
                                                   documents['linename']))

        names = set(names)  # Remove the duplicates.
        return '\n'.join(names)

    def levenshtein_distance(self, source, target, reversed=False):
        """A copy of levenshtein_distance from wikibooks.
        https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python
        Args:
            source: The longer string.
            target: The shorter string.
            reversed: True whe target's length is longer than source's.
        Returns:
            True: When source can change into target in 1/2 target's length.
            False: Else returns False.
        """
        source_length = len(source)
        target_length = len(target)

        if source_length < target_length:
            return self.levenshtein_distance(target, source, reversed=True)
        # So now we have source_length >= target_length.

        if not target_length:
            return False
        # We call tuple() to force strings to be used as sequences
        # ('c', 'a', 't', 's') - numpy uses them as values by default.
        source = numpy.array(tuple(source))
        target = numpy.array(tuple(target))

        # We use a dynamic programming algorithm, but with the
        # added optimization that we only need the last two rows
        # of the matrix.
        previous_row = numpy.arange(target.size + 1)
        for s in source:
            # Insertion (target grows longer than source):
            current_row = previous_row + 1

            # Substitution or matching:
            # Target and source items are aligned, and either
            # are different (cost of 1), or are the same (cost of 0).
            current_row[1:] = numpy.minimum(
                current_row[1:],
                numpy.add(previous_row[:-1], target != s))

            # Deletion (target grows shorter than source):
            current_row[1:] = numpy.minimum(
                current_row[1:],
                current_row[0: -1] + 1)

            previous_row = current_row

        threshold = source_length / 2 if reversed else target_length / 2

        return False if previous_row[-1] > threshold else True

    def get_picture(self, name, level, program=False):
        """Get picture of the program/node.
        Args:
            name: The name of the program or node.
            level: The level of the program or node.
            program: True when level is '',
                     because program's pictures are same at all levels.
        Returns:
            A ImageSendMessage instance of picture.
        """

        index_name = name + str(level)
        collection = self.db['pictures']
        data = collection.find_one({'Name': index_name})

        if data is None and not program:
            if program:
                return ''
            return self.get_picture(name, '', program=True)
        if data is None:
            return 'Error: Name or level is not correct！'
        else:
            return ImageSendMessage(
                original_content_url=data["originalContentUrl"],
                preview_image_url=data["previewImageUrl"])

    def get_rules(self, number=0):
        """Find out rules.
        Args:
            number: The number of rule:
                    0 means all of the rules,
                    -1 means the executers of the rules.
        Returns:
            The rule.
        """
        collection = self.db['rules']
        temp = collection.find_one({'_id': number})
        if temp is None:
            return 'Error: Rule not found！'
        else:
            return temp['rule']

    def correct(self, word):
        """Corrects the word that user misspell.
        Args:
            word: The word user types.
        Returns:
            The correct spelling of the word.
        """
        collection = self.db['correct']
        doc = collection.find_one({'_id': 0})
        if doc is None:
            return word
        else:
            return doc[word]

    def is_wiki_page(self, page):
        """Check whether the page exist or not.
        Args:
            page: The page need to check.
        Returns:
            True: The page is in hackers wikia
            False: The page is not in hackers wikia or is empty string
        """
        if not page:
            return False
        collection = self.db['wiki']
        document = collection.find_one({'_id': 0})

        return page in document['pages']

    def get_time_exp(self, title, number, level1, level2, n, i):
        """Get the upgrade time or exp from level1 to level2.
        Args:
            title: A program or node name.
            number: The amount of the node that need to upgrade.
            level1: The level of the node now.
            level2: The level the node will be after upgrade
            n: 0 for time 1 for exp
        Returns:
            How much time it take (minutes).
        """
        threshold = 10
        if number > threshold:
            raise(ValueError('Error: Node limit exceed at line {}！ Threshold: {}, got {}'.format(
                i, threshold, number)))
        try:
            total = self.data_table[n][title][level2]
            total -= self.data_table[n][title][level1]
        except KeyError:
            raise(ValueError('Error: Incorrect value at line {}！'.format(i)))
        total *= number
        return total


class Net(object):
    """Handles the web crawler
    Attributes:
        uri: The uri of the hackers wikia
        TC: Pages need to add '(TC)' after the uri
        column_one_name: The set contains the first column name of data
    """

    def __init__(self):
        """Initial the default values"""
        self.uri = "http://hackersthegame.wikia.com/wiki/"
        self.TC = set(["幻影", "核心", "入侵", "入侵策略"])
        self.column_one_name = set(['節點等級', '等級'])

    def get_data(self, title, level):
        """Get the data from wikia.
        Args:
            title: The name of the program or node.
            level: The level of the above title.
        Returns:
            The data fetch from the wikia.
        Raises:
            KeyError: The summary of the node/program doesn't have 0 key
                      and the level is not exist.
        """
        uri = self.get_uri(title)
        data = read_html(uri)
        reply_msg = []

        for dataframe in data:
            try:
                if not dataframe[0][0] in self.column_one_name:
                    continue  # Avoid picture table
            except KeyError:
                continue

            for i in range(1, dataframe.shape[1]):
                try:
                    reply_msg.append('{}：{}'.format(
                        dataframe[i][0], dataframe[i][level]
                    ))
                except KeyError:
                    return 'Error: Level limit exceed！'
        return '\n'.join(reply_msg)

    def get_uri(self, title):
        """Generates the wiki page's uri.
        Args:
            title: The page title.
        Returns:
            The uri of the page.
        """
        uri = '{}{}'.format(self.uri, quote(title, safe=''))

        if title in self.TC:
            return "{}%28TC%29".format(uri)
        return uri


database = DataBase()
net = Net()


@app.route("/", methods=['POST'])
def callback():
    """Validate the signature and call the handler."""
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

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
    global token
    token = event.reply_token
    if (
            event.source.type == "group" and
            event.source.group_id == environ['TalkID']):

        bot.push_message(environ['GroupMain'],
                         TextSendMessage(event.message.text))

    if event.message.text == "我的ID" and event.source.type == "user":
        reply(event.source.user_id)

    text_msg = event.message.text.split()
    if text_msg[0] == '貓':
        text_msg[1] = database.correct(text_msg[1])
        msg_length = len(text_msg)

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

        elif msg_length == 4 and event.source.type == "user":
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
                tofind = event.message.text.split('\n')
                del tofind[0]

                for i, data in enumerate(tofind, 1):
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
                        reply(e)
                if search_type:
                    reply('總共獲得：{} 經驗'.format(total))
                else:
                    hour, minute = divmod(total, 60)
                    day, hour = divmod(hour, 24)
                    reply('總共需要：{}天{}小時{}分鐘'.format(day, hour, minute))

    elif event.message.text[0] == '貓' and event.source.user_id in editors:
        text_msg = event.message.text.split(event.message.text[1])
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
