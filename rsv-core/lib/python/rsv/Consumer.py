#!/usr/bin/python

import os
import sys
import ConfigParser

class Consumer:
    """ Instantiable class to read and store configuration about a single consumer """
    
    def __init__(self, consumer, rsv):
        # Initialize vars
        self.name = consumer
        self.rsv  = rsv
        self.conf_dir = os.path.join("/", "etc", "rsv", "consumers")
        self.meta_dir = os.path.join("/", "etc", "rsv", "meta", "consumers")

        # Find executable
        self.executable = os.path.join("/", "usr", "libexec", "rsv", "consumers", consumer)
        if not os.path.exists(self.executable):
            rsv.log("ERROR", "Consumer does not exist at %s" % self.executable)
            sys.exit(1)

        # Load configuration
        defaults = get_consumer_defaults(consumer)
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str # make keys case-insensitive
        self.load_config(defaults)


    def load_config(self, defaults):
        """ Read the consumer configuration file, if it exists """
        
        if defaults:
            for section in defaults.keys():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                    
                for item in defaults[section].keys():
                    self.config.set(section, item, defaults[section][item])

        # Load the consumer's meta file
        meta_file = os.path.join(self.meta_dir, self.name + ".meta")
        if not os.path.exists(meta_file):
            self.rsv.log("INFO", "Consumer meta file '%s' does not exist" % meta_file)
            return
        else:
            try:
                self.config.read(meta_file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                # TODO - return exception, don't exit
                sys.exit(1)

        # Load the consumer's general configuration file
        # Load this after the meta file so it can override that file
        config_file = os.path.join(self.conf_dir, self.name + ".conf")
        if not os.path.exists(config_file):
            self.rsv.log("INFO", "Consumer config file '%s' does not exist" % config_file)
            return
        else:
            try:
                self.config.read(config_file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                # TODO - return exception, don't exit
                sys.exit(1)



    def config_get(self, key):
        """ Get a value from the consumer-specific configuration """
        
        try:
            return self.config.get(self.name, key)
        except ConfigParser.NoOptionError:
            self.rsv.log("DEBUG", "consumer.config_get - no key '%s'" % key)
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


    def get_unique_name(self):
        """ Return a unique ID for this consumer to use in the Condor job ad """
        return self.name


    def requested_time_format(self):
        """ Determine what time format the consumer is requesting.  Options include
        local, epoch, and GMT """

        try:
            value = self.config.get(self.name, "timestamp")
            return value.lower()
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return ""


    def get_environment(self):
        """ Return the environment string from the configuration file after making
        necessary substitutions. """

        try:
            env = self.config.get(self.name, "environment")
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return ""

        return env

    def get_args_string(self):
        """ Return the arguments string as defined in the configuration file """

        try:
            args = self.config.get(self.name, "args")
            return args
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return ""


    def dump_config(self):
        """ Print out all config information for this consumer """

        self.rsv.echo("------------------------------------------------------")
        self.rsv.echo("Configuration dump for consumer '%s'\n" % self.name)

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
        self.rsv.echo("\nCommand line options passed to consumer:")
        self.rsv.echo("\t" + args)

        # Environment
        environment = self.get_environment() or "<none>"
        self.rsv.echo("\nCustom environment set for this consumer:")
        self.rsv.echo("\t" + environment)

        self.rsv.echo("") # newline for nicer formatting
        return


def get_consumer_defaults(consumer_name):
    """ Load consumer default values """
    defaults = {}
    def set_default_value(section, option, value):
        if section not in defaults:
            defaults[section] = {}
        defaults[section][option] = value

    # There are currently no consumer defaults

    return defaults
