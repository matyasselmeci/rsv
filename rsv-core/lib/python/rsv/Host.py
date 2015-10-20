#!/usr/bin/python

import os
import sys
import ConfigParser

class Host:
    """ Instantiable class to read and store configuration about a single host """

    def __init__(self, host, rsv):
        self.host = host
        self.rsv  = rsv
        self.conf_dir = os.path.join("/", "etc", "rsv")

        # Load configuration
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str  # Make keys case-sensitive
        self.load_config()


    def load_config(self):
        """ Load host specific configuration file """

        self.config_file = os.path.join(self.conf_dir, self.host + ".conf")
        if not os.path.exists(self.config_file):
            self.rsv.log("INFO", "Host config file '%s' does not exist" % self.config_file)
        else:
            try:
                self.config.read(self.config_file)
            except ConfigParser.ParsingError, err:
                self.rsv.log("CRITICAL", err)
                sys.exit(1)

        # Create the default config section so we don't have to error check for this in other spots
        if not self.config.has_section(self.host):
            self.config.add_section(self.host)


    def metric_enabled(self, metric_name):
        """ Return true if the specified metric is enabled, false otherwise """

        try:
            value = self.config.get(self.host, metric_name)
            if not value or value == "0" or value == "off":
                return False
            return True
        except ConfigParser.NoOptionError:
            return False
        

    def get_enabled_metrics(self):
        """ Return a list of all metrics enabled to run against this host """
        
        enabled_metrics = []
        for metric in self.config.options(self.host):
            if self.metric_enabled(metric):
                enabled_metrics.append(metric)

        return enabled_metrics


    def set_config(self, option, value, write_file=False):
        """ Set a value in the host configuration dict. """

        self.config.set(self.host, option, value)

            
    def write_config_file(self):
        """ Write the config back to the INI file on disk """
        
        self.rsv.log("INFO", "Writing configuration file '%s'" % self.config_file)
        
        if not os.path.exists(self.config_file):
            self.rsv.echo("Creating configuration file '%s'" % self.config_file)
            
        config_fp = open(self.config_file, 'w')
        self.config.write(config_fp)
        config_fp.close()
