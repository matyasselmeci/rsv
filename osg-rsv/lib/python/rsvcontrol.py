#!/usr/bin/env python
# rsvcontrol.py
# Marco Mambelli <marco@hep.uchicago.edu>

import os 
import re
import sys
import time
import socket
from optparse import OptionParser

import osgrsv
import table

try:
    import logging
    rootlog = logging.getLogger('osgrsv.rsvcontrol')

    # create console handler and set level to warning
    # --verbose will set the console handler level to INFO
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    ch.setFormatter(formatter)
    ch.setLevel(logging.WARNING)
    rootlog.addHandler(ch)
    
    # Create a log file with more information
    # TODO: add log dir in VDT installation?
    hdlr = logging.FileHandler('/tmp/rsv-control.%s.log' % os.getuid())
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    hdlr.setFormatter(formatter)
    hdlr.setLevel(logging.INFO)
    rootlog.addHandler(hdlr)

    # set general level to DEBUG so that handlers can set the level
    rootlog.setLevel(logging.DEBUG)
    log = rootlog

    #TODO: ideally extend the logger class adding the method
    def set_console_logging_level(level):
        """Set console logging level.
        Level can be a number or one of the strings: DEBUG, INFO, WARNING, ERROR, CRITICAL
        """
        handlers = [i for i in log.handlers if isinstance(i, logging.StreamHandler)]
        l_level = level
        if level == 'DEBUG':
            l_level = logging.DEBUG
        elif level == 'INFO':
            l_level = logging.INFO
        elif level == 'WARNING':
            l_level = logging.WARNING
        elif level == 'ERROR':
            l_level = logging.ERROR
        elif level == 'CRITICAL':
            l_level = logging.CRITICAL
        for i in handlers:
            i.setLevel(l_level)
            
except ImportError:
    # logging available starting python 2.3
    import altlogging
    log = altlogging.LogFake()    
    set_console_logging_level = altlogging.set_console_logging_level


SUBMISSION_LIST_FORMATS = ['brief', 'long', 'full', 'log', 'out', 'err']
LIST_FORMATS = ['local'] + SUBMISSION_LIST_FORMATS

_cacheHostName = None
def getLocalHostName():
    global _cacheHostName
    if not _cacheHostName:
        try:
            _cacheHostName = os.environ.get('HOSTNAME', socket.gethostname())
        except:
            _cacheHostName = 'localhost'
    return _cacheHostName

