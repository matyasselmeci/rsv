#!/usr/bin/env python

import os
import re
import sys
import ConfigParser

class Metric:
    """ Instantiable class to read and store configuration for a single metric """

    rsv = None
    name = None
    host = None
    config = None
    conf_dir = None
    meta_dir = None
    executable = None


    def __init__(self, metric, rsv, host=None):
        # Initialize vars
        self.name = metric
        self.rsv  = rsv
        self.conf_dir = os.path.join(rsv.rsv_location, "etc", "metrics")
        self.meta_dir = os.path.join(rsv.rsv_location, "meta", "metrics")

        # Find executable
        self.executable = os.path.join(rsv.rsv_location, "bin", "metrics", metric)
        if os.path.lexists(self.executable) and not os.path.exists(self.executable):
            rsv.log("ERROR", "Metric is a broken symlink at %s" % self.executable)
            sys.exit(1)
        elif not os.path.exists(self.executable):
            rsv.log("ERROR", "Metric does not exist at %s" % self.executable)
            sys.exit(1)

        if host:
            self.host = host

        # Load configuration
        defaults = get_metric_defaults(metric)
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str
        self.load_config(defaults)


    def load_config(self, defaults):
        """ Load metric configuration files """
        if defaults:
            for section in defaults.keys():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                    
                for item in defaults[section].keys():
                    self.config.set(section, item, defaults[section][item])

        # Load the metric's meta information file
        meta_file = os.path.join(self.meta_dir, self.name + ".meta")
        if not os.path.exists(meta_file):
            self.rsv.log("ERROR", "Metric meta file '%s' does not exist" % meta_file)
            return
        else:
            try:
                self.config.read(meta_file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                sys.exit(1)


        # Load the metric's general configuration file
        config_file = os.path.join(self.conf_dir, self.name + ".conf")
        if not os.path.exists(config_file):
            self.rsv.log("INFO", "Metric config file '%s' does not exist" % config_file)
            return
        else:
            try:
                self.config.read(config_file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                sys.exit(1)


        # If this is for a specified host, load the metric/host config file
        if self.host:
            config_file = os.path.join(self.conf_dir, self.host, self.name + ".conf")
            if not os.path.exists(config_file):
                self.rsv.log("INFO", "Metric/host config file '%s' does not exist" % config_file)
            else:
                try:
                    self.config.read(config_file)
                except ConfigParser.ParsingError, err:
                    self.rsv.log("CRITICAL", err)
                    sys.exit(1)

        

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
                elif (not value and action not in actions_without_value):
                    self.rsv.log("WARNING", "Invalid environment config setting in section '%s'" % section)
                    self.rsv.log("WARNING", "Invalid entry: %s = %s" % (var, setting))
                    self.rsv.log("WARNING", "Format must be VAR = ACTION | VALUE")
                    self.rsv.log("WARNING", "\t(VALUE may be blank if ACTION is 'UNSET')")
                else:
                    value = re.sub("!!VDT_LOCATION!!", self.rsv.vdt_location, value)
                    value = re.sub("!!VDT_PYTHONPATH!!", self.rsv.get_vdt_pythonpath(), value)
                    value = re.sub("!!VDT_PERL5LIB!!", self.rsv.get_vdt_perl5lib(), value)
                    env[var] = [action, value]

        except ConfigParser.NoSectionError:
            self.rsv.log("INFO", "No environment section in metric configuration", 4)

        return env


    def get_args_string(self):
        """ Build the custom parameters to the script based on the config file """
        
        self.rsv.log("INFO", "Forming arguments:")
        args_section = self.name + " args"
        args = ""
        try:
            for option in self.config.options(args_section):
                args += "--%s %s " % (option, self.config.get(args_section, option))
        except ConfigParser.NoSectionError:
            self.rsv.log("INFO", "No '%s' section found" % args_section, 4)

        # RSVv3 requires a few more arguments
        if self.config_val("probe-spec", "v3"):
            # We always need to tell RSVv3 about where the proxy is
            proxy_file = self.rsv.get_proxy()
            if proxy_file:
                self.rsv.log("INFO", "Adding -x because probe version is v3", 4)
                args += "-x %s " % proxy_file

            self.rsv.log("INFO", "Adding --verbose because probe version is v3", 4)
            args += "--verbose "


        self.rsv.log("INFO", "Arguments: '%s'" % args, 4)

        return args


    def get_unique_name(self):
        """ Return a unique ID to be used in Condor based on the metric and host """
        if self.host:
            return "%s__%s" % (self.host, self.name)
        else:
            self.rsv.log("CRITICAL", "Attempted to get unique name for metric without host")
            return None


    def get_cron_entry(self):
        """ Return a dict containing the cron time information """
        if self.config.has_option(self.name, "cron-interval"):
            interval = self.config.get(self.name, "cron-interval")
        elif self.config.has_option(self.name, "default-cron-interval"):
            interval = self.config.get(self.name, "default-cron-interval")
        else:
            self.rsv.log("ERROR", "cron-interval missing from metric")
            return {}

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


    def get_timeout(self):
        """ Return the jobs custom timeout setting, or None """
        try:
            timeout = self.config.getint(self.name, "timeout")
            self.rsv.log("INFO", "Custom timeout (%s seconds) is set for metric '%s'" % (timeout, self.name))
            return timeout
        except ValueError:
            self.rsv.log("WARNING", "A non-integer value is set for timeout for metric '%s'" % self.name)
            return None
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            # It's expected that this won't be defined most of the time
            return None
        

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
        args = self.get_args_string() or "<none>"
        self.rsv.echo("\nCommand line options passed to metric:")
        self.rsv.echo("\t" + args)

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

        self.rsv.echo("") # newline for nicer formatting
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
