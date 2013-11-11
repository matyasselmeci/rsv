#!/usr/bin/python

# System libraries
import os
import re
import sys
import logging
import ConfigParser
from pwd import getpwnam

# RSV libraries
import Host
import Metric
import Results
import Sysutils
import Consumer

# Define base system paths
OPENSSL_EXE = "/usr/bin/openssl"
CONFIG_DIR = os.path.join("/", "etc", "rsv")
LIBEXEC_DIR = os.path.join("/", "usr", "libexec", "rsv")
LOG_DIR = os.path.join("/", "var", "log", "rsv")
CONSUMER_CONFIG_FILE = os.path.join(CONFIG_DIR, "consumers.conf")

class RSV:
    """ Class to load and store configuration information about this install
    of RSV.  This could be replaced with a singleton pattern to reduce the need
    to pass the instance around in functions. """

    def __init__(self, options):
        """ Constructor.  Take the command line options as a parameter """
        self.options = options

        # Initialize some instance vars
        self.consumer_config = None
        self.config = None
        self.logger = None
        self.proxy = None

        # For any messages that won't go through the logger
        self.quiet = 0
        if self.options.verbose == 0:
            self.quiet = 1

        # Instantiate our helper objects
        self.sysutils = Sysutils.Sysutils(self)
        self.results  = Results.Results(self, options)

        # Setup the logger
        self.init_logging(self.options.verbose)

        # Setup the initial configuration
        self.setup_config()
        self.setup_consumer_config()
        return


    def setup_config(self):
        """ Load configuration """
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str # make keys case-insensitive
        defaults = get_rsv_defaults()
        if defaults:
            for section in defaults.keys():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                    
                for item in defaults[section].keys():
                    self.config.set(section, item, defaults[section][item])

        self.load_config_file(self.config, os.path.join(CONFIG_DIR, "rsv.conf"), required=1)
        return


    def setup_consumer_config(self):
        """ Load configuration """
        self.consumer_config = ConfigParser.RawConfigParser()
        self.consumer_config.optionxform = str # make keys case-insensitive
        self.load_config_file(self.consumer_config, CONSUMER_CONFIG_FILE, required=0)
        return


    def load_config_file(self, config_obj, config_file, required):
        """ Parse a configuration file in INI form. """

        self.log("INFO", "Reading configuration file " + config_file)

        if not os.path.exists(config_file):
            if required:
                self.log("ERROR", "missing required configuration file '%s'" % config_file)
                sys.exit(1)
            else:
                self.log("INFO", "configuration file does not exist '%s'" % config_file, 4)
                return

        try:
            config_obj.read(config_file)
        except ConfigParser.ParsingError, err:
            self.log("CRITICAL", err)
            sys.exit(1)

        return


    
    def get_installed_metrics(self):
        """ Return a list of installed metrics """
        metrics_dir = os.path.join(LIBEXEC_DIR, "metrics")
        try:
            files = os.listdir(metrics_dir)
            files.sort()
            metrics = []
            for entry in files:
                # Each metric should be something like org.osg.
                # This pattern will specifically not match '.', '..', '.svn', etc
                if re.search("\w\.\w", entry):
                    metrics.append(entry)
            return metrics
        except OSError, err:
            self.log("ERROR", "The metrics directory (%s) could not be accessed.  Error msg: %s" %
                     (metrics_dir, err))
            return []


    def get_installed_consumers(self):
        """ Return a list of installed consumers """
        consumers_dir = os.path.join(LIBEXEC_DIR, "consumers")
        try:
            files = os.listdir(consumers_dir)
            files.sort()
            consumers = []
            for entry in files:
                if re.search("-consumer$", entry):
                    consumers.append(entry)
            return consumers
        except OSError, err:
            self.log("ERROR", "The consumers directory (%s) could not be accessed.  Error msg: %s" %
                     (consumers_dir, err))
            return []
        
        
    def get_metric_info(self):
        """ Return a dictionary with information about each installed metric """

        metrics = {}
        for metric in self.get_installed_metrics():
            metrics[metric] = Metric.Metric(metric, self)

        return metrics



    def get_hosts(self):
        """ Return a list of hosts that have configuration files """

        special_config_files = ["rsv.conf", "consumers.conf", "rsv-nagios.conf"]

        conf_dir = CONFIG_DIR
        try:
            config_files = os.listdir(conf_dir)
            hosts = []
            for config_file in config_files:
                # Somewhat arbitrary pattern, but it won't match '.', '..', or '.svn'
                if re.search("\.conf$", config_file) and config_file not in special_config_files:
                    host = re.sub("\.conf$", "", config_file)
                    hosts.append(host)
            return hosts
        except OSError:
            # todo - check for permission problem
            self.log("ERROR", "The conf directory does not exist (%s)" % conf_dir)



    def get_host_info(self):
        """ Return a list containing one Host instance for each configured host """

        hosts = []
        for host in self.get_hosts():
            hosts.append(Host.Host(host, self))

        return hosts



    def init_logging(self, verbosity):
        """ Initialize the logger """

        self.logger = logging.getLogger()
        if verbosity == 0:
            self.logger.setLevel(logging.CRITICAL)
        elif verbosity == 1:
            self.logger.setLevel(logging.WARNING)
        elif verbosity == 2:
            self.logger.setLevel(logging.INFO)
        elif verbosity == 3:
            self.logger.setLevel(logging.DEBUG)

        stream = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        stream.setFormatter(formatter)

        self.logger.addHandler(stream)


    def log(self, level, message, indent=0):
        """ Interface to logger. Accepted logging levels are (case insensitive):
        debug, info, warning, error, critical.
        """
        level = level.lower()

        if indent > 0:
            message = " "*indent + message

        if level == "debug":
            self.logger.debug(message)
        elif level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "critical":
            self.logger.critical(message)
        else:
            self.logger.warning("Invalid level (%s) passed to RSV.log." % level)
            self.logger.warning(message)

    def echo(self, message, indent=0):
        """ Print a message unless verbosity level==0 (quiet) """
        
        if self.quiet:
            return
        else:
            if indent > 0:
                message = " "*indent + message

            print message
        

    def get_metric_log_dir(self):
        """ Return the directory to store condor log/out/err files for metrics """
        return os.path.join(LOG_DIR, "metrics")


    def get_consumer_log_dir(self):
        """ Return the directory to store condor log/out/err files for consumers """
        return os.path.join(LOG_DIR, "consumers")


    def get_user(self):
        """ Return the user defined in rsv.conf """
        try:
            return self.config.get("rsv", "user")
        except ConfigParser.NoOptionError:
            self.log("ERROR", "'user' not defined in rsv.conf")
            return ""


    def get_enabled_consumers(self, want_objects=1):
        """ Return a list of all consumers enabled in consumers.conf """

        try:
            consumers = []
            for consumer in re.split("\s*,\s*", self.consumer_config.get("consumers", "enabled")):
                if consumer and not consumer.isspace():
                    if want_objects:
                        consumer_obj = Consumer.Consumer(consumer, self)
                        consumers.append(consumer_obj)
                    else:
                        consumers.append(consumer)
            return consumers
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return []


    def set_enabled_consumers(self, consumer_list):
        """ Set the list of consumers enabled in consumers.conf """

        enabled_consumers = ", ".join(consumer_list)

        if not self.consumer_config.has_section("consumers"):
            self.consumer_config.add_section("consumers")

        self.consumer_config.set("consumers", "enabled", enabled_consumers)
        return


    def is_consumer_enabled(self, consumer):
        """ Return true if consumer is enabled, false otherwise """

        if consumer in self.get_enabled_consumers(want_objects=0):
            return True
        else:
            return False


    def enable_consumer(self, consumer_name):
        """ Add a consumer to the list of consumers that are enabled in consumers.conf """

        enabled_consumers = self.get_enabled_consumers(want_objects=0)
        if consumer_name in enabled_consumers:
            # Already enabled, nothing needs to be done
            return
        else:
            enabled_consumers.append(consumer_name)
            self.set_enabled_consumers(enabled_consumers)
            self.write_consumer_config_file()

        return


    def disable_consumer(self, consumer_name):
        """ Add a consumer to the list of consumers that are disabled in consumers.conf """

        enabled_consumers = self.get_enabled_consumers(want_objects=0)
        if consumer_name not in enabled_consumers:
            # Already disabled, nothing needs to be done
            return
        else:
            # Just in case it's listed multiple times, loop the remove statement
            while consumer_name in enabled_consumers:
                enabled_consumers.remove(consumer_name)

            self.set_enabled_consumers(enabled_consumers)
            self.write_consumer_config_file()

        return


    def write_consumer_config_file(self):
        """ Write out the consumers.conf file to disk """

        self.log("INFO", "Writing consumer configuration file '%s'" % CONSUMER_CONFIG_FILE)
        
        if not os.path.exists(CONSUMER_CONFIG_FILE):
            self.echo("Creating configuration file '%s'" % CONSUMER_CONFIG_FILE)
            
        config_fp = open(CONSUMER_CONFIG_FILE, 'w')
        self.consumer_config.write(config_fp)
        config_fp.close()


    def get_extra_globus_rsl(self):
        """ Fetch the extra-globus-rsl value which is optional. """
        try:
            return self.config.get("rsv", "extra-globus-rsl")
        except ConfigParser.NoOptionError:
            return ""


    def get_wrapper(self):
        """ Return the wrapper script that will run the metrics """
        return os.path.join("/", "usr", "bin", "rsv-control")


    def get_proxy(self):
        """ Return the path of the proxy file being used """
        return self.proxy


    def check_proxy(self, metric):
        """ Determine if we're using a service cert or user proxy and
        validate appropriately """

        self.log("INFO", "Checking proxy:")

        if metric.config_val("need-proxy", "false"):
            self.log("INFO", "Skipping proxy check because need-proxy=false", 4)
            return

        # First look for the service certificate.  Since this is the preferred option,
        # it will override the proxy-file if both are set.
        try:
            service_cert  = self.config.get("rsv", "service-cert")
            service_key   = self.config.get("rsv", "service-key")
            service_proxy = self.config.get("rsv", "service-proxy")
            self.renew_service_certificate_proxy(metric, service_cert, service_key, service_proxy)
            self.proxy = service_proxy
            return
        except ConfigParser.NoOptionError:
            self.log("INFO", "Not using service certificate.  Checking for user proxy", 4)
            pass

        # If the service certificate is not available, look for a user proxy file
        try:
            proxy_file = self.config.get("rsv", "proxy-file")
            self.check_user_proxy(metric, proxy_file)
            self.proxy = proxy_file
            return
        except ConfigParser.NoOptionError:
            pass

        # If we won't have a proxy, and need-proxy was not set above, we bail
        self.results.no_proxy_found(metric)
        sys.exit(1)


    def renew_service_certificate_proxy(self, metric, cert, key, proxy):
        """ Check the service certificate.  If it is expiring soon, renew it. """

        self.log("INFO", "Using service certificate proxy", 4)

        hours_til_expiry = 6
        seconds_til_expiry = str(hours_til_expiry * 60 * 60)
        (ret, out, err) = self.run_command([OPENSSL_EXE, "x509", "-in", proxy, "-noout", "-enddate", "-checkend", seconds_til_expiry])

        if ret == 0:
            self.log("INFO", "Service certificate valid for at least %s hours." % hours_til_expiry, 4)
        else:
            self.log("INFO", "Service certificate proxy expired or expiring within %s hours.  Renewing it." %
                    hours_til_expiry, 4)

            cmd = ["grid-proxy-init", "-cert", cert, "-key", key, "-valid", "12:00", "-bits", "1024", "-debug", "-out", proxy]
            if self.use_legacy_proxy():
                self.log("INFO", "Generating a legacy Globus proxy because it was requested.", 4)
                # This should come right after "grid-proxy-init"
                cmd.insert(1, "-old")
                
            (ret, out, err) = self.run_command(cmd)

            if ret:
                self.results.service_proxy_renewal_failed(metric, cert, key, proxy, out, err)
                sys.exit(1)

        # Globus needs help finding the service proxy since it probably does not have the
        # default naming scheme of /tmp/x509_u<UID>
        os.environ["X509_USER_PROXY"] = proxy
        os.environ["X509_PROXY_FILE"] = proxy

        return



    def check_user_proxy(self, metric, proxy_file):
        """ Check that a proxy file is valid """

        self.log("INFO", "Using user proxy", 4)

        # Check that the file exists on disk
        if not os.path.exists(proxy_file):
            self.results.missing_user_proxy(metric, proxy_file)
            sys.exit(1)

        # Check that the proxy is not expiring in the next 10 minutes.  globus-job-run
        # doesn't seem to like a proxy that has a lifetime of less than 3 hours anyways,
        # so this check might need to be adjusted if that behavior is more understood.
        minutes_til_expiration = 10
        seconds_til_expiration = str(minutes_til_expiration * 60)
        (ret, out, err) = self.run_command([OPENSSL_EXE, "x509", "-in", proxy_file, "-noout", "-enddate", "-checkend", seconds_til_expiration])
        
        if ret:
            self.results.expired_user_proxy(metric, proxy_file, out, minutes_til_expiration)
            sys.exit(1)

        # Just in case this isn't the default /tmp/x509_u<UID> we'll explicitly set it
        os.environ["X509_USER_PROXY"] = proxy_file
        os.environ["X509_PROXY_FILE"] = proxy_file

        return


    def run_command(self, command, timeout=None):
        """ Wrapper for Sysutils.system """

        if not timeout:
            # Use the timeout declared in the config file
            timeout = self.config.getint("rsv", "job-timeout")
            
        self.log("INFO", "Running command with timeout (%s seconds):\n\t%s" % (timeout, " ".join(command)))
        return self.sysutils.system(command, timeout)


    def use_condor_g(self):
        """ Return True or False depending on if we should submit remote jobs using
        Condor-G.  We will default to true because it is the better behavior. """

        try:
            value = self.config.get("rsv", "use-condor-g")
            if value.lower() == "true":
                return True
            else:
                return False
        except ConfigParser.NoOptionError:
            self.log("INFO", "use-condor-g is not defined in Condor config file.  Defaulting to true.")
            return True


    def use_legacy_proxy(self):
        """ Return True or False depending on if we should use a legacy Globus proxy.
        We will default to False if the user did not specify. """

        try:
            value = self.config.get('rsv', 'legacy-proxy')
            if value.lower() == "true":
                return True
        except ConfigParser.NoOptionError:
            pass

        return False

