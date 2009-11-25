#!/bin/bash 
edg_log=$1;
if [ ! -e $edg_log ]; then
  echo "3<split>Log file from edg-mkgridmap ('$edg_log') is missing."
  exit
fi
# Checking to see if edg-mkgridmap ever finished running 
tmp=`grep 'Finished edg-mkgridmap' $edg_log 2>/dev/null`
if [ $? -ne 0  ]; then
  echo "3<split>The log file '$edg_log' does not have a record of edg-mkgridmap ever completing successfully"
  exit
fi
#Retrieving last time edg-mkgridmap finished running 
out=`grep 'Finished edg-mkgridmap' $edg_log | tail -1 | gawk '{print $1}' 2>/dev/null` 
if [ $? -eq 0 ]; then
  echo "0<split>$out"
else 
  echo "1<split>Non zero exit code returned from execution of commond '/bin/grep 'Finished edg-mkgridmap' $edg_log | tail -1 | gawk '{print $1}' 2>/dev/null''."
  exit
fi
