#!/usr/bin/env python

# Standard libraries
import os
import re
import sys
from optparse import OptionParser

# RSV libraries
import utils
import results

# todo - remove before releasing
import pdb


#
# Declare some variables globally so that we don't have to pass them around
#
options = None
config  = None



def initialize():
    """ Handle the command line, load configuration files and do other basic
    error checking that is not metric specific """
    
    process_arguments()
    load_config()
    check_proxy()
    return



def clean_up():
    """ This will always be called before exiting.  Clean up any temporary
    files """

    pass



def log(message, level):
    """ Print a message based on the verbosity level """

    if(options.verbose >= level):
        print message
    return



def process_arguments():
    """Process the command line arguments and populate global variables"""

    global options

    #
    # Define the options to parse on the command line
    #
    usage = "usage: %prog -m <METRIC> -u <HOST> [more options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-m", "--metric",  dest="metric", help="Metric to run")
    parser.add_option("-u", "--uri",     dest="uri",    help="URI to probe")
    parser.add_option("-v", "--verbose", dest="verbose", default=1,
                      help="Verbosity level (0-3). Default=1")
    parser.add_option("-j", "--jobmanager", dest="jobmanager", default="fork",
                      help="JobManager to use.  Default=fork")
    parser.add_option("--vdt-location", dest="vdt_location",
                      help="Supersedes VDT_LOCATION environment variable")

    (options, args) = parser.parse_args()

    #
    # Do error checking on the options supplied
    #
    if options.vdt_location:
        log("Using alternate VDT_LOCATION supplied on command line", 1)
    elif "VDT_LOCATION" in os.environ:
        options.vdt_location = os.environ["VDT_LOCATION"]
    else:
        parser.error("You must have VDT_LOCATION set in your environment.\n" +\
                     "  Either source setup.sh or pass --vdt-location")

    if not options.metric:
        parser.error("You must provide a metric to run")

        options.executable = os.path.join(options.vdt_location, "osg-rsv", "bin", "metrics", options.metric)
    if not os.path.exists(options.executable):
        # todo - not parser error
        parser.error("Metric does not exist at " + options.executable)

    if not options.uri:
        parser.error("You must provide a URI to test against")


    # Share options with the functions in results
    results.options = options

    return



def load_config():
    """ Load RSV configuration and any metric specific configuration """

    global config
    config = {}

    #
    # Load the global RSV configuration file
    #
    global_conf_file = os.path.join(options.vdt_location, "osg-rsv", "etc", "rsv.conf")
    load_config_file(global_conf_file)

    #
    # Load configuration specific to the metric
    #
    

    #
    # Load configuration specific to the metric/host combination
    #


    # Share config with the functions in results
    results.config = config

    return



def load_config_file(file):
    """ Parse a configuration file of "key=val" format. """

    log("reading configuration file " + file, 2)

    if not os.path.exists(file):
        log("configuration file does not exist " + file, 2)
        return config

    lines = open(file).readlines()
    for line in lines:
        line = line.strip()
        
        # Ignore comments
        if re.match("\#", line):
            continue

        (key, val) = re.split("\s*=\s*", line, 2)
        if key and val:
            config[key] = val

    return



def ping_test():
    """ Ping the remote host to make sure it's alive before we attempt
    to run jobs """

    log("Pinging host " + options.uri, 2)

    # Send a single ping, with a timeout.  We just want to know if we can reach
    # the remote host, we don't care about the latency unless it exceeds the timeout
    (ret, out) = utils.system("/bin/ping -W 3 -c 1 " + options.uri)

    # If we can't ping the host, it's CRITICAL
    if ret:
        results.ping_failure(out)
        
    log("Ping successful", 2)
    return



def check_proxy():
    """ If we're using a service certificate, renew it now.
        If we're using a user certificate, check that it still is valid """

    #
    # User proxy file validation
    # 
    if "proxy_file" in config:
        # Check that the file exists on disk
        if not os.path.exists(config["proxy_file"]):
            results.missing_user_proxy()

        # Check that the proxy is not expiring in the next 10 minutes.  If it is
        # going to expire our job could have a strange failure
        (ret, out) = utils.system("/usr/bin/openssl x509 -in " + config["proxy_file"] +\
                                  " -noout -enddate -checkend 600")
        if ret:
            results.expired_user_proxy(out)
        
    # todo - check service certificate.  Renew if applicable

    #
    # Service certificate validation and renewal
    #

    return
    

def parse_job_output(output):
    """ Parse the job output from the worker script """

    # todo - standardize output format
    results.print_result("OK", "foo")



def execute_job():
    """ Dispatch the job to the appropriate task, remote or local """
    pass



def execute_local_job():
    pass


def execute_remote_job():
    """ Execute the remote job via globus-job-run """

    # todo - wrap in a timeout
    job = "globus-job-run %s/jobmanager-%s -s %s" % (options.uri,
                                                     options.jobmanager,
                                                     options.executable)
    log("Running command '" + job + "'", 2)
    (ret, out) = utils.system(job)

    if ret:
        results.remote_job_failed(job, out)
        
    parse_job_output(out)