def processoptions(arguments=None):
    usage = """usage: rsv-control [ --verbose ] 
      --help | -h 
      --version
      --list [ --wide | -w ] [ --all ] [ --format <format> ] [ <pattern> ]
      --on        [METRIC ...]
      --off       [METRIC ...]
      --enable    [--user <user>] --host <host-name> METRIC [METRIC ...]
      --disable   --host <host-name> METRIC [METRIC ...]
      --full-test [--user <user>] --host <host-name> METRIC [METRIC ...]
      --test      [--user <user>] --host <host-name> METRIC [METRIC ...]
    """
    version = "rsv-control 0.14"
    description = """This script is used to control or verify a probe."""
    parser = OptionParser(usage=usage, description=description, version=version)
    parser.add_option("--vdt-install", dest="vdtlocation", default=None,
                      help="Root directory of the OSG installation", metavar="DIR")
    parser.add_option("--verbose", action="store_true", dest="verbose", default=False,
                      help="Verbose output")
    parser.add_option("-l", "--list", action="store_true", dest="rsvctrl_list", default=False,
                      help="List probe information.  If <pattern> is supplied, only probes matching the regular expression pattern will be displayed")
    parser.add_option("-w", "--wide", action="store_true", dest="list_wide", default=False,
                      help="Wide list display to avoid truncation in metric listing")
    parser.add_option("--all", action="store_true", dest="list_all", default=False,
                      help="Display all metrics, including metrics not enabled on any host.")
    parser.add_option("--format", dest="list_format", choices=tuple(LIST_FORMATS), default='local',
                      help="Specify the list format (%s; default: %%default)" % (LIST_FORMATS,))
    parser.add_option("--on", action="store_true", dest="rsvctrl_on", default=False,
                      help="Turn on all enabled metrics.  If a metric is specified, turn on only that metric.")
    parser.add_option("--off", action="store_true", dest="rsvctrl_off", default=False,
                      help="Turn off all running metrics.  If a metric is specified, turn off only that metric.")
    parser.add_option("--enable", action="store_true", dest="rsvctrl_enable", default=False,
                      help="Enable metric. May be specified multiple times.")
    parser.add_option("--disable", action="store_true", dest="rsvctrl_disable", default=False,
                      help="Disable metric. May be specified multiple times.")
    #parser.add_option("--setup", action="store_true", dest="rsvctrl_setup", default=False,
    #                  help="NOT READY... COMING SOON: Setup the RSV installation (change file permissions, start Condor, ...)")
    parser.add_option("--test", action="store_true", dest="rsvctrl_test", default=False,
                      help="Run a probe and return its output.")
    parser.add_option("--full-test", action="store_true", dest="rsvctrl_full_test", default=False,
                      help="Test a probe within OSG-RSV. Probe is executed only once, immediately.")
    parser.add_option("--user", dest="user", default=None,
                      help="Specify the user to run OSG-RSV probes")
    parser.add_option("--host", dest="uri", default=None,
                      help="Specify the host FQDN and optionally the port to be used by the probe (e.g. host or host:port)")
    parser.add_option("--host-file", dest="uri_file", default=None,
                      help="Supply a path to a file containing the hosts to test against, one host per line (overrides --host)")
    #group = OptionGroup(parser, "Gratia Options",
    #                    "Enable and configure the upload to the RSV collector in Gratia")
    #group.add_option("--gratia", action="store_true", dest="gratia", default=False, 
    #                 help="Enable Gratia output (default: %default)")
    #parser.add_option_group(group)
    #parser.add_option("-v", "--verbose",
    #                  action="store_true", dest="probe_verbose", default=None,
    #                  help="Pass the --verbose flag to all probes")
    #parser.add_option("-t", "--time", dest="crontime", default=None,
    #                  help="Set the cron TIME to repeat the probe (format min-hour-day-mon-wday, e.g. '%s')" % (OPTIONS_DEFAULT.crontime,), metavar="TIME") 
    #parser.add_option("--vo-name", dest="probe_voname", default=None,
    #                  help="Pass supplied argument with --virtual-organization flag to the probes")
    #parser.add_option("--print-local-time", dest="probe_localtime", default=None,
    #                  help="Pass the --print-local-time flag to all probes")


    #parser.disable_interspersed_args()
    #default: (options, args) = parser.parse_args(sys.argv[1:]) - alt args possible
    if arguments == None:
        (options, args) = parser.parse_args()
    else:
        (options, args) = parser.parse_args(arguments)

    # Check options consistency
    # parser.error() prints the message and exits with ec 2
    if not options.vdtlocation:
        options.vdtlocation = osgrsv.findPathOSG()
    if not options.vdtlocation:
        parser.error("VDT_LOCATION is not set.\nEither set this environment variable, or pass the --vdt-location command line option.")

    # Ownership problem:
    # - probes should not be submittted to condor as root
    # - enable/disable/test require ownership of the directory tree
    tmp_fname = os.path.join(options.vdtlocation, osgrsv.OSGRSV_NAME)
    file_uid = os.stat(tmp_fname)[4]   # stat.ST_UID=4
    user_id = os.getuid()
    number_of_commands = len([i for i in [options.rsvctrl_enable, options.rsvctrl_disable, options.rsvctrl_test, options.rsvctrl_on,
                                          options.rsvctrl_off, options.rsvctrl_full_test, options.rsvctrl_list] if i])
    if number_of_commands > 1:
        parser.error("Commands are mutually exclusive, you can use only one of list, test, enable, disable.")
    if number_of_commands == 0:
        parser.error("Invalid syntax. You must specify one command.")

    # rsvctrl_test is OK since it is not touching the files in the RSV directory
    if options.rsvctrl_enable or options.rsvctrl_disable or options.rsvctrl_full_test:       
        if not file_uid == user_id:
            parser.error("Operation not possible. You are not the owner of the installation in: %s." % (tmp_fname))
            #exit(2)
        # root cannot submit jobs
        # root can disable jobs of other users
        if user_id == 0 and not options.user and not options.rsvctrl_disable: 
            #running as root
            log.error('You cannot run the jobs as root, use "--user <username>" to submit the jobs as a different user.')
            tmp_fname = os.path.join(options.vdtlocation, "osg/etc/config.ini")
            if os.path.isfile(tmp_fname):
                tmp_user = osgrsv.getConfigOSG(tmp_fname).get("RSV", "rsv_user")
                log.error("The user in osg/etc/config.ini is %s." % (tmp_user,))
            parser.error("Run with --user <user>")
    return args, options


