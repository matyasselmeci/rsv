#!/usr/bin/env python

# Standard libraries
import os
import re
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
    trim_length = config.get("rsv", "details_data_trim_length")
    if trim_length > 0:
        rsv.log("Trimming data to %s bytes because details_data_trim_length is set" %
                trim_length, 2)
        data = data[:trim_length]

    #
    # We want to print the time different depending on the consumer
    #
    utc_timestamp   = utils.timestamp()
    local_timestamp = utils.timestamp(local=True)

    this_host = socket.getfqdn()

    utc_summary   = get_summary(status, this_host, utc_timestamp,   data)
    local_summary = get_summary(status, this_host, local_timestamp, data)
    
    #
    # Create a record for each consumer
    #
    for consumer in re.split("\s*,\s*", config.get("rsv", "consumers")):
        if not consumer.isspace():
            create_consumer_record(consumer, utc_summary, local_summary)

    # 
    # Print the local summary to the screen
    #
    rsv.log("\n\n", 2) # separate final output from debug output
    rsv.log(local_summary, 1)

    #
    # enhance - should we have different exit codes based on status?
    #
    rsv.clean_up()
    sys.exit(0)



def get_summary(status, this_host, timestamp, data):
    """ Generate a summary string
    Currently metricStatus and summaryData are identical (per RSVv3)
    """

    try:
        metricType = config.get(options.metric, "metricType")
        type =       config.get(options.metric, "type")
    except ConfigParser.NoOptionError:
        rsv.fatal("gs1: metricType or type not defined in config")

    result  = "metricName: %s\n"   % options.metric
    result += "metricType: %s\n"   % metricType
    result += "timestamp: %s\n"    % timestamp
    result += "metricStatus: %s\n" % status
    result += "serviceType: %s\n"  % type
    result += "serviceURI: %s\n"   % options.uri
    result += "gatheredAt: %s\n"   % this_host
    result += "summaryData: %s\n"  % status
    result += "detailsData: %s\n"  % data
    result += "EOT\n"
    
    return result



def create_consumer_record(consumer, utc_summary, local_summary):
    """ Make a file in the consumer records area """

    # Check/create the directory that we'll put record into
    output_dir = os.path.join(rsv_loc, "output", consumer)

    if not validate_directory(output_dir):
        rsv.log("WARNING: Cannot write record for consumer '%s'" % consumer, 1, 0)
    else:
        prefix = options.metric + "."
        (file_handle, file_path) = tempfile.mkstemp(prefix=prefix, dir=output_dir)

        # todo - allow for consumer config files that specify which time to use
        # for now we'll just give the html-consumer local time, and UTC to the rest
        if consumer == "html-consumer":
            os.write(file_handle, local_summary)
        else:
            os.write(file_handle, utc_summary)

        os.close(file_handle)

    return


def validate_directory(output_dir):
    """ Validate the directory and create it if it does not exist """

    rsv.log("Validating directory '%s'" % output_dir, 3, 0)
    
    if os.path.exists(output_dir):
        rsv.log("Directory '%s' already exists" % output_dir, 3, 4)
        if os.access(output_dir, os.W_OK):
            rsv.log("Directory '%s' is writable" % output_dir, 3, 4)
            return True
        else:
            rsv.log("WARNING: Directory '%s'is NOT writable by user '%s'" %
                    (output_dir, os.getlogin()), 1, 4)
            return False


    rsv.log("Creating directory '%s'" % output_dir, 2, 0)

    if not os.access(os.path.dirname(output_dir), os.W_OK):
        rsv.log("WARNING: insufficient privileges to make directory '%s'." % output_dir, 1, 4)
        return False
    else:
        try:
            os.mkdir(output_dir, 0755)
        except OSError:
            rsv.log("WARNING: Failed to make directory '%s'." % output_dir, 1, 4)
            return False

    return True



def missing_user_proxy():
    """ CRITICAL status if we don't have a proxy """
    status = "CRITICAL"
    data   = "No proxy is setup in rsv.conf.\n\n"
    data  += "To use a service certificate (recommended), set the following variables:\n"
    data  += "service_cert, service_key, service_proxy\n\n"
    data  += "To use a user certificate, set the following variable:\n"
    data  += "proxy_file"
    print_result(status, data)



def missing_user_proxy(proxy_file):
    """ CRITICAL status if user proxy is missing """
    status = "CRITICAL"
    data   = "proxy_file is set in rsv.conf, but the file '%s' does not exist." % proxy_file
    print_result(status, data)



def expired_user_proxy(proxy_file, openssl_output, minutes_til_expiration):
    """ CRITICAL status if proxy file is expired """
    
    status = "CRITICAL"
    data   = "Proxy file '%s' is expired (or is expiring within %s minutes)\n\n" %\
             (proxy_file, minutes_til_expiration)
    data  += "openssl output:\n%s" % openssl_output
    
    print_result(status, data)


def service_proxy_renewal_failed(cert, key, proxy, openssl_output):
    """ CRITICAL status if we can't renew the proxy """

    status = "CRITICAL"
    data   = "Proxy file '%s' could not be renewed.\n" % proxy
    data  += "Service cert - %s\n" % cert
    data  += "Service key  - %s\n" % key
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


def job_timed_out(command, timeout):
    status = "CRITICAL"
    data   = "Timeout hit - execution of the job exceeded %s seconds\n\n" % timeout
    data  += "Job run:\n%s\n\n" % command

    print_result(status, data)
