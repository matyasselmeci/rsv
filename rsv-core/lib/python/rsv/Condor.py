#!/usr/bin/env python

import os
import re
import pwd
import time
import commands
from time import strftime

import Host

class Condor:
    """ Define the interface to condor-cron """

    def __init__(self, rsv):
        self.rsv = rsv


    def is_condor_running(self):
        """
        Determine if Condor-Cron is running.  Return True is so, false otherwise
        """

        (ret, out) = self.commands_getstatusoutput("condor_cron_q")

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

        if classads is None:
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
        cmd = "condor_cron_q -l"
        if  constraint is not None:
            cmd += " -constraint '%s'" % constraint

        (ret, out) = self.commands_getstatusoutput(cmd)

        # Run the command and parse the classad
        if ret != 0:
            self.rsv.log("ERROR", "Command returned error code '%i': '%s'" % (ret, cmd))
            return None
        else:
            return parse_classads(out)


    def number_of_running_metrics(self):
        """ Return the number of running metrics """
        try:
            return len(self.get_classads("OSGRSV==\"metrics\""))
        except TypeError:
            self.rsv.log("ERROR", "Classad parsing failed, unable to count running metrics")


    def number_of_running_consumers(self):
        """ Return the number of running consumers """
        try:
            return len(self.get_classads("OSGRSV==\"consumers\""))
        except TypeError:
            self.rsv.log("ERROR", "Classad parsing failed, unable to count running consumers")


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


    def start_consumer(self, rsv, consumer):
        """ Start a single consumer condor-cron job. """
        
        self.rsv.log("INFO", "Submitting consumer job to condor: consumer '%s'" % consumer)

        condor_id = consumer.get_unique_name()

        # Check if the consumer is enabled
        if not rsv.is_consumer_enabled(consumer.name):
            self.rsv.log("ERROR", "The consumer '%s' is not enabled." % consumer.name)
            return False

        # Check if the consumer is already running in condor_cron
        if self.is_job_running(condor_id):
            self.rsv.log("INFO", "Consumer '%s' is already running" % consumer.name)
            return True

        # Generate a submission file
        submit_file_contents = self.build_consumer_submit_file(consumer)
        self.rsv.log("DEBUG", "%s submit file:\n%s" % (consumer.name, submit_file_contents), 4)
        return self.submit_job(submit_file_contents, condor_id)


    def submit_job(self, submit_file_contents, condor_id, dir="/tmp", remove=1):
        """
        Input: submit file contents and job identifier
        Create submission file, submits it to Condor and removes it
        """

        sub_file_name = os.path.join(dir, condor_id + ".sub")
        try:
            file_handle = open(sub_file_name, 'w')
            file_handle.write(submit_file_contents)
            file_handle.close()
        except IOError, err:
            self.rsv.log("ERROR", "Cannot write temporary submission file '%s'." % sub_file_name)
            self.rsv.log("ERROR", "Error message: %s" % err)
            return False

        # We need to change to a directory that can be read by the RSV user.  This is
        # because Condor puts the current working directory into the job ad as 'Iwd'
        # (Initial working dir).  When starting the job condor cd's to Iwd then starts
        # the process.  If it cannot cd into the dir it gives a 'permission denied' error.
        os.chdir(os.path.join("/", "tmp"))

        # Submit the job and remove the file
        cmd = "condor_cron_submit %s" % sub_file_name
        raw_ec, out = self.commands_getstatusoutput(cmd, self.rsv.get_user())
        exit_code = os.WEXITSTATUS(raw_ec)
        self.rsv.log("INFO", "Condor submission: %s" % out)
        self.rsv.log("DEBUG", "Condor submission completed: %s (%s)" % (exit_code, raw_ec))

        if remove:
            os.remove(sub_file_name)

        if exit_code != 0:
            self.rsv.log("ERROR", "Problem submitting job to condor.  Command output:\n%s" % out)
            return False

        # Determine the job cluster ID
        match = re.search("submitted to cluster (\d+)\.", out)
        if match:
            job_id = match.group(1)
            self.rsv.log("DEBUG", "Condor job cluster ID: %s" % job_id)
            return job_id
        else:
            self.rsv.log("ERROR", "Could not determine job cluster ID from output:\n%s" % out)
            return False


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
        if jobs is None:
            self.rsv.log("ERROR", "Problem stopping RSV jobs.  Condor may not be running")
            return False
        if len(jobs) == 0:
            self.rsv.log("INFO", "No jobs to be removed with constraint '%s'" % constraint)
            return True

        # Build the command
        cmd = "condor_cron_rm"
        if constraint is not None:
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
        environment = "PATH=/usr/bin:/bin\n"
        condor_id = metric.get_unique_name()
        arguments = "-v 3 -r -u %s %s %s" % (metric.host, metric.name, metric.get_settings())
        timestamp = strftime("%Y-%m-%d %H:%M:%S %Z")

        probe_interval = metric.get_probe_interval()
        if not probe_interval:
            cron = metric.get_cron_entry()
            if not cron:
                self.rsv.log("ERROR", "Invalid cron time for metric %s on host %s.  Will not start." %
                             (metric.name, metric.host))
                return ""

        submit = ""
        submit += "######################################################################\n"
        submit += "# Temporary submit file generated by rsv-control\n"
        submit += "# Generated at %s " % timestamp
        submit += "######################################################################\n"
        submit += "Environment = %s\n"    % environment

        if probe_interval:
            submit += "DeferralPrepTime = ifThenElse(%d - ScheddInterval + 31 > 0, %d - ScheddInterval + 31, 180) \n" % (probe_interval, probe_interval)
            submit += "DeferralTime = (CurrentTime + %d + random(30))\n" % probe_interval
            submit += "DeferralWindow = 99999999\n"
            submit += "+OSGRSVProbeInterval = %d\n" % probe_interval
        else:
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
        submit += "+OSGRSVHost = \"%s\"\n" % metric.host
        submit += "+OSGRSVMetric = \"%s\"\n" % metric.name
        submit += "+OSGRSVUniqueName = \"%s\"\n" % condor_id
        submit += "Queue\n"
        
        return submit


    def build_consumer_submit_file(self, consumer):
        """ Create a submission file for a consumer """
        log_dir = self.rsv.get_consumer_log_dir()

        environment = "PATH=/usr/bin:/bin;"
        environment += consumer.get_environment()

        condor_id = consumer.get_unique_name()
        arguments = consumer.get_args_string()
        timestamp = strftime("%Y-%m-%d %H:%M:%S %Z")

        submit = ""
        submit += "######################################################################\n"
        submit += "# Temporary submit file generated by rsv-control\n"
        submit += "# Generated at %s\n" % timestamp
        submit += "######################################################################\n"
        submit += "Arguments = %s\n" % arguments
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
            this_uid = os.getuid()
            if this_uid == 0:
                # If we are root, we can switch to the user to run the command
                command = 'su -c "%s" %s' % (command, user)
            else:
                # If we are not root then make sure that our current UID is the same
                # as the user we want to run the command as.  Otherwse, error out.
                if this_uid != pwd.getpwnam(user).pw_uid:
                    self.rsv.echo("ERROR: Cannot run a job as user '%s'.  Current user is '%s'" %
                                  (user, pwd.getpwuid(this_uid).pw_name))
                    return 1, ""

        ret, out = commands.getstatusoutput(command)
        return ret, out


    def display_jobs(self, parsable=False, hostname=None):
        """ Create a nicely formatted list of RSV jobs running in Condor-Cron """

        job_status = ["U", "I", "R", "X", "C", "H", "E"]

        def display_metric(classad, parsable):
            status = job_status[int(classad["JobStatus"])]

            next_run_time = "UNKNOWN"
            deferral_time = 0
            try:
                probe_interval = int(classad['OSGRSVProbeInterval'])
                deferral_time = int(classad['EnteredCurrentStatus']) + probe_interval
            except (KeyError, TypeError, ValueError):
                try:
                    deferral_time = int(classad['DeferralTime'])
                except (KeyError, TypeError, ValueError):
                    pass

            if deferral_time:
                if parsable:
                    next_run_time = strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(deferral_time))
                else:
                    next_run_time = strftime("%m-%d %H:%M", time.localtime(deferral_time))

            metric = "UNKNOWN?"
            if "OSGRSVMetric" in classad:
                metric = classad["OSGRSVMetric"].strip('"')

            owner = classad["Owner"].replace('"', "")

            if parsable:
                output = "%s.%s | %s | %s | %s | %s\n" % (classad["ClusterId"], classad["ProcId"],
                                                                owner, status, next_run_time, metric)
            else:
                output = "%5s.%-1s %-10s %-2s %-15s %-44s\n" % (classad["ClusterId"], classad["ProcId"],
                                                                owner, status, next_run_time, metric)
                
            return metric, output


        #
        # Build a table of jobs for each host
        #
        hosts = {}
        running_metrics = {}
        classads = self.get_classads("OSGRSV==\"metrics\"")

        if not classads:
            if parsable:
                self.rsv.echo("ERROR: Condor-cron is running but no RSV metrics are running")
            else:
                self.rsv.echo("No metrics are running")
        else:
            for classad in classads:
                host = "UNKNOWN?"
                if "OSGRSVHost" in classad:
                    host = classad["OSGRSVHost"].strip('"')

                if hostname and hostname != host:
                    continue

                if host not in hosts:
                    running_metrics[host] = []
                    hosts[host] = "Hostname: %s\n" % host
                    if not parsable:
                        hosts[host] += "%7s %-10s %-2s %-15s %-44s\n" % \
                                       ("ID", "OWNER", "ST", "NEXT RUN TIME", "METRIC")

                (metric, text) = display_metric(classad, parsable)
                running_metrics[host].append(metric)
                hosts[host] += text

            # Add in any hosts that have ALL their metric missing
            for host in self.rsv.get_hosts():
                if host not in hosts:
                    hosts[host] = "Hostname: %s\n\tThis host has no running metrics.\n" % host
                    running_metrics[host] = []


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
                    if parsable:
                        self.rsv.echo("MISSING: " + " | ".join(missing_metrics))
                    else:
                        self.rsv.echo("WARNING: The following metrics are enabled for this host but not running:\n%s\n" %
                                      " ".join(missing_metrics))

                
        #
        # Show the consumers also if a specific hostname was not requested
        #
        if not hostname and not parsable:
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

        return True

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
