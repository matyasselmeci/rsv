from time import sleep
from time import strftime
from time import localtime
import sys
from esmonduploader import *
import signal
import os

### File that would call EsmondUploader() with specified parameters to get and post the data ###
caller = EsmondUploader(verbose=False,start=int(opts.start),end=int(opts.end),connect=opts.url, username=opts.username, key=opts.key, goc=opts.goc)

def str2bool(word):
  return word.lower() in ("true")

def get_post():
    caller.add2log("Getting data...")
    try:
        caller.getData(str2bool(opts.disp), str2bool(opts.summary))
    except Exception as err:
        print "Error! Get unsuccessful! Exception: \"%s\" of type: \"%s\" was thrown! Quitting out." % (err,type(err))
    else:
        caller.add2log("Finished getting data succesfully!")
        caller.add2log("Starting to post data...")
        try:
            caller.postData(str2bool(opts.disp))
        except Exception as err:
            print "Error! Post unsuccessful! Exception: \"%s\" of type: \"%s\" was thrown! Quitting out." % (err,type(err))
            sys.exit(1)
        else:
            caller.add2log("Finished Posting data successfully!")
            sys.exit(0)


def handler(signum, frame):
    caller.add2log('WARNING: Running time took more than %d seconds' % int(opts.timeout))
    sys.exit(0)

# Option: Display Metadata
#if opts.disp:
#    try:
#        caller.getData(opts.disp)
#    except Exception as err:
#        print "An error occurred! Exception:  \"%s\" of type: \"%s\" was thrown!" % (err, type(err))

# Option: Get and Post Metadata
if opts.post:
    # Option: Loop Process (Repeat every 12 hours)
    if opts.loop:    
        while True:
            get_post()
            print "Waiting 43200 seconds (12 hours)"
            sleep(43200)
    # Else do once and quit out
    else:
        # Implementing some timeout
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(int(opts.timeout))
        get_post()
        signal.alarm(0)

# Option: Error Checking (Get/Post without error catching)
if opts.err:
    caller.getData()
    caller.postData()
