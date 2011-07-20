
------------------------------------------------------------------------------
 README.txt for OSG Resource & Service Validation (RSV)  Probes
------------------------------------------------------------------------------


WHAT IS THIS FILE?
-----------------

This README file describes various probes we're writing here at the OSG GOC to 
test resource and service availability (on OSG sites). 

The objective of the Resource and Service Validation project is to allow 
sites (and site admins) to run their own tests using the probes provided, 
and a combination of a scheduling infrastructure (that uses a cron feature
in Condor) and a Gratia based infrastructure (for uploading the results to
a central GOC maintained RSV database) -- those entities will be addressed 
in separate documents. 

The RSV probes are basically simple perl scripts that call various routines, 
in turn, within a OSG_Probe_Functions.pm perl module (also developed by us).
The probes test resources and services a resource may offer, and generate
a Gratia sender script, while also printing results in a format specified 
in the WLCG specs 0.91 [11].

Provided below are some relevant refererences:

 [0] VDT PACKAGE INSTALLATION, CONFIGURATION, TESTING OF 
     ENTIRE RSV INFRASTRUCTURE
  http://rsv.grid.iu.edu/documentation/vdt-package.html

 [1] TEST ONLY RSV PROBES (and not complete infrastructure)
  http://rsv.grid.iu.edu/documentation/rsv-testing.html#probes-only

 [2] RSV PROBE HELP PAGES (on the web)
  http://rsv.grid.iu.edu/documentation/help/

 [3] PROBES DEVELOPMENT HOME PAGE (on the web)
  http://rsv.grid.iu.edu/documentation/



WLCG STANDARDS
--------------

The probes are designed to conform to the WLCG standard as described here: 
 [11] https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification

Note: As of the date of writing this document, we only have probes that 
report status metrics; Probes that do performance metrics will be 
implemented later.


Note about Local (vs) Remote probes:
-----------------------------------
Local probes have the word "local" in their filename, and run on the
local host; where as all the other probes are run against a remote site.
The local probes are provided mainly to enable site admins to debug their
own "monitoring" hosts, especially during times when they are unable to
run the other probes on remote machines (possibly within their own site) 
because of an expired hostcert or some such. 


"Central monitoring" vs. "Site level monitoring" 
------------------------------------------------

It's important to disambiguate between the notion of "local vs. remote probes"
and that of "central/site-level monitoring".

The above notion of "local" and "remote" probes should not be confused with 
whether a probe is run "centrally" (for example, by the OSG Grid Operations 
Center aka GOC), or run at a "site level" by a site admin on a monitoring 
host that resides in their site.

The ultimate objective of the OSG leadership is to let site admins run
their own probes within their infrastructure, and have them upload results to 
a GOC database periodically and to have them displayed on a web interface.


------------------------------------------------------------------------------


HOW TO RUN A TYPICAL PROBE AND WHAT TO EXPECT BACK
--------------------------------------------------

The typical probe (unless specificied as local) runs tests against a remote
host and produces a Gratia sender python script, as follows:

 ./probe -u <hostname[:port][/service]> -m <metric name> --ggs


Each probe also returns output in the WLCG standard [11] output format 
 on STDOUT: 

metricName: org.osg.batch.jobmanagers-available
timestamp: 2007-06-18T17:24:59Z
metricStatus: OK
serviceType: other
serviceURI: itb-zero.uits.indiana.edu
gatheredAt: peart.ucs.indiana.edu
summaryData: OK
detailsData: Available Batch Schedulers are condor.pm fork.pm managedfork.pm 
EOT


Note about Service URI:
----------------------
 The probes use ServiceURIs to figure out which site to hit, so forth. As
of now, the only thing that matters is the hostname; the service name and port, 
for now, are ignored for all practical purposes, excepting for display. 
The serviceURI is the Globus service URI formatl; A typical serviceURI 
would be of the form:

     hostname[:port][/service] 

 I've used "other" as the service name for probes that don't specifically
test for a service, or ones that fall under no specific GLUE schema entry. 
You could use foo if you'd like! We do recommend you stick to GLUE schema
entries if you can.


Note about the -m option:
------------------------

Consider the -m option to be a required option, even if a probe only does 
one metric.

Why? The -m option is not required by the probes but will be likely a
required option according to the WLCG specs. If you are writing scripts to 
automate probe runs (apart from the ones we provide you) then please include 
-m <metric name> in the probe-execution line.