# End of RSV class


def get_rsv_defaults():
    """
    This is where to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """

    defaults = {}

    def set_default_value(section, option, value):
        if section not in defaults:
            defaults[section] = {}
        defaults[section][option] = value

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to in bytes.  A value of 0 means no trimming.
    set_default_value("rsv", "details-data-trim-length", 10000)

    # Set the job timeout default in seconds
    set_default_value("rsv", "job-timeout", 1200)

    return defaults


def validate_config(rsv):
    """ Perform validation on config values.  Note that this is not a class method that
    is called every time we load the configuration because this validation is specific
    to running metrics.  When we are calling rsv-control with --enable we don't want to
    do this validation. """

    rsv.log("INFO", "Validating configuration:")

    #
    # make sure that the user is valid, and we are either that user or root
    #
    rsv.log("INFO", "Validating user:")
    try:
        user = rsv.config.get("rsv", "user")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR", "'user' is missing in rsv.conf.  Set this value to your RSV user", 4)
        sys.exit(1)

    try:
        (desired_uid, desired_gid) = getpwnam(user)[2:4]
    except KeyError:
        rsv.log("ERROR", "The '%s' user defined in rsv.conf does not exist" % user, 4)
        sys.exit(1)

    # If appropriate, switch UID/GID
    rsv.sysutils.switch_user(user, desired_uid, desired_gid)

                
    #
    # "details_data_trim_length" must be an integer because we will use it later
    # in a splice
    #
    try:
        rsv.config.getint("rsv", "details_data_trim_length")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe set it again here.
        rsv.config.set("rsv", "details_data_trim_length", "10000")
    except ValueError:
        rsv.log("ERROR: details_data_trim_length must be an integer.  It is set to '%s'"
                % rsv.config.get("rsv", "details_data_trim_length"))
        sys.exit(1)


    #
    # job_timeout must be an integer because we will use it later in an alarm call
    #
    try:
        rsv.config.getint("rsv", "job-timeout")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        rsv.config.set("rsv", "job-timeout", "1200")
    except ValueError:
        rsv.log("ERROR", "job-timeout must be an integer.  It is set to '%s'" %
                rsv.config.get("rsv", "job-timeout"))
        sys.exit(1)


    #
    # warn if consumers are missing
    #
    try:
        consumers = rsv.consumer_config.get("consumers", "enabled")
        rsv.log("INFO", "Registered consumers: %s" % consumers, 0)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        if not rsv.consumer_config.has_section("consumers"):
            rsv.consumer_config.add_section("consumers")
        rsv.consumer_config.set("consumers", "enabled", "")
        rsv.log("WARNING", "no consumers are registered in consumers.conf.  This " +
                "means that records will not be sent to a central collector for " +
                "availability statistics.")

    return
    
