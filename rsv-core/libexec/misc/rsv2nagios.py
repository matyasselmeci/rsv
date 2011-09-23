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
	theurl="URL?"
	theurl=theurl+"cmd_typ=30"
	theurl=theurl+"&cmd_mod=2"
	theurl=theurl+"&service=SERVICE"
	theurl=theurl+"&host=HOST"
	theurl=theurl+"&plugin_state=PLUGIN_STATE"
	theurl=theurl+"&plugin_output=PLUGIN_OUTPUT"
	theurl=theurl+"&btnSubmit=Commited"

	PLUGIN_OUTPUT=string.strip(PLUGIN_OUTPUT)
	PLUGIN_OUTPUT=string.replace(PLUGIN_OUTPUT," ","+")
	PLUGIN_OUTPUT=urllib.quote(PLUGIN_OUTPUT)

	theurl=string.replace(theurl,"URL",URL)
	theurl=string.replace(theurl,"SERVICE",SERVICE)
	theurl=string.replace(theurl,"HOST",HOST)
	theurl=string.replace(theurl,"PLUGIN_OUTPUT",PLUGIN_OUTPUT)
	theurl=string.replace(theurl,"PLUGIN_STATE",PLUGIN_STATE)

	# now the user name and password

	req = urllib2.Request(theurl)
	try:
	    handle = urllib2.urlopen(req)
	except IOError, e:
	    pass
	else:
	    # Here I will have to put code to deal with unauthenticated pages
	    print "No authentication, I will exit"
	    sys.exit(1)


	if not hasattr(e, 'code') or e.code != 401:
	    # we got an error - but not a 401 error
	    print "This page isn't protected by authentication."
	    print 'But we failed for another reason.'
	    print e
	    sys.exit(1)

	authline = e.headers['www-authenticate']

	authobj = re.compile(
	    r'''(?:\s*www-authenticate\s*:)?\s*(\w*)\s+realm=['"]([^'"]+)['"]''',
	    re.IGNORECASE)
	# this regular expression is used to extract scheme and realm
	matchobj = authobj.match(authline)

	if not matchobj:
	    # if the authline isn't matched by the regular expression
	    # then something is wrong
	    print 'The authentication header is badly formed.'
	    print authline
	    sys.exit(1)

	scheme = matchobj.group(1)
	realm = matchobj.group(2)
	# here we've extracted the scheme
	# and the realm from the header
	if scheme.lower() != 'basic':
	    print 'This code only works with BASIC authentication.'
	    sys.exit(1)

	base64string = base64.encodestring(
			'%s:%s' % (USERNAME, PASSWORD))[:-1]
	authheader =  "Basic %s" % base64string
	req.add_header("Authorization", authheader)
	try:

	    handle = urllib2.urlopen(req)

	except IOError, e:
            if hasattr(e, 'code') and e.code==404:
            #The NAGIOS_URL parameter is wrong
                print "NAGIOS_URL "+URL+" returned 404 not found."
		sys.exit(1)
	    # Username/password is wrong
	    print "It looks like the username or password is wrong."
            print e;
	    sys.exit(1)

	thepage = handle.read()

	for line in string.split(thepage,"\n"):
	  if string.find(line,"<P><DIV CLASS='infoMessage'>")!=-1:
	    message=string.replace(line,"<P><DIV CLASS='infoMessage'>","")
	    message=string.replace(message,"<BR><BR>","")
	    print message
	  if string.find(line,"<P><DIV CLASS='errorMessage'>")!=-1:
	    message=string.replace(line,"<P><DIV CLASS='errorMessage'>","")
	    message=string.replace(message,"</DIV></P>","")
	    print message


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
