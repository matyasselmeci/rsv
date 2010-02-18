#!/usr/bin/env python
# Probe.py
# Marco Mambelli

import re
import os 
import sys
import copy
import stat
import time
import shutil
import socket
import commands

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.probe")

_cachedHostName = None
def getLocalHostName():
    """
    Returns the local hostname
    """
    global _cachedHostName
    if not _cachedHostName:
        try:
            _cachedHostName = os.environ.get("HOSTNAME", socket.gethostname())
        except:
            _cachedHostName = "localhost"
    return _cachedHostName

def introspect_probe(probe, rsv=None):
    """
    Look at the .meta file for the probe in the osg-rsv/bin/probes/meta dir
    One file may contain multiple probes (LCG would require only one)
    """
    if not os.path.isabs(probe):
        if os.path.isfile(probe):
            probe = os.path.abspath(probe)
        else:
            if rsv:
                probe = os.path.join(rsv.getBinDir(), probe)
            if not os.path.isfile(probe):
                log.warning("Unable to find probe file: %s", probe)
                return None

    metafile = os.path.join(os.path.dirname(probe), "meta", os.path.basename(probe) + ".meta")

    lines = open(metafile).readlines()
    retlist=[]
    retv = {}
    if lines:
        for i in range(len(lines)):
            if lines[i].strip()=='EOT':
                retlist.append(retv)
                retv={}
                continue
            info = lines[i].split(':', 1)
            if len(info) != 2:
                log.warning("Invalid line in meta file '" + metafile + "'")
                print lines[i]
                continue
            retv[info[0].strip()] = info[1].strip()
        if retv:
            # output ended and last EOT was missing 
            log.warning("meta file '" + metafile + "' is missing trailing 'EOT'")
            retlist.append(retv)
    return retlist


def get_metrics_from_probe(fname, rsv, uri=None, uridict=None, options=None):
    """
    Returns all metrics from the given probe file
    NB in LCG there should be only one metric per probe
    """
    vallist = introspect_probe(fname, rsv)
    if not vallist:
        log.error("Unable to load probe: introspection failed")
        return None

    retlist = []
    for val in vallist:
        ptype = val.get('probeType', None)
        if not ptype: 
            ptype = val.get('serviceType', ptype)
        if not ptype:
            log.error("Unable to load probe: probeType and serviceType not defined")
            continue
        if not uri and uridict:
            uri = uridict.get(ptype, uri)
        probe = getProbe(ptype, fname, uri, ptype, rsv=rsv,
                         metricName=val['metricName'], metricType=val['metricType'],
                         serviceType=val['serviceType'], options=options)

        # add remaining values:
        if 'metricInterval' in val:
            probe.setCronValues(val['metricInterval'].split())

        probe.enableByDefault = val.get('enableByDefault', probe.enableByDefault)

        probe.metricValuesExtra = {}
        for k, v in val.items():
            # Skip the fields we already have explicit variables for
            if k in ['metricName', 'metricType', 'probeType', 'serviceType',
                    'metricInterval', 'enableByDefault']:
                continue
            probe.metricValuesExtra[k] = v

        retlist.append(probe)

    return retlist


