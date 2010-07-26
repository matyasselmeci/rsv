#!/usr/bin/env python

import os
from time import strftime, gmtime

def system(command):
    if command.find("2>") == -1:
        command += " 2>&1"

    child = os.popen(command)
    data = child.read()
    err = child.close()
    return (err, data)


def timestamp(local=False):
    """ When generating timestamps, we want to use UTC when communicating with
    the remote collector.  For example:
      2010-07-25T05:18:14Z

    However, it's nice to print a more readable time for the local display, for
    example:
      2010-07-25 00:18:14 CDT

    This is consistent with RSVv3
    """
    
    if local:
        return strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        return strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())
