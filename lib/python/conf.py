#!/usr/bin/env python

# Standard libraries
import os
import sys
import ConfigParser
from pwd import getpwnam

# RSV libraries
import rsv

def set_defaults(config, options):
    """ This is where to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """
    
    config.add_section("rsv")
    config.add_section(options.metric)

    def set_default_value(section, key, val):
        """ Set an individual item """
        config.set(section, key, val)
        rsv.log("Setting default '%s=%s'" % (key, val), 3, 4)


    # We want remote jobs to execute on the CE headnode, so they need to use
    # the fork jobmanager.
    set_default_value(options.metric, "jobmanager", "fork")

    # The only metricType that any current metric has is "status".  So instead
    # of declaring it in every single <metric>.conf file, we'll set it here but
    # still make it possible to configure in case it is needed in the future.
    set_default_value(options.metric, "metric-type", "status")

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to in bytes.  A value of 0 means no trimming.
    set_default_value("rsv", "details-data-trim-length", 10000)

    # Set the job timeout default in seconds
    set_default_value("rsv", "job_timeout", 300)

    return




def validate(config, options):
    """ Perform validation on config values """

    #
    # make sure that the user is valid, and we are either that user or root
    #
    rsv.log("Validating user:", 2)
    try:
        user = config.get("rsv", "user")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR: 'user' is missing in rsv.conf.  Set this value to your RSV user", 1)
        sys.exit(1)

    try:
        (desired_uid, desired_gid) = getpwnam(user)[2:4]
    except KeyError:
        rsv.log("ERROR: The '%s' user defined in rsv.conf does not exist" % user, 1, 4)
        sys.exit(1)
        
    this_process_uid = os.getuid()
    if this_process_uid == desired_uid:
        rsv.log("Invoked as the RSV user (%s)" % user, 2, 4)
    else:
        if this_process_uid == 0:
            rsv.log("Invoked as root.  Switching to '%s' user (uid: %s - gid: %s)" %
                    (user, desired_uid, desired_gid), 2, 4)
            os.setgid(desired_gid)
            os.setuid(desired_uid)
        else:
            rsv.log("You can only run metrics as root or the RSV user (%s)." %
                    user, 1, 0)
            sys.exit(1)


                
    #
    # "details_data_trim_length" must be an integer because we will use it later
    # in a splice
    #
    try:
        config.getint("rsv", "details_data_trim_length")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        config.set("rsv", "details_data_trim_length", "10000")
    except ValueError:
        rsv.log("ERROR: details_data_trim_length must be an integer.  It is set to '%s'"
                % config.get("rsv", "details_data_trim_length"), 1)
        sys.exit(1)


    #
    # job_timeout must be an integer because we will use it later in an alarm call
    #
    try:
        config.getint("rsv", "job_timeout")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        config.set("rsv", "job_timeout", "300")
    except ValueError:
        rsv.log("ERROR: job_timeout must be an integer.  It is set to '%s'" %
                config.get(options.metric, "job_timeout"), 1)
        sys.exit(1)


    #
    # warn if consumers are missing
    #
    try:
        consumers = config.get("rsv", "consumers")
        rsv.log("Registered consumers: %s" % consumers, 2, 0)
    except ConfigParser.NoOptionError:
        config.set("rsv", "consumers", "")
        rsv.log("WARNING: no consumers are registered in rsv.conf.  This means that\n" +
                "records will not be sent to a central collector for availability\n" +
                "statistics.", 1)


    #
    # check vital configuration for the job
    #
    try:
        config.get(options.metric, "service-type")
        config.get(options.metric, "execute")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR: metric configuration is missing 'service-type' or 'execute' declaration.\n" +
                "This is likely caused by a missing or corrupt metric configuration file", 1, 0)
        sys.exit(1)

    
    return config