Note about the -m option in the context of multi-metric probes:
--------------------------------------------------------------

For  probes that are capable of doing more than one metric test, if you'd like
to retrieve all the metric names programatically, then please do:
 ./probe -m all -l


Note about Gratia sender script generation:
------------------------------------------
Gratia sender script generation is DISABLED by default to conform to the 
WLCG standards. To enable it, please use the --ggs switch.


The status codes, and other key-value pairs in the above output are described 
in the WLCG standard document referenced above [11].


------------------------------------------------------------------------------


PROCEDURE TO RUN PROBES IN THIS DIRECTORY
-----------------------------------------


**** BEGIN IMPORTANT NOTE  ****

You can also go to reference [1] given above. That page has instructions
on how to test all the probes using a test script. The following 
instruction describe how you can run individual probes.

**** ENG IMPORTANT NOTE    ****



INITIAL SETUP
-------------

* Do you usual setup.sh for the CE client / CE.
  . /path/to/ce/client/setup.sh
* Then make sure there is a valid proxy or get a proxy 
 $ grid-proxy-init

  Note:If there is no valid proxy, then all the non-local probes will exit 
       early with a corresponding metric result)



RUN PROBES
----------

INFORMATIONAL OPTIONS IN EACH PROBE
------------------------------------

1) Help for each probe; describes all options available for use when using 
  a specific probe (This information is also available online [3])

  ./probe -h

For example:

$ ./osg-directories-probe -h

osg-directories-probe
probeVersion: 1.13
serviceType: other
serviceVersion: >= OSG CE 0.6.0
probeSpecificationVersion: 0.91

Probe to check if permissions are set correctly on important user-accesible
 OSG directories defined by environment variables: OSG_GRID, OSG_APP, 
 OSG_DATA, and OSG_WN_TMP

USAGE
 ./osg-directories-probe <Required Arguments> [Optional Arguments]