class Probe(object):
    """
    Probe class to group Probe configuration and start, stop, ...
    
    Probes are executables, normally Perl scripts, part of the RSV infrastructures
    They are (should be) developed following LCG specification:
    https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
    They can be invoked as 'PERL5LIB=$OSG_RSV_LOCATION/bin/probes:$PERL5LIB $probe -l -m all' 
    Only one metric can be returned (by specification), therefore -m all makes no sense
    to discover supported metrics (description):
    serviceType: SRM
    metricName: org.glite.SRM-getFile
    metricType: status
    - 
    """        
        
    # Keep linear MRO
    SUBMIT_PARAM_EXECUTABLE = "probe_wrapper.pl"
    SUBMIT_PARAM_ENVIRONMENT = "PATH=$PATH;PERL5LIB=$OSG_RSV_LOCATION/bin/" \
        "probes:$PERL5LIB;VDT_LOCATION=$VDT_LOCATION"
    SUBMIT_PARAM_CRON = { "CronHour": "*/2",
                          "CronMonth": "*",
                          "CronDayOfMonth": "*",
                          "CronDayOfWeek": "*",
                        }
    SUBMIT_PARAM_OTHER = { "Universe": 'local',
                           #"Arguments": '',
                         }
    SUBMIT_DEFAULT_ARGS = ''

    #vars for editor
    name = ''
    type = ''
    rsvlocation = ''
    urilist = []
    extra_spec_content = ''
    submit_params = {}
    
    def __init__(self, name, uriliststring, type, rsv=None, metricName=None, 
                 serviceType=None, metricType='status', extra_args=None,
                 options=None):
        # retrieving and storing options form the command line
        # TODO: select only what will be used?
        # better way to pass probe options?
        # used in _aux_getCLParameters getCLParameters (also by subclasses)
        self.options = options
        if name:
            self.name = name.strip()
        else:
            self.name = name
        if metricName:
            self.metricName = metricName.strip()
        else:
            self.metricName = self.name
        self.probeType = type
        if serviceType:
            self.serviceType = serviceType
        else:
            self.serviceType = type
        self.metricType = metricType
        self.enableByDefault = False
        self.metricValuesExtra = {} # Excluding: metricName, metricType, probeType, serviceType, metricInterval, enableByDefault
        self.rsv = rsv
        if rsv:
            self.rsvlocation = rsv.getLocation()
            self.rsvperllibdir = rsv.getPerlLibDir()
        else:
            self.rsvlocation = ''
            self.rsvperllibdir = ''
        #self.extra_spec_content = ''
        self.local = False
        if not uriliststring:
            self.urilist = []
        else:
            # convert to lowercase (case not important in URI)
            # avoids useless duplicates
            self.urilist = [i.lower() for i in uriliststring.split()]
        self.submit_params = copy.copy(Probe.SUBMIT_PARAM_CRON)
        self.submit_params.update(Probe.SUBMIT_PARAM_OTHER)
        self.executable = os.path.join(self.rsvperllibdir, Probe.SUBMIT_PARAM_EXECUTABLE)
        # should this be used or just getCLParams?
        self.clparams = Probe.SUBMIT_DEFAULT_ARGS
        self.setCronValues('*-*/2-*-*-*'.split('-'))   # inport from rsvcontrol? (OPTIONS_DEFAULT.crontime.split('-'))
        #self.submit_params["Executable": os.path.join(location, bin/probes/probe_wrapper.pl) # "$OSG_RSV_LOCATION/bin/probes/probe_wrapper.pl",
        if options:
            #TODO: check these options
            #condor-cron is always using local universe!
            #if options.jobuniverse:
            #    self.submit_params["Universe"] = options.jobuniverse
            if hasattr(options, 'crontime') and options.crontime: # self.submit_params["Cron..."]
                self.setCronValues(options.crontime.split("-"))
            # command line options
            if hasattr(options, 'probe_name') and options.probe_voname:
                self.clparams += " --virtual-organization %s" % (options.probevoname,)
            if hasattr(options, 'probe_verbose') and options.probe_verbose:
                self.clparams += " --verbose"      
            if hasattr(options, 'probe_localtime') and options.probe_localtime:
                self.clparams += " --print-local-time"
        if extra_args:
            self.clparams += extra_args
        self.enabledict={}
            
    def _loadProbeMetrics(self):
        pass

    _cron_input_format = ["CronMinute", "CronHour", "CronDayOfMonth", "CronMonth",
        "CronDayOfWeek"]
    def setCronValues(self, values):
        """
        values array follows the cron (5) standard
        """
        if not values or len(values) != 5:
            # Should control better for valid values (e.g. inspect each value)?
            log.warning("Invalid cron period setting (%s), ignored" % \
                str(values))
            return
        for cron_key, value in zip(self._cron_input_format, values):
            self.submit_params[cron_key] = value

    def getMetricInterval(self, novalue=None):
        rets = ""
        for i in self._cron_input_format:
            if i in self.submit_params:
                tmp = self.submit_params[i]
            else:
                if novalue:
                    tmp = novalue
                else:
                    raise KeyError(i)
            rets += "%s " % tmp
        
        return rets[:-1]
    
    def addURI(self, uri):
        """
        Appending URI to probe's URI list.
        """
        if uri in self.urilist:
            log.warning("URI %s not added, already in probe's URI list" % uri)
            return
        self.urilist.append(uri)
        log.debug("Added URI %s. URI List: %s" % (uri, self.urilist))
            
    def getType(self):
        """
        Returns Probe Type
        probeType. It may be different from serviceType (but often it is the
        same). It is different from metricType (e.g. "service")
        """
        return self.probeType
    
    def getName(self):
        """
        Returns the probe name
        Probe name. It is not the file name. It may be different from the
        metricName (but often it is the same). 
        """
        return self.name
    
    #def _fixProbeSuffix(self, instr):
    def _fixProbeSuffix(instr):
        """
        Adjust the probe suffix. Probe file name should end in -probe.
        """
        if not instr.endswith('-probe'):
            instr += "-probe"
        return instr
    _fixProbeSuffix=staticmethod(_fixProbeSuffix)

    def getProbe(self):
        "Return the absolute path of the probe"
        pname = self.name
        if not pname:
            log.warning("Probe file name not defined")
            return None
        if pname[0]==['/']:
            return pname
        pname = self._fixProbeSuffix(pname)
        return os.path.join(self.rsvperllibdir, pname)

    def getExecutable(self):
        """
        Return the wrapper script used to run the probes. Its absolute path.
        Default is $VDT_LOCATION/osg-rsv/%s
        """ % Probe.SUBMIT_PARAM_EXECUTABLE
        executable = self.executable
        if not executable:
            log.warning("Probe's executable (wrapper) file name not defined")
            return None
        if executable[0]==['/']:
            return executable
        return os.path.join(self.rsvperllibdir, executable)

    def getLocalUniqueName(self, uri=None):
        """
        Name as '%(host)s__%(key)s', where key = "%s@%s" % (basename, metricName)
        file basename (from getProbe)
        TODO: Concern about host from URI: are host unique or should the full URI be used?
        """
        name = "%s__%s@%s" % (self._getonlyhost(uri), os.path.basename(self.getProbe()),
            self.metricName)
        return name

    def getKey(self):
        name = "%s@%s" % (os.path.basename(self.getProbe()), self.metricName)
        return name

    def getLocation(self):
        # either RSV or RSVLOCATION
        return self.rsvlocation

    def make_spec_file(self, spec_file):
        dir = os.path.dirname(spec_file)
        if not os.path.exists(dir):
            log.info("Creating directory '%s' for spec files" % dir)
            os.makedirs(dir)

        # make a blank file for people to add to if they want
        # TODO: do we need to change permissions on the file and/or directories?
        try:
            log.info("Creating blank spec file '%s'" % spec_file)
            open(spec_file, 'w').close()
        except:
            log.warn("Unable to create %s" % spec_file)
        
    
    def _aux_getCLParameters(self, uri):
        "auxiliary function to return CL parameters as string"
        outstr = ""

        # extra command line options can be declared in the spec files
        global_spec = os.path.join(self.rsv.getSpecDir(), 'global-specs', "%s.spec" % self.getKey())
        probe_spec = os.path.join(self.rsv.getSpecDir(), "%s" % self._getonlyhost(uri), "%s.spec" % self.getKey())
        for spec_file in [global_spec, probe_spec]:
            if os.path.isfile(spec_file):
                tmp = open(spec_file).readlines()
                if tmp: 
                    # replace the newlines with spaces because these are command line arguments
                    outstr += re.sub('\n', ' ', ' '.join(tmp))
            else:
                self.make_spec_file(spec_file)
                
        #retrieve params from file
        metric = self.metricName
        if metric:
            if outstr.find("-m %s" % (metric,)) < 0:
                outstr += " -m %s" % (metric,)

        outstr += self.clparams

        # parameters from options:
        #TODO: replace options
        #global options
        options = self.options
        if options:
            if hasattr(options, 'probe_voname') and options.probe_voname:
                ourstr += " --virtual-organization "+options.probe_voname
            if hasattr(options, 'probe_verbose') and options.probe_verbose:
                ourstr += " --verbose"
            if hasattr(options, 'probe_localtime') and options.probe_localtime:
                ourstr += " --print-local-time"

        """
      ## If extra specs are passed, then append them
      $local_submit_params{Arguments} .= " $extra_spec_contents" if (defined($extra_spec_contents));
"""
        # Add in additional flags if it is not a local probe
        # Handle this redefining the function in the subclass ProbeLocal or ProbeNotLocal?
        if not self.local:
            if hasattr(options, 'gratia') and options.gratia and outstr.find("--ggs")<0:
                    # Find python, so that the probes can put it in shebang line
                    # If we can't find python, we probably don't want these scripts to accumulate
                    if sys.executable:
                        #TODO: ? add gratia grid type? grid_type, rsvgratiafile
                        outstr += " --ggs --gsl %s/output/gratia --python-loc %s" % (self.rsvlocation, sys.executable)
                    else:
                        warning = "Gratia output cannot be enabled for OSG-RSV because python cannot be found.\n"
                        post_install_log(warning)
                        log.warning(warning)
            ## Check whether we need to add the "--uri" flag
            if outstr.find('--uri') < 0:
                #          unless ($local_submit_params{Arguments} =~ /\-\-uri /) {
                outstr += " --uri %s" % uri
            # Check if we need to add a --proxy argument
            #TODO: ? service proxy is handled automatically?
            if hasattr(options, 'proxy_file') and options.proxy_file:
                    outstr += " --proxy %S" % (options.proxy_file,)
        # probe name added in caller (getCLParameters)
        return outstr
        
    def getCLParameters(self, uri=None):
        """Return CL parameters as string
        use self.metricName, self.getProbe, uri, options
        """
        outstr = self._aux_getCLParameters(uri)
        # The probe name is the first argument, because we need to tell the wrapper what probe to execute
        outstr = "%s %s" % (self.getProbe(), outstr)
        return outstr

    def _getonlyhost(uri):
        # LocalProbes allow no uri and the host is localhost
        if not uri:
            uri = getLocalHostName()
        # if URI string passed, assume [method://]host.domain[:port][/url]
        host_re = re.compile('^(\w*://)?([\w_\-\.]+)(:[0-9]*)?(/.*)$')
        m = host_re.match(uri)
        if not m:
            return uri
        return m.groups()[1]
    _getonlyhost = staticmethod(_getonlyhost)

    def configure(self, probe, uri, host, extra_spec_contents):
        """Probe configuration
        - create extra spec file
        """        
        return
    
    def configureTest(self, uri, force=False, enable=False, disable=False, value=None):
        """Configure a test:
        If no additional value is provided will use self.enableByDefault (from the probe itself) to configure as default
        - enable: force the enabling of the probe
        - disable: force the disabling of the probe (overrides enable)
        - value: specifies the values of the configuration including enable/disable:
                [ enabled(boolean), 5 cron values (minute, hour, domonth, month, doweek)]
                (overrides enable and disable)
        - change the test run parameters (metrics)
        - installTest = add submit file or 
        - removeTest = delete submit file depending on configuration
        """
        #TODO: check value of value if provided
        #TODO: role of force not clear, not used
        if not self.rsv:
            log.error("No OSG RSV defined. Probe cannot be installed or configured.")
            
        host = self._getonlyhost(uri)
        log.info("Changing configuration for RSV probes of type %s\n\t for URI: %s (host: %s)" %
                 (self.name, uri, host))

        if not self.rsv.metricsFileFix(host):
            log.error("Bad metrics file for host %s, check it manually" % (host,))
            return
        
        if not value:
            value = self.getMetricInterval().split()
            to_be_enabled = (self.enableByDefault or enable) and not disable
            if to_be_enabled:
                value.insert(0, True)
                self.installTest(uri)
                #self.startTest(uri)
            else:        
                value.insert(0, False)
                self.removeTest(uri)
                #self.stopTest(uri)
                #TODO: remove sub file?

        self.rsv.metricsFileUpdate(host, self.getKey(), value)
    
    def configureTestAll(self, uri_list):
        """Configure all tests for this probe:
        using configuration file
        """
        for i in uri_list:
            self.configureTest(i)

    def removeTest(self, uri):
        """Remove a test
        - remove submit file
        """
        if not self.rsv:
            log.error("No RSV defined. Probe cannot be installed or configured.")
            return
        lun = self.getLocalUniqueName(uri)
        log.info("Removing .sub files for RSV probe of type %s\n\t for URI: %s (LUN: %s)" %
                 (self.name, uri, lun))
        subm = self.rsv.getSubmitter()
        subm.cleanupById(lun, self.rsv)

    def installTest(self, uri, test_only=False):
        """Installs a test
        - install submit file
        """
        if not self.rsv:
            log.error("No RSV defined. Probe cannot be installed or configured.")
            return
        host = self._getonlyhost(uri)
        log.info("Creating .sub files for RSV probes of type %s\n\t for URI: %s (host: %s)\n" %
                 (self.name, uri, host))
        #TODO: go through RSV, no direct CondorSubmitter self.rsv.getSubmitter()
        subm = self.rsv.getSubmitter()
        subm.prepare(self, self.rsv, uri, cron_submission=(not test_only))
        
        # extra options, touch file
        spec_file = os.path.join(self.rsv.getSpecDir(), "%s" % (host,), "%s.spec" % (self.getKey(),))
        if not os.path.exists(spec_file):
            log.info("Adding spec file (for metric extra options): %s" % (spec_file,))
            open(spec_file,'w').close()  # make a blank file for people to add to if they want

    def install(self):
        """Install the probe
        - copy the file in the RSV bin directory
        - invoke configure
        """
        probefile = os.path.abspath(self.getProbe())
        if not self.rsv:
            log.error("No RSV defined. Probe cannot be installed or configured.")
            return
        if not os.path.dirname(probefile) == os.path.abspath(self.rsv.getBinDir()):
            # probe not in the RSV binary dir
            try:
                shutil.copy(probefile, os.path.abspath(self.rsv.getBinDir()))
                log.info("Probe file %s copied in OSG-RSV bin directory (%s)." % 
                         (probefile, os.path.abspath(self.rsv.getBinDir())))
            except:
                log.error("Unable to install the probe in RSV.")
                log.info("Probe file %s could not be copied in OSG-RSV bin directory (%s)." % 
                         (probefile, os.path.abspath(self.rsv.getBinDir())))
                return
        # extra options, touch file
        spec_file = os.path.join(self.rsv.getSpecDir(), 'global-specs', "%s.spec" % (self.getKey(),))
        if not os.path.exists(spec_file):
            log.info("Adding spec file (for probe extra options): %s" % (spec_file,))
            open(spec_file,'w').close()  # make a blank file for people to add to if they want
        #self.configure()
        return

    def startTest(self, uri):
        """Start probe (add it to condor-cron)
        """
        subm = self.rsv.getSubmitter()
        subm.submit(self, self.rsv, uri)
    
    def start(self):
        """Start probe (add it to condor-cron)
        """
        subm = self.rsv.getSubmitter()
        #TODO: imlement
        log.error("Not implemented. Start all the probes")
        raise Exception("Incomplete method")
        #subm.submit(self, self.rsv)

    def stopTest(self, uri):
        """Stop probe (remove it from condor-cron)
        """
        subm = self.rsv.getSubmitter()
        subm.stopByID(self.getLocalUniqueName(uri), self.rsv)

    def stop(self):
        """Stop probe (remove it from condor-cron)
        """
        subm = self.rsv.getSubmitter()
        #TODO: imlement
        log.error("Not implemented. Stop all the probes")
        raise Exception("Incomplete method")
        #subm.stop(self, self.rsv, uri)

    def status(self, uri=None):
        """List probe status in RSV:
        UNDEFINED, UNINSTALLED, INSTALLED (and not configured), (configured,) DISABLED, ENABLED
        """
        status = "UNDEFINED"
        if not self.rsv:
            return status
        status = "UNINSTALLED"
        if not os.path.isfile(os.path.join(self.rsv.getBinDir(), os.path.basename(self.getProbe()))):
            return status
        # executable file there
        status = "INSTALLED"
        if uri:
            urilist = [uri]
        else:
            urilist = self.urilist
        #passed = False
        met = None
        for u in urilist:
            met = self.rsv.metricsFileRetrieve(u, self.getKey())
            if met:
                #passed = True
                break
        if not met:
            log.warning("Probe %s is installed but probably misconfigured" % self.getLocalUniqueName(uri)) 
            return status #"UNDEFINED"
        try:
            if met['enable']:
                return "ENABLED"
            else:
                return "DISABLED"
        except KeyError:
            # Bad file format
            pass
        log.warning("Irregular status file")
        return "UNDEFINED"

    def isEnabled(self, uri):
        """Returns if a probe is enabled for a specific URI
        A probe/uri is enabled if:
        - the metric files reports the probe enabled
        - the submitted job is queued or running fine 
        This function is not checking:
        - if there is recent output from the probe (is not wwre of the supposed period)
        - if the output is correct (a probe could be running but return wrong output, it is still enabled)
        """
        if self.status(uri) == 'ENABLED':
            # check status of submitted job
            subm_status = self.submission_status(uri)
            if self.rsv.getSubmitter().isHealthy(subm_status):
                return True
        return False
    
    # Undefined, disabled, enabled, installed, uninstalled, undefined
    def submission_status(self, uri, format='brief', probe_test=False):
        """Submitter (Condor) status of the job.
        Uses LocalUniqueID to get the status from the submitter defined in RSV
        Check the Submitter for possible status formats.
        """
        subm = self.rsv.getSubmitter()
        retv = subm.listByID(self.getLocalUniqueName(uri), self.rsv, format,
            probe_test=probe_test)
        return retv
    
    def enable(self, uri):
        """Enables the probe
        """
        self.install()
        self.configureTest(uri, enable=True)
        self.startTest(uri)
        log.info("Metric %s enabled" % self.getLocalUniqueName(uri))

    def disable(self, uri):
        self.stopTest(uri)

        # remove line from configuration file
        self.configureTest(uri, disable=True)

        # Remove the metric line from the HTML consumer page
        self.remove_metric_from_html_consumer(uri)
        
        log.info("Metric %s disabled" % self.getLocalUniqueName(uri))


    def remove_metric_from_html_consumer(self, uri):
        """When disabling a metric, this method will remove the line from the
        html consumer output
        We need to make a state file lock to remove the race condition for the
        state file being updated by the html-consumer.  If we can't get the lock
        here, we'll give up after 5 seconds, because it's not critical that we
        remove the data
        """
        html_consumer_state_file = self.rsvlocation + "/output/html/state.file"
        state_file_lock = html_consumer_state_file + ".lock"

        count = 0
        while os.path.exists(state_file_lock):
            count += 1
            # Give up after 5 seconds because it's not critical that we update this
            # file, and we don't want this script to hang
            if count > 5:
                log.info("Unable to remove metric info from html page because lock is unavailable")
                return 1
            time.sleep(1)

        open(state_file_lock, 'w').close()

        state = open(html_consumer_state_file).readlines()

        # Open up the state file and remove the one line associated with this metric
        # on this specific host.  Note that it might not exist, so we'll only re-write
        # the file if it has changed.
        new_state = []
        regex = re.compile(uri + " \|\| " + self.metricName + " \|\|")
        for line in state:
            if not regex.match(line):
                new_state.append(line)

        if state != new_state:
            open(html_consumer_state_file, 'w').write(''.join(new_state))

        os.unlink(state_file_lock)


    def test(self, uri):
        "Probe is executed and output returned"
        fname = self.getExecutable()
        if not os.path.isabs(fname):
            if os.path.isfile(fname):
                fname = os.path.abspath(fname)
            else:
                if rsv:
                    fname = os.path.join(rsv.getBinDir(), fname)
                if not os.path.isfile(fname):
                    log.error("Unable to find probe file: %s", fname)
                    return
        if self.rsv:
            bindir = self.rsv.getPerlLibDir()
            vdtdir = ";VDT_LOCATION=%s" % (self.rsv.getVdtLocation(),)
            setupstr = self.rsv.getSetupCommand()
        else:
            bindir = '.'
            vdtdir = ""
            setupstr = ""
        # probe.getCLParameters()
        cmd = "%sPERL5LIB=%s:$PERL5LIB%s %s %s" % (setupstr, bindir, vdtdir, fname,
            self.getCLParameters(uri))
        ec, out = commands.getstatusoutput(cmd)
        log.info("Test command: '%s'" % (cmd,))
        if ec:
            log.error("Unable to run the probe (%s)\n" % os.WEXITSTATUS(ec))
            log.error("Probe output:\n%s" % out)
            return ""
        if not out:
            log.warning("No output returned.")
            return ""
        return out
    
    def full_test(self, uri):
        """Execute a full test inside the OSG-RSV infrastructure.
        Return the exit code of the job submission
        """
        self.install()
        #no configuratin necessary (configuration sets cron timing and enabled/disabled status)
        #skip self.configureTest(uri, enable=True), invoking installTest directly to prepare submit file
        self.installTest(uri, True)
        subm = self.rsv.getSubmitter()
        log.info("Testing metric %s" % self.getLocalUniqueName(uri))
        ec = subm.submit_immediate(self, self.rsv, uri)
        #skip self.configureTest(uri, disable=True)
        return ec
    
    def list(self, uri, format='local'):
        """List probe status
        Dismbiguation unction using status or submission_status depending on the format
        """
        if format=='local':
            return self.status(uri)
        else:
            return self.submission_status(uri, format)
    
    def diagnostic(self, uri, verbose=False, prefix="", probe_test=False):
        """Return a string with diagnostic information
        """
        p_exe = self.getExecutable()
        p_exe_date = "-na-"
        if os.path.isfile(p_exe):
            p_exe_date = time.ctime(os.path.getmtime(p_exe))
        outstr = "%sName %s, Verision %s, File name (mtime): %s(%s)\n" % (prefix, self.name,
            self.getVersion(), p_exe, p_exe_date)
        outstr += "URI: %s" % (uri,) #All URIs ('\n'.join(self.urilist),)
        outstr += "Local Status: %s" % (self.status(uri),)
        outstr += "Submission Status: %s" % (self.submission_status(uri, 'brief', probe_test),)
        # Diagnostic euristics?
        # - Try to parse files and infer probe status?
        #  - hold status in log file
        #  - no recent out/err file
        #  - err file not empty
        #  - CRITICAL string in out
        if verbose:
            outstr += "Full submision status:\n%s" % (self.submission_status(uri, 'full'))
            for i in ('out', 'err', 'log'):
                outstr += "Job %s:\n%s" % (i, self.submission_status(uri, i, probe_test))
        return outstr
    
    def describe(self, verbose=False, prefix=""):
        #
        outstr = "%sPROBE: Name %s, URI %s\n" % (prefix, self.name, '\n'.join(self.urilist))
        outstr += "%s metricName: %s, metricType: %s, probeType: %s, serviceType: %s, metricInterval: %s, enableByDefault: %s\n" % (
            prefix, self.metricName, self.metricType, self.probeType, self.serviceType, self.getMetricInterval('?'), self.enableByDefault)
        if self.metricValuesExtra:
            outstr += "%s Introspected parameters: " % (prefix,)
            for i in self.metricValuesExtra.items():
                outstr += "%s: %s " % (i[0], i[1])
            outstr += "\n"
        outstr += "%s File: %s, Wrapper: %s" % (prefix, self.getProbe(), self.getExecutable())
        if verbose:
            if not self.rsv:
                outstr += "%s No RSV" % (prefix,)
            else:
                outstr += "%s RSV description:\n" % (prefix,) + self.rsv.describe(prefix=prefix+"  ")
        return outstr
    
