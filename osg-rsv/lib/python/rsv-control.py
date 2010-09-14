#!/usr/bin/env python

# System libraries
import os 
import sys
from optparse import OptionParser

# Custom RSV libraries
import RSV
import rc_metric
import run_metric

import pdb


def process_options(arguments=None):
    usage = """usage: rsv-control [ --verbose <level> ]
      --run --host <HOST> METRIC [METRIC ...]
      --list [ --wide ] [ --all ] [ <pattern> ]
      --job-list [ --host <host-name> ]
      --on      [METRIC|CONSUMER ...]
      --off     [METRIC|CONSUMER ...]
      --enable  --host <host-name> METRIC|CONSUMER [METRIC|CONSUMER ...]
      --disable --host <host-name> METRIC|CONSUMER [METRIC|CONSUMER ...]
      --help | -h 
      --version
    """

    version = "rsv-control 0.14"
    description = "This script is used to configure and run the RSV monitoring software."

    parser = OptionParser(usage=usage, description=description, version=version)
    parser.add_option("--vdt-location", dest="vdt_location", default=None,
                      help="Root directory of the OSG installation", metavar="DIR")
    parser.add_option("-v", "--verbose", dest="verbose", default=1, type="int",
                      help="Verbosity level (0-3). [Default=%default]")
    parser.add_option("-l", "--list", action="store_true", dest="list", default=False,
                      help="List metric information.  If <pattern> is supplied, only metrics " +
                      "matching the regular expression pattern will be displayed")
    parser.add_option("-j", "--job-list", action="store_true", dest="job_list", default=False,
                      help="List metrics/consumers running in condor-cron.  If host is specified " +
                      "then only metrics from that host are displayed")
    parser.add_option("-w", "--wide", action="store_true", dest="list_wide", default=False,
                      help="Wide list display to avoid truncation in metric listing")
    parser.add_option("-a", "--all", action="store_true", dest="list_all", default=False,
                      help="Display all metrics, including metrics not enabled on any host.")
    parser.add_option("-r", "--run", action="store_true", dest="run", default=False,
                      help="Run the supplied list of metrics against the specified host.")
    parser.add_option("--on", action="store_true", dest="on", default=False,
                      help="Turn on all enabled metrics.  If a metric is specified, turn on only that metric.")
    parser.add_option("--off", action="store_true", dest="off", default=False,
                      help="Turn off all running metrics.  If a metric is specified, turn off only that metric.")
    parser.add_option("--enable", action="store_true", dest="enable", default=False,
                      help="Enable metric. May be specified multiple times.")
    parser.add_option("--disable", action="store_true", dest="disable", default=False,
                      help="Disable metric. May be specified multiple times.")
    parser.add_option("-u", "--host", dest="host", default=None,
                      help="Specify the host [and port] to be used by the metric (e.g. host or host:port)")

    if arguments == None:
        (options, args) = parser.parse_args()
    else:
        (options, args) = parser.parse_args(arguments)

    #
    # Validate options
    #

    # Check for VDT_LOCATION
    if not options.vdt_location:
        options.vdt_location = RSV.get_osg_location()
    if not options.vdt_location:
        parser.error("VDT_LOCATION is not set.\nEither set this environment variable, or " +
                     "pass the --vdt-location command line option.")

    # Check that we got exactly one command
    number_of_commands = len([i for i in [options.run, options.enable, options.disable, options.on,
                                          options.off, options.list, options.job_list] if i])
    
    if number_of_commands > 1:
        parser.error("You can use only one of run, list, enable, disable, on, or off.")
    if number_of_commands == 0:
        parser.error("You must specify one command.")

    # Check other conditions
    if options.run:
        if not options.host:
            parser.error("You must provide a host to run metrics against.")
        else:
            # Set options.uri for run_metric.py code
            options.uri = options.host

        if not args:
            parser.error("You must provide metrics to run")


    return options, args




def main_rsv_control():
    """ Drive the program """

    # Process the command line
    options, args = process_options()

    rsv = RSV.RSV(options.vdt_location, options.verbose)

    # List the metrics
    if options.list:
        if not args:
            return rc_metric.list_metrics(rsv, options, "")
        else:
            return rc_metric.list_metrics(rsv, options, args[0])
    elif options.run:
        run_metric.main(rsv, options, args)
    elif options.job_list:
        rc_metric.job_list(rsv, options.host)
    elif options.on:
        return rc_metric.dispatcher(rsv, "start", args, options.host)
    elif options.off:
        return rc_metric.dispatcher(rsv, "stop", args, options.host)
    elif options.enable:
        return rc_metric.dispatcher(rsv, "enable", args, options.host)
    elif options.disable:
        return rc_metric.dispatcher(rsv, "disable", args, options.host)

    
if __name__ == "__main__":
    PROGNAME = os.path.basename(sys.argv[0])
    if PROGNAME == 'rsv-control' or PROGNAME == 'rsv-control.py':
        if not main_rsv_control():
            sys.exit(1)
        else:
            sys.exit(0)
    else:
        print "Wrong invocation!"
        sys.exit(1)
