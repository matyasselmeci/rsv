#!/bin/bash
host=$1 start=$2 scl enable python27 - << \EOF
echo $home
source ./esmond.env
python esmonduploader/caller.py -s $start -u $host -p
EOF

