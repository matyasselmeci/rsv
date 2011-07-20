#!/usr/bin/env python

# Standard libraries
import re
import os
import sys
import copy
import ConfigParser
from optparse import OptionParser

# RSV libraries
import RSV
import Metric
import Results
import Sysutils



def ping_test(rsv, metric):
    """ Ping the remote host to make sure it's alive before we attempt
    to run jobs """

    uri = metric.host
    if uri.find(":") > 0:
        (host, port) = re.split(":", uri, 1)
    else:
        host = uri

    rsv.log("INFO", "Pinging host %s:" % host)

    # Send a single ping, with a timeout.  We just want to know if we can reach
    # the remote host, we don't care about the latency unless it exceeds the timeout
    try:
        cmd = "/bin/ping -W 3 -c 1 %s" % host
        (ret, out, err) = rsv.run_command(cmd)
    except Sysutils.TimeoutError, err:
        rsv.results.ping_timeout(metric, cmd, err)
        sys.exit(1)

    # If we can't ping the host, don't bother doing anything else
    if ret:
        rsv.results.ping_failure(metric, out, err)
        sys.exit(1)
        
    rsv.log("INFO", "Ping successful", 4)
    return



def parse_job_output(rsv, metric, stdout, stderr):
    """ Parse the job output from the worker script """

    if(metric.config_val("output-format", "wlcg")):
        parse_job_output_wlcg(rsv, metric, stdout, stderr)
    elif(metric.config_val("output-format", "wlcg-multiple")):
        parse_job_output_multiple_wlcg(rsv, metric, stdout, stderr)
    elif(metric.config_val("output-format", "brief")):
        parse_job_output_brief(rsv, metric, stdout, stderr)
    else:
        rsv.log("ERROR", "output format unknown")

        

def parse_job_output_wlcg(rsv, metric, stdout, stderr):
    """ Parse WLCG formatted output. """
    rsv.results.wlcg_result(metric, stdout, stderr)


def parse_job_output_multiple_wlcg(rsv, metric, stdout, stderr):
    """ Parse multiple WLCG formatted records separated by EOT. """

    rsv.log("CRITICAL", "wlcg-multiple implementation may not be fully functional")

    records = stdout.split("\nEOT\n")
    rsv.echo("Parsing wlcg-multiple style record.  Found %s records" % len(records))
    num = 1
    for record in records:
        if not re.search("\S", record):
            continue
        record = record + "\nEOT\n"
        rsv.echo("Record %s of %s:" % (num, len(records)))
        rsv.results.wlcg_result(metric, record, stderr)
        rsv.echo("\n")
        num += 1


def parse_job_output_brief(rsv, metric, stdout, stderr):
    """ Parse the "brief" job output.  This format consists of just a keyword, status
    and details.  Here is an example:
    RSV BRIEF RESULTS:
    OK
    More information, which can
    be on multiple lines.
    """

    status = None
    details = None

    lines = stdout.split("\n")

    if lines[0] == "RSV BRIEF RESULTS:":
        status = lines[1].strip()
        details = "\n".join(lines[2:])

    if status and details:
        rsv.results.brief_result(metric, status, details, stderr)
    else:
        rsv.log("ERROR", "Data returned from job not in 'brief' format.")

        # We want to display the trimmed output
        # TODO - display non-trimmed output if we are in -v3 mode?
        if not rsv.quiet:
            trim_length = rsv.config.get("rsv", "details-data-trim-length")
            rsv.echo("Displaying first %s bytes of output (use -v3 for full output)" %
                    trim_length, 1)
            stdout = stdout[:trim_length]
        else:
            rsv.log("DEBUG", "Displaying full output received from command:")
            
        rsv.echo(stdout)
        sys.exit(1)


