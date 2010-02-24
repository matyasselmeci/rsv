#!/usr/bin/env python
# condorsubmitter.py
# Marco Mambelli <marco@hep.uchicago.edu>

"""
condorsubmitter

This module provides a class, CondorSubmitter, which implements the Submitter
interface.  It is used to take a probe description and submit it to condor-cron
"""

import os
#import sys         # to flush stdout
import logging
import shutil # copy to backup .sub files (1 version)
import commands

# Local imports
import submitter

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.condorsubmitter")

def getSubmitter(*args, **kwrds):
    return CondorSubmitter.getOne(*args, **kwrds)

def _makedict(**kwargs):
    return kwargs
    
# DEFAULT_FILE_SAFE if true provides backup of files instead of deleting or overwriting (only one copy)
DEFAULT_FILE_SAFE = True

class CondorSubmitter(submitter.Submitter):
    """Submits 'probes' using Condor Cron"""
    
    STATUS_CONSTANTS = {
        '1': ['I', 'IDLE'],
        '2': ['R', 'RUNNING'],
        }

    def isHealthy(status):
        """Returns if the status is considered healthy
        A healthy job is running correctly.
        For CondorCron a job is healthy if it is RUNNING (2) or IDLE (1)
        """
        status = str(status).strip()
        if status=="1" or status=="2":
            return True
        return False
    isHealthy = staticmethod(isHealthy)

    def _get_template_cron(local_executable, cline_params, local_run_dir, local_unique_name, 
                           custom_id, vdt_location, perl_lib_dir, cron_dict):
        # Filling submission template
        # See http://www.cs.wisc.edu/condor/manual/v7.2/2_12Time_Scheduling.html
        # for information about Condor delayed submission and cron like functionalities
        _str = """\
######################################################################
# Submit file template, from RSV
######################################################################
CronPrepTime = 180
CronWindow = 99999999
CronMonth = %(cronMonth)s
CronDayOfWeek = %(cronDayOfWeek)s
CronDayOfMonth = %(cronDayOfMonth)s
CronHour = %(cronHour)s
CronMinute = %(cronMinute)s
Executable = %(local_executable)s
Error = %(local_run_dir)s/%(local_unique_name)s.err
Output = %(local_run_dir)s/%(local_unique_name)s.out
Log = %(local_run_dir)s/%(local_unique_name)s.log
Environment = PATH=/usr/bin:/bin;PERL5LIB=%(perl_lib_dir)s:%(env_perl5lib)s;VDT_LOCATION=%(vdt_location)s
Arguments = %(cline_params)s
Universe = local
Notification = never
OnExitRemove = false
PeriodicRelease = HoldReasonCode =!= 1
+OSGRSV = "probes"
+OsgRsvLocalUniqueName = "%(local_unique_name)s"
+OsgRsvCustomID = "%(custom_id)s"
Queue
"""
        
        # Arguments = /opt/osg/osg-rsv/bin/probes/certificate-expiry-local-probe  -m org.osg.local.hostcert-expiry --verbose
        # cronMonth cronDayOfWeek cronDayOfMonth cronHour cronMinute
        #executable_name = os.path.basename(local_executable)
        # local_run_dir
        # local_unique_name
        # vdt_location
        # perl_lib_dir
        # cline_params
        # any ID? idstr? no because running locally
        _str = _str % _makedict(local_executable=local_executable, 
                                cline_params=cline_params, 
                                local_run_dir=local_run_dir, local_unique_name=local_unique_name, 
                                custom_id=custom_id,
                                vdt_location=vdt_location, perl_lib_dir=perl_lib_dir,
                                cronMonth=cron_dict['CronMonth'], cronDayOfWeek=cron_dict['CronDayOfWeek'], 
                                cronDayOfMonth=cron_dict['CronDayOfMonth'], cronHour=cron_dict['CronHour'], 
                                cronMinute=cron_dict['CronMinute'], 
                                env_perl5lib=os.getenv("PERL5LIB", ""),
                            )
        return _str
    _get_template_cron = staticmethod(_get_template_cron)

    def _get_template_immediate(local_executable, cline_params, local_run_dir, local_unique_name, 
                                custom_id, vdt_location, perl_lib_dir):
        # Filling submission template
        _str = """\
######################################################################
# Submit file template, from RSV
######################################################################
Executable = %(local_executable)s
Error = %(local_run_dir)s/%(local_unique_name)s.test.err
Output = %(local_run_dir)s/%(local_unique_name)s.test.out
Log = %(local_run_dir)s/%(local_unique_name)s.test.log
Environment = PATH=/usr/bin:/bin;PERL5LIB=%(perl_lib_dir)s:%(env_perl5lib)s;VDT_LOCATION=%(vdt_location)s
Arguments = %(cline_params)s
Universe = local
Notification = never
#OnExitRemove = false
OnExitRemove = true
PeriodicRelease = HoldReasonCode =!= 1
+OSGRSV = "probes"
+OsgRsvLocalUniqueName = "%(local_unique_name)s.test"
+OsgRsvCustomID = "%(custom_id)s"
Queue
"""
        _str = _str % _makedict(local_executable=local_executable, 
                                cline_params=cline_params, 
                                local_run_dir=local_run_dir, local_unique_name=local_unique_name, 
                                custom_id=custom_id,
                                vdt_location=vdt_location, perl_lib_dir=perl_lib_dir,
                                env_perl5lib=os.getenv("PERL5LIB", ""),
                            )
        return _str
    _get_template_immediate = staticmethod(_get_template_immediate)

    def __init__(self, rsv=None, submitterid=None, user=None):
        #Submitter.Submitter.__init__(self, rundir)
        super(CondorSubmitter, self).__init__(rsv, submitterid, user)
        # setup run directory?
        #These should be setup in Submitter
        #self.submitterid = submitterid
        #self.rsv = rsv
        #self.user = user
        
    def _makeCronDict(cronstr):
        "Return a dictionary given tim information in metricInterval (cron) format"
        values = cronstr.split()
        if not values or len(values)<>5:
            log.error("Unable to set the time parameter, invalid setting: "+cronstr)
            return None
        
        retv = {}
        retv["CronMinute"]     = values[0]
        retv["CronHour"]       = values[1]
        retv["CronDayOfMonth"] = values[2]
        retv["CronMonth"]      = values[3]
        retv["CronDayOfWeek"]  = values[4]
        return retv
    _makeCronDict=staticmethod(_makeCronDict)

    def prepare(self, probe, rsv, uri=None, idstr=None, cron_submission=True):
        """Prepare submission for CondorSubmitter
        - prepare and save submit file
        - return file name (submit handle)
        """
        # directories are prapared by RSV: rundir=logdir, subdir (managed by the submitter)
        #jobrundir = self.subInit(job.getSubDir())
        # pass it a meaningful dirname
        #tstamp="%s-%s-%s-%s-%s-%s"%(time.localtime()[0:6])
        #ran=random.randrange(10,1000000,1)
        #proberundir = self.subInit(rsv.getLogDir()) #self.subInit("%s-%s-%d"%(where.getID(),tstamp,ran))

        executable_fname = probe.getExecutable()
        #self.setCLParams(job.getCLParameters(), job=job, rsv=rsv)
        cline_params = probe.getCLParameters(uri=uri)
        local_unique_name = probe.get_unique_name(uri)
        if not idstr:
            idstr = local_unique_name

        # these are used only to set the environment
        vdt_location = rsv.getVdtLocation()
        perl_lib_dir = rsv.getPerlLibDir()
        proberundir = rsv.getLogDir()

        if cron_submission:
            cron_dict = CondorSubmitter._makeCronDict(probe.getMetricInterval())
            _str = CondorSubmitter._get_template_cron(executable_fname, cline_params, proberundir, 
                                                      local_unique_name, idstr,
                                                      vdt_location, perl_lib_dir, cron_dict)
            sub_fname = os.path.join(rsv.getSubmitDir(), "%s.sub" % (local_unique_name,))
        else:
            _str = CondorSubmitter._get_template_immediate(executable_fname, cline_params, proberundir, 
                                                           local_unique_name, idstr,
                                                           vdt_location, perl_lib_dir)
            sub_fname = os.path.join(rsv.getSubmitDir(), "%s.test.sub" % (local_unique_name,))
        # copy the old submit file before writing the new one
        try:
            shutil.copyfile(sub_fname, "%s.bck" % (sub_fname,))
        except IOError:
            if os.path.isfile(sub_fname):
                log.warning("Backup failed for: "+sub_fname)
        open(sub_fname, 'w').write(_str)
        log.debug("condor submit file written for probe: %s" % (sub_fname,))
        return sub_fname

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
        if not rsv:
            rsv = self.rsv
        if not user:
            user = self.user

        if cron_submision and not force_prepare:        
            sub_fname = os.path.join(rsv.getSubmitDir(), "%s.sub" % (probe.get_unique_name(uri),))
        else:
            sub_fname = self.prepare(probe, rsv, uri, idstr, cron_submission=cron_submision)
            
        if cron_submision:
            log.debug("submitting condor job %s: %s" % (probe.get_unique_name(uri), sub_fname))
        else:
            log.debug("submitting condor job for immediate execution %s: %s" % 
                      (probe.get_unique_name(uri), sub_fname))
        cmd = "condor_cron_submit %s" % (sub_fname,)
        raw_ec, out = self.commands_getstatusoutput(cmd, user)
        #if os.WIFEXITED(raw_ec):
        exit_code = os.WEXITSTATUS(raw_ec) 
        log.info("Condor submission: %s" % out)
        log.debug("condor submission completed: %s (%s)" % (exit_code, raw_ec))
        return exit_code
        
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

    def _retrieveID(self, probe=None, ExtraInfo=False):
        """
        - retrieve log file name (build it)
        - parse ID at the end of the file:
         001 (NNN) ... started
         004 (NNN) ... ended
        - get NNN 
        if ExtraInfo, parse the log:
        - running or queued
        - Ended with...
        """
        return ""

    def _processListOutput(self, out, format, probe_test):
        if format=='full':
            return out
        probeatt = {}
        for i in out.split('\n'):
            if i.startswith('UserLog ='): 
                probeatt['UserLog'] = i[11:-1] # len('UserLog = "')=11
            elif i.startswith('Out ='): 
                probeatt['Out'] = i[7:-1] # len('Out = "')=7
            elif i.startswith('Err ='): 
                probeatt['Err'] = i[7:-1] 
            elif i.startswith('ClusterId ='):
                probeatt['ClusterId'] = i[12:]
            elif i.startswith('JobStatus ='):
                probeatt['JobStatus'] = i[12:]
            #if i.startswith(" ="):
            #    probeatt[''] = i[:]
            # end parsing
        #try block in caller
        if format=='brief':
            return probeatt['JobStatus']    # translate status? 
        elif format=='log':
            return ''.join(open(probeatt['UserLog']).readlines()) 
        elif format=='out':
            return ''.join(open(probeatt['Out']).readlines()) 
        elif format=='err':
            return ''.join(open(probeatt['Err']).readlines()) 
        elif format=='long':
            if probe_test:
                # Condor job should always be complete (C)
                ec, out = self.commands_getstatusoutput('condor_cron_history %s' % (probeatt['ClusterId'],))
            else:
                ec, out = self.commands_getstatusoutput('condor_cron_q %s' % (probeatt['ClusterId'],))
            return out
        # wrong/unknown format
        log.warning("Unknown output format: %s" % format)
        return None
    
    def listBySubmitterID(self, sid, rsv=None, format='brief', probe_test=False):
        cmd = "condor_cron_l -l %s" % (sid,)
        ec, out = self.commands_getstatusoutput(cmd)
        if ec>0:
            log.warning("Error running Condor command (%s): %s" % (cmd, out))
            return None
        if out and len(out.split('\n'))>10:
            try:
                return self._processListOutput(out, format, probe_test)
            except KeyError, ee:
                log.debug('Status lookup failed for job %s' % sid)
                log.error('Wrong job classad format, missing: %s' % ee)
                return None
        return None
    
    def listByID(self, lun, rsv=None, format='brief', probe_test=False):
        """
        format: brief, long, full, log, out, err
        """
        if not format:
            format = 'brief'
        if probe_test:
            lun += ".test"
        #TODO: once probe migrate support only LUN
        # Enabled jobs should be in queue (running or idle)
        # Test jobs should be in the history, completed
        if probe_test:
            for constraint in ('OsgRsvLocalUniqueName == "%s"' % (lun,), 
                               'UserLog == "%s/%s.log"' % (rsv.getLogDir(), lun)):
                cmd = "condor_cron_history -constraint '%s'" % (constraint,)
                ec, out = self.commands_getstatusoutput(cmd)
                if ec>0:
                    log.warning("Error running Condor command (%s): %s" % (cmd, out))
                    continue
                if out:
                    # lines with completed jobs are like 
                    #   38.0   marco           9/25 16:46   0+00:00:00 C   9/25 16:46 /raid/tests/rsv
                    # the last one has the last test
                    job_list = [i for i in out.split('\n') if i.find(" C ")>0] # ' C ' not at the beginning
                    if job_list:
                        job_id = job_list[-1].split()[0]
                        cmd = "condor_cron_history -l %s" % (job_id,)
                        ec, out = self.commands_getstatusoutput(cmd)
                        if ec>0:
                            log.warning("Error running Condor command (%s): %s" % (cmd, out))
                            continue
                        if out and len(out.split('\n'))>10:
                            break
        else: #no probe_test
            for constraint in ('OsgRsvLocalUniqueName == "%s"' % (lun,), 
                               'UserLog == "%s/%s.log"' % (rsv.getLogDir(), lun)):
                cmd = "condor_cron_q -l -constraint '%s'" % (constraint,)
                ec, out = self.commands_getstatusoutput(cmd)
                if ec>0:
                    log.warning("Error running Condor command (%s): %s" % (cmd, out))
                    continue
                if out and len(out.split('\n'))>10:
                    break
        if ec>0 or len(out.split('\n'))<10:
            # probe not found or bad output from Condor
            return None
        # OK, process and return the output
        try:
            return self._processListOutput(out, format, probe_test)
        except KeyError, ee:
            log.debug('Status lookup failed for %s' % lun)
            log.error('Wrong job classad format, missing: %s' % ee)
            return None
        #should never get here!
        return None            

    def list(self, probe=None, uri=None):
        """Returns the status of one or more probes
        - retrieve ID
        - no log file
        - status
        
        """
        # if submit file exists
        # if output/log file exist
        # condor_q results
        if probe:
            return ""
        return ""
    
    def cleanupById(self, lun, rsv=None, safe=DEFAULT_FILE_SAFE):
        """Removes all job information from condor_cron
        - lun: locally unique metric ID (uri__file@metric)
        The opposite of prepare:
        - removes the submit file
        """
        # probe+uri->lun: lun = probe.get_unique_name(uri)
        if not rsv:
            rsv = self.rsv
        sub_fname = os.path.join(rsv.getSubmitDir(), "%s.sub" % (lun,))
        # copy the old submit file before writing the new one
        if safe:
            try:
                shutil.copyfile(sub_fname, "%s.deleted" % (sub_fname,))
            except IOError:
                log.warning("Backup failed for file to remove: "+sub_fname)
        try:
            os.remove(sub_fname)
        except OSError:
            if os.path.isfile(sub_fname):
                log.warning("Removal of submit file failed: "+sub_fname)
        else:
            log.debug("Condor submit file removed: %s" % (sub_fname,))
        # (re)move the .out .err files to avoid the consumer to read them
        for i in ('out', 'err'):
            tmp_fname = "%s.%s" % (os.path.join(rsv.getLogDir(), lun), i)
            if not os.path.isfile(tmp_fname):
                log.debug("File already missing: "+tmp_fname)
                continue
            if safe:
                try:
                    shutil.copyfile(tmp_fname, "%s.deleted" % (tmp_fname,))
                except IOError:
                    log.warning("Backup failed for file to remove: "+tmp_fname)
            try:
                os.remove(tmp_fname)
            except OSError:
                log.warning("Removal of file failed: "+tmp_fname)
            else:
                log.debug("Condor file removed: %s" % (tmp_fname,))
        rsv.cleanHTML()
        return
    
    def stop(self, probe=None, rsv=None, uri=None, idstr=None):
        """removes the job from condor_cron
        - retrieve ID from log file
        - condor_cron_rm -reason "Removed by RSV control" cluster.proc
        """
        #TODO: retrieve job also using idstr (if no probe, uri)
        self.stopByID(probe.get_unique_name(uri), rsv)
        return
    
    def stopByID(self, lun, rsv=None):
        """stop removes the job from condor_cron
        - lun: locally unique metric ID (uri__file@metric)
        It is the opposite of start.
        - retrieve ID from log file
        - condor_cron_rm -reason "Removed by RSV control" cluster.proc
        """
        # TODO: once probe migrate support only LUN
        # Find the job
        for constraint in ('OsgRsvLocalUniqueName == "%s"' % (lun,), 
                           'UserLog == "%s/%s.log"' % (rsv.getLogDir(), lun)):
            cmd = "condor_cron_q -l -constraint '%s'" % (constraint,)
            ec, out = self.commands_getstatusoutput(cmd)
            if ec>0:
                log.warning("Error running Condor command (%s): %s" % (cmd, out))
                continue
            if out and len(out.split('\n'))>10: # check content? ec always 0 with condor
                # OK    
                clusterid = ''
                procid = ''
                for i in out.split('\n'):
                    if i.startswith('ClusterId ='):
                        clusterid = i[12:].strip() # len('ClusterId = ') == 12
                    if i.startswith('ProcId ='):
                        procid = i[9:].strip() 
                    if clusterid and procid:
                        # job found:
                        cmd = 'condor_cron_rm -reason "Removed by RSV control" %s.%s' % (clusterid, procid)
                        ec, out = self.commands_getstatusoutput(cmd)
                        if ec>0:
                            log.warning("Error running Condor command (%s) %s: %s" % (cmd, ec, out))
                        else:
                            if out and out.find("marked for removal")>0: # Should be "Job XX.YY marked for removal"
                                return
                            log.error("Condor removal failed (%s): %s" % (cmd, out))
        # job not found
        log.info("No job is running with ID '%s'" % (lun))
        return

    def areProbesRunning(self, filter=None):
        cmd = "condor_cron_q --constraint 'OSGRSV == \"probes\"' | grep probe_wrapper"
        if filter:
            cmd = "%s | grep %s" % (cmd, filter)
        ec, out = self.commands_getstatusoutput(cmd)
        # Exit code will be from grep. 
        #TODO: Isolating the condor command and filtering in Python may be safer and allow error checking
        #if ec>0:
        #    log.warning("Error running Condor command (%s) %s: %s" % (cmd, ec, out))
        #else:
        if out and out.split('\n')>0: 
            return True
        return False
