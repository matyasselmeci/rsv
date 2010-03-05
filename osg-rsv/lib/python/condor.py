#!/usr/bin/env python

import os
import commands

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.condor")

class Condor:
    """
    Defines a system able to submit RSV probes
    """

    def __init__(self, rsv=None, user=None):
        self.rsv = rsv
        self.user = user


    def is_metric_running(self, id):
        """
        Return true if a metric is running in Condor-Cron
        Return false if it is not
        """
        classads = self.get_classads(constraint = "OsgRsvUniqueName=='%s'" % id)
        if classads == None:
            log.error("Could not determine if job is running")

        for classad in classads:
            if classad[OsgRsvUniqueName] == id:
                return True

        return False

    def get_classads(self, constraint=None):
        """
        Run a condor_cron_q command and return a hash of the classad.
        If there is an error, return None
        """
        log.debug("Getting Condor classads with constraint '%s'" % (constraint or ""))

        if not self.is_condor_running():
            log.error("Cannot fetch classads because Condor-Cron is not running")
            return None

        # Build the command
        cmd = "condor_cron_q -l"
        if constraint != None:
            cmd += " -constraint \'%s\'" % constraint

        (ret, out) = commands_getstatusoutput(cmd);

        # Run the command and parse the classad
        if ret != 0:
            log.error("Command returned error code '%i': '%s'" % (ret, cmd))
            return None
        else:
            return self.parse_classads(out)


    def parse_classads(self, output):
        """
        Parse a set of condor classads in "attribute = value" format
        A blank line will be between each classad
        Return an array of hashes
        """
        classads = []
        tmp = {}
        for line in output.split("\n"):
            # A blank line signifies that this classad is finished
            if line == "":
                if len(tmp) > 0:
                    classads.append(tmp)
                    tmp = {}

            pair = line.split(" = ", 2)
            if len(pair) == 2:
                tmp[pair[0]] = pair[1]

        return classads


    def start_condor_job(self, metric, uri):
        """
        Take a metric/uri pair as a parameter and start the job
        """
        log.info("Submitting job to condor: metric '%s' - host '%s'" % (metric.metricName, uri))

        # TODO: Make sure that the metric is enabled

        # Check if the metric is already running in condor_cron
        condor_id = metric.get_unique_name(uri)
        if self.is_metric_running(condor_id):
            print "Metric '%s' is already running against host '%s'" % (metric.metricName, uri)
            return True

        # Generate a submission file
        submit_file_contents = self.build_submit_file(metric, uri)
        sub_file_name = os.path.join(self.rsv.location, "submissions", condor_id + ".sub")

        try:
            fh = open(sub_file_name, 'w')
            fh.write(submit_file_contents)
            fh.close()
        except IOError:
            log.error("Cannot write temporary submission file %s.  Check permissions" % sub_file_name)
            return False

        # Submit the job and remove the file
        cmd = "condor_cron_submit %s" % (sub_file_name)
        raw_ec, out = commands_getstatusoutput(cmd, self.user)
        exit_code = os.WEXITSTATUS(raw_ec)
        log.info("Condor submission: %s" % out)
        log.debug("Condor submission completed: %s (%s)" % (exit_code, raw_ec))
        os.remove(sub_file_name)

        if exit_code != 0:
            log.error("Problem submitting job to condor-cron.  Command output follows:")
            log.error(out)
            return False

        return True


    def stop_condor_jobs(self, constraint):
        """
        Stop the probes with the supplied constraint
        return True if jobs are stopped successfully, False otherwise
        """
        log.info("Stopping all probes with constraint '%s'" % constraint)

        if not self.is_condor_running():
            log.error("Cannot stop jobs because Condor-Cron is not running")
            return False

        # Check if any jobs are running to be removed
        jobs = self.get_classads(constraint=constraint)
        if len(jobs) == 0:
            log.info("No jobs to be removed with constraint '%s'" % constraint)
            return True

        # Build the command
        cmd = "condor_cron_rm"
        if constraint != None:
            cmd += " -constraint \'%s\'" % constraint

        (ret, out) = commands_getstatusoutput(cmd);

        if ret != 0:
            log.error("Command returned error code '%i': '%s'" % (ret, cmd))
            return False

        return True


    def is_condor_running(self):
        """
        Determine if Condor-Cron is running.  Return True is so, false otherwise
        """
        (ret, out) = commands_getstatusoutput("condor_cron_q")

        if not ret and out.index("-- Submitter") != -1:
            log.debug("Condor-Cron is running")
            return True

        log.info("Condor-Cron does not seem to be running.  Output of condor_cron_q:\n%s" % out)

        return False


    def build_submit_file(self, metric, uri):
        """
        Create a submission file for a metric
        """
        log_dir = self.rsv.getLogDir()
        condor_id = metric.get_unique_name(uri)
        # TODO: Do I need to add the current PERL5LIB?  I think so, but how do I know it is valid?
        perl_lib_dirs = self.rsv.getPerlLibDir() + ":" + os.getenv("PERL5LIB", "")

        submit = ""
        submit += "######################################################################\n"
        submit += "# Submit file generated by rsv-control\n"
        submit += "######################################################################\n"
        submit += "Environment = PATH=/usr/bin:/bin;PERL5LIB=%s;VDT_LOCATION=%s\n" % (perl_lib_dirs, self.rsv.getVdtLocation())
        submit += "CronPrepTime = 180\n"
        submit += "CronWindow = 99999999\n"
        submit += "CronMonth = %s\n"      % metric.submit_params["CronMonth"]
        submit += "CronDayOfWeek = %s\n"  % metric.submit_params["CronDayOfWeek"]
        submit += "CronDayOfMonth = %s\n" % metric.submit_params["CronDayOfMonth"]
        submit += "CronHour = %s\n"       % metric.submit_params["CronHour"]
        submit += "CronMinute = %s\n"     % metric.submit_params["CronMinute"]
        submit += "Executable = %s\n"     % metric.getExecutable()
        submit += "Error = %s/%s.err\n"   % (log_dir, condor_id)
        submit += "Output = %s/%s.out\n"  % (log_dir, condor_id)
        submit += "Log = %s/%s.log\n"     % (log_dir, condor_id)
        submit += "Arguments = %s\n"      % metric.getCLParameters(uri=uri)
        submit += "Universe = local\n"
        submit += "Notification = never\n"
        submit += "OnExitRemove = false\n"
        submit += "PeriodicRelease = HoldReasonCode =!= 1\n"
        submit += "+OSGRSV = \"probes\"\n"
        submit += "+OsgRsvUniqueName = \"%s\"\n" % condor_id
        submit += "Queue\n"
        
        return submit


def commands_getstatusoutput(command, user=None):
    """Run a command in a subshell using commands module and setting up the environment"""
    log.debug("commands_getstatusoutput: command='%s' user='%s'" % (command, user))
    
    if user:
        command = 'su -c "%s" %s' % (command, user)
    ec, out = commands.getstatusoutput(command)
    return ec, out