class ProbeTest(Probe):
    """Simple probe
    """
    def __init__(self, name='test', uri=None, type='Test', *args, **kwrds):
        Probe.__init__(self, name, uri, type, *args, **kwrds)
        
    def makeProbeFile(fname='test'):
        if not os.path.isabs(fname):
            fname = Probe._fixProbeSuffix(fname)
        try:
            log.info("Creating a test probe in file: "+fname)
            fp = open(fname, 'w')
            fp.write("""#!/bin/sh
cat << EOF
serviceType: OSG-CE-General
metricName: org.osg.general.osg-directories-CE-permissions
metricType: status
probeType: OSG-CE
enableByDefault: true
metricInterval: 5 6 * * *
EOT
""")
            fp.close()
            fmode = os.stat(fname).st_mode | stat.S_IEXEC
            os.chmod(fname, fmode)
        except IOError:
            log.error('Unable to write probe file: '+fname)
            return None
        return fname
    makeProbeFile = staticmethod(makeProbeFile)

    def makeProbe(name='test', rsv=None, uri='', probe_index=0):
        fname = ProbeTest.makeProbeFile(name)
        if fname:
            try:
                retp = get_metrics_from_probe(fname, rsv, uri)[probe_index]
                return retp
            except IndexError:
                pass
        retp = ProbeTest()
        return retp
    makeProbe = staticmethod(makeProbe)
    
