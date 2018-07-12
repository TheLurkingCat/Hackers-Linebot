from os import environ

import numpy
from linebot.models.send_messages import ImageSendMessage
from pymongo import MongoClient

from pyxdameraulevenshtein import normalized_damerau_levenshtein_distance


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
                if self.levenshtein_distance(name, documents['linename'], 0.5):
                    names.append('{}--->{}'.format(documents['linename'],
                                                   documents['gamename']))

                if self.levenshtein_distance(name, documents['gamename'], 0.5):
                    names.append('{}--->{}'.format(documents['gamename'],
                                                   documents['linename']))

        names = set(names)  # Remove the duplicates.
        return '\n'.join(names)

    @staticmethod
    def levenshtein_distance(source, target, threshold):
        """
        A module build by 
        https://github.com/gfairchild/pyxDamerauLevenshtein
        Args:
            source: The string user input.
            target: The string to find.
        Returns:
            True: When source can change into target in 1/2 target's length.
            False: Else returns False.
        """
        distance = normalized_damerau_levenshtein_distance(source, target)
        return distance < threshold

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
        try:
            return doc[word]
        except KeyError:
            return word

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
        if not self.is_wiki_page(title):
            raise (ValueError('Error: {} not found at line {}！'.format(title, i)))

        if int(level1) > int(level2):
            raise (ValueError('Error: {} > {} at line {}！'.format(level1, level2, i)))

        threshold = 10

        if number > threshold:
            raise(ValueError('Error: Node limit exceed at line {}！\nThreshold: {}, got {}'.format(
                i, threshold, number)))
        try:
            total = self.data_table[n][title][level2]
            total -= self.data_table[n][title][level1]
        except KeyError:
            raise(ValueError('Error: Incorrect value at line {}！'.format(i)))
        total *= number
        return total
