#!/bin/sh

###############################################################################
##
## ReSS Project, Fermi National Accelerator Laboratory
## Original Author(s): Parag Mhashilkar 
##
## This script prints out validation attributes in site classads from ReSS.
##  It's used by the classads-valid-probe as a worker script
##
## It accept a the CE host fqdn (GlueCEInfoHostName) and a ReSS collector, 
##   then queris ReSS to get the  validation attributes, evaluates them, 
##   and print them out.
##
## For each site, ReSS has multiple classads. A site passes the validation
##   test if for all the classads the attribute 'isClassadValid' is 1
##
###############################################################################

# static variables
tmpdir=/tmp

# use osg-ress-1.fnal.gov for OSG Production Resources
# use osg-ress-4.fnal.gov for OSG ITB Resources
defaultCollector=osg-ress-1.fnal.gov


#helper functions
die () { echo "$0: $*" >&2; exit 1; }
get_arg_value () { echo $1 | sed "s?^--[a-z|-]*=??g"; } 
#usage () 
#{ echo "$0 usage: $0 --glue-ce-host=<ce-host-fqdn> [--collector=<ReSS-collector-host>] [--debug] [--help]";
#  echo "   Default for ReSS-collector-host = $defaultCollector"
#}

# preconditions
[ "${VDT_LOCATION}" ] || die '$VDT_LOCATION not defined'

# arg parsing and validation
debug=false
collector=$defaultCollector
while [ -n "$1" ]; do
   case $1 in
   --help)
#      usage
      exit 0
      ;;

   --debug)
      debug=true
      ;;

   --glue-ce-host=*)
     glueCEHostName=`get_arg_value "$1"`
     ;;
   --collector=*)
     collector=`get_arg_value "$1"`
     ;;
   *)
#      usage
      exit 1
   esac
   shift
done

if [ -z $glueCEHostName ]; then
  #echo "$0: you must specify a CE host fqdn." >&2
#  usage
  exit 1
fi

if [ "x$debug" = "xtrue" ]; then
  echo "DEBUG: Arguments:"
  echo "DEBUG: debug="$debug
  echo "DEBUG: collector="$collector
  echo "DEBUG: glueCEHostName="$glueCEHostName
  echo
fi


########

# get all attribute names
tmpFileTestAttributes=$tmpdir/isClassadValidTestAttributes.$$.txt
rm -f $tmpFileTestAttributes

# setenv for condor AG: Is this still necessary with the condor_status wrappers?
export _CONDOR_NETWORK_INTERFACE=""


#####################################################
## Comment for > OSG CE 1.0 (VDT 1.10.x installs)
## Uncomment For Pre OSG CE 1.0  ( pre VDT 1.10.x installs  )
#####################################################
## Is condor_status in path - added by AG 2008-04-01
# if [ ! `which condor_status` ]; then
#    ## Try adding condor-devel instead --- AG: This needs to be changed to condor-cron
#    source ${VDT_LOCATION}/vdt/etc/condor-devel-env.sh 
#    ## Now try again ... 
#    if [ ! `which condor_status 2>/dev/null`  ]; then
#	notfound="condor_status command not found"  
#	printf "%s\n" "$notfound"
#	exit 2
#    fi
#fi
# condor_status -l -pool ${collector} -constraint "GlueCEInfoHostName == \"$glueCEHostName\"" | grep "isClassadValid =" | sort | uniq > $tmpFileTestAttributes
####################################################


#####################################################
## UnComment for > OSG CE 1.0 (VDT 1.10.x installs)
## Comment For Pre OSG CE 1.0  ( pre VDT 1.10.x installs  )
#####################################################
## This will work with > (OSG 0.9.1) ie > VDT 1.10.x -- since condor-devel is now condor-cron
if [ ! -e ${VDT_LOCATION}/condor-cron/wrappers/condor_cron_status ]; then
    notfound="condor_cron_status command not found"  
    printf "%s\n" "$notfound"
    exit 2
fi
${VDT_LOCATION}/condor-cron/wrappers/condor_cron_status -l -pool ${collector} -constraint "GlueCEInfoHostName == \"$glueCEHostName\"" | grep "isClassadValid =" | sort | uniq > $tmpFileTestAttributes
#####################################################


if [ ! -s $tmpFileTestAttributes ]; then
  #echo "$0: cannot find CE host $glueCEHostName in ReSS at $collector OR no isClassadValid attributes present" >&2
  notfound="no match"  
  printf "%s" "$notfound"
  rm -f $tmpFileTestAttributes
  exit 1
fi

# generate condor_cron_status command to evaluate classad validity; awk executes the command
tmpAwkCmd=$tmpdir/isClassadValidAwkCmd.$$.awk
cat > $tmpAwkCmd <<EOF
  BEGIN { cmd = "${VDT_LOCATION}/condor-cron/wrappers/condor_cron_status -pool $collector -constraint 'GlueCEInfoHostName == \"$glueCEHostName\"' -format 'GlueSiteName=%s\n' GlueSiteName -format 'GlueCEInfoContactString=%s\n' GlueCEInfoContactString -format 'Name=%s\n' Name" }
  {
    cmd = sprintf("%s -format '%s=%%d\\\n' %s ",cmd,\$1,\$1)
  }
  END { system(cmd) }
EOF

if [ "x$debug" = "xtrue" ]; then
  echo "DEBUG: generated awk script: $tmpAwkCmd"
  cat $tmpAwkCmd
  echo
fi

awk -f $tmpAwkCmd $tmpFileTestAttributes


# clean up
rm -f $tmpAwkCmd
rm -f $tmpFileTestAttributes