probe_dict = {}
probe_dict = {'Probe': Probe,
              'ProbeTest': ProbeTest}                
                
class ProbeLocal(Probe):
    """Local probe. It checks that added URI are local. Throws a warning if not.
    """
    def __init__(self, name, uri=None, type='OSG-Local-Monitor', *args, **kwrds):
        #super(ProbeLocal, self).__init__(name, uri)
        Probe.__init__(self, name, uri, type, *args, **kwrds)
        ##TODO: fix local probe behavior 
        self.local = True 

    def _fixProbeSuffix(executable):
        "Adjust the probe suffix"
        if not executable.endswith('-local-probe'):
            if not executable.endswith('-local'):
                executable += "-local"
            executable += "-probe"
        return executable
    _fixProbeSuffix=staticmethod(_fixProbeSuffix)

    def addURI(self, uri):
        """Add uri to local probe. If URI is not local, it will not be added.
        Program will continue and a warning will be logged.
        """
        # TODO: how are URI handled in local probes? Confirm that is the desired way
        log.debug("Local Probe addURI")
        hostname = Probe._getonlyhost(uri)
        #TODO: Adding also IP of local host? How for dual homed hosts?
        if not hostname in [getLocalHostName(), "localhost.localdomain", "localhost", "127.0.0.1"]:
            log.warning("Local probe %s (ul: %s). Ignoring request to add non local URI: %s" % (self.getKey(), self.urilist, uri))
            return
        Probe.addURI(self, uri)

    
