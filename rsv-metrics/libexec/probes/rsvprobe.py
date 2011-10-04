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
# re for config.ini parsing
import re

# Find the correct certificate directory
def get_ca_dir():
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

def get_config_val(req_key, req_section=None): 
  if os.getenv("OSG_LOCATION"):
    confini_fname =  os.path.join(os.getenv("OSG_LOCATION"), "osg/etc/config.ini")
  elif os.getenv("VDT_LOCATION"):
    confini_fname =  os.path.join(os.getenv("VDT_LOCATION"), "osg/etc/config.ini")
  else:    
    # NEW osg-configure code/API 
    from osg_configure.modules import configfile
    try:                                                                                                                                     
      config = configfile.read_config_files()                                                                                                 
    except IOError, e:                                                                                                                       
      # error_exit("Can't read configuration files: %s" % e) 
      return None
    if req_section:
      config.get(req_section, req_key)
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
  # config.ini parsing in perl probe
  # cat $1/osg/etc/config.ini | sed -e's/ //g'| grep '^group=OSG-ITB' &>/dev/null
  grid_type = get_config_val("group", "Site Information")
  if grid_type:
    if grid_type.strip() == "OSG-ITB":
      return 1
  return 0 

def get_temp_dir():
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
    "get list of file info objects for files of particular extensions"
    fileList = [os.path.normcase(f) for f in os.listdir(directory)]
    fileList = [os.path.join(directory, f) for f in fileList
                  if os.path.splitext(f)[1] in fileExtList]
    return fileList
 

# equivalent of which in python
# wrapper around commands.getstatusoutput (eventually timedcommand)
# Options parser

def process_command_line(extra_opts):
  return

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
  def __init__(self):
    self.status = OK
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
    pass

  def init(self, args):
    self.parseopt(args)

  def invalid_option_handler(self, msg):
    self.return_unknown("Invalid option. Aborting probe")      
    
  def get_version(self):
    ret = "Probe %s: version %s" % (self.name, self.version)
    return ret

  def get_usage(self):
    ret = "Usage: %s [opts] \n" % sys.argv[0]
    if self.help_message:
      ret += "%s\n" % self.help_message
    ret += "Optons:\n"
    ret += '\n'.join(self.options_help)
    return ret

  def get_metrics(self):
    ret = ""
    for m in self.supported_metrics:
      ret += m.describe()
    ret += "EOT\n"
    return ret

  def get_metric(self,  metric):
    for m in self.supported_metrics:
      if metric == m.name:
        return m
    return None

  def addopt(self, short_str, long_str, help_str):
    self.options_short += short_str
    self.options_long.append(long_str)
    self.options_help.append(help_str)

  def parseopt(self):
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

  def add_message(self, text):
    self.detailed.append("MSG: %s" % text)

  def add(self, what, text, exit_code):
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

  def add_ok(self, text, exit_code=-1):
    self.add(OK, text, exit_code)

  def add_warning(self, text, exit_code=-1):
    self.add(WARNING, text, exit_code)

  def add_critical(self, text, exit_code=-1):
    self.add(CRITICAL, text, exit_code)


  # add_unknown make no sense because it is exit condition

  def probe_return(self, what, text, exit_code=-1):
    self.add(what, text, exit_code)
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
    outstring = "RSV BRIEF RESULTS:\n"
    outstring += "%s\n" % status_dict[self.status]
    outstring += "%s\n" % self.summary
    outstring += '\n'.join(self.detailed)
    print outstring

  def print_wlcg_output(self):
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



  print_output = print_short_output


class RSVMetric:
  """A probe may heve one or more metrics. Each probe has:
stype - serviceType	 The service type that this probe works against
name - metricName	 The name of the metric
mtype - metricType	 This should be the constant value 'performance' or 'status'
dtype - dataType	 The type of the data: float, int, string, boolean (only 'performance' probes)
"""

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
    ret = "serviceType:	%s\nmetricName: %s\nmetricType: %s\n" % (self.stype, self.name, self.mtype)
    if self.mtype == 'performance':
      ret += "dataType: %s\n" % self.dtype # The type of the data: float, int, string, boolean
    return ret



