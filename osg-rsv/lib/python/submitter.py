#!/usr/bin/env python
# submitter.py
# Marco Mambelli <marco@hep.uchicago.edu>

"""
This module provides the Submitter class.  This is a class which implements
the Singleton pattern.  It is designed to be able to submit a RSV probe.
The Submitter class should be subclassed by an actual implementation.
"""

import os
import sha # used by _safe_write
import commands

import probe

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.submit")

def getSubmitter(*args, **kwrds):
    return Submitter.getOne(*args, **kwrds)


class Submitter(object):
    """Defines a system able to submit RSV probes
    The probe itself is a Perl executable launched with a wrapper on local Condor cron)
    """

    __childDict = {}
    __altChildDict = {}

    def __init__(self, rsv=None, submitterid=None, user=None):
        self.rsv = rsv
        self.submitterid = submitterid
        self.user = user
        
    def getOne(cls, *args, **kwrds):
        """
        Creates and provides exactly one instance for each required subclass
        of getSubmitter. Implements the Singleton pattern
        """
        cl_name = cls.__name__
        if not issubclass(cls, Submitter):
            log.error("Wrong Factory invocation, %s is not subclass of  Submitter." % cls)
        else:
            if not Submitter.__childDict.has_key(cl_name):
                Submitter.__childDict[cl_name] = cls(*args, **kwrds)
            return Submitter.__childDict[cl_name]
    getOne = classmethod(getOne)
    
    def getInstance(cls, iname, *args, **kwrds):
        if iname == "default":
            return cls.getOne(*args, **kwrds)
        else:
            cl_name = cls.__name__
            if not issubclass(cls, Submitter):
                log.error("Wrong Factory invocation, %s is not subclass of Submitter." % cls) 
            else:
                try:
                    tdic = Submitter.__altChildDict[iname]
                except KeyError:
                    tdic = {}
                    Submitter.__altChildDict[iname] = tdic
                if not tdic.has_key(cl_name):
                    tdic[cl_name] = cls(*args, **kwrds)
                return tdic[cl_name]
    getInstance = classmethod(getInstance)
    
    def getSetupCommand(self):
        "Return the setup command"
        if self.rsv:
            return self.rsv.getSetupCommand()
        return ""
    
    def commands_getstatusoutput(self, command, user=None):
        """Run a command in a subshell using commands module and setting up the environment"""
        cmd = "%s%s" % (self.getSetupCommand(), command)
        if user:
            cmd = 'su -c "%s" %s' % (cmd, user)
        ec, out = commands.getstatusoutput(cmd)
        return ec, out
    
    def _safe_write(file, data):
        """
        Write the data to the file only if it is different. This makes for 
        better caching, since it won't change the Last-Modified date unless 
        necessary.
        
        version = 0.61
        Copyright (c) 2004 Mark Nottingham <mnot@pobox.com>

        Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:

        The above copyright notice and this permission notice shall be included in all
        copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
        IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
        OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
        SOFTWARE.
        """
        
        try:
            fh = open(file, 'r')
            cur_data = sha.new(fh.read()).digest()
            fh.close()
        except IOError:
            cur_data = None
        if cur_data != sha.new(data).digest():
            fh = open(file, 'w')
            fh.write(data)
            fh.close()
    _safe_write = classmethod(_safe_write)

    def subInit(self, jobSubDir):
        """Set up for job submission:
        - creates submit dir (submit dir+job subdir)
        """
        wdir = jobSubDir
        try:
            os.makedirs(wdir)
        except:
            if not os.path.isdir(wdir):
                log.error("Unable to create the job directory: %s" % wdir)
        log.info("Initializing submit directory: %s" % (wdir,))
        return wdir

    def prepare(self, probe, rsv, uri=None, idstr=None, cron_submission=True):
        """Prepare submission for CondorSubmitter
        - prepare and save submit file
        - return file name (submit handle)
        """
        return None
    
    #def submit(self, where, job, clparams):
    #    print job

    def submit(self, probe, rsv=None, uri=None, idstr=None, force_prepare=False, user=None, cron_submision=True):
        """Submit a condor job for immediate or delayed execution
        submit_cron and submit_immediate both refer to this function and preset cron_submission
        - probe: the probe to execute
        - rsv: the rsv server
        - uri: the URI or hostname used for probe execution
        - idstr: string that will be added in a classad of the job (TODO: and written in idfile.txt and transferred to the execution dir)
        - force_prepare: flag, if true then if submit file is already there skips preparation
        - user: username used for job execution
        - cron_submission: control is the submission is delayed (True) or immediate (False)
        TODO: add timeout to condor-cron-submit (external command)
        """
        return 1

    def submit_immediate(self, probe, rsv, uri=None, idstr=None, force_prepare=False, user=None):
        """Submit a condor job for immediate execution
        Used to test the probe. See submit (cron_submission=False)
        """
        return self.submit(probe, rsv, uri, idstr, force_prepare, user, False)

    def submit_cron(self, probe, rsv, uri=None, idstr=None, force_prepare=False, user=None):
        """Submit a condor job using a standard template (condor cron)
        Submits to condor-cron for delayed execution. See submit (cron_submission=True)
        """
        return self.submit(probe, rsv, uri, idstr, force_prepare, user, True)
    
    def listBySubmitterID(self, sid, rsv=None, format='brief', probe_test=False):
        return None
    
    def listByID(self, lun, rsv=None, format='brief', probe_test=False):
        return None

    def list(self, probe=None):
        """Returns the status of one or more probes
        """
        # if submit file exists
        # if output/log file exist
        # condor_q results
        if probe:
            return ""
        return ""
    
    def stop(self, probe=None, rsv=None, uri=None, idstr=None):
        """removes the job from condor_cron
        - retrieve ID from log file
        - condor_cron_rm -reason "Removed by RSV control" cluster.proc
        """
        #TODO: retrieve job also using idstr (if no probe, uri)
        self.stopByID(probe.getLocalUniqueName(uri), rsv)
        return
    
    def stopByID(self, lun, rsv=None):
        """stop removes the job from condor_cron
        """
        return
    
    def areProbesRunning(self, filter=None):
        return False


def getProbeTest():
    """returns a simple probe, useful for testing
    """
    return probe.ProbeTest('uct3-edge7.uchciago.edu')
