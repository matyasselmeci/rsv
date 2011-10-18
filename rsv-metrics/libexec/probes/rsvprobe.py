# First version Sep 2011, Marco Mambelli marco@hep.uchicago.edu
# Probes are specified in:
# https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
# Other useful URLS:
# https://twiki.grid.iu.edu/bin/view/ReleaseDocumentation/ValidateRSVProbes
# https://twiki.grid.iu.edu/bin/view/SoftwareTools/RsvControl
# https://twiki.grid.iu.edu/bin/view/MonitoringInformation/ConfigureRSV
# https://twiki.grid.iu.edu/bin/view/MonitoringInformation/InstallAndConfigureRsvAdvanced

import os
import sys
import commands
import getopt
import urllib
import urllib2
# re for config.ini parsing
import re


# Find the correct certificate directory
def get_ca_dir():
  "Find the CA certificate directory in both Pacman and RPM installations"
  if os.getenv("OSG_LOCATION"):
    cadir =  os.path.join(os.getenv("OSG_LOCATION"),"globus/TRUSTED_CA")
  elif os.getenv("VDT_LOCATION"):
    cadir =  os.path.join(os.getenv("VDT_LOCATION"),"globus/TRUSTED_CA")
  else:
    cadir = "/etc/grid-security/certificates"
  # check error (If CA dir does not exist) - differentiate message depending old/new
  return cadir

# Wrapper around commands (add timeout in the future)
def run_command(cmd, timeout=0, workdir=None):
  "Run an external command in the workdir directory. Timeout is not implemented yet."
  olddir=None
  if workdir: 
    olddir = os.getcwd()
    try:
      os.chdir(workdir)
    except OSError, e:
      return 1, "cd to workdir %s failed: %s" % (workdir, e)
  ec, out = commands.getstatusoutput(cmd)
  if olddir:
    os.chdir(olddir)
  return ec, out

def get_http_doc(url, quote=True):
  "Retrieve a document using HTTP and return all lines"
  if quote:
    u = url.split('/',3)
    u[-1] = urllib.quote(u[-1]) 
    u = '/'.join(u)
  else:
    u = url
  try:
    f = urllib2.urlopen(u)
  except urllib2.URLError:
    return None
  ret = f.readlines()
  return ret

def get_config_val(req_key, req_section=None): 
  "Get the value of an option from a section of OSG configuration in both Pacman and RPM installations."
  if os.getenv("OSG_LOCATION"):
    confini_fname =  os.path.join(os.getenv("OSG_LOCATION"), "osg/etc/config.ini")
  elif os.getenv("VDT_LOCATION"):
    confini_fname =  os.path.join(os.getenv("VDT_LOCATION"), "osg/etc/config.ini")
  else:    
    # NEW osg-configure code/API 
    from osg_configure.modules import configfile
    # necassary for exception raised by osg_configure
    import ConfigParser
    try:                                                                                                                                     
      config = configfile.read_config_files()                                                                                                 
    except IOError, e:                                                                                                                       
      return None
    if req_section:
      try:
        ret = config.get(req_section, req_key)
      except ConfigParser.NoSectionError:
        return None
    else:
      for section in config.sections():
        if config.has_option(section, req_key):
          return config.get(req_section, req_key)
      try:
        ret = config.defaults()[req_key]
      except KeyError:
        return None
    return ret
  # Continue old Pacman installation
  # Behaves like the old probe: no variable substitution in config.ini
  try:
    f = open(confini_fname)
  except OSError:
    # unable to find config.ini
    return None
  # comments at end of section line are OK
  # comment at end of key = val line are not OK
  SECTION = re.compile('^\s*\[\s*([^\]]*)\s*\]\s*(?:#.*)$')
  PARAM   = re.compile('^\s*(\w+)\s*=\s*(.*)\s*$')
  COMMENT = re.compile('^\s*#.*$')  
  if not req_section:
    in_section = True
  else:
    in_section = False
  for line in f:
    if COMMENT.match(line): continue
    if req_section:
      m = SECTION.match(line) 
      if m:
        section = m.groups()
        if section == req_section:
          in_section = True
        else:
          if in_section:
            # assume sections are all differents (same section not coming back later in file)
            break
          in_section = False
        continue
    if in_section:          
      m = PARAM.match(line)
      if m:
        key, val = m.groups()
        return val
      continue
    # malformed line (not matching comment, section header or key=val)
  # key not found (in section)
  return None  

