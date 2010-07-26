#!/usr/bin/env python

# Standard libraries
import os
import re
import sys
from pwd import getpwnam

# RSV libraries
import rsv

def set_defaults():
    """ This is where to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """
    
    config = {}


    def set_default_value(key, val):
        config[key] = val
        rsv.log("Setting default '%s=%s'" % (key, val), 3, 4)


    # We want remote jobs to execute on the CE headnode, so they need to use
    # the fork jobmanager.
    set_default_value("jobmanager", "fork")

    # The only metricType that any current metric has is "status".  So instead
    # of declaring it in every single <metric>.conf file, we'll set it here but
    # still make it possible to configure in case it is needed in the future.
    set_default_value("metricType", "status")

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to in bytes.  A value of 0 means no trimming.
    set_default_value("details_data_trim_length", 10000)

    return config




def validate(config):
    """ Perform validation on config values """

    #
    # make sure that the user is valid, and we are either that user or root
    #
    rsv.log("Validating user:", 2)
    if "user" not in config:
        rsv.log("ERROR: 'user' is missing in rsv.conf.  Set this value to your RSV user", 1)
        sys.exit(1)
    else:
        (desired_uid, desired_gid) = getpwnam(config["user"])[2:4]
        
        this_process_uid = os.getuid()
        if this_process_uid == desired_uid:
            rsv.log("Invoked as the RSV user (%s)" % config["user"], 2, 4)
        else:
            if this_process_uid == 0:
                rsv.log("Invoked as root.  Switching to '%s' user (uid: %s - gid: %s)" %
                        (config["user"], desired_uid, desired_gid), 1, 4)
                os.seteuid(desired_uid)
                os.setegid(desired_gid)
            else:
                rsv.log("You can only run metrics as root or the RSV user (%s)."
                        % config["user"], 1, 0)
                sys.exit(1)

                
    #
    # "details_data_trim_length" must be an integer because we will use it later
    # in a splice
    #
    try:
        config["details_data_trim_length"] = int(config["details_data_trim_length"])
    except ValueError:
        rsv.log("ERROR: details_data_trim_length must be an integer.  It is set to '%s'"
                % config["details_data_trim_length"], 1)
        sys.exit(1)


    #
    # put the consumers into a list
    #
    if "consumers" not in config:
        config["consumers"] = [] # define it so we can use it later without exception
        rsv.log("WARNING: no consumers are registered in rsv.conf.  This means that\n" +
                "records will not be sent to a central collector for availability\n" +
                "statistics.", 1)
    else:
        tmp_list = re.split("\s*,\s*", config["consumers"])
        config["consumers"] = []
        for consumer in tmp_list:
            if not consumer.isspace():
                config["consumers"].append(consumer.strip())
        rsv.log("Registered consumers: %s" % " ".join(config["consumers"]), 2, 0)

    return config
