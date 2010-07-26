#!/usr/bin/env python

# Standard libraries
import os
import sys
import time
import socket
import tempfile

# RSV libraries
import rsv
import utils

# todo -remove before release
import pdb

options = None
config  = None
rsv_loc = None

def print_result(status, data):
    """ Print the result to all consumers """

    #
    # Trim the data appropriately based on details_data_trim_length.
    # A value of 0 means do not trim it.
    #
    if config["details_data_trim_length"] > 0:
        rsv.log("Trimming data to %s bytes because details_data_trim_length is set" %
                config["details_data_trim_length"], 2)
        data = data[:config["details_data_trim_length"]]

    #
    # We want to print the time different depending on the consumer
    #
    utc_timestamp   = utils.timestamp()
    local_timestamp = utils.timestamp(local=True)

    this_host = socket.getfqdn()

    utc_summary   = get_summary(status, this_host, utc_timestamp,   data)
    local_summary = get_summary(status, this_host, local_timestamp, data)
    

    # 
    # Print the local summary to the screen
    #
    rsv.log("\n\n", 2) # separate final output from debug output
    rsv.log(local_summary, 1)

    #
    # print to the rest of the consumers
    #
    for consumer in config["consumers"]:
        create_consumer_record(consumer, utc_summary, local_summary)

    #
    # enhance - should we have different exit codes based on status?
    #
    rsv.clean_up()
    sys.exit(0)



def get_summary(status, this_host, timestamp, data):
    """ Generate a summary string
    Currently metricStatus and summaryData are identical (per RSVv3)
    """

    result  = "metricName: %s\n"   % options.metric
    result += "metricType: %s\n"   % config["metricType"]
    result += "timestamp: %s\n"    % timestamp
    result += "metricStatus: %s\n" % status
    result += "serviceType: %s\n"  % config["type"]
    result += "serviceURI: %s\n"   % options.uri
    result += "gatheredAt: %s\n"   % this_host
    result += "summaryData: %s\n"  % status
    result += "detailsData: %s\n"  % data
    result += "EOT\n"
    
    return result



def create_consumer_record(consumer, utc_summary, local_summary):
    """ Make a file in the consumer records area """

    # Check that the directory exists
    output_dir = os.path.join(rsv_loc, "output", consumer)
    if not os.path.exists(output_dir):
        os.mkdir(output_dir, 0755)

    prefix = options.metric + "."
    (file_handle, file_path) = tempfile.mkstemp(prefix=prefix, dir=output_dir)

    # todo - allow for consumer config files that specify which time to use
    # for now we'll just give the html-consumer local time, and UTC to the rest
    if consumer == "html-consumer":
        os.write(file_handle, local_summary)
    else:
        os.write(file_handle, utc_summary)
    os.close(file_handle)



def missing_user_proxy():
    """ CRITICAL status if user proxy is missing """
    status = "CRITICAL"
    data   = "Proxy file '" + config["proxy_file"] + "' does not exist."
    print_result(status, data)


def expired_user_proxy(openssl_output):
    """ CRITICAL status if proxy file is expired """

    status = "CRITICAL"
    data   = "Proxy file '%s'' is expired (or is expiring within 10 minutes)\n\n" % config["proxy_file"]
    data  += "openssl output:\n%s" % openssl_output
    
    print_result(status, data)


def service_proxy_renewal_failed(openssl_output):
    """ CRITICAL status if we can't renew the proxy """

    status = "CRITICAL"
    data   = "Proxy file '%s' could not be renewed.\n" % config["service_proxy"]
    data  += "Service cert - %s\n" % config["service_cert"]
    data  += "Service key  - %s\n" % config["service_key"]
    data  += "openssl output:\n%s" % openssl_output
    
    print_result(status, data)


def ping_failure(output):
    """ CRITICAL status if we can't ping remote host """
    
    status = "CRITICAL"
    data   = "Failed to ping host\n\n"
    data  += "Troubleshooting:\n"
    data  += "  Is the network available?\n"
    data  += "  Is the remote host available?\n\n"
    data  += "Ping output:\n%s" % output

    print_result(status, data)


def local_job_failed(command, output):
    status = "CRITICAL"
    data   = "Failed to run local job\n\n"
    data  += "Job run:\n%s\n\n" % command
    data  += "Output:\n%s" % output

    print_result(status, data)


def remote_job_failed(command, output):
    status = "CRITICAL"
    data   = "Failed to run job via globus-job-run\n\n"
    data  += "Job run:\n%s\n\n" % command
    data  += "Output:\n%s" % output

    print_result(status, data)