# Returns the grid type:
# 1 for itb (OSG-ITB)
# 0 for production (OSG) or anything else
def get_grid_type():
  "Return 1 for OSG-ITB sites, 0 otherwise (production sites)"
  # Equivalent of config.ini parsing in perl probe:
  # cat $1/osg/etc/config.ini | sed -e's/ //g'| grep '^group=OSG-ITB' &>/dev/null
  grid_type = get_config_val("group", "Site Information")
  if grid_type:
    if grid_type.strip() == "OSG-ITB":
      return 1
  return 0 

def get_temp_dir():
  "Return the a temporary directory to store data across executions."
  # Should I create a directory per user?
  # /var/tmp/osgrsv, /tmp/osgrsv or at least /tmp (or "")?
  if os.path.isdir('/var/tmp/osgrsv'):
    return '/var/tmp/osgrsv'
  # Try /var/tmp first
  try:
    os.mkdir('/var/tmp/osgrsv')
  except OSError:
    pass
  if os.path.isdir('/var/tmp/osgrsv'):
    return '/var/tmp/osgrsv'
  # Try /tmp next
  try:
    os.mkdir('/tmp/osgrsv')
  except OSError:
    pass
  if os.path.isdir('/tmp/osgrsv'):
    return '/tmp/osgrsv'
  return '/tmp'

    #TORM old perl tempdir function
    #tempdir = os.path.join(rsvprobe.get_temp_dir(), 'osgrsv-ca') # tempdir("osgrsv-ca`-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    #try:
    #  os.mkdir(tempdir)
    #except:
    #  if not os.path.isdir(tempdir):
    #    self.return_unknown("Unable to create temporary directory: %s" % tempdir)
 
 
def _listDirectory(directory, fileExtList):                                         
    "Get the list of file info objects for files of particular extensions"
    fileList = [os.path.normcase(f) for f in os.listdir(directory)]
    fileList = [os.path.join(directory, f) for f in fileList
                  if os.path.splitext(f)[1] in fileExtList]
    return fileList
 

# TODO: equivalent of which in python to help with external commands

# Valid probe status (according to specification)
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

status_dict = {
  OK:"OK",
  WARNING:"WARNING",
  CRITICAL:"CRITICAL",
  UNKNOWN:"UNKNOWN"
  }

status_list = status_dict.keys()
status_val_list = status_dict.values()