def new_table(header, options):
    table_ = table.Table((58, 20))
    if options.list_wide:
        table_.truncate = False
    else:
        table_.truncate_leftright = True
    table_.makeFormat()
    table_.makeHeader(header, 'Service')
    return table_


def list_probes(rsv, options, pattern):
    log.info("Listing all probes")
    retlines = []
    num_metrics_displayed = 0
    num_disabled_probes = 0

    probelist = rsv.getConfiguredProbes(options=options)
    if options.list_format == 'local':
        tables = {} # to hold one table per host
        tables['DISABLED'] = new_table('DISABLED METRICS', options)

        for probe in probelist:
            pmetric = probe.metricName

            if pattern and not re.search(pattern, pmetric):
                continue

            ptype = probe.getType()
            ret_list_uri = []
            ret_list_status = []
            for uri in probe.urilist:
                if not uri in tables:
                    tables[uri] = new_table("Metrics running on host: " + uri, options)

                # If the user supplied --host, only show that host's metrics
                if options.uri and options.uri != uri:
                    continue

                rets = probe.status(uri)
                log.debug("Metric %s (%s): %s on %s" % (pmetric, ptype, rets, uri))
                if rets == "ENABLED":
                    ret_list_uri.append(uri)
                else:
                    if not rets in ret_list_status:
                        ret_list_status.append(rets)

            if not ret_list_uri:
                # should I just add DISABLED?
                # if multiple status are appearing probably there is an error
                for i in ret_list_status:
                    tables['DISABLED'].addToBuffer(pmetric, ptype)
                    num_disabled_probes += 1
                continue
            
            for i in ret_list_uri:                        
                tables[i].addToBuffer(pmetric, ptype)

            num_metrics_displayed += 1

        # After looping on all the probes, create the output
        for host in sorted(tables.keys()):
            if host != "DISABLED" and not tables[host].isBufferEmpty():
                retlines.append(tables[host].getHeader())
                retlines += tables[host].formatBuffer()
                retlines += "\n"

        if options.list_all:
            if num_disabled_probes > 0:
                retlines.append("The following metrics are not enabled on any host:")
                retlines.append(tables["DISABLED"].getHeader())
                retlines += tables["DISABLED"].formatBuffer()
        elif num_disabled_probes > 0:
            tmp = ""
            if pattern:
                tmp = " that match the supplied pattern"
            retlines.append("The are %i disabled metrics%s.  Use --all to display them." % \
                            (num_disabled_probes, tmp))
            
    else:
        # Format != 'local'
        for probe in probelist:
            if pattern and not re.search(pattern, probe.metricName):
                continue
                            
            retlines.append("%s" % (probe.getKey(),))
            for uri in probe.urilist:
                if options.uri and options.uri != uri:
                    continue
                                    
                if options.list_format in SUBMISSION_LIST_FORMATS:
                    rets = probe.submission_status(uri, format=options.list_format)
                else:
                    rets = probe.status(uri)

                retlines.append("               %-30s : %s" % (uri, rets))
                num_metrics_displayed += 1

    if not probelist:
        log.error("No configured probes!")
    else:
        print '\n' + '\n'.join(retlines) + '\n'
        if num_metrics_displayed == 0:
            print "No metrics matched your query.\n"
    return


