"""
處理資料庫相關操作的模組
"""
from asyncio import gather, get_event_loop
from hashlib import sha3_256
from os import environ
from time import time
from urllib.parse import quote

from google.oauth2.service_account import Credentials
from linebot.models.send_messages import ImageSendMessage
from pandas import read_html
from pygsheets import authorize
from pymongo import MongoClient
from requests import get

from pyxdameraulevenshtein import normalized_damerau_levenshtein_distance


def is_similar(source: str, target: str, threshold: float) -> bool:
    """
    使用現成模組，來源
    https://github.com/gfairchild/pyxDamerauLevenshtein
    Args:
        source: 使用者的查詢字串
        target: 資料庫的字串
        threshold: 一個介於0到1之間的值，表示可以容許兩個字串相異程度的最大值
    """
    distance = normalized_damerau_levenshtein_distance(source, target)
    return distance < threshold


def generate_url(title: str) -> str:
    """生成正確網址

    參數:
        title: 頁面名稱
    回傳:
        正確的連結
    """
    url = 'http://hackersthegame.wikia.com/wiki/{}{}'.format(
        quote(title, safe=''), '%28TC%29' if title in {"幻影", "核心", "入侵", "入侵策略"} else '')

    if get(url).status_code == 200:
        return url
    return ""


def get_data(name: str, level: int, max_level: int) -> str:
    """從維基頁面爬取資料

    參數:
        name: 程式或節點名稱
        level: 欲查詢的等級
    回傳:
        爬到的資料
    """
    reply_msg = []

    for dataframe in read_html(generate_url(name)):
        if (max_level < dataframe.shape[0] < max_level + 3 and
                dataframe.iloc[level, 0].isdigit() and
                level == int(dataframe.iloc[level, 0])):

            reply_msg.append(zip(*dataframe.iloc[[0, level], 1:].values))

    return '\n'.join('：'.join(pair) for data in reply_msg for pair in data)


