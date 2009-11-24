#! /bin/sh

TMP_LOC='/tmp'
CONDOR_SUBMIT='condor_cron_submit'

if [ ${DEBUG}0 = 'true0' ]
    then set -x
fi

if [ $# -lt 1 ]
    then echo 'Usage if $VDT_LOCATION is already set using setup.sh:'  $0 ' <metric_name>'
    exit 1
fi
METRIC=$1

## Right now environmental setting over-rides command line value .. not intuitive?
if [ ${VDT_LOCATION}0 = 0 ] 
    then
    if [ $# -lt 2 ]
	then echo 'Usage if $VDT_LOCATION is NOT already set using setup.sh:'$0 ' <metric_name> <VDT_LOCATION>'
	exit 1;
    else 
	VDT_LOCATION=$2
    fi
fi

echo 'Using VDT_LOCATION: '${VDT_LOCATION} ' to run metric: '${METRIC}

source ${VDT_LOCATION}/setup.sh

cd ${VDT_LOCATION}/osg-rsv/logs/probes
RSVUSER=`stat --format=%U ${VDT_LOCATION}/osg-rsv/logs/probes`

if [ ${USER}0 = ${RSVUSER}0 ]
    then
    cd ${VDT_LOCATION}/osg-rsv/submissions/probes

    unalias ls >&/dev/null
    for SUBFILE in `ls *${METRIC}*.sub`;
      do 
      OUTFILE=${TMP_LOC}/${SUBFILE}.$$.sub
      echo 'Using condor-cron submission file: '$SUBFILE' ; Will create '${OUTFILE}
      egrep -v "^Cron|OnExit|PeriodicRelease" ${SUBFILE} > ${OUTFILE}
#     echo 'OnExitRemove = True' >> ${OUTFILE}
      echo 'Submitting '${OUTFILE}' into Condor-Cron'
      condor_cron_submit ${OUTFILE}
      rm -f ${OUTFILE}

      echo 'All done! Above metrics should be updated shortly by this manual execution'
    done
else
    echo 'This script needs to by user: ['${RSVUSER}']. Quitting'
fi
