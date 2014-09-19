from time import sleep
import sys
from esmonduploader import *

### File that would call EsmondUploader() with specified parameters to get and post the data ###
caller = EsmondUploader(verbose=False,start=int(opts.start),end=int(opts.end),connect=opts.url, username=opts.username, key=opts.key, goc=opts.goc)

def get_post():
    print "Getting data..."
    try:
        caller.getData()
    except Exception as err:
        print "Error! Get unsuccessful! Exception: \"%s\" of type: \"%s\" was thrown! Quitting out." % (err,type(err))
    else:
        print "Get successful!"
        print "Posting data..."
        try:
            caller.postData()
        except Exception as err:
            print "Error! Post unsuccessful! Exception: \"%s\" of type: \"%s\" was thrown! Quitting out." % (err,type(err))
            sys.exit(1)
        else:
            print "Post successful!"
            sys.exit(0)


# Option: Display Metadata
if opts.disp:
    try:
        caller.getData(opts.disp)
    except Exception as err:
        print "An error occurred! Exception:  \"%s\" of type: \"%s\" was thrown!" % (err, type(err))

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
        get_post()
# Option: Error Checking (Get/Post without error catching)
if opts.err:
    caller.getData()
    caller.postData()