def execute_job(rsv, metric):
    """ Execute the job """

    jobmanager = metric.config_get("jobmanager")

    if not jobmanager:
        rsv.log("CRITICAL", "ej1: jobmanager not defined in config")
        sys.exit(1)

    #
    # Build the custom parameters to the script
    #
    args = metric.get_args_string()

    #
    # Set the environment for the job
    #
    rsv.log("INFO", "Setting up job environment:")
    original_environment = copy.copy(os.environ)

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

    prefix = ""
    if rsv.get_source_setup_sh():
        prefix = ". %s; " % os.path.join(rsv.vdt_location, "setup.sh")

    execute_type = metric.config_get("execute").lower()
    if execute_type == "local":
        # Anthony Tiradani uses extra RSL to get his jobs to run with priority at Fermi
        # This is done for old style metrics by passing --extra-globus-rsl.  For direct
        # globus-job-run calls we need to add the -x flag (see below in the 'grid' section)
        if metric.config_val("probe-spec", "v3") and rsv.get_extra_globus_rsl():
            args += " --extra-globus-rsl %s" % rsv.get_extra_globus_rsl()
            
        job = "%s%s -m %s -u %s %s" % (prefix,
                                       metric.executable,
                                       metric.name,
                                       metric.host,
                                       args)

    elif execute_type == "grid":
        globus_job_run_exe = os.path.join(rsv.vdt_location, "globus", "bin", "globus-job-run")

        # Anthony Tiradani uses extra RSL to get his jobs to run with priority at Fermi
        # This is done by passing -x to globus-job-run
        extra_globus_rsl = ""
        if rsv.get_extra_globus_rsl():
            extra_globus_rsl = "-x %s" % rsv.get_extra_globus_rsl()
            
        job = "%s%s %s/jobmanager-%s %s -s %s -- -m %s -u %s %s" % (prefix,
                                                                    globus_job_run_exe,
                                                                    metric.host,
                                                                    jobmanager,
                                                                    extra_globus_rsl,
                                                                    metric.executable,
                                                                    metric.name,
                                                                    metric.host,
                                                                    args)

    elif execute_type == "condor-grid":
        rsv.log("ERROR", "The condor-grid execute type is not yet implemented")
        sys.exit(1)

    else:
        rsv.log("ERROR", "The execute type of the probe is unknown: '%s'" % execute_type)
        sys.exit(1)

    # A metric can define a custom timeout, otherwise we'll default to the RSV global
    # settings for this value.  The custom timeout was added because the pigeon probe
    # can take a long time to run (many times longer than the average metric)
    job_timeout = metric.get_timeout()

    try:
        (ret, out, err) = rsv.run_command(job, job_timeout)
    except Sysutils.TimeoutError, err:
        os.environ = original_environment
        rsv.results.job_timed_out(metric, job, err)
        return

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
        elif metric.config_val("execute", "grid"):
            rsv.results.grid_job_failed(metric, job, out, err)
        elif metric.config_val("execute", "condor-grid"):
            rsv.results.condor_grid_job_failed(metric, job, out, err)
        return

    parse_job_output(rsv, metric, out, err)

    return



def main(rsv, options, metrics):
    """ Main subroutine: directs program flow """

    hosts = {}
    total = 0

    if options.all_enabled:
        for host in rsv.get_host_info():
            hosts[host.host] = host.get_enabled_metrics()
            total += len(hosts[host.host])
    else:
        hosts[options.uri] = metrics
        total = len(metrics)

    RSV.validate_config(rsv)

    # Process the command line and initialize
    count = 0
    for host in hosts:
        for metric_name in hosts[host]:
            count += 1
            metric = Metric.Metric(metric_name, rsv, host, options)

            # Check for some basic error conditions
            rsv.check_proxy(metric)

            if options.no_ping:
                rsv.log("INFO", "Skipping ping check because --no-ping was supplied")
            else:
                ping_test(rsv, metric)

            # Run the job and parse the result
            if total > 1:
                rsv.echo("\nRunning metric %s (%s of %s)\n" % (metric.name, count, total))
            else:
                rsv.echo("\nRunning metric %s:\n" % metric.name)
            execute_job(rsv, metric)

    return True
