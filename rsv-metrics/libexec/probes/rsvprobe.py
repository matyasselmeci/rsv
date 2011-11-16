# First version Sep 2011, Marco Mambelli marco@hep.uchicago.edu
"""Base class for RSV probes
Probes are specified in:
https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
Other useful URLS:
https://twiki.grid.iu.edu/bin/view/ReleaseDocumentation/ValidateRSVProbes
https://twiki.grid.iu.edu/bin/view/SoftwareTools/RsvControl
https://twiki.grid.iu.edu/bin/view/MonitoringInformation/ConfigureRSV
https://twiki.grid.iu.edu/bin/view/MonitoringInformation/InstallAndConfigureRsvAdvanced
"""

import os
import sys
import getopt
import time 
import socket   
import urllib
import urllib2
import urlparse
# root is not a supported schema: http://docs.python.org/library/urlparse.html
# Customization to fix root URI parsing (else netloc was not used) 
def urlparse_register_scheme(scheme):
  """Adds a scheme so that the uri will then be treated as http-like 
and will correctly return the path, fragment, username/password, ...
fragment, netloc, params, query, relative
"""
  for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
    getattr(urlparse, method).append(scheme)
urlparse_register_scheme('root')

# re for config.ini parsing
import re

# Add the current directory to the path:
# auxiliary files are staged in the same directory during remote execution
import sys
if not sys.path[0] == ".":
  sys.path.insert(0, ".")
try:
  import timed_command
except ImportError:
  import commands
  timed_command = None

# Wrapper around commands (add timeout in the future)
def run_command(cmd, timeout=0, workdir=None):
  "Run an external command in the workdir directory. Timeout is available only if timed_command is available."
  olddir = None
  if workdir: 
    olddir = os.getcwd()
    try:
      os.chdir(workdir)
    except OSError, e:
      return 1, "cd to workdir %s failed: %s" % (workdir, e)
  if timed_command:
    ec, elapsed, out, err = timed_command.timed_command(cmb, timeout)
    outerr = out + err
  else:      
    ec, outerr = commands.getstatusoutput(cmd)
  if olddir:
    os.chdir(olddir)
  return ec, outerr

# Test connection to host:port
def ping(host, port="80"):
  "Check if able to connect to HOST on the specified PORT (80 as default). Return True/False and a message."
  # Simple alive test
  # There are more complex implementation of ping running the command in a subprocess, 
  # as python function, or within a library: 
  #  http://stackoverflow.com/questions/316866/ping-a-site-in-python
  #  http://www.g-loaded.eu/2009/10/30/python-ping/
  #  http://code.google.com/p/pycopia/
  #  https://github.com/jedie/python-ping/blob/master/ping.py
  if not port:
    # None, "", 0 mapped to the default port 80
    port = 80
  soc = socket.socket()
  soc.settimeout(180.0)
  try:
    soc.connect((host, int(port)))
  except Exception, e:
    #return False, "Connection to %s:%s failed. Exception is: %s" % (host, port, e)
    return False, "%s" % e
  soc.shutdown(socket.SHUT_RDWR)
  soc.close()
  return True, "Connection successfull"

# Find the correct certificate directory
def get_ca_dir():
  "Find the CA certificate directory in both Pacman and RPM installations"
  cadirlt = []
  if os.getenv("OSG_LOCATION"):
    cadirlt.append(os.path.join(os.getenv("OSG_LOCATION"),"globus/TRUSTED_CA"))
  if os.getenv("VDT_LOCATION"):
    cadirlt.append(os.path.join(os.getenv("VDT_LOCATION"),"globus/TRUSTED_CA"))
  if os.getenv("GLOBUS_LOCATION"):
    cadirlt.append(os.path.join(os.getenv("GLOBUS_LOCATION"),"TRUSTED_CA"))
  cadirlt.append("/etc/grid-security/certificates")
  for cadir in cadirlt:
    if os.path.isdir(cadir):
      return cadir
  # check error (If CA dir does not exist) - differentiate message depending old/new
  return "/etc/grid-security/certificates"

def get_http_doc(url, quote=True):
  "Retrieve a document using HTTP and return all lines"
  if quote:
    u = url.split('/', 3)
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
  "Get the value of an option from a section of OSG configuration in both Pacman and RPM installations. Return None if option is not found."
  confini_fname = None
  confini_fname_list = []
  if os.getenv("OSG_LOCATION"):
    confini_fname_list.append(os.path.join(os.getenv("OSG_LOCATION"), "osg/etc/config.ini"))
  if os.getenv("VDT_LOCATION"):
    confini_fname_list.append(os.path.join(os.getenv("VDT_LOCATION"), "osg/etc/config.ini"))
  for i in confini_fname_list:
    if os.path.isfile(i):
      confini_fname = i
  if not confini_fname:
    # Assume new OSG 3    
    # Using NEW osg-configure code/API 
    try:
      from osg_configure.modules import configfile
    except:
      return None
    # necassary for exception raised by osg_configure
    import ConfigParser
    try:
      config = configfile.read_config_files() 
    except IOError:
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
  except (OSError, IOError):
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

