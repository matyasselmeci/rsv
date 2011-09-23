#!/usr/bin/python

import urllib2
import urllib
import sys
import re
import base64
from urlparse import urlparse
import string
import ConfigParser
import os

def translate_rsv_2_nagios(rsvOutput):
    nagiosCode = {}
    nagiosCode["OK"]="0"
    nagiosCode["CRITICAL"]="2"
    nagiosCode["WARNING"]="1"
    nagiosCode["UNKNOWN"]="3"

    nagiosStatus=nagiosCode["UNKNOWN"]
    nagiosOutput="RSV probe has no summaryData/detailsData"
    nagiosHost="UNKNOWN"
    detailsDataField=""
    for line in string.split(rsvOutput,"\n"):
        if string.find(line,"serviceURI")==0:
            nagiosHost=string.strip(string.split(line,":")[1])
        if string.find(line,"metricStatus")==0:
            status=string.strip(string.split(line,":")[1])
            nagiosStatus = nagiosCode[status]
        if detailsDataField!="":
            detailsDataField+=string.strip(line)
        if string.find(line,"detailsData")==0:
            detailsDataField=string.strip(string.split(line,":",1)[1])
    if detailsDataField!="":
         nagiosOutput=detailsDataField[0:255]
    return (nagiosStatus,nagiosOutput,nagiosHost)


def send_2_nagios(URL, SERVICE, HOST, USERNAME, PASSWORD, PLUGIN_STATE, PLUGIN_OUTPUT): 

        # send_nsca -H $nagios_host
        # $HOST, $SERVICE, $PLUGIN_STATE, $PLUGIN_OUTPUT

        nsca_cmd="/usr/sbin/send_nsca -d , -H " + URL
        nsca_id=os.popen(nsca_cmd, "w")
        nsca_id.write(HOST + "," + SERVICE + "," + PLUGIN_STATE + "," + PLUGIN_OUTPUT + "\n")
        nsca_id.close()


#MAIN
#Get the RSV probe output, host and state from STDIN and convert to NAGIOS format
rsvOutput=""
for line in sys.stdin.readlines():
        rsvOutput = rsvOutput + line
(PLUGIN_STATE,PLUGIN_OUTPUT,PLUGIN_HOST)=translate_rsv_2_nagios(rsvOutput)

#Get the NAGIOS server, username and password from the config file
if not os.path.exists(sys.argv[1]):
    print "ERROR: The supplied configuration file '%s' does not exist." % sys.argv[1]
    sys.exit(1)

config = ConfigParser.ConfigParser();
config.read(sys.argv[1]);
NAGIOS_URL=config.get("RSV", "NAGIOS_URL");
NAGIOS_USERNAME=config.get("RSV", "NAGIOS_USERNAME");
NAGIOS_PASSWORD=config.get("RSV", "NAGIOS_PASSWORD");
#Send output to NAGIOS server, using the service name passed by the nagios consumer
send_2_nagios(NAGIOS_URL, sys.argv[2], PLUGIN_HOST, NAGIOS_USERNAME, NAGIOS_PASSWORD, PLUGIN_STATE, PLUGIN_OUTPUT);
