#!/usr/bin/env python

import os
import re
import time
import commands
from time import strftime

import pdb

import Host

class Condor:
    """ Define the interface to condor-cron """

    rsv = None
    condor_cron_bin_dir = None

    def __init__(self, rsv):
        self.rsv = rsv
        self.condor_cron_bin_dir = os.path.join(rsv.vdt_location, "condor-cron", "wrappers")


    def is_condor_running(self):
        """
        Determine if Condor-Cron is running.  Return True is so, false otherwise
        """

        condor_cron_q_exe = os.path.join(self.condor_cron_bin_dir, "condor_cron_q")
        (ret, out) = self.commands_getstatusoutput(condor_cron_q_exe)

        if not ret and out.index("-- Submitter") != -1:
            self.rsv.log("DEBUG", "Condor is running.  Output of condor_cron_q:\n%s" % out)
            return True

        self.rsv.log("INFO", "Condor-Cron does not seem to be running.  " +
                     "Output of condor_cron_q:\n%s" % out)

        return False


    def is_job_running(self, condor_id):
        """
        Return true if a metric is running in Condor-Cron
        Return false if it is not
        """

        classads = self.get_classads("OSGRSVUniqueName==\"%s\"" % condor_id)

        if classads == None:
            self.rsv.log("ERROR", "Could not determine if job is running")
            return False

        for classad in classads:
            # We put the attribute into the classad in quotes, so search for it accordingly
            if classad["OSGRSVUniqueName"] == '"' + condor_id + '"':
                return True

        return False


    def get_classads(self, constraint=None):
        """
        Run a condor_cron_q command and return a dict of the classad.
        If there is an error, return None
        """
        if constraint:
            self.rsv.log("DEBUG", "Getting Condor classads with constraint '%s'" % constraint)
        else:
            self.rsv.log("DEBUG", "Getting Condor classads with no constraint")

        if not self.is_condor_running():
            self.rsv.log("ERROR", "Cannot fetch classads because Condor-Cron is not running")
            return None

        # Build the command
        exe = os.path.join(self.condor_cron_bin_dir, "condor_cron_q")
        cmd = "%s -l" % exe
        if constraint != None:
            cmd += " -constraint '%s'" % constraint

        (ret, out) = self.commands_getstatusoutput(cmd)

        # Run the command and parse the classad
        if ret != 0:
            self.rsv.log("ERROR", "Command returned error code '%i': '%s'" % (ret, cmd))
            return None
        else:
            return parse_classads(out)


    def start_metric(self, metric, host):
        """
        Start a single metric condor-cron job.
        Takes a Metric and Host object as input.
        """
        
        self.rsv.log("INFO", "Submitting metric job to condor: metric '%s' - host '%s'" %
                     (metric.name, metric.host))

        condor_id = metric.get_unique_name()

        # Make sure that the metric is enabled
        if not host.metric_enabled(metric.name):
            self.rsv.log("ERROR", "The metric '%s' is not enabled on host '%s'." %
                         (metric.name, host.host))
            return False

        # Check if the metric is already running in condor_cron
        if self.is_job_running(condor_id):
            self.rsv.log("INFO", "Metric '%s' is already running against host '%s'" %
                         (metric.name, host.host))
            return True

        # Generate a submission file
        submit_file_contents = self.build_metric_submit_file(metric)

        return self.submit_job(submit_file_contents, condor_id)


    def start_consumer(self, consumer):
        """ Start a single consumer condor-cron job. """
        
        self.rsv.log("INFO", "Submitting consumer job to condor: consumer '%s'" % consumer)

        condor_id = consumer.get_unique_name()

        # Check if the metric is already running in condor_cron
        if self.is_job_running(condor_id):
            self.rsv.log("INFO", "Consumer '%s' is already running" % consumer.name)
            return True

        # Generate a submission file
        submit_file_contents = self.build_consumer_submit_file(consumer)
        self.rsv.log("DEBUG", "%s submit file:\n%s" % (consumer.name, submit_file_contents), 4)
        return self.submit_job(submit_file_contents, condor_id)


    def submit_job(self, submit_file_contents, condor_id):
        """
        Input: submit file contents and job identifier
        Create submission file, submits it to Condor and removes it
        """

        try:
            sub_file_name = os.path.join(self.rsv.rsv_location, "submissions", condor_id + ".sub")
            file_handle = open(sub_file_name, 'w')
            file_handle.write(submit_file_contents)
            file_handle.close()
        except IOError, err:
            self.rsv.log("ERROR", "Cannot write temporary submission file '%s'." % sub_file_name)
            self.rsv.log("ERROR", "Error message: %s" % err)
            return False

        # Submit the job and remove the file
        exe = os.path.join(self.condor_cron_bin_dir, "condor_cron_submit")
        cmd = "%s %s" % (exe, sub_file_name)
        raw_ec, out = self.commands_getstatusoutput(cmd, self.rsv.get_user())
        exit_code = os.WEXITSTATUS(raw_ec)
        self.rsv.log("INFO", "Condor submission: %s" % out)
        self.rsv.log("DEBUG", "Condor submission completed: %s (%s)" % (exit_code, raw_ec))
        os.remove(sub_file_name)

        if exit_code != 0:
            self.rsv.log("ERROR", "Problem submitting job to condor-cron.  Command output:\n%s" %
                         out)
            return False

        return True


    def stop_jobs(self, constraint):
        """
        Stop the jobs with the supplied constraint.
        Return True if jobs are stopped successfully, False otherwise
        """

        self.rsv.log("INFO", "Stopping all metrics with constraint '%s'" % constraint)

        if not self.is_condor_running():
            self.rsv.log("ERROR", "Cannot stop jobs because Condor-Cron is not running")
            return False

        # Check if any jobs are running to be removed
        jobs = self.get_classads(constraint)
        if len(jobs) == 0:
            self.rsv.log("INFO", "No jobs to be removed with constraint '%s'" % constraint)
            return True

        # Build the command
        cmd = os.path.join(self.condor_cron_bin_dir, "condor_cron_rm")
        if constraint != None:
            cmd += " -constraint '%s'" % constraint

        (ret, out) = self.commands_getstatusoutput(cmd)

        if ret != 0:
            self.rsv.log("ERROR", "Command returned error code '%i': '%s'.  Output:\n%s" %
                         (ret, cmd, out))
            return False

        return True



    def build_metric_submit_file(self, metric):
        """ Create a submission file for a metric """
        log_dir = self.rsv.get_metric_log_dir()

        # TODO: Do I need to add the current PERL5LIB?  I think so, but how do I know it is valid?

        # TODO - form environment using config definitions
        environment = ""
        environment += "PATH=/usr/bin:/bin;"
        #environment += "PERL5LIB=%s;" % perl_lib_dirs
        environment += "VDT_LOCATION=%s\n" % self.rsv.vdt_location

        cron = metric.get_cron_entry()

        condor_id = metric.get_unique_name()

        arguments = "-r -u %s %s" % (metric.host, metric.name)

        submit = ""
        submit += "######################################################################\n"
        submit += "# Temporary submit file generated by rsv-control\n"
        submit += "# Generated at %s " % "PUT TIME HERE"
        submit += "######################################################################\n"
        submit += "Environment = %s\n"    % environment
        submit += "CronPrepTime = 180\n"
        submit += "CronWindow = 99999999\n"
        submit += "CronMonth = %s\n"      % cron["Month"]
        submit += "CronDayOfWeek = %s\n"  % cron["DayOfWeek"]
        submit += "CronDayOfMonth = %s\n" % cron["DayOfMonth"]
        submit += "CronHour = %s\n"       % cron["Hour"]
        submit += "CronMinute = %s\n"     % cron["Minute"]
        submit += "Executable = %s\n"     % self.rsv.get_wrapper()
        submit += "Error = %s/%s.err\n"   % (log_dir, condor_id)
        submit += "Output = %s/%s.out\n"  % (log_dir, condor_id)
        submit += "Log = %s/%s.log\n"     % (log_dir, condor_id)
        submit += "Arguments = %s\n"      % arguments
        submit += "Universe = local\n"
        submit += "Notification = never\n"
        submit += "OnExitRemove = false\n"
        submit += "PeriodicRelease = HoldReasonCode =!= 1\n"
        submit += "+OSGRSV = \"metrics\"\n"
        submit += "+OSGRSVUniqueName = \"%s\"\n" % condor_id
        submit += "Queue\n"
        
        return submit


    def build_consumer_submit_file(self, consumer):
        """ Create a submission file for a consumer """
        log_dir = self.rsv.get_consumer_log_dir()

        environment = "PATH=/usr/bin:/bin;"
        environment += "VDT_LOCATION=%s;" % self.rsv.vdt_location
        environment += consumer.get_environment()

        condor_id = consumer.get_unique_name()

        submit = ""
        submit += "######################################################################\n"
        submit += "# Temporary submit file generated by rsv-control\n"
        submit += "# Generated at %s\n" % "PUT TIME HERE"
        submit += "######################################################################\n"
        submit += "Arguments = \n"
        submit += "DeferralPrepTime = 180\n"
        submit += "DeferralTime = (CurrentTime + 300 + random(30))\n"
        submit += "DeferralWindow = 99999999\n"
        submit += "Environment = %s\n"    % environment
        submit += "Executable = %s\n"     % consumer.executable
        submit += "Error = %s/%s.err\n"   % (log_dir, condor_id)
        submit += "Output = %s/%s.out\n"  % (log_dir, condor_id)
        submit += "Log = %s/%s.log\n"     % (log_dir, condor_id)
        submit += "Universe = local\n"
        submit += "Notification = never\n"
        submit += "OnExitRemove = false\n"
        submit += "PeriodicRelease = (HoldReasonCode =!= 1) " + \
                  "&& ((CurrentTime - EnteredCurrentStatus) > 60)\n"
        submit += "+OSGRSV = \"consumers\"\n"
        submit += "+OSGRSVUniqueName = \"%s\"\n" % condor_id
        submit += "Queue\n"

        return submit

    def commands_getstatusoutput(self, command, user=None):
        """Run a command in a subshell using commands module and setting up the environment"""
        self.rsv.log("DEBUG", "commands_getstatusoutput: command='%s' user='%s'" % (command, user))

        if user:
            command = 'su -c "%s" %s' % (command, user)

        ret, out = commands.getstatusoutput(command)
        return ret, out


    def display_jobs(self, hostname=None):
        """ Create a nicely formatted list of RSV jobs running in Condor-Cron """

        job_status = ["U", "I", "R", "X", "C", "H", "E"]

        def display_metric(classad):
            status = job_status[int(classad["JobStatus"])]

            next_run_time = "UNKNOWN"
            if "DeferralTime" in classad:
                next_run_time = strftime("%m-%d %H:%M", time.localtime(int(classad["DeferralTime"])))

            match = re.search("\s([\w.-]+)\s*\"", classad["Args"])
            metric = "UNKNOWN?"
            if match:
                metric = match.group(1)

            owner = classad["Owner"].replace('"', "")

            return (metric,
                    "%5s.%-1s %-10s %-2s %-15s %-44s\n" % (classad["ClusterId"], classad["ProcId"],
                                                           owner, status, next_run_time, metric))


        #
        # Build a table of jobs for each host
        #
        hosts = {}
        running_metrics = {}
        classads = self.get_classads("OSGRSV==\"metrics\"")

        if not classads:
            self.rsv.echo("No metrics are running")
        else:
            for classad in classads:
                match = re.search("-u ([\w.-]+)", classad["Args"])
                host = "UNKNOWN?"
                if match:
                    host = match.group(1)

                if hostname and hostname != host:
                    continue

                if host not in hosts:
                    running_metrics[host] = []
                    hosts[host] = "Hostname: %s\n" % host
                    hosts[host] += "%7s %-10s %-2s %-15s %-44s\n" % \
                                   ("ID", "OWNER", "ST", "NEXT RUN TIME", "METRIC")

                (metric, text) = display_metric(classad)
                running_metrics[host].append(metric)
                hosts[host] += text


            self.rsv.echo("") # get a newline to separate output from command
            for host in hosts:
                self.rsv.echo(hosts[host])

                # Determine if any metrics are enabled on this host, but not running
                missing_metrics = []
                enabled_metrics = Host.Host(host, self.rsv).get_enabled_metrics()
                for metric in enabled_metrics:
                    if metric not in running_metrics[host]:
                        missing_metrics.append(metric)

                if missing_metrics:
                    self.rsv.echo("WARNING: The following metrics are enabled for this host but not running:\n%s\n" %
                                  " ".join(missing_metrics))

                
        #
        # Show the consumers also if a specific hostname was not requested
        #
        if not hostname:
            classads = self.get_classads("OSGRSV==\"consumers\"")
            running_consumers = []
            if not classads:
                self.rsv.echo("No consumers are running")
            else:
                self.rsv.echo("%7s %-10s %-2s %-30s" % ("ID", "OWNER", "ST", "CONSUMER"))

                for classad in classads:
                    status = job_status[int(classad["JobStatus"])]
                    owner = classad["Owner"].replace('"', "")
                    consumer = classad["OSGRSVUniqueName"].replace('"', "")
                    running_consumers.append(consumer)
                    self.rsv.echo("%5s.%-1s %-10s %-2s %-30s" % (classad["ClusterId"], classad["ProcId"],
                                                                 owner, status, consumer))

                # Display a warning if any consumers are enabled but not running
                enabled_consumers = self.rsv.get_enabled_consumers()
                missing_consumers = []
                for consumer in enabled_consumers:
                    if consumer.name not in running_consumers:
                        missing_consumers.append(consumer.name)

                if missing_consumers:
                    self.rsv.echo("\nWARNING: The following consumers are enabled but not running:\n%s\n" %
                                  " ".join(missing_consumers))


def parse_classads(output):
    """
    Parse a set of condor classads in "attribute = value" format.
    A blank line will be between each classad.
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
