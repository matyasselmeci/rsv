# altlogging.py
# Marco Mambelli <marco@hep.uchicago.edu>

# logging available starting python 2.3
class LogFake:
    """Simple stub for when logging is not available"""
    def _mywrite(mystr):
        print mystr
    _mywrite = staticmethod(_mywrite)

    def debug(self, mystr):
        _mywrite(mystr)

    def info(self, mystr):
        _mywrite(mystr)

    def warning(self, mystr):
        _mywrite(mystr)

    def error(self, mystr):
        _mywrite(mystr)

def set_console_logging_level(level):
    pass

has_logging = True
try:
    import logging
except ImportError:
    has_logging = False

def getLogger(logger_name):
    if has_logging:
        return logging.getLogger(logger_name)
    else:
        return LogFake()

