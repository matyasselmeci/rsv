#!/usr/bin/env python

import os
import re
import sys
import ConfigParser

class Consumer:
    """ Instantiable class to read and store configuration about a single consumer """
    
    rsv = None
    name = None
    config = None
    conf_dir = None
    meta_dir = None
    executable = None


    def __init__(self, consumer, rsv):
        # Initialize vars
        self.name = consumer
        self.rsv  = rsv
        self.conf_dir = os.path.join(rsv.rsv_location, "etc", "consumers")
        self.meta_dir = os.path.join(rsv.rsv_location, "meta", "consumers")

        # Find executable
        self.executable = os.path.join(rsv.rsv_location, "bin", "consumers", consumer)
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


    def wants_local_time(self):
        """ Determine if the consumer should get a record with local time instead
        of GMT """

        try:
            value = self.config.get(self.name, "timestamp")
            if value.lower() == "local":
                return True
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return False

        return False


    def get_environment(self):
        """ Return the environment string from the configuration file after making
        necessary substitutions. """

        try:
            env = self.config.get(self.name, "environment")
            env = re.sub("!!VDT_LOCATION!!", self.rsv.vdt_location, env)
            env = re.sub("!!VDT_PYTHONPATH!!", self.rsv.get_vdt_pythonpath(), env)
            env = re.sub("!!VDT_PERL5LIB!!", self.rsv.get_vdt_perl5lib(), env)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return ""

        return env

def get_consumer_defaults(consumer_name):
    """ Load consumer default values """
    defaults = {}
    def set_default_value(section, option, value):
        if section not in defaults:
            defaults[section] = {}
        defaults[section][option] = value

    # There are currently no consumer defaults

    return defaults
