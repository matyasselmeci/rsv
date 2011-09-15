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
import Condor
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

    execute_type = metric.config_get("execute").lower()
    if execute_type == "local":
        rsv.log("INFO", "Executing job locally")
        execute_local_job(rsv, metric)
    elif execute_type == "grid":
        if rsv.use_condor_g():
            rsv.log("INFO", "Executing job remotely using Condor-G")
            execute_condor_g_job(rsv, metric)
        else:
            rsv.log("INFO", "Executing job remotely using globus-job-run")
            execute_grid_job(rsv, metric)
    else:
        rsv.log("ERROR", "The execute type of the probe is unknown: '%s'" % execute_type)
        sys.exit(1)

    return


def execute_local_job(rsv, metric):
    """ Execute the old-style probes, or any probe that should run locally, e.g. srm probes """

    # Build the custom parameters to the script
    args = metric.get_args_string()

    # Anthony Tiradani uses extra RSL to get his jobs to run with priority at Fermi
    # This is done for old style metrics by passing --extra-globus-rsl.
    if metric.config_val("probe-spec", "v3") and rsv.get_extra_globus_rsl():
        args += " --extra-globus-rsl %s" % rsv.get_extra_globus_rsl()

    job = "%s -m %s -u %s %s" % (metric.executable,
                                 metric.name,
                                 metric.host,
                                 args)

    # A metric can define a custom timeout, otherwise we'll default to the RSV global
    # settings for this value.  The custom timeout was added because the pigeon probe
    # can take a long time to run (many times longer than the average metric)
    job_timeout = metric.get_timeout()

    original_environment = copy.copy(os.environ)
    setup_job_environment(rsv, metric)

    try:
        (ret, out, err) = rsv.run_command(job, job_timeout)
    except Sysutils.TimeoutError, err:
        os.environ = original_environment
        rsv.results.job_timed_out(metric, job, err)
        return

    os.environ = original_environment

    if ret:
        rsv.results.local_job_failed(metric, job, out, err)
        return

    parse_job_output(rsv, metric, out, err)
    return


def execute_grid_job(rsv, metric):
    """ Execute a job using globus-job-run.  This is an old method and we will likely
    replace all uses of this with Condor-G in the future. """

    # Build the custom parameters to the script
    args = metric.get_args_string()

    jobmanager = metric.config_get("jobmanager")

    if not jobmanager:
        rsv.log("CRITICAL", "ej1: jobmanager not defined in config")
        sys.exit(1)

    # Anthony Tiradani uses extra RSL to get his jobs to run with priority at Fermi
    # This is done by passing -x to globus-job-run
    extra_globus_rsl = ""
    if rsv.get_extra_globus_rsl():
        extra_globus_rsl = "-x %s" % rsv.get_extra_globus_rsl()

    job = "globus-job-run %s/jobmanager-%s %s -s %s -- -m %s -u %s %s" % (metric.host,
                                                                          jobmanager,
                                                                          extra_globus_rsl,
                                                                          metric.executable,
                                                                          metric.name,
                                                                          metric.host,
                                                                          args)

    # A metric can define a custom timeout, otherwise we'll default to the RSV global
    # settings for this value.  The custom timeout was added because the pigeon probe
    # can take a long time to run (many times longer than the average metric)
    job_timeout = metric.get_timeout()

    original_environment = copy.copy(os.environ)
    setup_job_environment(rsv, metric)

    try:
        (ret, out, err) = rsv.run_command(job, job_timeout)
    except Sysutils.TimeoutError, err:
        os.environ = original_environment
        rsv.results.job_timed_out(metric, job, err)
        return

    os.environ = original_environment

    if ret:
        rsv.results.grid_job_failed(metric, job, out, err)

    parse_job_output(rsv, metric, out, err)
    return


def execute_condor_g_job(rsv, metric):
    """ Execute a remote job via Condor-G.  This is the preferred format so that we
    can support both Globus and CREAM """

    original_environment = copy.copy(os.environ)
    setup_job_environment(rsv, metric)

    # Submit the job
    condor = Condor.Condor(rsv)

    attrs = {}
    if rsv.get_extra_globus_rsl():
        attrs["globus_rsl"] = rsv.get_extra_globus_rsl()

    (log_file, out_file, err_file) = condor.condor_g_submit(metric, attrs)

    os.environ = original_environment

    if not log_file:
        rsv.results.condor_g_submission_failed(metric)
        return

    # Monitor the job's log and watch for it to finish
    keywords = ["return value", "error", "abort", "Globus job submission failed", "Detected Down Globus Resource"]
    job_timeout = metric.get_timeout() or rsv.config.get("rsv", "job-timeout")
    utils = Sysutils.Sysutils(rsv)

    try:
        keyword = utils.watch_log(log_file, keywords, job_timeout)
    except Sysutils.TimeoutError, err:
        rsv.results.job_timed_out(metric, "condor-g submission", err)
        return            

    # Read the out and err from the files
    out = utils.slurp(out_file)
    err = utils.slurp(err_file)

    ret = None
    if keyword == "return value":
        ret = 0
    elif keyword == "abort":
        rsv.results.condor_grid_job_aborted(metric, out, err)
    elif keyword == "error":
        rsv.results.condor_grid_job_failed(metric, out, err)
    elif keyword == "Globus job submission failed":
        rsv.results.condor_g_submission_authentication_failure(metric)
    elif keyword == "Detected Down Globus Resource":
        rsv.results.condor_g_remote_gatekeeper_down(metric)

    parse_job_output(rsv, metric, out, err)
    return


def setup_job_environment(rsv, metric):
    """ Set the appropriate environment values that a metric expects """

    rsv.log("INFO", "Setting up job environment:")

    env = metric.get_environment()

    if not env:
        rsv.log("INFO", "No environment setup declared", 4)
        return
    
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