probe_dict['local'] = ProbeLocal
probe_dict['OSG-Local-Monitor'] = ProbeLocal

class ProbeNonLocal(Probe):
    """Base class for non local probes
    """ 
    def getCLParameters(self, uri=None): #TORM:, metric=None):
        "Return CL parameters as string"
        outstr = self._aux_getCLParameters(uri) #TORM:, metric)
        #TODO: replace options
        options = self.options
        if options:
            try:
                if (options.gratia and outstr.find('--ggs') < 0):
                    # Find python, so that the probes can put it in shebang line
                    #if($path) { # If we can't find python, we probably don't want these scripts to accumulate
                    if sys.executable:
                        outstr += " --ggs --gsl %s/output/gratia --python-loc %s" % (self.rsvlocation, sys.executable)
                    else:
                        warning = "Gratia output cannot be enabled for OSG-RSV because python cannot be found.\n"
                        post_install_log(warning)
                        log.warning(warning)
            except AttributeError:
                log.debug("No gratia attribute in options")
            # Check if we need to add a --proxy argument
            try:
                if options.proxy_file:
                    outstr += " --proxy %S" % (options.proxy_file,)
            except AttributeError:
                log.debug("No proxy_file attribute in options")
        ## Check whether we need to add the "--uri" flag
        if outstr.find('--uri') < 0:
            outstr += " --uri %s" % (uri,)
        # The probe name is the first argument, because we need to tell the wrapper what probe to execute
        outstr = "%s %s" % (self.getProbe(), outstr)
        return outstr


