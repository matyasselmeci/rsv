#!/bin/bash 

/usr/bin/stat -L -c "%n %Y" $*
echo $?
