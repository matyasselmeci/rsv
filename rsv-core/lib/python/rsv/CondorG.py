#!/usr/bin/env python

import os
import pwd
import sys    # for sys.exit
import shutil
import tempfile

import Condor
import Sysutils

KEYWORDS = ["return value", "error", "abort", "Globus job submission failed", "Detected Down Globus Resource"]

class CondorG:
    """ Interface to submit Condor-G jobs """

    rsv = None
    log = None
    out = None
    err = None
    utils = None
    metric = None
    tempdir = None
    cleanup = True
    cluster_id = None

    def __init__(self, rsv, cleanup=True):
        """ Constructor """
        self.rsv = rsv
        self.cleanup = cleanup
        self.utils = Sysutils.Sysutils(rsv)

    def __del__(self):
        """ Destructor - do filesystem cleanup """
        if self.cleanup:
            if os.path.exists(self.tempdir):
                try:
                    shutil.rmtree(self.tempdir)
                except OSError, err:
                    self.rsv.log("WARNING", "Could not remove Condor-G temporary directory '%s'.  Error %s" % (self.tempdir, err))


    def submit(self, metric, attrs=None, timeout=None):
        """ Form a grid submit file and submit the job to Condor """

        self.metric = metric

        # Make a temporary directory to store submit file, input, output, and log
        parent_dir = os.path.join("/", "var", "tmp", "rsv")
        if not os.path.exists(parent_dir):
            # /var/tmp/rsv can be periodically deleted by system cleanup utilities so we sometimes
            # have to re-create it
            os.mkdir(parent_dir, 0755)
            (uid, gid) = pwd.getpwnam('rsv')[2:4]
            os.chown(parent_dir, uid, gid)
        self.tempdir = tempfile.mkdtemp(prefix="condor_g-", dir=parent_dir)
        self.rsv.log("INFO", "Condor-G working directory: %s" % self.tempdir)
        
        self.log = os.path.join(self.tempdir, "%s.log" % metric.name)
        self.out = os.path.join(self.tempdir, "%s.out" % metric.name)
        self.err = os.path.join(self.tempdir, "%s.err" % metric.name)

        #
        # Build the submit file
        #
        submit_file = "Universe = grid\n"
        if metric.config_get("condor-ce") or metric.ce_type == 'htcondor':
            self.rsv.log("INFO", "Submitting to HTCondor-CE gatekeeper")
            collector_host = metric.config_get("condor-ce-collector")
            if not collector_host:
                collector_host = "%s:9619" % metric.host
            schedd_name = metric.config_get("condor-ce-schedd")
            if not schedd_name:
                schedd_name = metric.host
            submit_file += "grid_resource = condor %s %s\n\n" % (schedd_name, collector_host)
            submit_file += "remote_universe = local\n"
            if 'X509_USER_PROXY' in os.environ:
                submit_file += "x509userproxy = %s\n" % os.environ['X509_USER_PROXY']
        else:
            self.rsv.log("INFO", "Submitting to GRAM gatekeeper")
            jobmanager = metric.config_get("jobmanager")
            if not jobmanager:
                self.rsv.log("CRITICAL", "CondorG->submit: jobmanager not defined in config")
                # TODO - this should not exit because it causes 'rsv-control --run --all-enabled' to end
                sys.exit(1)
            submit_file += "grid_resource = gt2 %s/jobmanager-%s\n\n" % (metric.host, jobmanager)

        submit_file += "Executable = %s\n" % metric.executable

        args = "-m %s -u %s %s" % (metric.name, metric.host, metric.get_args_string())
        submit_file += "Arguments  = %s\n" % args

        # Add in custom attributes
        if attrs:
            for key in attrs.keys():
                submit_file += "%s = %s\n" % (key, attrs[key])

        transfer_files = metric.get_transfer_files()
        if transfer_files:
            submit_file += "transfer_input_files = %s\n" % ", ".join(transfer_files)
            
        submit_file += "Log = %s\n" % self.log
        submit_file += "Output = %s\n" % self.out
        submit_file += "Error = %s\n\n" % self.err
        submit_file += "Notification = never\n"
        submit_file += "WhenToTransferOutput = ON_EXIT_OR_EVICT\n\n"
        submit_file += "Queue\n"

        condor = Condor.Condor(self.rsv)
        self.cluster_id = condor.submit_job(submit_file, metric.name, dir=self.tempdir, remove=0)

        if not self.cluster_id:
            return False

        self.rsv.log("DEBUG", "Condor-G submission job ID - %s" % self.cluster_id)
        return True
        

    def wait(self):
        """ Wait for the job to complete """
        
        # Monitor the job's log and watch for it to finish
        job_timeout = self.metric.get_timeout() or self.rsv.config.get("rsv", "job-timeout")

        try:
            (keyword, log_contents) = self.utils.watch_log(self.log, KEYWORDS, job_timeout)
        except Sysutils.TimeoutError, err:
            self.remove()
            return 5

        if keyword == "return value":
            return 0
        elif keyword == "abort":
            return 1
        elif keyword == "error":
            return 2
        elif keyword == "Globus job submission failed":
            self.remove()
            return 3
        elif keyword == "Detected Down Globus Resource":
            self.remove()
            return 4

        # We should not reach here, but just in case
        return False
        

    def remove(self):
        """ Remove the job from the Condor queue """

        if self.cluster_id:
            constraint = "ClusterId==%s" % self.cluster_id
            condor = Condor.Condor(self.rsv)
            if not condor.stop_jobs(constraint):
                self.rsv.log("WARNING", "Could not stop Condor-G jobs.  Constraint: %s" % constraint)
                return False

        return True


    def get_stdout(self):
        """ Return the STDOUT of the job """
        return self.utils.slurp(self.out)

    def get_stderr(self):
        """ Return the STDERR of the job """
        return self.utils.slurp(self.err)

    def get_log_contents(self):
        """ Return the log contents of the job """
        return self.utils.slurp(self.log)
