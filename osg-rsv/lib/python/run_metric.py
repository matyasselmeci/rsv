#!/usr/bin/env python

# Standard libraries
import re
import os
import sys
import ConfigParser
from pwd import getpwnam
from optparse import OptionParser

# RSV libraries
import RSV
import Metric
import Results
import Sysutils

# todo - remove before releasing
import pdb


#
# Globals
#
VALID_OUTPUT_FORMATS = ["wlcg", "brief"]


def validate_config(rsv, metric):
    """ Perform validation on config values """

    rsv.log("INFO", "Validating configuration:")

    #
    # make sure that the user is valid, and we are either that user or root
    #
    rsv.log("INFO", "Validating user:")
    try:
        user = rsv.config.get("rsv", "user")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR", "'user' is missing in rsv.conf.  Set this value to your RSV user", 4)
        clean_up(1)

    try:
        (desired_uid, desired_gid) = getpwnam(user)[2:4]
    except KeyError:
        rsv.log("ERROR", "The '%s' user defined in rsv.conf does not exist" % user, 4)
        clean_up(1)

    # If appropriate, switch UID/GID
    rsv.sysutils.switch_user(user, desired_uid, desired_gid)

                
    #
    # "details_data_trim_length" must be an integer because we will use it later
    # in a splice
    #
    try:
        rsv.config.getint("rsv", "details_data_trim_length")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe set it again here.
        rsv.config.set("rsv", "details_data_trim_length", "10000")
    except ValueError:
        rsv.log("ERROR: details_data_trim_length must be an integer.  It is set to '%s'"
                % rsv.config.get("rsv", "details_data_trim_length"))
        clean_up(1)


    #
    # job_timeout must be an integer because we will use it later in an alarm call
    #
    try:
        rsv.config.getint("rsv", "job-timeout")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        rsv.config.set("rsv", "job-timeout", "300")
    except ValueError:
        rsv.log("ERROR", "job-timeout must be an integer.  It is set to '%s'" %
                rsv.config.get("rsv", "job-timeout"))
        clean_up(1)


    #
    # warn if consumers are missing
    #
    try:
        consumers = rsv.consumer_config.get("consumers", "enabled")
        rsv.log("INFO", "Registered consumers: %s" % consumers, 0)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        if not rsv.consumer_config.has_section("consumers"):
            rsv.consumer_config.add_section("consumers")
        rsv.consumer_config.set("consumers", "enabled", "")
        rsv.log("WARNING", "no consumers are registered in consumers.conf.  This " +
                "means that records will not be sent to a central collector for " +
                "availability statistics.")


    #
    # check vital configuration for the job
    #
    if not metric.config_get("service-type") or not metric.config_get("execute"):
        rsv.log("ERROR", "metric configuration is missing 'service-type' or 'execute' " +
                "declaration.  This is likely caused by a missing or corrupt metric " +
                "configuration file")
        clean_up(1)


    # 
    # Check the desired output format
    #
    try:
        output_format = metric.config_get("output-format").lower()
        if output_format not in VALID_OUTPUT_FORMATS:
            valid_formats = " ".join(VALID_OUTPUT_FORMATS)
            rsv.log("ERROR", "output-format '%s' is not supported.  Valid formats: %s\n" %
                    (output_format, valid_formats))
            clean_up(1)
                    
    except ConfigParser.NoOptionError:
        rsv.log("ERROR", "desired output-format is missing.\n" +
                "This is likely caused by a missing or corrupt metric configuration file")
        clean_up(1)


    return



def ping_test(rsv, metric, options):
    """ Ping the remote host to make sure it's alive before we attempt
    to run jobs """

    rsv.log("INFO", "Pinging host %s:" % options.uri)

    # Send a single ping, with a timeout.  We just want to know if we can reach
    # the remote host, we don't care about the latency unless it exceeds the timeout
    try:
        cmd = "/bin/ping -W 3 -c 1 %s" % options.host
        (ret, out, err) = rsv.run_command(cmd)
    except Sysutils.TimeoutError, err:
        rsv.results.ping_timeout(metric, cmd, err)

    # If we can't ping the host, don't bother doing anything else
    if ret:
        rsv.results.ping_failure(metric, out, err)
        
    rsv.log("INFO", "Ping successful", 4)
    return



def parse_job_output(rsv, metric, stdout, stderr):
    """ Parse the job output from the worker script """

    if(metric.config_val("output-format", "wlcg")):
        parse_job_output_wlcg(rsv, metric, stdout, stderr)
    elif(metric.config_val("output-format", "brief")):
        parse_job_output_brief(rsv, metric, stdout, stderr)
    else:
        rsv.log("ERROR", "output format unknown")

        