class RSVProbe:
  """Base class for RSV probes. Probes are executables performing tests and returning a specific output.
A single probe can run multiple tests, metrics.
Possible output statuses are: 
OK - the test was successful
WARNING - the probe found some problems demanding attention (and raised a warning)
CRITICAL - the service tested is not passing the test
UNKNOWN - the probe was unable to run
The behavior is specified in a WLCG document:
https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
"""
  def __init__(self):
    self.status = OK
    self.select_wlcg_output = False
    self.summary = ""
    self.detailed = []
    self.warning_count = 0
    self.critical_count = 0
    self.ecode = 0
    self.detailsDataTrim = False
    self.detailsDataMaxLength = -1
    self.supported_metrics = []
    self.metric = None # Requested metric
    ## options and default values
    self.host = "localhost"
    self.uri = None
    self.verbose = False
    self.options_short = 'm:lu:h:t:x:V?v'
    self.options_long = ['metric=', 
      'list', 
      'uri=', 'host=',
      'timeout=', 'proxy=',
      'version',
      'help', 'verbose']
    self.options_help = ['-m,--metric METRIC_NAME \twhich metric output is desired',
      '-l,--list \tlist all the metrics suppotrted by the probe',
      '-u,--uri URI \tURI passed to the metric',
      '-h,--host HOST \tHOST passed to the metric',
      '-t,--timeout TIMEOUT \tset a timeout (int) for the probe execution (NOT SUPPORTED)',
      '-x,--proxy CERTFILE \tset the user proxy to CERTFILE (Default: /tmp/x509up_u500) (NOT SUPPORTED)',
      '-V,--version \tprint probe version and exit',
      '-?,--help \t print help message and exit',
      '-v,--verbose \tverbose output']
    self.help_message = ""
  #@staticmethod
  #def _listDirectory(directory, fileExtList):                                         
  #  "get list of file info objects for files of particular extensions"
  #  fileList = [os.path.normcase(f) for f in os.listdir(directory)]           
  #  fileList = [os.path.join(directory, f) for f in fileList
  #                if os.path.splitext(f)[1] in fileExtList]
  #  return fileList
  
  def run(self):
    "Probe execution - replaced by the specific probes"
    pass

  def invalid_option_handler(self, msg):
    "By default a probe aborts if an unvalid option is received. This can be changed replacing this handler."
    self.return_unknown("Invalid option. Aborting probe")      
    
  def get_version(self):
    "Returns the probe's name and version."
    ret = "Probe %s: version %s" % (self.name, self.version)
    return ret

  def get_usage(self):
    "Usage string."
    ret = "Usage: %s [opts] \n" % sys.argv[0]
    if self.help_message:
      ret += "%s\n" % self.help_message
    ret += "Optons:\n"
    ret += '\n'.join(self.options_help)
    return ret

  def get_metrics(self):
    "Returns a list of the supported metrics, described according to specification."
    ret = ""
    for m in self.supported_metrics:
      ret += m.describe()
    ret += "EOT\n"
    return ret

  def get_metric(self,  metric_name):
    "Returns the metric named. None if it is not supported by the probe."
    for m in self.supported_metrics:
      if metric_name == m.name:
        return m
    return None

  def addopt(self, short_str, long_str, help_str):
    "Helper function to add options supported by subclasses."
    self.options_short += short_str
    self.options_long.append(long_str)
    self.options_help.append(help_str)

  def parseopt(self):
    """Parse the command line options and arguments. Options and parameters are retrieved from sys.argv[1:], 
validated and processed with getopt, using self.options_short and self.options_long. Actions on some options are taken.
Finally all processed options and reminder are returned to daisy chain the processing in subclasses.
Define parseopt(self) and first call the one of the parent 'options, remainder = rsvprobe.RSVProbe.parseopt(self)'
then process the options as desired and at the end return all of them for processing in subclasses: 'return options, remainder'
"""
    # using sys.argv, no real usecase to pass different args
    try:
      options, remainder = getopt.getopt(sys.argv[1:], self.options_short, self.options_long)
    except getopt.GetoptError, e:
      #invalid option
      self.return_unknown("Invalid option (%s). Aborting probe" % e)      
    for opt, arg in options:
      if opt in ('-o', '--output'):
        output_filename = arg
      elif opt in ('-v', '--verbose'):
        self.verbose = True
      elif opt in ('-V', '--version'):
        print self.get_version()
        sys.exit(0)
      elif opt in ('-?', '--help'):
        print self.get_usage()
        sys.exit(0)
      elif opt in ('-l', '--list'):
        print self.get_metrics()
        sys.exit(0)
      elif opt in ('-m', '--metric'):
        if not self.get_metric(arg):
          self.return_unknown("Unsupported metric %s. Aborting probe" % arg)      
        self.metric = arg
      elif opt in ('-h', '--host'):
        self.host = arg
      elif opt in ('-u', '--uri'):
        self.uri = arg
      elif opt in ('-x', '--proxy', '-t', '--timeout'):
        # TODO: options not implemented
        pass
    return options, remainder 

  def out_debug(self, text):
    "Debug messages are sent to stderr."
    # output the text to stderr
    #print >> sys.stderr, text
    sys.stderr.write("%s\n" % test)

  def add_message(self, text):
    "Add a message to the probe detailed output. The status is not affected."
    self.detailed.append("MSG: %s" % text)

  def add(self, what, text, exit_code):
    "All the add_... functions add messages to the probe output and affect its return status."
    if not what in status_list:
      self.return_unknown("Invalid probe status: %s" % what, 1)
    self.detailed.append(status_dict[what]+": %s" % text)
    if what == WARNING:
      self.warning_count += 1
    elif what == CRITICAL:
      self.critical_count += 1 
    # Change only status code to warning, only if an error has not been recorded   
    if what >= self.status: # and what != UNKNOWN:
      if what == UNKNOWN and self.status != OK:
        self.detailed.append(status_dict[what]+": bad probe. Status UNKNOWN should never happen after the probe has been evaluated and returned CRITICAL/WARNING")
      self.status = what
      self.ecode = exit_code
      self.summary = status_dict[what]+": %s" % text

  def trim_detailed(self, number=1):
    "detailed normally contains a copy of te summary, trim_detailed allows to remove it"
    self.detailed = self.detailed[:-number]

  def add_ok(self, text, exit_code=-1):
    self.add(OK, text, exit_code)

  def add_warning(self, text, exit_code=-1):
    self.add(WARNING, text, exit_code)

  def add_critical(self, text, exit_code=-1):
    self.add(CRITICAL, text, exit_code)

  # add_unknown makes no sense because UNKNOWN is an exit condition

  def probe_return(self, what, text, exit_code=-1):
    "All the return_... functions add messages to the probe output, affect the status and terminate the probe"
    self.add(what, text, exit_code)
    self.trim_detailed()
    self.print_output()
    sys.exit(self.ecode)

  def return_ok(self, text):
    self.probe_return(OK, text, 0)

  def return_critical(self, text, exit_code=1):
    self.probe_return(CRITICAL, text, exit_code)

  def return_warning(self, text, exit_code=-1):
    self.probe_return(WARNING, text, exit_code)

  def return_unknown(self, text, exit_code=-1):
    self.probe_return(UNKNOWN, text, exit_code)

  def print_short_output(self):
    "Print the probe output in the short format (RSV short format)"
    outstring = "RSV BRIEF RESULTS:\n"
    outstring += "%s\n" % status_dict[self.status]
    outstring += "%s\n" % self.summary
    outstring += '\n'.join(self.detailed)
    print outstring

  def print_wlcg_output(self):
    "Print the probe output in the extended format (WLCG standard)"
    metric = self.get_metric(self.metric)
    out_detailed = '\n'.join(self.detailed)
    ## Trim detailsData if it is too long
    if self.detailsDataTrim and len(out_detailed) > detailsDataMaxLength:
      out_detailed = out_detailed[0:detailsDataMaxLength] + "\n... Truncated ...\nFor more details, use --verbose 3"
    ## Append proxy warning if applicable
    #self.append_proxy_validity_warning()

    ## No Gratia record 
    ## No local time zone

    ## Only handles status metrics as of now (and no checking)
	
    ## Print metric in WLCG standard output format to STDOUT; 
    ##  detailsData has to be last field before EOT
    outstring = "metricName: %s\n" + \
	    "metricType: %s\n" + \
	    "timestamp: %s\n" % (metric.name, metric.mtype, self.timestamp);
    #optional output
    if self.vo_name:
      outstring += "voName: %s\n" % self.vo_name
    # siteName is used for Pigeon Tools
    if self.site_name:
      outstring += "siteName: %s\n" % self.site_name
    # status
    outstring += "metricStatus: %s\n" + \
	    "serviceType: %sn" % (status_dict[self.status], metric.stype);
    # not menitoning host/URI
    outstring += "summaryData: %s\n" % self.summary
    outstring += "detailsData: %s\n" % out_detailed
    outstring += "EOT\n";
    print outstring;
    ## Print to file missing

  def print_output(self):
    "Select the output format"
    if self.select_wlcg_output:
      self.print_wlcg_output()
    else:
      self.print_short_output()


class RSVMetric:
  """A probe may heve one or more metrics. Each probe has:
stype - serviceType	 The service type that this probe works against
name - metricName	 The name of the metric
mtype - metricType	 This should be the constant value 'performance' or 'status'
dtype - dataType	 The type of the data: float, int, string, boolean (only 'performance' probes)
"""
  # Metric type constants
  STATUS='status'
  PERFORMANCE='performance'

  def __init__(self, stype, name, mtype=STATUS, dtype=None):
    self.stype = stype
    self.name = name
    if not mtype in [RSVMetric.STATUS, RSVMetric.PERFORMANCE]:
      raise ValueError("Invalid metricType")
    self.mtype = mtype
    self.dtype = dtype
 
  def describe(self):
    "Return a metric description in the standard WLCG format"
    ret = "serviceType:	%s\nmetricName: %s\nmetricType: %s\n" % (self.stype, self.name, self.mtype)
    if self.mtype == 'performance':
      ret += "dataType: %s\n" % self.dtype # The type of the data: float, int, string, boolean
    return ret


