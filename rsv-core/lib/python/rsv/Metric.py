#!/usr/bin/python
from __future__ import print_function

import os
import re
import sys
import ConfigParser

VALID_OUTPUT_FORMATS = ["wlcg", "wlcg-multiple", "brief"]
DEAD_METRICS_FILE = "/usr/libexec/rsv/dead-metrics"


__dead_metrics = None
def is_dead_metric(metric):
    global __dead_metrics
    if __dead_metrics is None:
        try:
            with open(DEAD_METRICS_FILE) as deadfile:
                __dead_metrics = set([l.strip() for l in deadfile.readlines()])
        except EnvironmentError as err:
            print("Error opening dead metrics file %s: %s" % (
                    DEAD_METRICS_FILE, err), file=sys.stderr)
            __dead_metrics = set()

    return metric in __dead_metrics


class Metric:
    """ Instantiable class to read and store configuration for a single metric """

    def __init__(self, metric, rsv, host=None, options=None):
        # Initialize vars
        self.name = metric
        self.rsv  = rsv
        self.dead = is_dead_metric(metric)

        if self.dead:
            self.rsv.log("DEBUG", "Metric %s is in dead metrics file" % self.name)
            return

        conf_dir = os.path.join("/", "etc", "rsv", "metrics")
        meta_dir = os.path.join("/", "etc", "rsv", "meta", "metrics")

        self.meta_file = os.path.join(meta_dir, metric + ".meta")
        self.top_config_file = os.path.join(conf_dir, metric + ".conf") 

        # Find executable
        self.executable = os.path.join("/", "usr", "libexec", "rsv", "metrics", metric)
        if os.path.islink(self.executable) and not os.path.exists(self.executable):
            rsv.log("ERROR", "Metric is a broken symlink at %s" % self.executable)
            sys.exit(1)
        elif not os.path.exists(self.executable):
            rsv.log("ERROR", "Metric does not exist at %s" % self.executable)
            sys.exit(1)

        self.host = None
        if host:
            self.host = host
            self.host_config_file = os.path.join(conf_dir, host, metric + ".conf")
            self.host_allmetrics_config_file = os.path.join(conf_dir, host, "allmetrics.conf")

        # Load configuration
        defaults = get_metric_defaults(metric)
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str
        self.load_config(defaults, options)

        if not self.validate_config():
            self.rsv.log("ERROR", "Metric %s is not configured correctly." % self.name)

        self.ce_type = None
        if options and options.ce_type:
            self.ce_type = options.ce_type

        return


    def load_config_file(self, file, required=0):
        """ Load a single configuration file """
        log_level = "INFO"
        prefix = "Optional"
        if required:
            log_level = "ERROR"
            prefix = "Mandatory"

        if not os.path.exists(file):
            self.rsv.log(log_level, "%s config file '%s' does not exist" % (prefix, file))
        elif not os.access(file, os.R_OK):
            self.rsv.log("WARNING", "Config file '%s' is not readable by RSV user" % file)
        else:
            self.rsv.log("INFO", "Loading config file '%s'" % file)
            try:
                ret = self.config.read(file)
                # Python 2.3 (RHEL-4) does not return anything so we can only do this check
                # if we get an array back.
                if ret is not None:
                    if file not in ret:
                        self.rsv.log("ERROR", "An unknown error occurred while trying to load config file '%s'" %
                                     file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                sys.exit(1)

        return


    def load_allmetrics_config_file(self, file):
        """Load 'allmetrics.conf' for a host. If it exists, then use options
        defined in its [allmetrics], and [allmetrics env] sections (if they
        exist) for this metric. It is not an error if the file doesn't exist.
        It IS an error if it contains sections other than the two mentioned
        above.

        """
        if not os.path.exists(file):
            self.rsv.log("DEBUG", "Config file '%s' does not exist" % file)
        elif not os.access(file, os.R_OK):
            self.rsv.log("WARNING", "Config file '%s' exists but is not readable by RSV user" % file)
        else:
            self.rsv.log("INFO", "Loading config file '%s'" % file)
            try:
                # Use a separate config parser to read this and then combine
                # the results into self.config.  Two reasons for this: first,
                # we want to error out if we see sections other than
                # [allmetrics.*] in the conf file. Second, we want to put
                # options in [allmetrics] into the appropriate section for the
                # current metric (i.e. if self.name is 'foo' then options in
                # [allmetrics] should go into [foo], options in
                # [allmetrics env] should go into [foo env], etc).
                allmetrics = ConfigParser.RawConfigParser()
                allmetrics.optionxform = str
                ret = allmetrics.read(file)
                # Python 2.3 (RHEL-4) does not return anything so we can only do this check
                # if we get an array back.
                if ret is not None:
                    if file not in ret:
                        self.rsv.log("ERROR", "An unknown error occurred while trying to load config file '%s'" % file)

                # Now combine the sections
                for section in allmetrics.sections():
                    if section == 'allmetrics args':
                        self.rsv.log("WARNING", "Config file '%s' contains deprecated section '%s', which will be ignored" % (file, section))
                        continue
                    if section not in ['allmetrics', 'allmetrics env']:
                        self.rsv.log("CRITICAL", "Config file '%s' contains forbidden section '%s'" % (file, section))
                        sys.exit(1)
                    metric_section = re.sub(r'allmetrics', self.name, section)
                    if not self.config.has_section(metric_section):
                        continue
                    for opt in allmetrics.options(section):
                        value = allmetrics.get(section, opt)
                        self.rsv.log("DEBUG",
                                     "Setting option '%s' for section '%s' to '%s' (from allmetrics section)" %
                                         (opt, metric_section, value))
                        self.config.set(metric_section, opt, value)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                sys.exit(1)

        return


    def load_config(self, defaults, options=None):
        """ Load metric configuration files """
        if defaults:
            for section in defaults.keys():
                if not self.config.has_section(section):
                    self.config.add_section(section)

                for item in defaults[section].keys():
                    self.config.set(section, item, defaults[section][item])

        # Load the metric's meta information file
        self.load_config_file(self.meta_file, required=1)

        # Load the metric's general configuration file
        self.load_config_file(self.top_config_file, required=0)

        # If this is for a specified host, load the metric/host config file and the allmetrics conf file
        if self.host:
            self.load_allmetrics_config_file(self.host_allmetrics_config_file)
            self.load_config_file(self.host_config_file, required=0)

        # If we were given a file on the command line load it now
        if options and options.extra_config_file:
            # If the user specified this on the command line then it should be required (so it procudes
            # ERROR messages if anything goes wrong)
            self.load_config_file(options.extra_config_file, required=1)

        return

    def validate_config(self):
        """ Validate metric-specific configuration """

        if not self.config_get("service-type") or not self.config_get("execute"):
            self.rsv.log("ERROR", "Metric configuration is missing 'service-type' or 'execute' " +
                         "declaration.  This is likely caused by a missing or corrupt metric " +
                         "meta file or configuration file.")
            return False

        try:
            output_format = self.config_get("output-format").lower()
            if output_format not in VALID_OUTPUT_FORMATS:
                valid_formats = " ".join(VALID_OUTPUT_FORMATS)
                self.rsv.log("ERROR", "output-format '%s' is not supported.  Valid formats: %s\n" %
                        (output_format, valid_formats))
                return False

        except ConfigParser.NoOptionError:
            self.rsv.log("ERROR", "Metric output-format is missing.\n" +
                         "This is likely caused by a missing or corrupt metric configuration file")
            return False

        return True


    def get_type(self):
        """ Return the serviceType """

        try:
            return self.config.get(self.name, "service-type")
        except ConfigParser.NoOptionError:
            self.rsv.log("ERROR", "Metric '%s' missing serviceType" % self.name)
            return "UNKNOWN"


    def config_get(self, key):
        """ Fetch a value from the metric configuration """
        try:
            return self.config.get(self.name, key)
        except ConfigParser.NoOptionError:
            self.rsv.log("DEBUG", "metric.config_get - no key '%s'" % key)
            return None


    def config_getboolean(self, key):
        """Fetch a value from the metric configuration, coercing to a boolean.
        Return None if the key does not exist or cannot be used as a boolean.

        """
        try:
            return self.config.getboolean(self.name, key)
        except ConfigParser.NoOptionError:
            self.rsv.log("DEBUG", "metric.config_getboolean - no key '%s'" % key)
            return None
        except ValueError:
            self.rsv.log("DEBUG", "metric.config_getboolean - invalid boolean value for key '%s' (%s)" % (key, self.config.get(self.name, key)))
            return None


    def config_val(self, key, value, case_sensitive=0):
        """ Check if key is in config, and if it equals val. """

        try:
            if case_sensitive == 0:
                if self.config.get(self.name, key).lower() == str(value).lower():
                    return True
            else:
                if self.config.get(self.name, key) == str(value):
                    return True
        except ConfigParser.NoOptionError:
            return False

        return False


    def get_environment(self):
        """ Return the environment configuration """

        env = {}

        try:
            section = self.name + " env"
            for var in self.config.options(section):
                setting = self.config.get(section, var)

                if setting.find("|") == -1:
                    action = setting.strip()
                    value = ""
                else:
                    (action, value) = re.split("\s*\|\s*", setting, 1)
                    action = action.upper().strip()

                valid_actions = ["SET", "UNSET", "APPEND", "PREPEND"]
                actions_without_value = ["UNSET"]
                if action not in valid_actions:
                    self.rsv.log("WARNING", "Invalid environment config setting in section '%s'" % section)
                    self.rsv.log("WARNING", "Invalid entry: %s = %s" % (var, setting))
                    self.rsv.log("WARNING", "Action '%s' must be one of (%s)" %
                                 (action, " ".join(valid_actions)))
                elif not value and action not in actions_without_value:
                    self.rsv.log("WARNING", "Invalid environment config setting in section '%s'" % section)
                    self.rsv.log("WARNING", "Invalid entry: %s = %s" % (var, setting))
                    self.rsv.log("WARNING", "Format must be VAR = ACTION | VALUE")
                    self.rsv.log("WARNING", "\t(VALUE may be blank if ACTION is 'UNSET')")
                else:
                    env[var] = [action, value]

        except ConfigParser.NoSectionError:
            self.rsv.log("INFO", "No environment section in metric configuration", 4)

        return env


    def get_classAds(self):
        """ Return the classAds configuration """
        
        classAds = {}
        
        section = self.name+ " classAds"
        try:
            for ad in self.config.options(section):
                classAds[ad] = self.config.get(section, ad)
        except ConfigParser.NoSectionError:
             self.rsv.log("INFO", "No '%s' section found" % section, 4)

        return classAds

    def get_args_list(self):
        """ Build the custom parameters to the script based on the config file """

        self.rsv.log("INFO", "Forming arguments:")
        args_section = self.name + " args"
        args = []
        try:
            for option in self.config.options(args_section):
                args += ["--%s" % option, self.config.get(args_section, option)]
        except ConfigParser.NoSectionError:
            self.rsv.log("INFO", "No '%s' section found" % args_section, 4)

        # RSVv3 requires a few more arguments
        if self.config_val("probe-spec", "v3"):
            # We always need to tell RSVv3 about where the proxy is
            proxy_file = self.rsv.get_proxy()
            if proxy_file:
                self.rsv.log("INFO", "Adding -x because probe version is v3", 4)
                args += ["-x", proxy_file]

            self.rsv.log("INFO", "Adding --verbose because probe version is v3", 4)
            args += ["--verbose"]


        self.rsv.log("INFO", "Arguments: '%s'" % args, 4)

        return args


    def get_args_string(self):
        """ Stringify the custom parameters to the script based on the config file """

        return ' '.join(self.get_args_list())


    def get_unique_name(self):
        """ Return a unique ID to be used in Condor based on the metric and host """
        if self.host:
            return "%s__%s" % (self.host, self.name)
        else:
            self.rsv.log("CRITICAL", "Attempted to get unique name for metric without host")
            return None


    def get_cron_string(self):
        """ Return the literal cron time string """
        if self.config.has_option(self.name, "cron-interval"):
            interval = self.config.get(self.name, "cron-interval")
        elif self.config.has_option(self.name, "default-cron-interval"):
            interval = self.config.get(self.name, "default-cron-interval")
        else:
            self.rsv.log("ERROR", "cron-interval missing from metric")
            return ""

        return interval

    def get_cron_entry(self):
        """ Return a dict containing the cron time information """

        interval = self.get_cron_string()

        arr = interval.split()

        cron = {}
        if len(arr) != 5:
            self.rsv.log("ERROR", "cron-interval is invalid: '%s'" % interval)
        else:
            cron["Minute"]     = arr[0]
            cron["Hour"]       = arr[1]
            cron["DayOfMonth"] = arr[2]
            cron["Month"]      = arr[3]
            cron["DayOfWeek"]  = arr[4]

        return cron

    def get_probe_interval(self):
        """ If set, return the deferral interval for the probe """
        if self.config.has_option(self.name, "probe-interval"):
            interval = self.config.get(self.name, "probe-interval")
        elif self.config.has_option(self.name, "default-probe-interval"):
            interval = self.config.get(self.name, "default-probe-interval")
        else:
            return 0

        try:
            return int(interval)
        except (TypeError, ValueError):
            self.rsv.log("ERROR", "probe-interval is invalid: '%s'" % interval)
            return 0

    def get_timeout(self):
        """ Return the job's custom timeout setting, or None """

        # check 'timeout' option first, but generate a warning if used
        try:
            timeout = self.config.getint(self.name, 'timeout')
            self.rsv.log("INFO", "Custom timeout (%s seconds) is set for metric '%s'" % (timeout, self.name))
            self.rsv.log("WARNING", ("Deprecated 'timeout' option used for metric '%s', " 
                                     "please use 'job-timeout' instead") % self.name)
            return timeout
        except ValueError:
            self.rsv.log("WARNING", "A non-integer value is set for timeout for metric '%s'" % self.name)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            # It's expected that this won't be defined most of the time
            pass

        # then try 'job-timeout'
        try:
            timeout = self.config.getint(self.name, 'job-timeout')
            self.rsv.log("INFO", "Custom job-timeout (%s seconds) is set for metric '%s'" % (timeout, self.name))
            return timeout
        except ValueError:
            self.rsv.log("WARNING", "A non-integer value is set for job-timeout for metric '%s'" % self.name)
            return None
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            # It's expected that this won't be defined most of the time
            return None


    def get_settings(self):
        """ Get settings that need to be passed to rsv-control.  This is different than
        get_args_string() because the args get passed to the metric script.  This section
        is to get settings the will be passed to rsv-control when Condor-Cron invokes it.
        Since not all values in the namespace should be passed we will just add entries
        to a list here. """

        settings = ["no-ping"]

        string = ""
        for setting in settings:
            try:
                value = self.config.get(self.name, setting)
                string += "--%s %s" % (setting, value)
            except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
                # It is ok if they are not defined
                pass

        return string


    def get_transfer_files(self):
        """ Return the list of required files to transfer for a probe. """
        try:
            transfer_files = self.config.get(self.name, "transfer-files")
            self.rsv.log("INFO", "List of files to transfer: %s" % transfer_files)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            self.rsv.log("INFO", "No files to transfer are declared.")
            return None

        transfer_files = transfer_files.split()
        return transfer_files


    def dump_config(self):
        """ Print out all config information for this metric/host pair """

        self.rsv.echo("------------------------------------------------------")
        self.rsv.echo("Configuration dump for metric '%s' against host '%s'\n" % (self.name, self.host))

        # Metric settings
        self.rsv.echo("Settings:")
        try:
            if len(self.config.options(self.name)) == 0:
                self.rsv.echo("\t<none>")
            else:
                for key in sorted(self.config.options(self.name)):
                    self.rsv.echo("\t%s = %s" % (key, self.config.get(self.name, key)))
        except ConfigParser.NoSectionError:
            self.rsv.echo("\t<none>")

        # Command line switches
        settings = self.get_settings() or "<none>"
        self.rsv.echo("\nExtra command line options passed to rsv-control:")
        self.rsv.echo("\t" + str(settings))

        # Command line switches
        args = self.get_args_string() or "<none>"
        self.rsv.echo("\nCommand line options passed to metric:")
        self.rsv.echo("\t" + str(args))

        # Environment
        self.rsv.echo("\nCustom environment set for this metric:")
        environment = self.get_environment()
        if len(environment) == 0:
            self.rsv.echo("\t<none>")
        else:
            for var in sorted(environment.keys()):
                self.rsv.echo("\t%s" % var)
                self.rsv.echo("\t\tAction: %s" % environment[var][0])
                if environment[var][1]:
                    self.rsv.echo("\t\tValue: %s" % environment[var][1])
        
        # ClassAds
        self.rsv.echo("\nCustom classAds for this metric:")
        classAds = self.get_classAds()
        if len(environment) == 0:
            self.rsv.echo("\t<none>")
        else:
            for ad in classAds:
                self.rsvecho("\t%s=%s" % ad, classAds[ad])
        self.rsv.echo("") # newline for nicer formatting
        return


    def set_config_val(self, knobs):
        """ Put a value in the metric config file.  If host is set, it will go
        into the host-specific file.  If not, it will go into the general file.
        """

        if self.host:
            file = self.host_config_file
        else:
            file = self.top_config_file

        # The file and parent directory are not guaranteed to exist.
        # But we want to create them if not.
        if not os.path.exists(file):
            if not os.path.exists(os.path.dirname(file)):
                os.makedirs(os.path.dirname(file))
            open(file, 'w').close()

        local_config = ConfigParser.RawConfigParser()
        local_config.optionxform = str
        local_config.read(file)

        section = "%s args" % self.name
        if not local_config.has_section(section):
            local_config.add_section(section)

        for knob in knobs:
            if knob.find('=') == -1:
                self.rsv.log("WARNING", "Invalid knob supplied (%s).  Must be Key=Value" % knob)
                continue

            (key, val) = knob.split('=', 1)
            self.rsv.log("INFO", "Setting config value (%s=%s)" % (key, val))
            local_config.set(section, key, val)

        fp = open(file, 'w')
        local_config.write(fp)
        fp.close()

        return


def get_metric_defaults(metric_name):
    """ Load metric default values """
    defaults = {}
    def set_default_value(section, option, value):
        if section not in defaults:
            defaults[section] = {}
        defaults[section][option] = value

    # We want most remote Globus jobs to execute on the CE headnode, so they
    # need to use the fork jobmanager (unless they declare something different)
    set_default_value(metric_name, "jobmanager", "fork")

    # The only metricType that any current metric has is "status".  So instead
    # of declaring it in every single <metric>.conf file, we'll set it here but
    # still make it possible to configure in case it is needed in the future.
    set_default_value(metric_name, "metric-type", "status")

    return defaults
