#!/usr/bin/env python

# Standard libraries
import re
import os
import sys
import copy
import shutil
import tempfile
import ConfigParser
from optparse import OptionParser

# RSV libraries
import RSV
import Metric
import CondorG
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
        cmd = ["/bin/ping", "-W", "3", "-c", "1", host]
        (ret, out, err) = rsv.run_command(cmd)
    except Sysutils.TimeoutError, err:
        rsv.results.ping_timeout(metric, " ".join(cmd), err)
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
        trim_length = rsv.config.get("rsv", "details-data-trim-length")
        if not rsv.quiet:
            rsv.echo("Displaying first %s bytes of output" % trim_length, 1)
            stdout = stdout[:trim_length]
        else:
            rsv.log("DEBUG", "Displaying full output received from command:")

        rsv.echo(stdout)

        rsv.echo("STDERR from metric:")
        rsv.echo(stderr[:trim_length])

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

    job = [metric.executable, "-m", metric.name, "-u", metric.host, args]

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
        rsv.results.job_timed_out(metric, " ".join(job), err)
        return

    os.environ = original_environment

    if ret:
        rsv.results.local_job_failed(metric, " ".join(job), out, err)
        return

    parse_job_output(rsv, metric, out, err)
    return


def execute_grid_job(rsv, metric):
    """ Execute a job using globus-job-run.  This is an old method and we use Condor-G
    by default now, but some people might want to use globus-job-run instead. """

    # Build the custom parameters to the script
    args = metric.get_args_string()

    jobmanager = metric.config_get("jobmanager")

    if not jobmanager:
        rsv.log("CRITICAL", "ej1: jobmanager not defined in config")
        sys.exit(1)

    # If the probe depends on any modules we need to prepare a SHAR file to send
    # because globus-job-run can only send one file (it can't send supporting libraries)
    (shar_dir, shar_file) = prepare_shar_file(rsv, metric)
    if not shar_dir:
        return

    job = ["globus-job-run", "%s/jobmanager-%s" % (metric.host, jobmanager),
           "-s", shar_file, "--", "-m", metric.name, "-u", metric.host, args]

    # Anthony Tiradani uses extra RSL to get his jobs to run with priority at Fermi
    # This is done by passing -x to globus-job-run
    if rsv.get_extra_globus_rsl():
        job.insert(2, "-x")
        job.insert(3, rsv.get_extra_globus_rsl())

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
        shutil.rmtree(shar_dir)
        rsv.results.job_timed_out(metric, " ".join(job), err)
        return

    os.environ = original_environment
    shutil.rmtree(shar_dir)

    if ret:
        rsv.results.grid_job_failed(metric, " ".join(job), out, err)

    parse_job_output(rsv, metric, out, err)
    return


def prepare_shar_file(rsv, metric):
    """ Create a shar file wrapped in a perl script to be used with globus-job-run.

    globus-job-run can only send one file, so we will wrap up all the files into a
    sh archive.  But after unshar'ing we need to execute one of the files so we will
    use a perl script to do the extraction followed by executing the necessary script """

    # Check for shar
    utils = Sysutils.Sysutils(rsv)
    path = utils.which("shar")
    if not path:
        rsv.results.shar_not_installed(metric)
        return (None, None)

    # Make a temporary path to create the shar file
    parent_dir = os.path.join("/", "var", "tmp", "rsv")
    tempdir = tempfile.mkdtemp(prefix="shar-", dir=parent_dir)
    shar_file = os.path.join(tempdir, "shar.pl")

    # Make a perl header for the shar file
    f = open(shar_file, 'w')
    f.write("""#!/usr/bin/env perl

use strict;
use warnings;
use File::Temp;

if(system("which uudecode >/dev/null 2>&1") != 0) {
    print "RSV BRIEF RESULTS:\n";
    print "UNKNOWN\n";
    print "Cannot extract the shar file on remote system because uudecode is missing.\n";
    print "To solve this, install uudecode (provided by the sharutils RPM) on the remote system you are monitoring.\n";
    exit 0;    
}

my $temp_dir = mkdtemp("rsv-shar-XXXXXXXX");
chdir($temp_dir);
my $out_file = "shar.sh";

my $shar = join "", <DATA>;
open(OUT, '>', $out_file) or die("cannot write to $out_file: $!");
print OUT $shar;
close(OUT);

my $ret = system("/bin/sh shar.sh >shar.out 2>&1");
if($ret != 0) {
    print "RSV BRIEF RESULTS:\n";
    print "UNKNOWN\n";
    print "Failed to extract shar file.\n";
    system("cat shar.out");
}
else {
    system("./%s @ARGV");
    chdir("..");
    system("rm -fr $temp_dir");
}

__DATA__""" % metric.name)
    f.close()

    # Create the shar file
    transfer_files = metric.get_transfer_files()
    cmd = ["shar", "-f", metric.executable, transfer_files]
    (ret, out, err) = rsv.run_command(cmd)
    if ret != 0:
        rsv.results.shar_creation_failed(metric, out, err)
        return (None, None)

    f = open(shar_file, 'a')
    f.write(out)
    f.close()

    return (tempdir, shar_file)
    

def execute_condor_g_job(rsv, metric):
    """ Execute a remote job via Condor-G.  This is the preferred format so that we
    can support both Globus and CREAM """

    # Submit the job
    condorg = CondorG.CondorG(rsv)

    attrs = {}
    if rsv.get_extra_globus_rsl():
        attrs["globus_rsl"] = rsv.get_extra_globus_rsl()

    original_environment = copy.copy(os.environ)
    setup_job_environment(rsv, metric)

    ret = condorg.submit(metric, attrs)

    os.environ = original_environment

    if not ret:
        rsv.results.condor_g_globus_submission_failed(metric)
        return

    ret = condorg.wait()

    if ret == 0:
        parse_job_output(rsv, metric, condorg.get_stdout(), condorg.get_stderr())
    elif ret == 1:
        rsv.results.condor_grid_job_aborted(metric, condorg.get_log_contents())
    elif ret == 2:
        rsv.results.condor_grid_job_failed(metric, condorg.get_stdout(), condorg.get_stderr(), condorg.get_log_contents())
    elif ret == 3:
        rsv.results.condor_g_globus_submission_failed(metric, condorg.get_log_contents())
    elif ret == 4:
        rsv.results.condor_g_remote_gatekeeper_down(metric, condorg.get_log_contents())
    elif ret == 5:
        rsv.results.job_timed_out(metric, "condor-g submission", "", info=condorg.get_log_contents())

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
            elif metric.config_get('no-ping') and metric.config_get('no-ping').lower() == 'true':
                rsv.log("INFO", "Skipping ping check because metric config contains no-ping=True")
            else:
                ping_test(rsv, metric)

            # Run the job and parse the result
            if total > 1:
                rsv.echo("\nRunning metric %s (%s of %s)\n" % (metric.name, count, total))
            else:
                rsv.echo("\nRunning metric %s:\n" % metric.name)
            execute_job(rsv, metric)

    return True
