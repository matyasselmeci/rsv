#!/usr/bin/env python

# Standard libraries
import os
import re
import sys
from optparse import OptionParser

# RSV libraries
import conf
import utils
import results

# todo - remove before releasing
import pdb


#
# Declare some variables globally so that we don't have to pass them around
#
options = None
config  = None
rsv_loc = None


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



def log(message, level, indent=0):
    """ Print a message based on the verbosity level
    Current verbosity levels:
    0 - absolutely nothing
    1 - [DEFAULT] standard messages
    2 - additional debugging output
    3 - absolutely everything
    """

    if(options.verbose >= level):
        # Only indent for debugging messages.
        if level > 1 and indent != 0:
            message = " "*indent + message
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
    parser.add_option("-v", "--verbose", dest="verbose", default=1, type="int",
                      help="Verbosity level (0-3). [Default=%default]")
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

    # Set rsv_loc as a shortcut for using in other code
    global rsv_loc
    rsv_loc = os.path.join(options.vdt_location, "osg-rsv")
    results.rsv_loc = rsv_loc

    if not options.metric:
        parser.error("You must provide a metric to run")

    options.executable = os.path.join(rsv_loc, "bin", "metrics", options.metric)
    if not os.path.exists(options.executable):
        log("ERROR: Metric does not exist at %s" % options.executable, 1)
        sys.exit(1)

    if not options.uri:
        parser.error("You must provide a URI to test against")


    # Share options with the functions in results
    results.options = options

    return



def load_config():
    """ Load all configuration files:
    Load RSV configuration
    Load metric global configuration
    Load host-specific metric configuration
    """

    global config

    # Load the default values
    log("Loading default configuration settings:", 3, 0)
    config = conf.set_defaults()

    log("Reading configuration files:", 2, 0)

    #
    # Load the global RSV configuration file
    #
    global_conf_file = os.path.join(rsv_loc, "etc", "rsv.conf")
    load_config_file(global_conf_file, required=1)

    #
    # Load configuration specific to the metric
    #
    metric_conf_file = os.path.join(rsv_loc, "etc", "metrics",
                                    options.metric + ".conf")
    load_config_file(metric_conf_file, required=1)
    
    #
    # Load configuration specific to the metric/host combination
    #
    metric_host_conf_file = os.path.join(rsv_loc, "etc", "metrics", options.uri,
                                         options.metric + ".conf")
    load_config_file(metric_host_conf_file, required=0)

    #
    # Validate the configuration file
    #
    config = conf.validate(config)

    #
    # Share config with the functions in results
    #
    results.config = config

    return



def load_config_file(file, required):
    """ Parse a configuration file of "key=val" format. """
    
    log("reading configuration file " + file, 2, 4)

    if not os.path.exists(file):
        if required:
            log("ERROR: missing required configuration file '%s'" % file, 1)
            sys.exit(1)
        else:
            log("configuration file does not exist " + file, 2)
            return

    lines = open(file).readlines()
    for line in lines:
        line = line.strip()
        
        # Ignore comments
        if re.match("\#", line):
            continue

        arr = re.split("\s*=\s*", line, 2)
        if len(arr) == 2:
            (key, val) = arr
            if (key in config) and (val != str(config[key])):
                log("Overriding '%s' in config: old '%s' - new '%s'" % (key, config[key], val), 3)
            config[key] = val

    return



def ping_test():
    """ Ping the remote host to make sure it's alive before we attempt
    to run jobs """

    log("Pinging host %s:" % options.uri, 2)

    # Send a single ping, with a timeout.  We just want to know if we can reach
    # the remote host, we don't care about the latency unless it exceeds the timeout
    (ret, out) = utils.system("/bin/ping -W 3 -c 1 " + options.uri)

    # If we can't ping the host, it's CRITICAL
    if ret:
        results.ping_failure(out)
        
    log("Ping successful", 2, 4)
    return



