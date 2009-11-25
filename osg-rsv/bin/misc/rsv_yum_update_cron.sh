#!/bin/sh

getopt=/usr/bin/getopt

getoptResult=`${getopt} -o l: -l local-install-dir: -- "$@"`
if [ $? != 0 ] ; then
   echo "Error"
   exit 1
fi

eval set -- "${getoptResult}"
while true ; do
   case "$1" in
      -l|--local-install-dir)   localDirectory="$2"; shift 2 ;;
      --)         shift; break;;
   esac
done

if [ "X${localDirectory}" = "X" ]; then
   echo "Please specify the local install directory, on which RSV yum process probe should use. We do not wish to run 'yum update' on your root install"
   exit 1
fi

if [ ! -e ${localDirectory} ]; then
    echo "The directory you specified does not exist. Quiting."
    exit 1
fi

timeStamp=`date +%s`
symlinkLoction="${localDirectory}/rsv-test-yumupdate"
currentDir="${localDirectory}/rsv-test-yumupdate-$timeStamp"
oldDir=`readlink "${symlinkLoction}"`
mkdir "${currentDir}"
#if [ ! -e "${localDirectory}/rsv-test-yumupdate" ]; then
#mkdir "${localDirectory}/rsv-test-yumupdate"
#fi
yum update -y --installroot ${localDirectory} 2>&1 > "${currentDir}/output"
echo $? >  "${currentDir}/status"
echo ${timeStamp} > "${currentDir}/lastrun"

# Not entirely atomic, but should be ok for our purposes. Moving symlinks donot seem to work
if [ -h  ${symlinkLoction} ]; then
    unlink ${symlinkLoction}
fi
ln -s "${currentDir}" "${symlinkLoction}"
if [ -e ${oldDir} ]; then
    rm -rf ${oldDir};
fi
