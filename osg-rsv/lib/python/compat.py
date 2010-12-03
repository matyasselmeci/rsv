
""" A compatability module to implement some Python 2.4+ things for Python 2.3 """

try:
    sorted = sorted
except NameError:
    def sorted(iterable):
        """ Backporting the sorted function to Python 2.3 for RedHat 4 systems """
        tmp = list(iterable)
        tmp.sort()
        return tmp
