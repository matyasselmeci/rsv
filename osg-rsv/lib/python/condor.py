#!/usr/bin/env python

import os
import commands

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.condor")

class Condor(object):
    """
    Defines a system able to submit RSV probes
    """

    def __init__(self, rsv=None, user=None):
        self.rsv = rsv
        self.user = user



def is_metric_running(id):
    """
    Return true if a metric is running in Condor-Cron
    Return false if it is not
    """
    classads = get_classads(constraint = "OsgRsvUniqueName=='%s'" % id)
    if classads == None:
        log.error("Could not determine if job is running")

    for classad in classads:
        if classad[OsgRsvUniqueName] == id:
            return True

    return False

def get_classads(constraint=None):
    """
    Run a condor_cron_q command and return a hash of the classad.
    If there is an error, return None
    """
    log.debug("Getting Condor classads with constraint '%s'" % (constraint or ""))

    if not is_condor_running():
        log.error("Cannot fetch classads because Condor-Cron is not running")
        return None

    # Build the command
    cmd = "condor_cron_q -l"
    if constraint != None:
        cmd += " -constraint \'%s\'" % constraint

    # TODO: Add setup command (. setup.sh)?
    cmd = "%s; %s" % ("true", cmd)
    (ret, out) = commands.getstatusoutput(cmd);

    # Run the command and parse the classad
    if ret != 0:
        log.error("Command returned error code '%i': '%s'" % (ret, cmd))
        return None
    else:
        return parse_classads(out)


def parse_classads(output):
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


def stop_condor_jobs(constraint):
    """
    Stop the probes with the supplied constraint
    return True if jobs are stopped successfully, False otherwise
    """
    log.info("Stopping all probes with constraint '%s'" % constraint)

    if not is_condor_running():
        log.error("Cannot stop jobs because Condor-Cron is not running")
        return False

    # Check if any jobs are running to be removed
    jobs = get_classads(constraint=constraint)
    if len(jobs) == 0:
        log.info("No jobs to be removed with constraint '%s'" % constraint)
        return True
    
    # Build the command
    cmd = "condor_cron_rm"
    if constraint != None:
        cmd += " -constraint \'%s\'" % constraint

    # TODO: Add setup command (. setup.sh)?
    cmd = "%s; %s" % ("true", cmd)
    (ret, out) = commands.getstatusoutput(cmd);

    if ret != 0:
        log.error("Command returned error code '%i': '%s'" % (ret, cmd))
        return False

    return True


def is_condor_running():
    """
    Determine if Condor-Cron is running.  Return True is so, false otherwise
    """
    (ret, out) = commands.getstatusoutput("condor_cron_q")

    if not ret and out.index("-- Submitter") != -1:
        log.debug("Condor-Cron is running")
        return True

    log.info("Condor-Cron does not seem to be running.  Output of condor_cron_q:\n%s" % out)
    
    return False
