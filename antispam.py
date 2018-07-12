class AntiSpamer(object):
    def __init____(self, time):
        self.spamlist = set()
        self.create_time = time

    def outdated(self, time):
        return time - self.create_time > 3600

    def unlock(self):
        self.spamlist.clear()
