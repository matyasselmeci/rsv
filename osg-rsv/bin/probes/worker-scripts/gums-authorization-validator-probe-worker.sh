#!/bin/bash
SERVICE_DN=`openssl x509 -text -in /etc/grid-security/hostcert.pem | grep OU=Services | sed 's/Subject: /\//g' | sed 's/ //g' | sed 's/,/\//g'`
export X509_USER_PROXY=$1
export X509_PROXY_FILE=$1
OUTPUT=`gums generateFqanMapfile "$SERVICE_DN" 2>&1`
if [ $? -eq 0 ]; then
   echo "<WorkerScriptOut>"
   echo "  <StdOut>$OUTPUT</StdOut>"
   echo "</WorkerScriptOut>"
else
   echo "<WorkerScriptOut>"
   echo "  <StdErr>$OUTPUT</StdErr>"
   echo "</WorkerScriptOut>"
fi
