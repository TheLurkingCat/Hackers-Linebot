class AntiSpamer(object):
    def __init__(self, time):
        self.spamlist = set()
        self.create_time = time

    def outdated(self, time):
        return time - self.create_time > 60

    def unlock(self):
        self.spamlist.clear()
