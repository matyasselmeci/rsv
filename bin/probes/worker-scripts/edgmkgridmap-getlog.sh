#!/bin/bash 
edg_log=$1;
if [ ! -e $edg_log ]; then
  echo "3<split>Log file from edg-mkgridmap ('$edg_log') is missing."
  exit
fi
out=`cat $edg_log`
if [ $? -eq 0 ]; then
  echo "0<split>$out"
else 
  echo "1<split>Non zero exit code returned from execution of commond 'cat $edg_log''."
  exit
fi
