from urllib.parse import quote

from pandas import read_html


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
        if level < 1:
            return 'Error: Level limit exceed！'
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
