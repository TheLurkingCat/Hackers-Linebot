from urllib.parse import quote

from pandas import read_html


class Net(object):
    """控制爬蟲引擎
    屬性:
        url: 維基最基本的網址
        TC: 需要在後面加上 '(TC)' 才能正確識別的集合
        column_one_name: 資料第一欄(column)的名稱
    """

    def __init__(self):
        """基本參數"""
        self.url = "http://hackersthegame.wikia.com/wiki/"
        self.TC = set(["幻影", "核心", "入侵", "入侵策略"])
        self.column_one_name = set(['節點等級', '等級'])

    def get_data(self, title, level):
        """從維基頁面爬取資料

        參數:
            title: 程式或節點名稱
            level: 欲查詢的等級
        回傳:
            爬到的資料
        """
        if level < 1:
            return '等級不存在！'
        url = self.get_uri(title)
        data = read_html(url)
        reply_msg = []

        for dataframe in data:
            try:
                # 防止爬到圖片
                if not dataframe[0][0] in self.column_one_name:
                    continue
            except KeyError:
                continue
            for i in range(1, dataframe.shape[1]):
                try:
                    reply_msg.append('{}：{}'.format(
                        dataframe[i][0], dataframe[i][level]
                    ))
                except KeyError:
                    return '等級不存在！'
        return '\n'.join(reply_msg)

    def get_uri(self, title):
        """生成正確網址

        參數:
            title: 頁面名稱
        回傳:
            正確的連結
        """
        url = '{}{}'.format(self.url, quote(title, safe=''))

        if title in self.TC:
            return "{}%28TC%29".format(url)
        return url