def main_rsv_control():
    # Option error checking is handled in the processoptions subroutine
    args, options = processoptions()
        
    if options.verbose:
        set_console_logging_level(logging.INFO)
        log.info("%s: Executing rsvcontrol: %s" % (time.asctime(), sys.argv))
    # init configuration

    # take care of RSV cert?
    if options.user:
        rsv = osgrsv.OSGRSV(options.vdtlocation, user=options.user)
    else:        
        rsv = osgrsv.OSGRSV(options.vdtlocation)

    # listing probes
    if options.rsvctrl_list:
        if not args:
            list_probes(rsv, options, "")
        else:
            list_probes(rsv, options, args[0])
        return

    # Non-list options
    elif (options.rsvctrl_on      or options.rsvctrl_off  or options.rsvctrl_enable or
          options.rsvctrl_disable or options.rsvctrl_test or options.rsvctrl_full_test):
        # retrieve all probes and restrict to the selected ones
        #TODO: getConfiguredProbes or getInstalledProbes?
        # how about installation of new probes?
        all_probes = rsv.getConfiguredProbes(options=options) # getInstalledProbes()

        all_metrics = {}
        for p in all_probes:
            all_metrics[p.metricName] = p

        sel_metrics = []
        for i in args:
            if i in all_metrics:
                sel_metrics.append(all_metrics[i])
            else:
                log.warning("No matching metric for input '%s'" % i)

        # --on and --off can accept no probes, then they just enable everything
        if not sel_metrics and not (options.rsvctrl_on or options.rsvctrl_off):
            log.error("No metrics matching your input. No action taken.")
            return

        # Parse the --host-file if they supply one
        uri_list = []
        if options.uri_file:
            if not options.rsvctrl_full_test and not options.rsvctrl_test:
                print "WARNING: --host-file argument should only be used with --test and --full-test"
            else:
                if not os.path.exists(options.uri_file):
                    log.error("host-file passed '%s' does not exist" % options.uri_file)
                    return
                for line in open(options.uri_file).readlines():
                    uri_list.append(line.strip())
            
        if options.uri:
            uri = options.uri
        else:
            uri = getLocalHostName()
            log.info("No URI provided, assuming localhost: '%s'" % uri)

        log.debug("%s probes selected. (e/d/t/ft: %s/%s/%s/%s)" % (len(sel_metrics), options.rsvctrl_enable, 
                                                                   options.rsvctrl_disable, options.rsvctrl_test,
                                                                   options.rsvctrl_full_test))
        if options.rsvctrl_on:
            pass
        elif options.rsvctrl_off:
            rsv.stop(sel_metrics)
        elif options.rsvctrl_disable:
            for metric in sel_metrics:
                print "Disabling " + metric.getName() + ":" 
                metric.disable(uri)
                print "Metric disabled\n"
        elif options.rsvctrl_full_test:
            for p in sel_metrics:
                ec = p.full_test(uri)
                if ec == 0:
                    print "Metric tested"
                else:
                    print "Metric test failed"
        elif options.rsvctrl_test:
            for p in sel_metrics:
                if uri_list:
                    for uri in uri_list:
                        print p.test(uri)
                else:
                    print p.test(uri)
        elif options.rsvctrl_enable:
            for metric in sel_metrics:
                print "Enabling " + metric.getName() + ":" 
                if metric.isEnabled(uri):
                    print "    Metric " + metric.metricName + " is already running against " + uri + ".  No action taken at this time."
                    print "    If you changed some information and would like to restart the probe, please disable the probe first and then enable it."
                    continue
                metric.enable(uri)
                print "Metric enabled\n"
        return
    #elif options.rsvctrl_setup:
    #    log.error("Not yet implemented")
    #    return
    else:
        log.error("Unknown request")
    return
    
def main():
    print "Wrong invocation!"
    
if __name__ == "__main__":
    progname = os.path.basename(sys.argv[0])
    if progname == 'rsv-control' or progname == 'rsvcontrol.py':
        main_rsv_control()
    else:
        main()