def which(program):
  "Python replacement for which"
  def is_exe(fpath):
    "is a regular file and is executable"
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
  fpath, fname = os.path.split(program)
  if fpath:
    if is_exe(program):
      return program
  else:
    for path in os.environ["PATH"].split(os.pathsep):
      exe_file = os.path.join(path, program)
      if is_exe(exe_file):
        return exe_file
  return None

def list_directory(directory, file_ext_list):                                         
  "Get the list of file info objects for files of particular extensions"
  filelist = [os.path.normcase(f) for f in os.listdir(directory)]
  filelist = [os.path.join(directory, f) for f in filelist
               if os.path.splitext(f)[1] in file_ext_list]
  return filelist
 
def uri2host(uri):
  "Return the host part of a URI or ''. URI defined as [scheme://]host[:port][/[rest]]"
  components = urlparse.urlparse(uri)
  try:
    ret = components.hostname
    if not ret:
      return ""
    return ret
  except AttributeError:
    # urlparse attributes added in python 2.5
    ret = components[1].lower()
    i = ret.find(':')
    if i < 0:
      return ret
    return ret[:i]

def uri2port(uri, default=None):
  "Return the port (int) part of a URI or default/None. URI defined as [scheme://]host[:port][/[rest]]"
  components = urlparse.urlparse(uri)
  try:
    ret = components.port
    if ret == None:
      return default
    return ret
  except AttributeError:
    # urlparse attributes added in python 2.5
    ret = components[1]
    i = ret.rfind(':')
    if i < 0:
      return default
    try:
      ret = int(ret[i+1:])
    except ValueError:
      return default
    return ret

def inlist(elements, checklist):
  "Return True if at least one of the elements is in the checklist, False otherwise."
  # Alt, not empty intersection: [i for i in elements if i in checklist]
  for i in elements:
    if i in checklist:
      return True
  return False


# Valid probe status (according to specification)
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

STATUS_DICT = {
  OK:"OK",
  WARNING:"WARNING",
  CRITICAL:"CRITICAL",
  UNKNOWN:"UNKNOWN"
  }

STATUS_LIST = STATUS_DICT.keys()
STATUS_VAL_LIST = STATUS_DICT.values()

DEFAULT_ECODE = -2

