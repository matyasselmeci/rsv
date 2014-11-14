#!/bin/bash
host=$1 start=$2 username=$3 key=$4 goc=$5 scl enable python27 - << \EOF
echo $home
source ./esmond.env
# Commenting no doing post for now
python esmonduploader/caller.py -d -s $start -u $host -p -w $username -k $key -g $goc
#python esmonduploader/caller.py -d -s $start -u $host -w $username -k $key -g $goc
EOF

