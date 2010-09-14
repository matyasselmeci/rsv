#!/usr/bin/env python

import re
import sys

import Host
import Table
import Condor
import Metric
import Consumer

import pdb

def new_table(header, options):
    """ Return a new table with default dimensions """
    table_ = Table.Table((58, 20))
    if options.list_wide:
        table_.truncate = False
    else:
        table_.truncate_leftright = True
    table_.makeFormat()
    table_.makeHeader(header, 'Service')
    return table_


def list_metrics(rsv, options, pattern):
    """ List metrics to the screen """

    rsv.log("INFO", "Listing all metrics")
    retlines = []
    num_metrics_displayed = 0

    metrics = rsv.get_metric_info()
    hosts   = rsv.get_host_info()
    used_metrics = {}

    # Form a table for each host listing enabled metrics
    for host in hosts:
        table = new_table("Metrics enabled for host: %s" % host.host, options)

        enabled_metrics = host.get_enabled_metrics()

        if enabled_metrics:
            for metric in host.get_enabled_metrics():
                used_metrics[metric] = 1
                if pattern and not re.search(pattern, metric):
                    continue
                
                metric_type = metrics[metric].get_type()
                table.addToBuffer(metric, metric_type)
                num_metrics_displayed += 1
        else:
            pass

        # We don't skip this host earlier in the loop so that we can get
        # a correct number for the disabled hosts.
        if options.host and options.host != host.host:
            rsv.log("DEBUG", "Not displaying host '%s' because --host %s was supplied." %
                    (host.host, options.host))
            continue

        if not table.isBufferEmpty():
            retlines.append(table.getHeader())
            retlines += table.formatBuffer()
            retlines += "\n"
                                

    # Find the set of metrics not enabled on any host
    num_disabled_metrics = 0
    table = new_table('DISABLED METRICS', options)        
    for metric in metrics:
        if metric not in used_metrics:
            if pattern and not re.search(pattern, metric):
                continue
            num_disabled_metrics += 1
            metric_type = metrics[metric].get_type()
            table.addToBuffer(metric, metric_type)

    # Display disabled metrics
    if options.list_all:
        if num_disabled_metrics > 0:
            retlines.append("The following metrics are not enabled on any host:")
            retlines.append(table.getHeader())
            retlines += table.formatBuffer()
    elif num_disabled_metrics > 0:
        tmp = ""
        if pattern:
            tmp = " that match the supplied pattern"

        retlines.append("The are %i metrics not enabled on any host%s.  Use --all to display them." %
                        (num_disabled_metrics, tmp))
            

    # Display the result
    if not metrics:
        rsv.log("ERROR", "No installed metrics!")
    else:
        print '\n' + '\n'.join(retlines) + '\n'
        if num_metrics_displayed == 0:
            print "No metrics matched your query.\n"

    return True


def job_list(rsv, hostname=None):
    """ Display jobs running similar to condor_cron_q but in a better format """
    condor = Condor.Condor(rsv)

    if not condor.is_condor_running():
        rsv.echo("ERROR: condor-cron is not running.")
        return False

    if condor.display_jobs(hostname):
        return True
    else:
        return False


def dispatcher(rsv, action, jobs=None, hostname=None):
    """ Handle on, off, enable, disable.  Determine if jobs are metrics or
    consumers. """

    condor = Condor.Condor(rsv)

    if not condor.is_condor_running():
        rsv.echo("ERROR: condor-cron is not running.")
        return False

    # 
    # If we are not passed specific jobs to start, start all metrics and consumers
    #
    if not jobs:
        if action == "start":
            return start_all_jobs(rsv, condor)
        elif action == "stop":
            return stop_all_jobs(rsv, condor)
        elif action == "enable":
            rsv.echo("ERROR: You must supply metrics/consumers to enable")
            return False
        elif action == "disable":
            rsv.echo("ERROR: You must supply metrics/consumers to disable")
            return False
            
    #
    # If we are passed a list of specific metrics/consumers, determine whether each
    # item in the list is a metric or consumer, and send to the appropriate function
    #
    else:
        # Since a user can input either metric of consumer names we need to get a list
        # of the installed metrics and consumers and check which category each job is in.
        available_metrics   = rsv.get_installed_metrics()
        available_consumers = rsv.get_installed_consumers()

        host = None
        if hostname:
            host = Host.Host(hostname, rsv)

        num_errors = 0
        write_config_file = False

        for job in jobs:
            is_metric   = job in available_metrics
            is_consumer = job in available_consumers
            
            if is_metric and is_consumer:
                rsv.log("WARNING", "Both a metric and a consumer are installed with the name '%s'. " +
                        "Not starting either one" % job)
                num_errors += 1
            elif not is_metric and not is_consumer:
                rsv.log("WARNING", "Supplied job '%s' is not an installed metric or consumer" % job)
                num_errors += 1
            elif is_metric:
                if not host:
                    rsv.log("ERROR", "When passing specific metrics you must also specify a host.")
                    num_errors += 1
                    continue

                metric = Metric.Metric(job, rsv, hostname)

                if action == "start":
                    num_errors += start_metric(rsv, condor, metric, host)
                elif action == "stop":
                    num_errors += stop_metric(rsv, condor, metric, host)
                elif action == "enable":
                    write_config_file |= enable_metric(rsv, metric, host)
                elif action == "disable":
                    write_config_file |= disable_metric(rsv, metric, host)

            elif is_consumer:
                consumer = Consumer.Consumer(job, rsv)

                if action == "start":
                    num_errors += start_consumer(rsv, condor, consumer)
                elif action == "stop":
                    num_errors += stop_consumer(rsv, condor, consumer)
                elif action == "enable":
                    enable_consumer(rsv, consumer)
                elif action == "disable":
                    disable_consumer(rsv, consumer)

        if write_config_file:
            host.write_config_file()

        if num_errors > 0:
            actions = {"start" : "starting", "stop" : "stopping", "enable" : "enabling", "disable" : "disabling" }
            plural  = ""
            if len(jobs) > 1:
                plural = "s"
            rsv.log("ERROR", "Problem %s %s job%s." % (actions[action], num_errors, plural))
            return False
        else:
            return True



