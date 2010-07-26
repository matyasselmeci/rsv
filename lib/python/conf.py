#!/usr/bin/env python

# Standard libraries
import re
import sys

# RSV libraries
import rsv

def set_defaults():
    """ This is a clean place to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """
    
    config = {}

    # We want remote jobs to execute on the CE headnode, so they need to use
    # the fork jobmanager.
    config["jobmanager"] = "fork"

    # The only metricType that any current metric has is "status".  So instead
    # of declaring it in every single <metric>.conf file, we'll set it here but
    # still make it possible to configure in case it is needed in the future.
    config["metricType"] = "status"

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to 4k.  A value of 0 means no trimming.
    config["details_data_trim_length"] = 4096


    return config



def validate(config):
    """ Perform validation on config values """

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

    return config