PROBE OPTIONS                    DESCRIPTION
 -u, --uri <serviceURI>           Hostname, port and service to run probe on
                                   hostname[:port][/service]
 [-m <metric name>]               Metric to run
 [--workerscriptfile <file>       Worker script file to use.
 [-v <VO name>]                   VO to run probe against (Undefined)
 [-t <# seconds>]                 Timeout in seconds for system calls, for 
                                    eg.: globus job commands
                                    Default: 120 seconds per system call 
 [-l]                             List metric(s) per WLCG standards
 [--vdt-location </path/VDT>]     Provide custom $VDT_LOCATION (non OSG users)

GRID PROXY OPTIONS               DESCRIPTION
 [-x, --proxy <cert file>]        Location of Nagios user's proxy file
                                    Default: /tmp/x509up_u500
 [-w, --warning  <# hours>        Warning threshold for cert. lifetime
                                    Default: 6 hours
 [-c, --critical <#hours>]        Critical threshold for cert. lifetime
                                    Default: 3 hours

GRATIA SENDER SCRIPT OPTIONS     DESCRIPTION
 [--ggs]                          Generate Gratia upload python Script
 [--gsl <directory location>]     Directory to write Gratia upload script 
                                   Default: /tmp 
 [--gmpcf <file>]                 Metric ProbeConfig file to use
                                   Default: $VDT_LOCATION/gratia/probe/
                                             metric/ProbeConfig
 [--python-loc </path/python>]    Which python to use

HELP/DEBUGGING OPTIONS           DESCRIPTION
 [--verbose]                      Provide verbose output
 [--version]                      List revision of probe
 [-h, --help]                     Print this usage information


2) List probe/metric's name and type (only status metrics for now):
 ./probe -l -m all

  For example:
  $./ping-host-probe -l -m all
   serviceType: other
   metricName: org.osg.general.ping-host
   metricType: status
   EOT



3) Version of probe:

  ./probe --version



4) Verbose output for debugging:

  ./probe required-args -u hostname[:port][/service] --verbose
   (will cause verbose information useful for debugging to be printed 
    to STDERR)

  For example:
  $./osg-directories-probe -u itb-zero.uits.indiana.edu --verbose \
			    2>verbose-file



LISTING OF STANDARD PROBE OPTIONS: 
---------------------------------

All the probes take the following standard options; Additionally, each probe 
 may have its own specific command line arguments too - type ./probe -h 
 for more information:

 -u, --uri <serviceURI>           Hostname, port and service to run probe on
                                   hostname[:port][/service]
 -m <metric name>                 Metric to run 
 [-t <# seconds>]                 Timeout in seconds for system calls, for 
                                    eg.: globus job commands
                                    Default: 120 seconds per system call 
 [-l]                             List metric(s) per WLCG standards

 [--vdt-location </path/VDT>]     Provide custom $VDT_LOCATION (non OSG users)


GRID PROXY OPTIONS (for non-local probes that need to authenticate)
------------------

 [-x, --proxy <cert file>]        Location of Nagios user's proxy file
                                    Default: /tmp/x509up_u500
 [-w, --warning  <# hours>        Warning threshold for cert. lifetime
                                    Default: 6 hours
 [-c, --critical <#hours>]        Critical threshold for cert. lifetime
                                    Default: 3 hours

GRATIA OPTIONS
--------------

 [--ggs]                          Generate Gratia upload python Script
 [--gsl <directory location>]     Directory to write Gratia upload script 
                                   Default: /tmp 
 [--gmpcf <file>]                 Metric ProbeConfig file to use
                                   Default: $VDT_LOCATION/gratia/probe/
                                             metric/ProbeConfig
 [--python-loc </path/python>]    Which python to use

HELP/DEBUGGING OPTIONS
 [--verbose]                      Provide verbose output
 [--version]                      List revision of probe
 [-h, --help]                     Print this usage information


------------------------------------------------------------------------------


TYPICAL COMMAND LINE RUN INSTANCE FOR EACH OF THE PROBES PROVIDED
-----------------------------------------------------------------

Typical runs of the probes, including some additional parameters to specify
files and/or threshold hours type stuff, are as follows...


1) Certificate Probe (LOCAL):

* Test only hostcert in default location and write Gratia sender script 
  at standard location
 
 $ ./certificate-expiry-local-probe -m org.osg.local.hostcert-expiry

* Test all three certs; also I will provide cert file location and warning time
  of 10 days (i.e 240 hours); and write Gratia sender script at standard 
  location
 
 $ ./certificate-expiry-local-probe --hostcertfile ~/tmp/hostcert.pem \
                                    --containercertfile ~/tmp/containercert.pem\
                                    --httpcertFile ~/tmp/httpcert.pem \
                                    --warninghours 240 --ggs

 

2) CA Certificates (LOCAL) 

* Check all CA certs in ~/tmp/certificates directory; warn if any of them
  are expiring in 7200 hours ;). Do NOT generate Gratia sender script.
 
 $ ./cacert-expiry-local-probe --cacertsdir ~/tmp/certificates/ \
                               --warninghours 7200

NOTE: This probe does a weak test to look for expired/expiring CA certs 
      It's NOT a probe that tests for CA Cert package version or any such.  



3) Ping probe:

* Ping host sheepskin.cs.indiana.edu; send 2 ping packets at least, and wait
  4 seconds for response; and write Gratia sender script at location specified
  on command line (i.e. /foo/bar/)
 
 $ ./ping-host-probe -u itb-zero.uits.indiana.edu \
                     --pingtimeout 4 --pingcount 2 --ggs \
                     --gsl /foo/bar/



4) GRAM authentication:
 
 $ ./gram-authentication-probe -u itb-zero.uits.indiana.edu --ggs



5) Find out OSG version a site is running; Using results of probe, write 
  Gratia sender script at location specified  on command line (i.e. /foo/bar/);
  also use Gratia metric ProbeConfig file specified on command line:
 
 $ ./osg-version-probe -u itb-zero.uits.indiana.edu --ggs \
                       --gsl /foo/bar/ --gmpcf $VDT_LOCATION/foo/bar/ProbeConfig



6) OSG Directories probe:

* Check if OSG_XXX directories on the CE have the right permissions; 
  Using results of  probe, write Gratia sender script at standard location
  (AG: still would be nice to have a check for disk space as well -- in a 
  later version of the probes)
 
 $ ./osg-directories-probe -u itb-zero.uits.indiana.edu --ggs \
                           -m org.osg.general.osg-directories-CE-permissions



7) GridFTP test

* Transfer file to remote host and back; then diff 'em; Using results of 
  probe, write Gratia sender script at standard location
 
 $ ./gridftp-simple-probe -u itb-zero.uits.indiana.edu --ggs



8) Expired CA certs/ CRLs

* Requires -m argument even in this version.

