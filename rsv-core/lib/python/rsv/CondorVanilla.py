#!/usr/bin/env python

""" This class is basically the same as CondorG but to submit Vanilla jobs """
import os
import tempfile
import Condor
from CondorG import CondorG
import CondorG as libCondorG


class CondorVanilla(CondorG):


      def submit(self, metric, attrs=None, timeout=None):
        """ Form a grid submit file and submit the job to Condor """
        assert not metric.dead, "Attempt to submit dead metric"

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
        submit_file = "Universe = Vanilla\n"
        # The user proxy should be in the submit file regardless of the CE type
        if 'X509_USER_PROXY' in os.environ:
                submit_file += "x509userproxy = %s\n" % os.environ['X509_USER_PROXY']
        submit_file += "Executable = %s\n" % metric.executable
        args = ['-m', metric.name, '-u', metric.host] + metric.get_args_list()
        submit_file += "Arguments  = %s\n" % libCondorG.quote_arguments(args)

        # Add in custom attributes
        if attrs:
            for key in attrs.keys():
                submit_file += "%s = %s\n" % (key, attrs[key])

        # Add in custom classAds
        classAds = metric.get_classAds()
        self.rsv.log("INFO", "Submitting with following special classAds")
        for ad in classAds:
                submit_file += "+%s = %s\n" % (ad, classAds[ad])
                self.rsv.log("INFO", "+%s = %s\n" % (ad, classAds[ad]))

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

        self.rsv.log("DEBUG", "Vanilla Condor submission job ID - %s" % self.cluster_id)
        return True