#probe_dict['nonlocal'] = ProbeNonLocal

class ProbeCE(ProbeNonLocal):
    def __init__(self, name, uri, type='OSG-CE', *args, **kwrds):
        if not type=='OSG-CE':
            log.warning('Wrong Probe invoked: %s instead of OSG-CE' % (type,))
        Probe.__init__(self, name, uri, type, *args, **kwrds)
probe_dict['OSG-CE'] = ProbeCE

class ProbeGUMS(ProbeNonLocal):
    def __init__(self, name, uri, type='OSG-GUMS', *args, **kwrds):
        if not type=='OSG-GUMS':
            log.warning('Wrong Probe invoked: %s instead of GUMS' % (type,))
        Probe.__init__(self, name, uri, type, *args, **kwrds)
probe_dict['OSG-GUMS'] = ProbeGUMS

class ProbeGridFTP(ProbeNonLocal):
    def __init__(self, name, uri, type='OSG-GridFTP', *args, **kwrds):
        if not (type=='OSG-GridFTP' or type=='GridFTP'):
            log.warning('Wrong Probe invoked: %s instead of GridFTP' % (type,))
        Probe.__init__(self, name, uri, type, *args, **kwrds)
probe_dict['OSG-GridFTP'] = ProbeGridFTP
probe_dict['GridFTP'] = ProbeGridFTP