def check_proxy():
    """ Determine if we're using a service cert or user proxy and
    validate appropriately """

    if config_val("need_proxy", "false"):
        log("Skipping proxy check because need_proxy=false", 2)
        return

    if "service_cert" in config and "service_key" in config:
        renew_service_certificate_proxy()
    elif "proxy_file" in config:
        check_user_proxy()
    else:
        pass

    return



def renew_service_certificate_proxy():
    """ Check the service certificate.  If it is expiring soon, renew it. """

    log("Checking service certificate proxy:", 2, 0)

    hours_til_expiry = 6
    seconds_til_expiry = hours_til_expiry * 60 * 60
    (ret, out) = utils.system("/usr/bin/openssl x509 -in %s -noout -enddate -checkend %s" %
                              (config["service_proxy"], seconds_til_expiry))
    
    if ret == 0:
        log("Service certificate valid for at least %s hours." % hours_til_expiry, 2, 4)
    else:
        log("Service certificate proxy expiring within %s hours.  Renewing it." %
            hours_til_expiry, 2, 4)

        grid_proxy_init_exe = os.path.join(options.vdt_location, "globus", "bin", "grid-proxy-init")
        (ret, out) = utils.system("%s -cert %s %s -key %s -valid 12:00 -debug -out %s" %
                                  (grid_proxy_init_exe, config["service_cert"],
                                   config["service_key"], config["service_proxy"]))

        if ret:
            results.service_proxy_renewal_failed(out)

    return



def check_user_proxy():
    """ Check that a proxy file is valid """

    log("Checking user proxy", 2, 0)
    
    # Check that the file exists on disk
    if not os.path.exists(config["proxy_file"]):
        results.missing_user_proxy()

    # Check that the proxy is not expiring in the next 10 minutes.  globus-job-run
    # doesn't seem to like a proxy that has a lifetime of less than 3 hours anyways,
    # so this check might need to be adjusted if that behavior is more understood.
    (ret, out) = utils.system("/usr/bin/openssl x509 -in " + config["proxy_file"] +\
                              " -noout -enddate -checkend 600")
    if ret:
        results.expired_user_proxy(out)

    return



def parse_job_output(output):
    """ Parse the job output from the worker script """

    status = None
    details = None

    lines = output.split("\n")

    if lines[0] == "JOB RESULTS:":
        status = lines[1].strip()
        details = "\n".join(lines[2:])

    if status and details:
        results.print_result(status, details)
    else:
        log("ERROR: invalid data returned from job.", 1)

        # We want to display the trimmed output, unless we're in full verbose mode
        if options.verbose != 0 and options.verbose < 3:
            log("Displaying first %s bytes of output (use -v3 for full output)" %
                config["details_data_trim_length"], 1)
            output = output[:config["details_data_trim_length"]]
        else:
            log("Displaying full output received from command:", 3)
            
        log(output, 1)
        sys.exit(1)


def execute_job():
    """ Execute the job """

    if config["execute"] == "local":
        job = "%s -m %s -u %s" % (options.executable,
                                  options.metric,
                                  options.uri)

    elif config["execute"] == "remote":
        globus_job_run_exe = os.path.join(options.vdt_location, "globus", "bin", "globus-job-run")
        job = "%s %s/jobmanager-%s -s %s -m %s" % (globus_job_run_exe,
                                                   options.uri,
                                                   config["jobmanager"],
                                                   options.executable,
                                                   options.metric)

    log("Running command '" + job + "'", 2)
    # todo - wrap in a timeout
    (ret, out) = utils.system(job)

    if ret:
        if config["execute"] == "local":
            results.local_job_failed(job, out)
        elif config["execute"] == "remote":
            results.remote_job_failed(job, out)
        
    parse_job_output(out)

    return



def config_val(key, value):
    """ Check if key is in config, and if it equals val (case-insensitive) """

    if not key in config:
        return False

    if str(config[key]).lower() == str(value).lower():
        return True

    return False