def start_all_jobs(rsv, condor):
    """ Start all metrics and consumers """

    num_errors = 0

    # Start all the metrics for each host
    for host in rsv.get_host_info():
        enabled_metrics = host.get_enabled_metrics()
        if len(enabled_metrics) > 0:
            rsv.echo("Starting %s metrics for host '%s'." % (len(enabled_metrics), host.host))
            for metric_name in enabled_metrics:
                metric = Metric.Metric(metric_name, rsv, host.host)
                if not condor.start_metric(metric, host):
                    num_errors += 1

    # Start the consumers
    enabled_consumers = rsv.get_enabled_consumers()
    if len(enabled_consumers) > 0:
        rsv.echo("Starting %s consumers." % len(enabled_consumers))
        for consumer in enabled_consumers:
            if not condor.start_consumer(consumer):
                num_errors += 1
    else:
        rsv.echo("No consumers are enabled.  Jobs will run but records will not be generated.")

    if num_errors > 0:
        return False

    return True


def start_metric(rsv, condor, metric, host):
    """ Start a single metric against the supplied host """

    rsv.echo("Starting metric '%s' against host '%s'" % (metric.name, host.host))

    if not condor.start_metric(metric, host):
        return 1

    return 0


def start_consumer(rsv, condor, consumer):
    """ Start a single consumer """

    rsv.echo("Starting consumer %s" % consumer.name)

    if not condor.start_consumer(consumer):
        return 1

    return 0



def stop_all_jobs(rsv, condor):
    """ Stop all metrics """

    rsv.echo("Stopping all metrics on all hosts.")
    if not condor.stop_jobs("OSGRSV==\"metrics\""):
        rsv.echo("ERROR: Problem stopping metrics.")
        return False

    rsv.echo("Stopping consumers.")
    if not condor.stop_jobs("OSGRSV==\"consumers\""):
        rsv.echo("ERROR: Problem stopping consumers.")
        return False

    return True


def stop_metric(rsv, condor, metric, host):
    """ Stop a single metric against the specified host """
    rsv.echo("Stopping metric '%s' for host '%s'" % (metric.name, host.host))
    metric = Metric.Metric(metric.name, rsv, host.host)
    if not condor.stop_jobs("OSGRSVUniqueName==\"%s\"" % metric.get_unique_name()):
        return 1

    return 0

def stop_consumer(rsv, condor, consumer):
    """ Stop a single consumer """ 
    rsv.echo("Stopping consumer %s" % consumer.name)
    if not condor.stop_jobs("OSGRSVUniqueName==\"%s\"" % consumer.get_unique_name()):
        return 1

    return 0


def enable_metric(rsv, metric, host):
    """ Enable the specified metric against the specified host. """

    rsv.echo("Enabling metric '%s' for host '%s'" % (metric.name, host.host))

    if host.metric_enabled(metric.name):
        rsv.echo("   Metric already enabled")
        return False
    else:
        host.set_config(metric.name, 1)
        return True
    
        
def enable_consumer(rsv, consumer):
    """ Enable the specified consumer. """
    
    rsv.echo("Enabling consumer %s" % consumer.name)

    if rsv.is_consumer_enabled(consumer.name):
        rsv.echo("   Consumer already enabled")
    else:
        rsv.enable_consumer(consumer.name)


def disable_metric(rsv, metric, host):
    """ Disable the specified metric against the specified host. """

    rsv.echo("Disabling metric '%s' for host '%s'" % (metric.name, host.host))

    if not host.metric_enabled(metric.name):
        rsv.echo("   Metric already disabled")
        return False
    else:
        host.set_config(metric.name, 0)
        return True


def disable_consumer(rsv, consumer):
    """ Disable the specified consumer """

    rsv.echo("Disabling consumer %s" % consumer.name)

    if not rsv.is_consumer_enabled(consumer.name):
        rsv.echo("   Consumer already disabled")
    else:
        rsv.disable_consumer(consumer.name)