class RSVProbe:
  """Base class for RSV probes. Probes are executables performing tests and returning a specific output.
A single probe can run multiple tests, metrics.
Possible output statuses are: 
OK - the test was successful
WARNING - the probe found some problems demanding attention (and raised a warning)
CRITICAL - the service tested is not passing the test
UNKNOWN - the probe was unable to run
The return code from the probe can take on either one of two values, and should be syncronized with the value provided in metricStatus
0 If the probe could gather the metric successfully - metricStatus is OK, WARNING, CRITICAL.
1. The probe could not gather the metric successfully. metricStatus must be UNKNOWN. More details on the problem can be in the summaryData and detailsData fields of the metric data.
The behavior is specified in a WLCG document:
https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
"""
  HOST_OPTIONS = ('-h','--host')
  URI_OPTIONS = ('-u', '--uri')

  def __init__(self):
    self.name = "Base probe"
    self.version = "1.0"
    self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) # String ISO8601 UTC time
    self.status = OK
    self.select_wlcg_output = False
    self.summary = ""
    self.detailed = []
    self.warning_count = 0
    self.critical_count = 0
    self.ecode = DEFAULT_ECODE
    self.detailsDataTrim = False
    self.detailsDataMaxLength = -1
    self.force_wlcg_ecode = False
    self.supported_metrics = []
    self.metric = None # Requested metric
    self.is_local = True
    self.localhost = socket.gethostname()
    self.vo_name = None
    ## options and default values
    self.host = self.localhost
    self.uri = None
    # Timeout handling is left to the probe
    self.timeout = 0
    self.verbose = False
    self.output_filename = None
    self.x509proxy = "/tmp/x509up_u%s" % os.getuid()
    self.x509usercert = None
    self.x509userkey = None
    self.options_short = 'm:lu:h:t:x:V?v'
    self.options_long = ['metric=', 
      'list', 
      'uri=', 'host=',
      'timeout=', 
      'proxy=', 'usercert=', 'userkey=',
      'output-type=',
      'version',
      'help', 'verbose']
    self.options_help = ['-m,--metric METRIC_NAME \twhich metric output is desired',
      '-l,--list \tlist all the metrics suppotrted by the probe',
      '-u,--uri URI \tURI passed to the metric (host or hierarchical URI as in rfc2396/3986)',
      '-h,--host HOST \tHOST passed to the metric (hostname[:port])',
      '-t,--timeout TIMEOUT \tset a timeout (int, seconds) for the probe execution',
      '-x,--proxy CERTFILE \tset the user proxy to CERTFILE (Default: /tmp/x509up_uID with ID=uid) ',
      '--usercert CERTFILE \tset user x509 certificate to CERTFILE',
      '--userkey KEYFILE \tset user x509 key to KEYFILE',
      '--output-type TYPE \t output TYPE (short, wlcg - Default:short)',
      '-V,--version \tprint probe version and exit',
      '-?,--help \t print help message and exit',
      '-v,--verbose \tverbose output']
    self.help_message = ""

  def run(self):
    "Probe execution - replaced by the specific probes"
    pass

  def atexit(self):
    "Function invoked before exiting"
    pass

  def invalid_option_handler(self, msg):
    "By default a probe aborts if an unvalid option is received. This can be changed replacing this handler."
    self.return_unknown("Invalid option (%s). Aborting probe" % msg)      
    
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
optlist is a list of all options encountered (all first elements of options touples).
Finally all processed options optlist, and reminder are returned to daisy chain the processing in subclasses.
Define parseopt(self) and first call the one of the parent 'options, optlist, remainder = rsvprobe.RSVProbe.parseopt(self)'
then process the options as desired and at the end return all of them for processing in subclasses: 'return options, optlist, remainder'
"""
    # using sys.argv, no real usecase to pass different args
    try:
      options, remainder = getopt.getopt(sys.argv[1:], self.options_short, self.options_long)
    except getopt.GetoptError, emsg:
      #invalid option
      self.invalid_option_handler(emsg) 
    optlist = [i[0] for i in options]
    for opt, arg in options:
      if opt in ('-o', '--output'):
        self.output_filename = arg
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
          self.return_unknown("Unsupported metric %s. Use --list to list supported metrics. Aborting probe" % arg)      
        self.metric = arg
      elif opt in RSVProbe.HOST_OPTIONS: 
        self.host = arg
        if not inlist(RSVProbe.URI_OPTIONS, optlist):
          self.uri = arg
      elif opt in RSVProbe.URI_OPTIONS:
        self.uri = arg
        if not inlist(RSVProbe.HOST_OPTIONS, optlist):
          self.host = uri2host(arg)
      elif opt in ('-x', '--proxy'):
        self.x509proxy = arg
      elif opt == '--usercert':
        self.x509usercert = arg
      elif opt == '--userkey':
        self.x509userkey = arg
      elif opt in ('-t', '--timeout'):
        self.timeout = arg
      elif opt == '--output-type':
        if arg.lower() == 'wlcg':
          self.select_wlcg_output = True
        elif not arg.lower() == 'short':
          self.return_unknown("Unsupported output-type: %s. Use --help to list valid options (short,wlcg). Aborting probe" % arg) 
      # Consistency checking
      # probe will check for uri/host if the probe is not local 
    return options, optlist, remainder 

  def out_debug(self, text):
    "Debug messages are sent to stderr."
    # output the text to stderr
    #print >> sys.stderr, text
    sys.stderr.write("%s\n" % text)

  def add_message(self, text):
    "Add a message to the probe detailed output. The status is not affected."
    self.detailed.append("MSG: %s" % text)

  def add(self, what, text, exit_code):
    """All the add_... functions add messages to the probe output and affect its return status. 