* Check for expired CRLs on remote site 
  ($OSG_LOCATION/globus/share/certificates/*.r0);
  Using results of probe, write Gratia sender script at standard location
 
 $ ./crl-expiry-probe -u itb-zero.uits.indiana.edu \
                      -m org.osg.certificates.crl-expiry --ggs

* Check for expired CA certs on remote site
  ($OSG_LOCATION/globus/share/certificates/*.0);

  Do NOT write Gratia sender script at standard location

 $ ./crl-expiry-probe -u itb-zero.uits.indiana.edu \
                      -m org.osg.certificates.cacert-expiry


9) Job Managers Available Probe

* Tell me what job managers are running on a remote site; Using results of 
  probe, write Gratia sender script at standard location

  $ ./jobmanagers-available-probe -u itb-zero.uits.indiana.edu --ggs



10) Job Manager Status Probe

* Test if the job manager specified by the -m option works as expected; Using 
  results of probe, write Gratia sender script at standard location

  $ ./jobmanagers-status-probe -u itb-zero.uits.indiana.edu \
                               -m org.osg.batch.jobmanager-condor-status --ggs

 NOTE about DEPRECATED OPTION in jobmanager-status-probe: 

 -- This option will mess with WLCG interoperability but I've left it in there
    for the benefit of sysadmins who might want to run the probe to test
    more than one job manager on their resource

 -- It's possible to test all the available job managers on a resource if 
    "-m auto" is specified

    $ ./jobmanagers-status-probe -u itb-zero.uits.indiana.edu -m auto

 -- The above invokation of the jobmanager-status-probe will go figure out
    what jobmanagers exist on itb-zero.uits.indiana.edu and then will 
    verify if each of them works as expected.



11) Classad Validation Probe:

* Test if all the classad attributes are valid for a resource.
   The probe takes the given service URI and checks with the appropriate
   ReSS collector.  Each resource has multiple classads at ReSS.  Only if 
   all the isClassadValid Attributes are 1, does the resource pass the test. 
   If any of the isClassadValid Attributes are 0, or no valid data is returned, 
   the test fails and returns a CRITICAL status.

  RESS COLLECTOR:
   OSG Production: osg-ress-1.fnal.gov
   OSG ITB: osg-ress-4.fnal.gov

 $ ./classad-valid-probe -u cms-xen1.fnal.gov \
                         --ress-collector=osg-ress-4.fnal.gov


12) ReSS Classad Exists Probe:

* Test if the classad for a resource exists in the ReSS collector
   The probe takes the given service URI and checks with the appropriate
   ReSS collector. 
   If no classad for the resource is found in the collector, the test fails 
   and returns a CRITICAL status.

  RESS COLLECTOR:
   OSG Production: osg-ress-1.fnal.gov
   OSG ITB: osg-ress-4.fnal.gov

 $ ./ress-classad-exists-probe -u cms-xen1.fnal.gov \
                         --ress-collector=osg-ress-4.fnal.gov


13) CeMon Container Key file permissions Probe:

* Test the permissions of the sskeyfile used by cemon on the remote site.
   The probe takes the given service URI
   If the permissions are not 400 or 600 probe fails and returns a 
   CRITICAL status.

 $ ./cemon-containerkeyfile-ce-permissions-probe -u cms-xen1.fnal.gov 


NOTE ABOUT PROBE TIME OUT 
-------------------------

All the probes that use system calls to run globus commands, and such, have
an in-built timeout mechanism. The default is set to 60 seconds in the perl
module (OSG_Probe_Functions.pm). 

The -t option can be used to specify a different time out value (in seconds).
Note that this time out value is NOT for the entire probe itself but rather
for EACH individual system call (within the probes). 

The worst case time consumption we have seen so far is about 5 minutes.




NOTE ABOUT CUSTOMIZING SYSTEM COMMANDS AND SUCH
-----------------------------------------------

All system commands and such called within the probes are defined in the perl
module OSG_Probe_Functions.pm in the "Initialize_Probe()" function. If you
would like to change any of the defaults, that's the place to do so. I've 
tried to use hash-keys that correspond with the command names followed by
a -Cmd suffix; For example, 'lsCmd', 'pingCmd', etc.




------------------------------------------------------------------------------

 $Id: README.txt,v 1.10 2007/11/20 23:35:57 agopu Exp $

 Copyright 2007, The Trustees of Indiana University. 

 Open Science Grid Operations Team, Indiana University
 Original Author: Arvind Gopu (http://peart.ucs.indiana.edu)
 Last modified by Thomas Wang (on date shown in above Id line)

------------------------------------------------------------------------------