class ProbeSRM(ProbeNonLocal):
    def __init__(self, name, uri, type='OSG-SRM', *args, **kwrds):
        if not type=='OSG-SRM':
            log.warning('Wrong Probe invoked: %s instead of SRM' % (type,))
        Probe.__init__(self, name, uri, type, *args, **kwrds)
probe_dict['OSG-SRM'] = ProbeSRM

class ProbeSE(ProbeNonLocal):
    def __init__(self, name, uri, type='OSG-SE', *args, **kwrds):
        if not type=='OSG-SE':
            log.warning('Wrong Probe invoked: %s instead of OSG-CE' % (type,))
        #super(ProbeLocal, self).__init__(name, uri)
        Probe.__init__(self, name, uri, type, *args, **kwrds)
probe_dict['OSG-SE'] = ProbeSE


def getProbe(probetypename, *args, **kwrds):
    """Returns one object having as class one of the valid Probe classes.
    If the type is not available a test probe is returned.
    """
    retv = None
    if probetypename in probe_dict:
        rett = probe_dict[probetypename]
        retv = rett(*args, **kwrds)
    else:
        log.warning("Probe of type %s not found (%s), returning ProbeTest" % (probetypename,
            probe_dict.keys()))
        rett = ProbeTest
        retv = rett(*args, **kwrds)
        #retv = rett(*((None,) + args), **kwrds)
    return retv

def getProbeTypeList():
    "Returns a list of the available job types"
    return probe_dict.keys()

################


def main():
    #TODO: use it for testing
    # Main
    pass
    
if __name__ == "__main__":
    main()
