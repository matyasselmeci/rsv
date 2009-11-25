#!/bin/sh

###########################################################################
##
## $Id $
##
## Copyright 2007, The Trustees of Indiana University. 
##
## Open Science Grid Operations Team, Indiana University
## Original Author: Arvind Gopu (http://peart.ucs.indiana.edu)
## Last modified by Arvind Gopu (on date shown in above Id line)
##
## This shell script can be used to test RSV probes in the current directory
##
## * To run, execute the script as "source test-rsv-probes-by-hand.sh"
##
## * The script will generate output files named some-probe.out 
##   (and error files, if applicable, named some-probe.err
##
##
############################################################################




############################################################################
## Globals go here
############################################################################

## Uncomment to help debug 
## set -x

## Define host name of CE and SRM here; 
TESTHOST="osp1.lbl.gov"
TESTSE=""

## EDIT PROXYFILE and OUTDIR - proxy needs to be owned by you with 600 permissions!
PROXYFILE=" /home/agopu/goc_rsv.proxy "
OUTDIR="/tmp/rsv-test"


## Generate Gratia python script
GRATIAOPTION='--ggs'

## Uncomment following line to specify additional options
## For example, where gratia python scripts should go; 
## ./*-probe -h will list all available options
## EXTENDEDOPTIONS='--gsl /path/to/someplace/for/python/scripts/ -x /tmp/foo_x500'

## Uncomment following line to get verbose output
VERBOSE='--verbose --verbose' 






############################################################################
## Check if grid commands are in the PATH
###########################################################################

echo ' Checking if environment is setup right ... '

if [ `which grid-proxy-init` ]; 
    then 
    echo ' Environment is setup fine, continuing ...' 
    else 
    echo ''; 
    echo ' Please make sure you have executed $VDT_LOCATION/setup.[c]sh'; 
    echo ''; 
    exit 109; 
fi 2>/dev/null



## Directory where probes are located; Date.pm needs to be available 
##  system-wide or within the probe directory
##
## RSVProbeBase.pm, RSVProbeCACErt.pm, and worker-scripts/ directory need to be in place
##  within the probe directory
PROBEDIR="${VDT_LOCATION}/osg-rsv/bin/probes"
cd ${PROBEDIR}
mkdir -p ${OUTDIR}




############################################################################
## Test probes that do only one metric
############################################################################

SINGLEMETRICPROBES='ping-host-probe gram-authentication-probe osg-version-probe osg-directories-permissions-ce-probe jobmanagers-available-probe gridftp-simple-probe classad-valid-probe vdt-version-probe vo-supported-probe gums-authorization-validator-probe cacert-verify-probe crl-freshness-probe cacert-verify-supported-vo-probe cacert-verify-wlcg-probe crl-freshness-wlcg-probe osg-directories-diskspace-probe voms-handshake-verify-probe voms-handshake-success-verify-probe';

SINGLEMETRICSEPROBES='srm-ping-probe srmcp-srm-probe';

for PROBE in ${SINGLEMETRICPROBES}
  do 
    echo '  Executing ' $PROBE 'as:'
    echo "perl ${PROBE} -u ${TESTHOST} ${GRATIAOPTION} -x ${PROXYFILE} ${EXTENDEDOPTIONS} ${VERBOSE} 1>${OUTDIR}/${PROBE}.out 2>${OUTDIR}/${PROBE}.err";
    perl $PROBE -u $TESTHOST ${GRATIAOPTION} -x ${PROXYFILE} ${EXTENDEDOPTIONS} ${VERBOSE} 1>${OUTDIR}/${PROBE}.out 2>${OUTDIR}/${PROBE}.err;
done

exit
## Local single metric probe




############################################################################
## Test SE probes that do only one metric if TESTSE is defined
############################################################################

if [ ${TESTSE} ]
    then
    for PROBE in ${SINGLEMETRICSEPROBES}
      do 
      echo '  Executing SE probe ' $PROBE 'as:'
      echo "perl ${PROBE} -u ${TESTSE} ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} ${VERBOSE} 1>${OUTDIR}/${PROBE}.out 2>${OUTDIR}/${PROBE}.err";
      perl $PROBE -u ${TESTSE} ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} ${VERBOSE} 1>${OUTDIR}/${PROBE}.out 2>${OUTDIR}/${PROBE}.err;
    done;
fi



############################################################################
## Test multi metric probes now
############################################################################

## certificate-expiry-local-probe
PROBE='certificate-expiry-local-probe'
echo '  Executing ' $PROBE 'as:'
echo "perl ${PROBE} ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.hostcert-expiry ${VERBOSE}  1>${OUTDIR}/${PROBE}.hostcert-expiry.out 2>${OUTDIR}/${PROBE}.hostcert-expiry.err";
perl $PROBE ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.hostcert-expiry ${VERBOSE}  1>${OUTDIR}/${PROBE}.hostcert-expiry.out 2>${OUTDIR}/${PROBE}.hostcert-expiry.err
echo "perl ${PROBE} ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.httpcert-expiry ${VERBOSE} 1>${OUTDIR}/${PROBE}.httpcert-expiry.out 2>${OUTDIR}/${PROBE}.httpcert-expiry.err";
perl $PROBE ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.httpcert-expiry ${VERBOSE} 1>${OUTDIR}/${PROBE}.httpcert-expiry.out 2>${OUTDIR}/${PROBE}.httpcert-expiry.err
echo "perl ${PROBE} ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.containercert-expiry ${VERBOSE} 1>${OUTDIR}/${PROBE}.containercert-expiry.out 2>${OUTDIR}/${PROBE}.containercert-expiry.err";
perl $PROBE ${GRATIAOPTION} ${EXTENDEDOPTIONS}  -m org.osg.local.containercert-expiry ${VERBOSE} 1>${OUTDIR}/${PROBE}.containercert-expiry.out 2>${OUTDIR}/${PROBE}.containercert-expiry.err

## jobmanagers-status-probe
##
## Add more job managers as metrics if you run other job managers; 
##
## To get a list of valid metric names, run
##   perl jobmanagers-status-probe -m all -l 
##
## Fork     
PROBE='jobmanagers-status-probe'
echo '  Executing ' $PROBE 'as:'
echo "perl ${PROBE} -u ${TESTHOST} ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} -m org.osg.batch.jobmanager-fork-status ${VERBOSE} 1>${OUTDIR}/${PROBE}.fork.out 2>${OUTDIR}/${PROBE}.fork.err"
perl $PROBE -u $TESTHOST ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} -m org.osg.batch.jobmanager-fork-status ${VERBOSE} 1>${OUTDIR}/${PROBE}.fork.out 2>${OUTDIR}/${PROBE}.fork.err;
## Default job manager
echo '  Executing ' $PROBE 'as:'
echo "perl ${PROBE} -u ${TESTHOST} ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} -m org.osg.batch.jobmanager-default ${VERBOSE} 1>${OUTDIR}/${PROBE}.default.out 2>${OUTDIR}/${PROBE}.default.err"
perl $PROBE -u $TESTHOST ${GRATIAOPTION} ${PROXYFILE} ${EXTENDEDOPTIONS} -m org.osg.batch.jobmanager-default-status ${VERBOSE} 1>${OUTDIR}/${PROBE}.default.out 2>${OUTDIR}/${PROBE}.default.err;


############################################################################
## All done
############################################################################

echo ' Done testing all the probes in this set (of probes). '


# exit 0;

