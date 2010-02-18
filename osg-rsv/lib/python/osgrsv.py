#!/usr/bin/env python
# osgrsv.py
# Marco Mambelli <marco@hep.uchicago.edu>

import os
import sys
import commands  # used to get OSG RSV version 
import ConfigParser

import condorsubmitter
from probe import get_metrics_from_probe, ProbeLocal

import altlogging
log = altlogging.getLogger("osgrsv.rsvcontrol.osgrsv")
    
def findPathOSG():
    """
    Find the path to OSG root directory
    """
    return os.environ.get("OSG_LOCATION", os.environ.get("VDT_LOCATION", ""))

def getConfigOSG(fname, static_config=[None]):
    if static_config[0]:
        return static_config[0]

    # read and parse config.ini
    try:
        fp = open(fname)
    except:
        log.error("Unable to open OSG configuration file " + fname)
        return None

    cp = ConfigParser.SafeConfigParser()
    try:
        cp.readfp(fp)
    except:
        log.error("Error parsing the OSG configuration file " + fname)
        return None

    static_config[0] = cp
    return cp


# The name is used as name of the server and for the 
# root directory (VDT_LOCATION+OSGRSV_NAME)
OSGRSV_NAME = "osg-rsv"

class OSGRSV:
    DEFAULT_CONFIG_ENTRY = { "enable": True,
                             "CronMinute": "*",
                             "CronHour": "*/2",
                             "CronMonth": "*",
                             "CronDayOfMonth": "*",
                             "CronDayOfWeek": "*",
                         }
    DEFAULT_CONFIG_FILE = "config/rsv-config.pytxt"
    DEFAULT_CONFIG = {
        'username': 'rsvuser',
        'proxy': '/tmp/x509_u<uid>',
        'rsv_use_service_cert': False,
        'rsv_proxy_file': '/tmp/rsvproxy',
        'rsv_cert_file': '/etc/grid-security/rsvcert.pem',
        'rsv_key_file': '/etc/grid-security/rsvkey.pem',
    }
    
    def __init__(self, vdtlocation=None, config=None, user=None):
        self.name = OSGRSV_NAME
        if vdtlocation:
            self.vdtlocation = os.path.abspath(vdtlocation)
        else:
            self.vdtlocation = findPathOSG()
        if not self.vdtlocation:
            log.warning("Unable to determine VDT_LOCATION")
            self.vdtlocation = ''
        self.location = os.path.join(self.vdtlocation, self.name) # "$VDT_LOCATION/osg-rsv";
        self.metrics_loc = os.path.join(self.location, "config") #"$OSG_RSV_LOCATION/config";
        #self.probe_spec_loc = os.path.join(self.location, "specs") #"$OSG_RSV_LOCATION/specs";
        self.configfile = os.path.join(self.location, OSGRSV.DEFAULT_CONFIG_FILE)
        self.user = user
        
        #submitter
        self.submitter = None
        
        # configuration parameters
        self.config = OSGRSV.DEFAULT_CONFIG
        self._loadconfig(config)        
        
        self.register_svc = os.path.join(self.vdtlocation, "vdt/sbin/vdt-register-service")
        self.initfile = os.path.join(self.vdtlocation, "post-install", self.name)
        self.rsv_vdtapp = os.path.join(self.vdtlocation, "vdt-app-data/osg-rsv")
        
        # The Gratia ProbeConfig file should be a symlink.  We need the real location,
        # or else when we safe_write it, we'll overwrite the symlink.
        self.gratia_probeconf = os.path.realpath(os.path.join(self.vdtlocation,
            "gratia/probe/metric/ProbeConfig"))

        # Condor-Cron will be at VDT_LOCATION/condor-cron
        self.condorcron = os.path.join(self.vdtlocation, "condor-cron")
        if not os.path.exists(self.condorcron):
            log.error("Cannot find Condor-Cron at $VDT_LOCATION/condor-cron")
            # raise some error/exception

        ###TRAnslate
        # Always make sure we have the directories setup
        self.setup_dirs()

        # Preserve old (Probe?) config if necessary 
        if os.getenv('OLD_VDT_LOCATION'):
            self.preserve_old_config() 

    def getSetupCommand(self):
        """
        Return the source command to setup the environment. 
        Empty string is returned if no VDT_LOCTION is defined.
        """
        #TODO: handle multiple shells. Is commands using always sh or the default user shell?
        rets = self.getVdtLocation()
        if not rets:
            return ""
        rets = "source %s; " % (os.path.join(self.getVdtLocation(), "setup.sh"),)
        return rets
    
    # Functions to save and recover configuration
    def _saveconfig(self):
        # TODO: replace with something more robust (pickle, .ini)
        fp = open(self.configfile, 'w')
        fp.write(str(self.config))
        fp.close()
        
    def _loadconfig(self, override=None):
        try:
            lines = open(self.configfile).readlines()
            tmp = eval('\n'.join(lines), {}, {})
        except IOError:
            tmp = {}
        for k, v in tmp.items():
            self.config[k] = v
        if override:
            for k, v in override.items():
                self.config[k] = v
    # end
    
    def cleanHTML(self):
        """Clean HTML output
        - remove HTML subpages
        - remove HTML main page
        """
        html_dir = self.getHtmlOutputDir()
        for i in [os.path.join(html_dir, j) for j in os.listdir(html_dir)]:
            if os.path.isdir(i):
                try:
                    tmp_fname = os.path.join(i, "index.html")
                    os.remove(tmp_fname)
                    log.info("Removed html file "+tmp_fname)
                except OSError:
                    if os.path.isfile(tmp_fname):
                        log.warning("Unable to remove the file: "+tmp_fname)
        try:
            tmp_fname = os.path.join(self.getHtmlOutputDir(), "index.html")
            os.remove(tmp_fname)
            log.info("Removed html file "+tmp_fname)
        except OSError:
            if os.path.isfile(tmp_fname):
                log.warning("Unable to remove the file: "+tmp_fname)
        return
    
    def getSubmitter(self):
        if not self.submitter:
            self.submitter = condorsubmitter.getSubmitter(rsv=self, user=self.user)
        return self.submitter
    
    def configure(self):
        self._saveconfig()        

    # Function returning Paths. 
    # For the one that can be probe specific, should consider also consumers (and become getProbeXXX)? 
    def getProxyFile(self):
        if self.config['rsv_use_service_cert']:
            return self.config['rsv_proxy_file']
        tmp =  self.config['proxy']
        if tmp.endswith('<uid>'):
            #ALT: if the current user is not the expected user
            # import pwd, u1=pwd.getpwnam(self.config['username']), rsvid=u1.pw_uid
            rsvid = os.getuid()
            return "%s%s" % (tmp[:-5], rsvid)
        return tmp

    def getLocation(self):
        return self.location

    def getVdtLocation(self):
        return self.vdtlocation
    
    def getSpecDir(self):
        return os.path.join(self.location, "specs")
    
    def getBinDir(self):
        return os.path.join(self.location, "bin/probes")
    getPerlLibDir = getBinDir
    
    def getLogDir(self):
        return os.path.join(self.location, "logs/probes")
    
    def getSubmitDir(self):
        return os.path.join(self.location, "submissions/probes")
    
    def getHtmlOutputDir(self):
        return os.path.join(self.location, "output/html")

    def setup_dirs(self):
        """Create the appropriate directories, and make sure they have the right permissions
        """
        # TODO: implement
        return    
    
    def preserve_old_config(self):
        "Preserve old config"
        # TODO: implement
        return

    def getVersion(self, verbose=False):
        "Print the RSV version"
        #placeholder
        #TODO: provide better method
        # vdt-version provides several lines
        # 2 are about RSV and the probes: OSG Resource and Service Validation (RSV) 
        ec, out = commands.getstatusoutput(self.getSetupCommand()+"vdt-version")
        # control ec?
        if ec:
            return "UNKNOWN VDT VERSION"
        if out:
            lines = [i for i in out.split('\n') 
                     if i.startswith('OSG Resource and Service Validation (RSV)')>=0]
            if verbose:
                return '\n'.join(lines)
            start = len('OSG Resource and Service Validation (RSV)')
            version = lines[0][start:57].strip()
            return version
        return ""

    def describe(self, verbose=False, prefix=''):
        outstr = "%sRSV installation\n%sVersion: %s\n" % (prefix, prefix, self.getVersion())
        outstr += "%sInstall dir: %s\n" % (prefix, self.getLocation())
        outstr += "%sDirectories: \n\tPerlLib %s\n\tLog %s\n\tSubmit %s\n" % (prefix,
            self.getPerlLibDir(), self.getLogDir(), self.getSubmitDir())
        if self.config:
            tmp = "\nOptions: \n"
            for k, v in self.config.items():
                tmp += "\t%s (%s)\n " % (v, k)
            outstr += "\t%s %s\n" % (prefix, tmp[:-2],)
        if verbose:
            outstr += "%s Probes:\n" % prefix
            try:
                #dlist = os.listdir(self.getPerlLibDir())
                perl_lib_dir = self.getPerlLibDir()
                dlist = [i for i in os.listdir(perl_lib_dir) if i.endswith('probe')]
                outstr += "%s\n" % ('\n'.join(dlist),)
            except OSError:
                # PerlLibDir not existent/accessible
                pass
        #outstr += "" % ()
        return outstr


    def load_installed_metrics(self, uridict=None, options=None):
        """Lists all the probes installed in the bin directory
        Unless uridict is passed, no attention to URI is given 
        Perturn value contains one probe per installed probe binary
        """
        probes = []
        for probefile in os.listdir(self.getBinDir()):
            # directory may contain other files, probe files must end in "-probe"
            if not probefile.endswith("-probe"):
                continue
            tmp_probes = get_metrics_from_probe(probefile, self, uridict=uridict, options=options)
            probes += tmp_probes 
        return probes


    def getConfiguredProbes(self, hostid=None, options=None):
        """Gets all the configured probes
        Scan for all the installed metric files (configuration files, one per host, only the required host)
        Return one probe for each line in a metric file (lines referring the same executable are condensed in a single one)
        """
        metrics_files = []
        metricsarchive = {}
        onehost = False
        suffix_pos = -len("_metrics.conf")

        # Find all the metrics files that we care about
        if hostid:
            metrics_files = [os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)]
            onehost = True
        else:
            names = os.listdir(self.metrics_loc)
            # this may require python 2.4:
            metrics_files = [os.path.join(self.metrics_loc, name) for name in names if \
                name.endswith("_metrics.conf") and not name=="sample_metrics.conf"]

        # Get the set of metrics listed in each metrics file
        for metrics_file in metrics_files:
            if not os.path.isfile(metrics_file):
                log.warning("Expected file missing: " + metrics_file)
                continue
            if not onehost:
                hostid = os.path.basename(metrics_file)[:suffix_pos]
            metricsarchive[hostid] = self._read_metrics_file(metrics_file)

        # Form a hash of metrics with with info about each host they are enabled for
        probelist = []
        probearchive = {}
        log.debug("URIs found: %s" % (metricsarchive.keys(),))
        for host in metricsarchive.keys():
            for k in metricsarchive[host].keys():
                probe, metric = k.split('@', 1)

                if probe in probearchive:
                    probelist = probearchive[probe]
                else:
                    probelist = get_metrics_from_probe(probe, self, options=options)
                    if not probelist:
                        log.warning("Error in loading probes (%s, %s) from file %s" % (h, k, probe))
                        continue
                    log.debug("New file %s: %s" % (probe, [i.metricName for i in probelist]))
                    #if len(probelist)> 1:
                    #    log.warning("LCG standard violation. Probe producing multiple metrics: %s" % (probe,))
                    probearchive[probe] = probelist

                selprobe = None
                for probe in probelist:
                    if metric==probe.metricName:
                        selprobe = probe

                # add values to selprobe    
                if not selprobe:
                    #log.warning("No probe with URI %s and key %s" % (host,k))
                    log.warning("No probe with metric %s in probe file %s" % (metric, probe))
                    continue

                # Adding the URI and the values from the metrics configuration file
                selprobe.addURI(host)
                log.debug("Adding URI to probe %s: %s" % (selprobe.getKey(), host))
                # h,k are keys of the current iteration
                val = metricsarchive[host][k]
                selprobe.setCronValues([val['CronMinute'], val['CronHour'], val['CronDayOfMonth'], 
                                        val['CronMonth'], val['CronDayOfWeek']])
                # probe enabled = val['enable'] on/off
                selprobe.enabledict[host] = val['enable'] == "on"

        # preparing probes to return
        retlist = [i for i_list in probearchive.values() for i in i_list]
        return retlist

    def isValidProbeID(self, id):
        """Checks ID syntax and returns True/Flse
        hostName__fileName@metricsName
        """
        #TODO: may want also check if the probe is installed/configured
        try:
            ind1 = id.find("__")
        except:
            return False
        if ind1 > 0:
            ind2 = id.find('@')
            if ind2 > ind1: # ind2>(ind1+3)
                return True
        return False
    
    def getProbeByID(self, id):
        """Rerurn the probe with the iven ID from the current OSG-RSV installation.
        id: is of the form <host>__<filename>@metricname>
        Probe can be configured or not. If not configured a warning message is printed but the probe is returned using the URI (host) in the ID.
        """
        # ID like host__fname@metricname
        # should I accept __<filename>@metricname> ? Probably no, no URI
        if not id:
            log.error("Invalid probe ID, unable to retrieve probe.")
            return None
        hostid, pkey = id.split('__', 1)
        pfname, ptype = pkey.split('@', 1)
        # load probes (metrics) from probe file
        probelist = get_metrics_from_probe(pfname, self, hostid)
        if not probelist:
            log.error("Error in loading probe %s, %s" % (hostid, pkey))
            return None
        # select the right probe
        probelist = [i for i in probelist if i.getKey()==pkey]
        if len(probelist) != 1:
            if probelist:
                log.warning("Ambiguous probe, metrics not unique, using the first matching metric.")
            else:
                log.error("No matching ID (%s) in the selected probe %s" % (pkey, pfname))
                return None
        probe = probelist[0]
        # add URI
        probe.urilist = [hostid]
        # load and add configuration from metrics configuration file (if any)
        mfname = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)
        if not os.path.isfile(mfname):
            log.warning("Probes/metrics configuration file missing for host %s: %s" % (hostid, mfname))
            probemetrics = {}
        else:
            probemetrics = self._read_metrics_file(mfname)
            try:
                val = probemetrics[pkey]
                probe.setCronValues([val['CronMinute'], val['CronHour'], val['CronDayOfMonth'], 
                                     val['CronMonth'], val['CronDayOfWeek']])
            except KeyError:
                log.warning("No configuration for the metric "+id)
        return probe

    
    def metricsFileFix(self, hostid):
        metrics_file = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)

        file_ok = True
        linedict = {}

        # Create the file if it does not exist. and prepend a header
        if not os.path.isfile(metrics_file):
            try:
                fp = open(metrics_file, 'w')
                fp.write("# Configuration for host: %s\n" % hostid)
                fp.write("# -- DO NOT MODIFY THIS FILE BY HAND --\n")
                fp.write("# Manual changes may be overwritten by rsv-control\n\n")
                fp.close()
                log.info("Created metrics file: " + metrics_file)
            except IOError:
                log.error("Unable to create metrics file: " + metrics_file)
        else:
            # Load the metrics file and check its consistency
            lines = open(metrics_file).readlines()
            for line in lines:
                if line and line[0] == 'o':
                    info = line.split()
                    if not len(info)==7:
                        file_ok = False
                        log.warning("Invalid non comment line in metrics file %s:\n<%s>" % (file, lines[i]))
                        continue
                    key = info[1].strip()
                    if key in linedict.keys(): 
                        linedict[key].append(line)
                        file_ok = False
                        log.warning("Duplicate metric %s in metrics file %s:\n%s" % (key, file, linedict[key]))
                    else:
                        linedict[key] = [line]
            
        # TODO: Add any metrics to the file that are not yet present?
        #all_metrics = self.load_installed_metrics()
        #new_lines = ""
        #for metric in all_metrics:
        #    if not metric.getKey() in linedict:
        #        templ = "off  %-70s %s\n" % ( metric.getKey(),
        #                                      metric.getMetricInterval()
        #                                      )
        #        new_lines += templ
        #
        #if new_lines != "":
        #    try:
        #        fp = open(metrics_file, 'a')
        #        fp.write(new_lines)
        #        fp.close()
        #        log.info("Added metrics to file: " + metrics_file)
        #    except IOError:
        #        log.error("Unable to add to metrics file: " + metrics_file)
            
        
        return file_ok

                
    def metricsFileRetrieve(self, hostid, metricid, default=None):
        """retrieve a metric from file. Optional default if metric is not found
        hostid (host from the URI)
        metricid (probe.getKey, basename@metricName)
        """
        # assuming thet none of hostid, metricid are null. check?
        fname = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)
        if not os.path.isfile(fname):
            return default
        lines = open(fname).readlines()
        for line in lines:
            if line and line[0] == 'o':                    
                if line.find(metricid) >= 0:
                    info = line.split()
                    if not len(info)==7:
                        log.warning("Invalid matching line in metrics file %s:\n<%s>. Skipping." % (fname, lines[i]))                        
                        continue
                    retval = { 'enable': True }
                    if info[0] == 'off':
                        retval = { 'enable': False }
                    retval['CronMinute']     = info[2]
                    retval['CronHour']       = info[3]
                    retval['CronDayOfMonth'] = info[4]
                    retval['CronMonth']      = info[5]
                    retval['CronDayOfWeek']  = info[6]
                    return retval
        return default

    def metricsFileMakeEntry(enabled, minute, hour, domonth, month, doweek):
        "enabled(boolean), 5 cron values" 
        retv = {'enable':         enabled,
                'CronMinute':     minute,
                'CronHour':       hour,
                'CronDayOfMonth': domonth,
                'CronMonth':      month,
                'CronDayOfWeek':  doweek,
            }
        return retv
    metricsFileMakeEntry = staticmethod(metricsFileMakeEntry)

    def metricsFileUpdate(self, hostid, metricid, entry_par, default=None):
        """Change the config file. Returns True if the metrics file changed
        - hostid is fqdn
        - metricid is a key fname@metricName
        - entry_par list of parameters enabled(boolean), 5 cron values (minute, hour, domonth, month, doweek)
        """
        # assuming that none of hostid, metricid, entry_par are null. check?
        if type(entry_par)==type({}):
            entry = entry_par
        else:
            entry = OSGRSV.metricsFileMakeEntry(*entry_par)

        conf_file = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)
        if not os.path.isfile(conf_file):
            return False
        lines = open(conf_file).readlines()

        if not default:
            default = self.DEFAULT_CONFIG_ENTRY
        changed = False
        matching_index = -1
        oldentry = {}
        for i in range(len(lines)):
            if lines[i] and lines[i][0] == 'o':                    
                if lines[i].find(metricid) >= 0:
                    info = lines[i].split()
                    if not len(info)==7:
                        log.warning("Invalid matching line in metrics file %s:\n<%s>. Skipping." % (conf_file, lines[i]))                        
                        continue

                    # line matches and has 7 elements
                    oldentry = { 'enable': True }
                    if info[0] == 'off':
                        oldentry = { 'enable': False }
                    oldentry['CronMinute']     = info[2]
                    oldentry['CronHour']       = info[3]
                    oldentry['CronDayOfMonth'] = info[4]
                    oldentry['CronMonth']      = info[5]
                    oldentry['CronDayOfWeek']  = info[6]
                    matching_index = i
                    break

        # update entry dictionary
        if not oldentry:
            oldentry = default

        # to allow both missing values and none values 
        for j in entry.keys():
            if entry[j]:  # this will skip None but also a boolean set to False
                if entry[j] != oldentry[j]:
                    changed = True
                    oldentry[j] = entry[j]
        try:
            if entry['enable']==False and oldentry['enable']==True:
                oldentry['enable'] = False
                changed = True
        except KeyError:
            pass

        if oldentry['enable']:
            templ = "on   %-70s %-4s %-4s %-4s %-4s %-4s\n" 
        else:
            templ = "off  %-70s %-4s %-4s %-4s %-4s %-4s\n" 
        retv = templ % ( metricid, 
                         oldentry['CronMinute'], 
                         oldentry['CronHour'], 
                         oldentry['CronDayOfMonth'], 
                         oldentry['CronMonth'], 
                         oldentry['CronDayOfWeek'],
                     )

        if changed and matching_index != -1:
            lines[matching_index] = retv
        elif matching_index == -1:
            lines.append(retv)
            changed = True

        # write output file
        if changed:
            open(conf_file, 'w').write(''.join(lines))
            log.info("Metrics file updated: %s" % (conf_file,))

        return changed
    
    def _metricsFileRead(self, hostid):
        fname = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)
        return _read_metrics_file(fname)
    
    def _read_metrics_file(fname):
        # Parse metrics file
        # Columns - Enable | Probe@Metric | Cron Minute | Cron Hour | Cron Day of Month | Month | Day of Week
        metrics = {}
        log.debug("Re-using metrics config file for "+fname+"\n"+
                 " Existing settings like on/off and metric intervals will be used.\n"+
                 " Any new metrics found in probe set will be used with their default settings.")

        if os.path.isfile(fname):
            lines = open(fname).readlines()
            for line in lines:
                if line.startswith('on') or line.startswith('off'):
                    info = line.split()
                    if not len(info)==7:
                        log.warning("Invalid line in metrics file (%s).  Skipping." % (line,))
                        continue
                    metrics[info[1]] = { 'enable': 'on' }
                    if info[0] == 'off':
                        metrics[info[1]] = { 'enable': 'off' }
                    metrics[info[1]]['CronMinute'] =     info[2]
                    metrics[info[1]]['CronHour'] =       info[3]
                    metrics[info[1]]['CronDayOfMonth'] = info[4]
                    metrics[info[1]]['CronMonth'] =      info[5]
                    metrics[info[1]]['CronDayOfWeek'] =  info[6]

        return metrics
    _read_metrics_file = staticmethod(_read_metrics_file)

    def _metricsFileWrite(self, hostid, metrics):
        fname = os.path.join(self.metrics_loc, "%s_metrics.conf" % hostid)
        return _write_metrics_file(fname, metrics)
    
    def _write_metrics_file(fname, metrics):
        # Header for metrics configuration file
        outstr = "Enable | Probe\@Metric | Cron Minute | Cron Hour | Cron Day of Month | Cron Month | Cron Day of Week\n\n";

        # Print out the metrics.  It doesn't matter if they are sorted, but it 
        # might prevent the file from being written if it doesn't change?, since
        # python returns keys in semi-random order (hash)

        for metric in metrics.keys().sort():
            outstr += "%-4s %-70s %-4s %-4s %-4s %-4s %-4s\n" % ( metrics[metric]['enable'], 
                                                                  metric, 
                                                                  metrics[metric]['CronMinute'], 
                                                                  metrics[metric]['CronHour'], 
                                                                  metrics[metric]['CronDayOfMonth'], 
                                                                  metrics[metric]['CronMonth'], 
                                                                  metrics[metric]['CronDayOfWeek']
                                                              )                              
        # Don't register the HOST_metrics.conf files, we don't want to uninstall them
        open(fname, 'w').write(outstr)
        # TODO: Safe write i in Submitter
        #  _safe_write(fname, outstr);
    _write_metrics_file = staticmethod(_write_metrics_file)

    def start(self):
        """
        """
        #TODO: implement start
        # Start should start any jobs not running, even if other ones are

        # Make sure the jobs are not already in the queue
        if self.submitter.areProbesRunning():
            log.error("OSG-RSV jobs are already in the condor queue.")
            return
        return

    def stop(self):
        """stop() {
        """

        #TODO: implement stop

        if self.submitter.areProbesRunning():
            log.error("")
            return

        return
    
#for debugging
#commands to allow autocompletion
#import Probe
#mprobe = Probe.ProbeLocal()
#mrsv = OSGRSV()

def getStatus(probe, rsv, verbose=False):
    rsv = OSGRSV()
    mprobe.get
    rsv.metricsFileRetrieve()

def main():
    probe = ProbeLocal('cacert-expiry')
    if len(sys.argv)>1:
        rsv = OSGRSV(sys.argv[1])
    else:
        rsv = OSGRSV('test/vdtlocation')
    # turn on probe
    print "RSV server"
    print rsv.describe()
    
    probe.rsv = rsv    
    print "Probe"
    print probe.describe()
    
    #submitter = condorsubmitter.CondorSubmitter(rsv)
    
    #submitter.submit(probe)
    #submitter.list(probe)
    
if __name__ == '__main__':
    main()