Retuns True if status and summary have been updated, False otherwise.
"""
    if not what in STATUS_LIST:
      self.return_unknown("Invalid probe status: %s" % what, 1)
    self.detailed.append(STATUS_DICT[what]+": %s" % text)
    if what == WARNING:
      self.warning_count += 1
    elif what == CRITICAL:
      self.critical_count += 1 
    # Change only status code to warning, only if an error has not been recorded   
    if what >= self.status: # and what != UNKNOWN:
      if what == UNKNOWN and self.status != OK:
        self.detailed.append(STATUS_DICT[what]+
          ": bad probe. Status UNKNOWN should never happen after the probe has been evaluated and returned CRITICAL/WARNING")
      self.status = what
      self.ecode = exit_code
      self.summary = STATUS_DICT[what]+": %s" % text
      return True
    return False

  def trim_detailed(self, number=1):
    "detailed normally contains a copy of te summary, trim_detailed allows to remove it"
    self.detailed = self.detailed[:-number]

  def add_ok(self, text, exit_code=DEFAULT_ECODE):
    "OK message"
    self.add(OK, text, exit_code)

  def add_warning(self, text, exit_code=DEFAULT_ECODE):
    "WARNING mesage"
    self.add(WARNING, text, exit_code)

  def add_critical(self, text, exit_code=DEFAULT_ECODE):
    "CRITICAL message"
    self.add(CRITICAL, text, exit_code)

  # add_unknown makes no sense because UNKNOWN is an exit condition

  def probe_return(self, what, text, exit_code=DEFAULT_ECODE):
    "All the return_... functions add messages to the probe output, affect the status and terminate the probe"
    updated = self.add(what, text, exit_code)
    if updated:
      self.trim_detailed()
    self.print_output()
    self.atexit()
    if self.force_wlcg_ecode:
      if self.status == UNKNOWN:
        self.ecode = 1
      else:
        self.ecode = 0
    sys.exit(self.ecode)

  def return_ok(self, text):
    "return OK"
    self.probe_return(OK, text, 0)

  def return_critical(self, text, exit_code=0):
    "return CRITICAL"
    self.probe_return(CRITICAL, text, exit_code)

  def return_warning(self, text, exit_code=0):
    "return WARNING"
    self.probe_return(WARNING, text, exit_code)

  def return_unknown(self, text, exit_code=1):
    "return UNKNOWN"
    self.probe_return(UNKNOWN, text, exit_code)

  def print_short_output(self):
    "Print the probe output in the short format (RSV short format)"
    outstring = "RSV BRIEF RESULTS:\n"
    outstring += "%s\n" % STATUS_DICT[self.status]
    outstring += "%s\n" % self.summary
    outstring += "%s\n" % self.timestamp
    outstring += '\n'.join(self.detailed)
    if self.output_filename:
      try:
        #with open(self.output_filename, 'w') as f:
        #  f.write(outstring)
        open(self.output_filename, 'w').write(outstring)
      except IOError:
        print "UNKNOWN: Unable to open output file: %s" % self.output_filename
    else:
      print outstring

  def print_wlcg_output(self):
    "Print the probe output in the extended format (WLCG standard)"
    metric = self.get_metric(self.metric)
    if not metric:
      metric = EMPTY_METRIC
    out_detailed = '\n'.join(self.detailed)
    ## Trim detailsData if it is too long
    if self.detailsDataTrim and len(out_detailed) > self.detailsDataMaxLength:
      out_detailed = out_detailed[0:self.detailsDataMaxLength]
      out_detailed += "\n... Truncated ...\nFor more details, use --verbose"
    ## Append proxy warning if applicable
    #self.append_proxy_validity_warning()

    ## No Gratia record 
    ## No local time zone

    ## Only handles status metrics as of now (and no checking)
	
    ## Print metric in WLCG standard output format to STDOUT; 
    ##  detailsData has to be last field before EOT
    outstring = "metricName: %s\n" % metric.name
    outstring += "metricType: %s\n" % metric.mtype
    outstring += "timestamp: %s\n" % self.timestamp
    # Locality information
    if self.is_local:
      outstring += "hostName: %s\n" % self.localhost
    else:
      outstring += "serviceURI: %s\n" % self.uri
      outstring += "gatheredAt: %s\n" % self.localhost
    #optional output
    if self.vo_name:
      outstring += "voName: %s\n" % self.vo_name
    # siteName is used for Pigeon Tools
    if self.host:
      outstring += "siteName: %s\n" % self.host
    # status
    outstring += "metricStatus: %s\nserviceType: %s\n" % (STATUS_DICT[self.status], metric.stype)
    # not menitoning host/URI
    outstring += "summaryData: %s\n" % self.summary
    outstring += "detailsData: %s\n" % out_detailed
    outstring += "EOT\n"
    if self.output_filename:
      try:
        open(self.output_filename, 'w').write(outstring)
      except IOError:
        print "UNKNOWN: Unable to open output file: %s" % self.output_filename
    else:
      print outstring

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
  # Spec version, see https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
  DEFAULT_VERSION = "0.91" 
  # Metric type constants
  STATUS = 'status'
  PERFORMANCE = 'performance'

  def __init__(self, stype, name, mtype=STATUS, dtype=None):
    self.stype = stype
    self.name = name
    if not mtype in [RSVMetric.STATUS, RSVMetric.PERFORMANCE]:
      raise ValueError("Invalid metricType")
    self.mtype = mtype
    self.dtype = dtype
    ## What version of the WLCG specification does this probe conform to?  
    self.probe_spec_version = RSVMetric.DEFAULT_VERSION
    self.enable_by_default = False
 
 
  def describe(self):
    "Return a metric description in the standard WLCG format"
    ret = "serviceType:	%s\nmetricName: %s\nmetricType: %s\n" % (self.stype, self.name, self.mtype)
    if self.mtype == 'performance':
      ret += "dataType: %s\n" % self.dtype # The type of the data: float, int, string, boolean
    return ret

EMPTY_METRIC = RSVMetric('UNKNOWN', 'UNKNOWN')