def parse_job_output_wlcg(rsv, metric, stdout, stderr):
    """ Parse WLCG formatted output. """
    rsv.results.wlcg_result(metric, stdout, stderr)



def parse_job_output_brief(rsv, metric, stdout, stderr):
    """ Parse the "brief" job output.  This format consists of just a keyword, status
    and details.  Here is an example:
    JOB RESULTS:
    OK
    More information, which can
    be on multiple lines.
    """

    status = None
    details = None

    lines = stdout.split("\n")

    if lines[0] == "JOB RESULTS:":
        status = lines[1].strip()
        details = "\n".join(lines[2:])

    if status and details:
        rsv.results.brief_result(metric, status, details, stderr)
    else:
        rsv.log("ERROR", "Data returned from job not in 'brief' format.")

        # We want to display the trimmed output, unless we're in full verbose mode
        if not rsv.quiet and OPTIONS.verbose < 3:
            trim_length = rsv.config.get("rsv", "details-data-trim-length")
            rsv.log("Displaying first %s bytes of output (use -v3 for full output)" %
                    trim_length, 1)
            stdout = stdout[:trim_length]
        else:
            rsv.log("DEBUG", "Displaying full output received from command:")
            
        rsv.echo(stdout)
        sys.exit(1)


def execute_job(rsv, metric):
    """ Execute the job """

    jobmanager  = metric.config_get("jobmanager")
    job_timeout = rsv.config.getint("rsv", "job-timeout")

    if not jobmanager or not job_timeout:
        rsv.log("CRITICAL", "ej1: jobmanager or job-timeout not defined in config")
        sys.exit(1)

    #
    # Build the custom parameters to the script
    #
    args = metric.get_args_string()

    #
    # Set the environment for the job
    #
    rsv.log("INFO", "Setting up job environment:")
    original_environment = os.environ.copy()

    env = metric.get_environment()
    for var in env.keys():
        (action, value) = env[var]
        action = action.upper()
        rsv.log("INFO", "Var: '%s' Action: '%s' Value: '%s'" % (var, action, value), 4)
        if action == "APPEND":
            if var in os.environ:
                os.environ[var] = os.environ[var] + ":" + value
            else:
                os.environ[var] = value
            rsv.log("DEBUG", "New value of %s:\n%s" % (var, os.environ[var]), 8)
        elif action == "PREPEND":
            if var in os.environ:
                os.environ[var] = value + ":" + os.environ[var]
            else:
                os.environ[var] = value
            rsv.log("DEBUG", "New value of %s:\n%s" % (var, os.environ[var]), 8)
        elif action == "SET":
            os.environ[var] = value
        elif action == "UNSET":
            if var in os.environ:
                del os.environ[var]


    #
    # Build the command line for the job
    #
    if metric.config_val("execute", "local"):
        job = "%s -m %s -u %s %s" % (metric.executable,
                                     metric.name,
                                     metric.host,
                                     args)

    elif metric.config_val("execute", "remote-globus"):
        globus_job_run_exe = os.path.join(rsv.vdt_location, "globus", "bin", "globus-job-run")
        job = "%s %s/jobmanager-%s -s %s -- -m %s -u %s %s" % (globus_job_run_exe,
                                                               metric.host,
                                                               jobmanager,
                                                               metric.executable,
                                                               metric.name,
                                                               metric.host,
                                                               args)


    rsv.log("INFO", "Running command '%s'" % job)

    try:
        (ret, out, err) = rsv.run_command(job)
    except Sysutils.TimeoutError, err:
        rsv.results.job_timed_out(metric, job, err)


    #
    # Restore the environment
    # 
    os.environ = original_environment


    #
    # Handle the output
    #
    if ret:
        if metric.config_val("execute", "local"):
            rsv.results.local_job_failed(metric, job, out, err)
        elif metric.config_val("execute", "remote-globus"):
            rsv.results.remote_globus_job_failed(metric, job, out, err)
        
    parse_job_output(rsv, metric, out, err)

    return



def clean_up(exit_code=0):
    """ Clean up any temporary files before exiting.  Currently there are none. """
    sys.exit(exit_code)



def main(rsv, options, metrics):
    """ Main subroutine: directs program flow """

    # Validate the host, and if necessary, split off the port
    if options.uri.find(":") == -1:
        options.host = options.uri
    else:
        (options.host, options.port) = re.split(":", options.uri, 1)

    # Process the command line and initialize
    for metric_name in metrics:
        metric = Metric.Metric(metric_name, rsv, options.uri)
        validate_config(rsv, metric)

        # Check for some basic error conditions
        rsv.check_proxy(metric)
        ping_test(rsv, metric, options)
    
        # Run the job and parse the result
        execute_job(rsv, metric)

    return
