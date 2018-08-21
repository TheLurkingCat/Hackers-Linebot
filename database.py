from datetime import datetime, timedelta
from json import dumps
from os import environ
from re import compile
from time import time

import numpy
from linebot.models.send_messages import ImageSendMessage
from pandas import concat
from pygsheets import authorize
from pymongo import MongoClient

from pyxdameraulevenshtein import normalized_damerau_levenshtein_distance


def is_similar(source, target, threshold):
    """
    使用現成模組，來源
    https://github.com/gfairchild/pyxDamerauLevenshtein

    參數:
        source: 使用者的查詢字串
        target: 資料庫的字串
        threshold: 一個介於0到1之間的值，表示可以容許兩個字串相異程度的最大值
    回傳:
        當source 和 target 相異度是否小於 threshold

    """
    distance = normalized_damerau_levenshtein_distance(source, target)
    return distance < threshold


class Database(object):
    """處理資料庫相關請求

    屬性:
        UserID: MongoDB的使用者名稱
        UserPassword: MongoDB的使用者密碼
        url: 連接MongoDB的網址
        db: 主資料庫
        collection: 預設是查詢名字
        data_table: 一個用來決定是查時間還是經驗的元組
        threshold: 同樣查詢結果的冷卻時間，單位是秒
        pattern: 用來過濾惡意請求的正則表達式
    """

    def __init__(self, UserID=None, UserPassword=None):
        """初始化MongoDB的連線"""
        if UserID is None:
            UserID = environ['UserID']
            UserPassword = environ['UserPassword']
        self.url = "mongodb://{}:{}@ds149743.mlab.com:49743/meow".format(
            UserID, UserPassword)
        self.db = MongoClient(self.url).meow
        self.collection = self.db['name']
        time = self.db.time.find_one({'_id': 0})
        experience = self.db.time.find_one({'_id': 1})
        self.data_table = (time, experience)
        self.threshold = 18000
        self.pattern = compile(r'(.*){(.*)[$](.*)}(.*)')

    def get_username(self, name):
        """查詢此名字是否已被紀錄

        參數:
            name: 欲搜尋的名字
        回傳:
            多行的可能匹配名字.
        錯誤:
            ValueError: 當查詢字串包含{$}時觸發
        """
        if self.pattern.findall(name):
            raise ValueError('嚴重的輸入錯誤，請聯繫作者或管理員')
        names = []

        for documents in self.collection.find():
            if documents['linename'] == name:
                names.append(documents['gamename'])
            elif documents['gamename'] == name:
                names.append(documents['linename'])
            else:
                if is_similar(name, documents['linename'], 0.5):
                    names.append('{}--->{}'.format(documents['linename'],
                                                   documents['gamename']))

                if is_similar(name, documents['gamename'], 0.5):
                    names.append('{}--->{}'.format(documents['gamename'],
                                                   documents['linename']))

        names = set(names)  # Remove the duplicates.
        return '\n'.join(names)

    def get_picture(self, name, level, program=False):
        """取得程式或節點的圖片

        參數:
            name: 欲查詢的東西的名稱
            level: 欲查詢的等級
            program: 因為程式只有一個等級，所以額外處理
        回傳:
            一個 ImageSendMessage 物件
        錯誤:
            ValueError: 當查詢字串包含{$}時觸發
        """
        index_name = name + str(level)
        if self.pattern.findall(index_name):
            raise ValueError('嚴重的輸入錯誤，請聯繫作者或管理員')
        collection = self.db.pictures
        data = collection.find_one({'Name': index_name})

        if data is None and not program:
            return self.get_picture(name, '', program=True)

        if data is None:
            return '名稱或等級錯誤'
        else:
            return ImageSendMessage(
                original_content_url=data["originalContentUrl"],
                preview_image_url=data["previewImageUrl"])

    def get_rules(self, number=0):
        """搜尋群規

        參數:
            number: 第幾條群規，0 代表全部, -1 代表執法者
        回傳:
            對應的內容
        錯誤:
            ValueError: 當查詢字串包含{$}時觸發
        """
        if not isinstance(number, int):
            raise ValueError('嚴重的輸入錯誤，請聯繫作者或管理員')
        collection = self.db.rules
        temp = collection.find_one({'_id': number})
        if temp is None:
            return 'Error: Rule not found！'
        else:
            return temp['rule']

    def correct(self, word):
        """將常見錯誤名稱轉換成正確名稱

        參數:
            word: 使用者輸入的文字
        回傳:
            如果有紀錄，就回傳正確的字，不然就回傳原來的字
        """
        collection = self.db.correct
        doc = collection.find_one({'_id': 0})
        try:
            return doc[word]
        except KeyError:
            return word

    def is_wiki_page(self, name):
        """確認是否為維基頁面

        參數:
            name: 程式或節點名稱
        回傳:
            此頁面是否存在
        """
        if name:
            collection = self.db.wiki
            document = collection.find_one({'_id': 0})
            return name in document['pages']
        return False

    def get_time_exp(self, title, number, level1, level2, n, i):
        """取得從level1升級到level2要花多少時間或經驗

        參數:
            title: 程式或節點的名稱
            number: 有幾個東西要升級
            level1: 這東西的當前等級
            level2: 看你想升到幾級
            n: 0 代表時間 1 代表經驗
            i: 目前在第幾行，記錄錯誤用
        回傳:
            要升多久，單位是分鐘
        錯誤:
            ValueError: 輸入資料明顯錯誤時觸發
        """
        if not self.is_wiki_page(title):
            raise ValueError('第{}行錯誤: {}找不到！'.format(i, title))

        if int(level1) > int(level2):
            raise ValueError(
                '第{}行錯誤: 原來的等級{}大於後來的等級{}！'.format(i, level1, level2))

        threshold = 10

        if number > threshold:
            raise ValueError('第{}行錯誤: 數量超過上限，沒有那麼多{}！'.format(i, title))
        try:
            total = self.data_table[n][title][level2]
            total -= self.data_table[n][title][level1]
        except KeyError:
            raise ValueError('第{}行錯誤: 資料不正確！'.format(i))
        total *= number
        return total

    def anti_spam(self, x):
        """避免有人惡意洗版

        參數:
            x: 原本使用者輸入的字串
        回傳:
            是否禁止回覆
        """
        time_int = int(time())
        collection = self.db.banned
        temp = time_int - self.threshold
        collection.delete_many({"time": {"$lte": temp}})
        Taiwan_time = str(datetime.utcnow().replace(
            microsecond=0) + timedelta(hours=8))
        for document in collection.find():
            if is_similar(x, document['input'], 0.1):
                return True
        collection.insert_one(
            {"time": time_int, "time_string": Taiwan_time, "input": x})
        return False

    def unlock(self):
        """解鎖全部被鎖定的文字"""
        collection = self.db.banned
        collection.drop()

    def get_banned_list(self):
        """取得目前被封鎖的所有內容

        回傳:
            目前被封鎖的所有內容
        """
        time_int = int(time())
        temp = time_int - self.threshold
        collection = self.db.banned
        collection.delete_many({"time": {"$lte": temp}})
        output = []
        for documents in collection.find():
            output.append('{} banned at {}'.format(
                documents['input'], documents['time_string']))
        return '\n'.join(output)

    def add_common_name(self, common_name, real_name):
        """新增常見錯誤字詞

        參數:
            common_name: 常輸錯的字串
            real_name: 正確字串
        """
        collection = self.db.correct
        doc = collection.find_one({'_id': 0})
        if common_name not in doc:
            collection.update_one(
                {'_id': 0}, {'$set': {common_name: real_name}})

    def update_name(self):
        """一次更新全部使用者遊戲和line名字

        回傳:
            目前資料數
        """

        auth = self.db.Authkey.find_one({"_id": 0})

        self.collection.drop()

        # 避免密鑰一起被記錄，所以放在遠端，需要時生成
        with open('client_secret.json', 'w') as f:
            f.write(dumps(auth))

        update_query = []

        gc = authorize(service_file=r'client_secret.json')

        sheet = gc.open_by_url(
            'https://docs.google.com/spreadsheets/d/1K8TjqjurniPnQoB8Zmca8EujmKRhNDMOHDaX7QggRV8')

        worksheet = sheet.worksheet_by_title('name to ppl')

        df = worksheet.get_as_df(has_header=False)
        df = concat([df[2], df[4]], axis=1)
        df.columns = ['gamename', 'linename']
        df['gamename'] = df['gamename'].astype('str')
        df['linename'] = df['linename'].astype('str')
        df = df.loc[3:, :].iterrows()

        for _, data in df:
            temp = data.to_dict()
            if temp['gamename'] or temp['linename']:
                update_query.append(temp)
            else:
                break
        update_query.append({'gamename': 'Meow', 'linename': '小貓貓'})
        result = self.collection.insert_many(update_query)
        return len(result.inserted_ids) - 1

    def permission(self, key):
        """取得不同管理等級的UID名單

        參數:
            key: 管理等級
        回傳:
            對應的UID列表
        """
        return self.db.permission.find_one({"_id": 0})[key]