class Database:
    """處理資料庫相關請求
    屬性:
        UserID: MongoDB的使用者名稱
        UserPassword: MongoDB的使用者密碼
        client: 主資料庫
        threshold: 同樣查詢結果的冷卻時間，單位是秒
        pattern: 用來過濾惡意請求的正則表達式
    """

    def __init__(self, user_id=None, user_password=None):
        """初始化MongoDB的連線
        Args:
            user_id: MongoDB帳號
            user_password: MongoDB密碼
        """
        if user_id is None:
            user_id = environ['UserID']
        if user_password is None:
            user_password = environ['UserPassword']
        url = "mongodb+srv://{}:{}@meow-jzx99.mongodb.net/meow?retryWrites=true".format(
            user_id, user_password)
        self.client = MongoClient(url)['meow']
        self.threshold = 3600  # 1小時
        self.cache()

    def cache(self) -> None:
        """從資料庫更新資料"""
        self.item_data = self.client['item_info'].find_one(
            {'_id': 0}, {'_id': False})
        self.group_data = self.client['group_info'].find_one(
            {'_id': 0}, {'_id': False})

    def verify_input(self, name: str, level_from: int, level_to: int) -> None:
        """檢查輸入是否合法, 一般檢查時 level_from == level_to
        Args:
            name: 程式或節點名稱
            level_from: 原本的等級
            level_to: 想升到的等級
        """
        if name not in self.item_data:
            raise ValueError('無效的名稱')
        if level_from > level_to or level_from < 0 or level_to >= len(self.item_data[name]['data']):
            raise ValueError('無效的等級')

    def get_picture(self, name: str, level: int) -> ImageSendMessage:
        """取得程式或節點的圖片
        Args:
            name: 欲查詢的東西的名稱
            level: 欲查詢的等級
        """

        self.verify_input(name, level, level)
        data = self.item_data[name]

        if data['type'] == 'node':
            if level == 0:
                raise ValueError('Database::get_picture error!')
            return ImageSendMessage(original_content_url=data['data'][level]["OriginalContentUrl"],
                                    preview_image_url=data['data'][level]["PreviewImageUrl"])

        return ImageSendMessage(original_content_url=data['program_icon']["OriginalContentUrl"],
                                preview_image_url=data['program_icon']["PreviewImageUrl"])

    def correct(self, name: str) -> str:
        """將常見錯誤名稱轉換成正確名稱
        Args:
            name: 使用者輸入的文字
        """
        if name in self.item_data:
            return name

        for key, value in self.item_data.items():
            if name in value['nickname']:
                return key

        raise ValueError("No such word")

    def get_time(self, name: str, level_from: int, level_to: int) -> int:
        """取得 level_from -> level_to 所需總時間
        Args:
            name: 程式或節點名稱
            level_from: 原本的等級
            level_to: 想升到的等級
        """
        self.verify_input(name, level_from, level_to)
        total = self.item_data[name]['data'][level_to]['time']
        total -= self.item_data[name]['data'][level_from]['time']
        return total

    def get_experience(self, name: str, level_from: int, level_to: int) -> int:
        """取得 level_from -> level_to 所需總經驗
        Args:
            name: 程式或節點名稱
            level_from: 原本的等級
            level_to: 想升到的等級
        """
        self.verify_input(name, level_from, level_to)
        total = self.item_data[name]['data'][level_to]['experience']
        total -= self.item_data[name]['data'][level_from]['experience']
        return total

    def get_username(self, name: str) -> str:
        """查詢對應的遊戲ID或Line名字
        Args:
            name: 欲查詢的名字
        """
        names = [['遊戲ID：'], ['Line名字：'], ['模糊搜尋：']]

        for doc in self.client['name'].find():
            if doc['linename'] == name:
                names[0].append(doc['gamename'])
            elif doc['gamename'] == name:
                names[1].append(doc['linename'])
            elif is_similar(name, doc['linename'], 0.5) or is_similar(name, doc['gamename'], 0.5):
                names[2].append('{}: {}'.format(
                    doc['linename'], doc['gamename']))

        return '\n'.join(item for sublist in names if len(sublist) > 1 for item in sublist)

    def get_rules(self, number=0) -> str:
        """搜尋群規
        Args:
            number: 第幾條群規，0代表全部
        """
        if 0 <= number < len(self.group_data['rule']):
            return self.group_data['rule'][number]

        raise ValueError("編號錯誤")

    def is_banned(self, output: str) -> bool:
        """避免有人惡意洗版
        Args:
            output: 預期輸出字串
        """

        hashed_output = sha3_256(output.encode()).hexdigest()
        time_now = int(time())
        collection = self.client['banned']
        collection.delete_many({"time": {"$lte": time_now - self.threshold}})

        for document in collection.find():
            if document['hased_output'] == hashed_output:
                return True

        collection.insert_one(
            {"time": time_now, 'hased_output': hashed_output})
        return False

    def unlock(self) -> None:
        """解鎖全部被鎖定的文字"""
        self.client['banned'].drop()

    def get_names(self):
        """從Google試算表抓遊戲ID和Line名字"""
        scope = ('https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive')
        credentials = Credentials.from_service_account_info(
            self.group_data['authkey'], scopes=scope)

        google_client = authorize(custom_credentials=credentials)

        sheet = google_client.open_by_url(
            'https://docs.google.com/spreadsheets/d/1K8TjqjurniPnQoB8Zmca8EujmKRhNDMOHDaX7QggRV8')

        worksheet = sheet.worksheet_by_title('name to ppl')
        gamename = worksheet.get_col(3, include_tailing_empty=False)[3:]
        linename = worksheet.get_col(5, include_tailing_empty=False)[3:]
        return zip(gamename, linename)

    def update_name(self) -> int:
        """一次更新全部使用者遊戲和line名字"""
        update_query = []
        for gamename, linename in self.get_names():
            update_query.append({'gamename': gamename, 'linename': linename})
        update_query.append({'gamename': 'Meow', 'linename': '小貓貓'})
        self.client['name'].drop()
        result = self.client['name'].insert_many(update_query, ordered=False)
        return len(result.inserted_ids) - 1

    def get_item_data(self):
        """更新等級資訊"""
        loop = get_event_loop()
        final = self.item_data.copy()

        async def get_datadata(_name, _level, _max):
            return await loop.run_in_executor(None, get_data, _name, _level, _max)

        for name in final:
            final[name]['data'][0]['data_string'] = None
            tasks = []
            for i in range(1, len(final[name]['data'])):
                task = loop.create_task(get_datadata(
                    name, i, len(final[name]['data']) - 1))
                tasks.append(task)
            result = loop.run_until_complete(gather(*tasks))
            for i in range(1, len(final[name]['data'])):
                final[name]['data'][i]['data_string'] = result[i - 1]

        self.client['item_info'].drop()
        self.client['item_info'].insert_one(final)
