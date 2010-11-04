#! /bin/sh

. ${OSG_LOCATION}/setup.sh

## Default directory for CAcerts and CRLs
CACRL_DIR=${X509_CERT_DIR}

## Set it to different value if provided
if [ $1 ] 
    then CACRL_DIR=$1
fi

## Remove any possible ls aliases (for example --color)
unalias ls >& /dev/null

## Run openssl command on each .r0 file if CA (ie .0) file exists in that directory
cd ${CACRL_DIR}; 
for file in `ls *.r0`;   
  do 
  fname=`echo $file | cut -f1 -d.`; 
  if [ `ls ${fname}.0 2> /dev/null` ]; 
      then  
      echo -n "${file}==>";    
      openssl crl -in $file -nextupdate -noout;  
# For debuggin #  else echo ${fname}.0 'cannot be FOUND'; 
  fi ; 
done
