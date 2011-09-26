#!/usr/bin/env python

import os
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
    metric = None
    tempdir = None
    cleanup = True
    cluster_id = None

    def __init__(self, rsv, cleanup=True):
        """ Constructor """
        self.rsv = rsv
        self.cleanup = cleanup

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
        self.tempdir = tempfile.mkdtemp(prefix="condor_g-", dir=parent_dir)
        self.rsv.log("INFO", "Condor-G working directory: %s" % self.tempdir)
        
        self.log = os.path.join(self.tempdir, "%s.log" % metric.name)
        self.out = os.path.join(self.tempdir, "%s.out" % metric.name)
        self.err = os.path.join(self.tempdir, "%s.err" % metric.name)

        # This is Globus specific.  When we support CREAM we need to modify this section
        jobmanager = metric.config_get("jobmanager")
        if not jobmanager:
            self.rsv.log("CRITICAL", "CondorG->submit: jobmanager not defined in config")
            # TODO - this should not exit
            sys.exit(1)

        #
        # Build the submit file
        #
        submit_file = "Universe = grid\n"
        submit_file += "grid_resource = gt2 %s/jobmanager-%s\n\n" % (metric.host, jobmanager)

        metric_path = os.path.join("/", "usr", "libexec", "rsv", "metrics", metric.name)
        submit_file += "Executable = %s\n" % metric_path

        args = "-m %s -u %s %s" % (metric.name, metric.host, metric.get_args_string())
        submit_file += "Arguments  = %s\n" % args

        # Add in custom attributes
        if attrs:
            for key in attrs.keys():
                submit_file += "%s = %s\n" % (key, attrs[key])

        transfer_files = metric.get_transfer_files()
        if transfer_files:
            submit_file += "transfer_input_files = %s\n" % transfer_files
            
        submit_file += "Log = %s\n" % self.log
        submit_file += "Output = %s\n" % self.out
        submit_file += "Error = %s\n\n" % self.err
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
        utils = Sysutils.Sysutils(self.rsv)

        try:
            (keyword, log_contents) = utils.watch_log(self.log, KEYWORDS, job_timeout)
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
        return utils.slurp(self.out)

    def get_stderr(self):
        """ Return the STDERR of the job """
        return utils.slurp(self.err)

    def get_log_contents(self):
        """ Return the log contents of the job """
        return utils.slurp(self.log)
