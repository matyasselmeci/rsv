#!/bin/bash 

#cat $1/osg/etc/config.ini | grep group  | grep = | grep ITB &> /dev/null
cat $1/osg/etc/config.ini | sed -e's/ //g'| grep '^group=OSG-ITB' &>/dev/null
if [ $? -eq 0 ]; then
  echo "ITB";
else
  echo "OSG"
fi
indextype=`cat $1/globus/TRUSTED_CA/INDEX.txt | grep IndexTypeVersion | awk '{print $3}'`
if [ "$indextype" == "" ]; then
  indextype=0;
  echo "0"
else
  echo $indextype;
fi
if [ "$indextype" == "0" ]; then
  certs=$1/globus/TRUSTED_CA/*.0
else if [ "$indextype" == "1" ]; then
    certs=$1/globus/TRUSTED_CA/*.pem
  fi
fi
/usr/bin/md5sum $certs
echo $?
