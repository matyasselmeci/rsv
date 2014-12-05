#!/bin/bash
host=$1 start=$2 username=$3 key=$4 goc=$5 debug=$6 timeout=$7 scl enable python27 - << \EOF
echo $home
source ./esmond.env
python esmonduploader/caller.py -d $debug -s $start -u $host -p -w $username -k $key -g $goc -t $timeout
# Commentind the d option for extra debugging
#python esmonduploader/caller.py -d -s $start -u $host -p -w $username -k $key -g $goc
EOF

