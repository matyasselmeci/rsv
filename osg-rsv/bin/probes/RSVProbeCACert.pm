#!/usr/bin/env perl

package RSVProbeCACert;

use strict;

use RSVProbeBase;
use Time::Local;
use File::Basename;
use File::Temp qw/ tempdir /;

## And alias to RSV::Probe_Base variables
our %o;         *o         = \%RSVProbeBase::o;      
our %metric;    *metric    = \%RSVProbeBase::metric;
my $site_rsv_probe_version="1.1.2";

##---------------------------------------------------------------------
##
## Verify_CA: Verifies CAs in the certificate directory
##
## parameters :
##  First: 
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'  Directory where CA certs (*.0) can be found 
##      'warnHrs'  Number hours before certificate expiry a warning should be issued
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Verify_CA {
	
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    
    $o{'callingRoutine'} = "Verify_CA ()";

    ## Step 1: Check for existence of CAcertfiles directory ... 
    ##   return Unknown as metricsresult when directory does not exist
    if (!(-e $o{'certDir'})) {
        &RSVProbeBase::Set_Summary_Metric_Results (3,"ERROR: CA Certs Directory \"$o{'certDir'}\" does not exist.. Setting metric to unknown; Type $0 --help for more information...\n");
        return \%metric;
    }

    # Get all the certificates
    my $cmd = "ls -1 $o{'certDir'}/*.0";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    if ($o{'cmdExitValue'} != 0) {
	&RSVProbeBase::Set_Summary_Metric_Results (3,"ERROR: CA Certs Directory \"$o{'certDir'}\" contains no certificate files (*.0).. Setting metric to unknown; Type $0 --help for more information...\n");
        return \%metric;
    }
    my @cert_files = split /\n/, $o{'cmdOut'};
    my $error_count = my $warn_count = my $ok_count = 0;

    foreach my $local_certs_file (@cert_files) {
        chomp($local_certs_file);

        #Step 2: Get the subject, Hash and dates associated with the certificate
        $cmd = "$o{'opensslCmd'} x509 -in $local_certs_file -subject -hash -dates -noout";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my @values =  split(/\n/,$o{'cmdOut'});
        my $subject =  (split /subject=/, $values[0])[1];
        chomp(my $hash = $values[1]);
        my $start_time =  (split /notBefore=/, $values[2])[1];
        my $end_time =  (split /notAfter=/, $values[3])[1];

        # Step 3: Verify certificate using openssl verify command
        $cmd = "$o{'opensslCmd'} verify -CApath $o{'certDir'} $local_certs_file";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my $verify_ca = $o{'cmdOut'};
        chomp($verify_ca = (split /:/, $verify_ca)[1]);
        if ($verify_ca !~ /OK/){
            $status_code = 2;
            $status_out .= "ERROR: Certificate with subject '$subject' and hash '$hash' failed to verify.\n";
            $error_count++;
            next;
        }

        # Step 4: Check for expiry date on the cerrtificate and compare it with the current date

        # Parsing string of form: Oct  5 08:00:00 2008 GMT
        my @tmp_end_date = split /\s+/, $end_time;
        my @tmp_end_time = split /:/, $tmp_end_date[2];

        my $unix_end_time = gmt_to_unix_time($tmp_end_date[0],$tmp_end_date[1],$tmp_end_date[3], $tmp_end_time[0],  $tmp_end_time[1],  $tmp_end_time[2]);
        my $now = time();
        if($now >= $unix_end_time){
            $status_code=2;
            $status_out .= "ERROR: Certificate with subject '$subject' and hash '$hash' has expired on $end_time.\n";
            $error_count++;
        }elsif($now + $o{'warnHrs'}*60*60 >= $unix_end_time){
            $status_code=1 if($status_code!=2); # Change only status code to warning, only if an error has not been recorded
            $status_out .= "WARNING: Certificate with subject '$subject' and hash '$hash' is about to expire on $end_time.\n";
	    &RSVProbeBase::Verbose("$status_out; [NOW: $now; warnHrs: $o{'warnHrs'}; unix_end_time: $unix_end_time]");
            $warn_count++;
        }else{
            #$status_out .= "OK: Certificate with subject '$subject' and hash '$hash' was verified\n" if ($o{'verbose'});
            $ok_count++;
        }
    }
    # Step 5: Recording the result for RSV output
    $status_out .= ($error_count+$warn_count+$ok_count)." certificates found.\n\t$error_count failed varification/had expired;\n\t$warn_count are about to expire/had warnings;\n\t$ok_count verified OK.\n";
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);


     return \%metric;

}

##---------------------------------------------------------------------
##
## Check_Download_Certs_VDTUpdate: Check the process of downloading the certs using vdt-update-certs
##
## parameters :
##  First: 
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'errorHrs'  Number hours since the failing downloads before an error is issued
##      'warnHrs'   Number hours since the failing downloads before a warning is issued
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_Download_Certs_VDTUpdate{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Download_Certs_VDTUpdate()";

    # Step 1: Check for the existance of vdt-update-certs-wrapper
    my $vdt_update_wrapper =  $o{'caInstallBaseDir'}."/vdt/sbin/vdt-update-certs-wrapper";
    if (!(-e $vdt_update_wrapper)) {
        &RSVProbeBase::Set_Summary_Metric_Results (2,"ERROR: vdt-update-certs-wrapper \"$vdt_update_wrapper\" does not exist. So certificates were not downloaded. Setting metric to critical; Type $0 --help for more information...\n");
        return \%metric;
    }

    # Step 2: Run vdt-update-certs and checks for successful exit
    ## AG: Added 2>&1 to capture stderr .. might be useful error to print in detailsData -- no?
    ##    my $cmd = "$vdt_update_wrapper --vdt-install ". $o{'caInstallBaseDir'}." --force 2>&1";
    my $cmd = "$vdt_update_wrapper --vdt-install ". $o{'caInstallBaseDir'}." --force 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    if ($o{'cmdExitValue'} !=0){
        $status_out .= "vdt-update-certs process failed with the followig error:\n\n".$o{'cmdOut'};
        $status_code = 2;
    }
    
    # Step 3: Check when was the last time vdt-update-certs succcessfully downloaded the certs
    ## AG: Added 2>&1 to capture stderr .. might be useful error to print in detailsData -- no?
    my $vdt_ca_cert_status =  $o{'caInstallBaseDir'}."/vdt/var/certs-updater-status";
    if (!(-e $vdt_ca_cert_status)) {
        $status_code=2;
        $status_out .= "ERROR: Status file \"$vdt_ca_cert_status\" does not exist. So we will not be checking the time of last run.\n";
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;
    }
    $cmd = "cat $vdt_ca_cert_status | grep last_update";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    my $last_update = (split /-/, $o{'cmdOut'})[1];
    chomp($last_update);
    my $now = time();
    if($now >= $last_update + $o{'errorHrs'}*60*60){
        $status_code = 2;
        $status_out .= "ERROR: Certificates have not been updated for since ".localtime($last_update)."\n";
    }elsif($now >= $last_update + $o{'warnHrs'}*60*60){
        $status_code = 1;
        $status_out .= "WARNING: Certificates have not been updated for since ".localtime($last_update)."\n";
    }else{
        $status_out .= "OK: Certificates last downloaded on ".localtime($last_update)."\n";
    }

    # Step 4: Recording the result for RSV output
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;

}

##---------------------------------------------------------------------
##  
## Check_Download_Certs_YumUpdate: Check the process of downloading the certs using yum update
##
## parameters :
##  First: 
##   %Probe hash 
##  Second: 
##   %metric hash  
##  Third: 
##   %local hash containing 
##      'installDir' Root location of the local yum install used for RSV test
##     
## Returns 
##   Pointer to metric hash with all the details set
##  
##---------------------------------------------------------------------
sub Check_Download_Certs_YumUpdate{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Download_Certs_YumUpdate()";
    my $result_dir = "$o{'caInstallBaseDir'}/rsv-test-yumupdate";
    my $ret_code = 0;
    # Step 1: Check for the existance of output files and if so use them to set the results
    if (-e  "$result_dir/lastrun" && -e "$result_dir/output" && -e "$result_dir/status"){
        my $cmd = "cat $result_dir/status";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        chomp(my $status =  $o{'cmdOut'});

        $cmd = "cat $result_dir/lastrun";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        chomp(my $lastrun =  $o{'cmdOut'});

        $cmd = "cat $result_dir/output";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        $status_out .=  "Here is the output from yum update process:\n$o{'cmdOut'}\n";

        $status_code=2 if($status!=0);
        $status_out .= "\nSummary: Yum update was last run at '".localtime($lastrun)."' and it exited with exit_code='$status_code'.\n";

    }else{
        $status_code = 3;
        $status_out = "Some/All of the expected result files are missing from '$result_dir'. Unable to make judgement regarding the yum update process.\n";
    }
    # Step 2: Recording the result for RSV output
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;

}


##---------------------------------------------------------------------
##  
## Verify_CA_CRL: Verifies CA's CRLs present in the certificate directory
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'  Directory where CA certs (*.0) can be found 
##      'warnHrs'  Number hours before certificate expiry a warning should be issued
##      'warnShortHrs'  Number hours before certificate expiry a warning should be issued for Short Lived CRLs
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Verify_CA_CRL {

    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV

    $o{'callingRoutine'} = "Verify_CA_CRL ()";

    ## Step 1: Check for existence of CAcertfiles directory ... 
    ##   return Unknown as metricsresult when directory does not exist
    if (!(-e $o{'certDir'})) {
        &RSVProbeBase::Set_Summary_Metric_Results (3,"ERROR: CA Certs Directory \"$o{'certDir'}\" does not exist.. Setting metric to unknown; Type $0 --help for more information...\n");
        return \%metric;
    }

    # Get all the certificates
    my $cmd = "ls -1 $o{'certDir'}/*.0";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    my @cert_files = split /\n/, $o{'cmdOut'};
    my $error_count = my $warn_count = my $ok_count = my $missing_count = my $short_count = 0;

    foreach my $local_certs_file (@cert_files) {
        chomp($local_certs_file);

        # Step 2: Getting the subject and hash of the CA
        $cmd = "$o{'opensslCmd'} x509 -in $local_certs_file -subject -hash -noout";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my @values = split /\n/, $o{'cmdOut'};
        chomp(my $subject =  (split /subject=/, $values[0])[1]);
        chomp(my $local_hash = $values[1]);

        # Step 3: Checking for the presence of CRL
        my $local_crl_file = "$o{'certDir'}/$local_hash.r0";
        if (!defined $local_crl_file || ! -e $local_crl_file ){
            $status_code=1 if($status_code==0); 
            $status_out .= "MISSING: CRL file for CA with subject '$subject' and hash '$local_hash' is missing.\n";
            $missing_count++;
            next;
        }

        # Step 4: Verifying CRL using openssl command
        # Apprently the output "verify OK" is directed to stderr.
        $cmd = "$o{'opensslCmd'} crl -CApath $o{'certDir'} -in $local_crl_file -noout 2>&1";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my $verify_crl =  $o{'cmdOut'};
        chomp($verify_crl);
        if ($verify_crl !~ /verify OK/){
            $status_code = 2;
            $status_out .= "ERROR: CRL file for CA with subject '$subject' and hash '$local_hash' failed verification.\n";
            $error_count++;
            next;
        }
   
        # Step 5: Verifying the dates on the CRL
        $cmd  = "$o{'opensslCmd'} crl -in $local_crl_file -nextupdate -lastupdate -noout";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        @values =  split /\n/, $o{'cmdOut'};        
        my $crl_end_time =  (split /nextUpdate=/, $values[0])[1];
        my $crl_last_update =  (split /lastUpdate=/, $values[1])[1];
        my @tmp_end_date = split /\s+/, $crl_end_time;
        my @tmp_end_time = split /:/, $tmp_end_date[2];
        my $unix_end_time = gmt_to_unix_time($tmp_end_date[0],$tmp_end_date[1],$tmp_end_date[3], $tmp_end_time[0],  $tmp_end_time[1],  $tmp_end_time[2]);
        my $now = time();
        if($now >= $unix_end_time){
            $status_code = 2;
            $status_out .= "ERROR: CRL file for CA with subject '$subject' and hash '$local_hash' has expired on $crl_end_time.\n";
            $error_count++;
        }elsif($now + $o{'warnHrs'}*60*60 >= $unix_end_time){
            # Special case for short-lived CRLs < $o{'warnHrs'} hrs
            @tmp_end_date = split /\s+/, $crl_last_update;
            @tmp_end_time = split /:/, $tmp_end_date[2];
            my $unix_last_update_time = gmt_to_unix_time($tmp_end_date[0],$tmp_end_date[1],$tmp_end_date[3], $tmp_end_time[0],  $tmp_end_time[1],  $tmp_end_time[2]);
            if ($unix_end_time - $unix_last_update_time <= $o{'warnHrs'}*60*60){
            # This is a short lived CRL. We will test if it is atleast valid for next WarnShortHrs
            $short_count++;
            $status_out .= "INFORMATION: CRL file for CA with subject '$subject' and hash '$local_hash' had a short lived CRL with lifetime less than $o{'warnHrs'} hours.\n";
                if($now + $o{'warnShortHrs'}*60*60 < $unix_end_time){
                    # The certificate is atleast valid for next 'warnShortHrs'. So no warning is to be issued. If not fall throught and issue a warning
                    $ok_count++;
                    next;
                }
            }
            $warn_count++;
            $status_code=1 if($status_code!=2); 
            $status_out .= "WARNING: CRL file for CA with subject '$subject' and hash '$local_hash' is about to expire on $crl_end_time.\n";
        }else{
            $ok_count++;
            #$status_out .= "OK: CRL file for CA with subject '$subject' and hash '$local_hash' has no known issues.\n" if ($o{'verbose'});
        }

    }
    # Step 6: Recording the result for RSV output
    $status_out .= "OK: All CRLs verified successfully\n" if ($status_code==0);
    $status_out .= ($error_count+$missing_count+$warn_count+$ok_count)." CAs found. ". ($error_count+$warn_count+$ok_count) ." of them had CRLs.\n\t$error_count failed varification / had expired;\n\t$missing_count CAs are missing / did not have CRLs;\n\t$warn_count CRLs are about to expire;\n\t$short_count CRLs have a life time of less than $o{'warnHrs'} hours;\n\t$ok_count CRLs verified OK.\n";
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;
}

##---------------------------------------------------------------------
##  
## Check_Freshness_CRL: Checks the last time when the CRLs were successfully downloaded
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'   Directory where CA certs (*.0) can be found 
##      'errorHrs'  Number hours since the failing downloads before an error is issued
##      'warnHrs'   Number hours since the failing downloads before a warning is issued
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_Freshness_CRL{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Check_Freshness_CRL()";

    # Step 1: Check time stamps on the file to ensure that it has been recently downloaded
    
    my $cmd = "ls -1 $o{'certDir'}/*.r0";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    my @cert_files = split /\n/, $o{'cmdOut'};
    my $error_count = my $warn_count = my $ok_count = 0;
    
    foreach my $local_certs_file (@cert_files) {
        chomp($local_certs_file);
        my $last_update = (stat($local_certs_file))[9];
        chomp(my $local_hash = (split(/\.r0/,basename($local_certs_file)))[0]);
        my $now = time();
        if($now >= $last_update + $o{'errorHrs'}*60*60){
            $status_code = 2;
            $status_out .= "ERROR: CRL file for CA with hash '$local_hash' has not been updated for since ".localtime($last_update)."\n";
            $error_count++;
        }elsif($now >= $last_update + $o{'warnHrs'}*60*60){
            $status_code = 1 if($status_code!=2);
            $status_out .= "WARNING: CRL file for CA with hash '$local_hash' has not been updated for since ".localtime($last_update)."\n";
            $warn_count++;
        }else{
            #$status_out .= "OK: CRL file for CA with hash '$local_hash' was last downloaded on ".localtime($last_update)."\n" if ($o{'verbose'});
            $ok_count++;
        }

    }
    # Step 2: Recording the result for RSV output
    $status_out .= "OK: All CRLs have been recently updated\n" if ($status_code==0);
    $status_out .= ($error_count+$warn_count+$ok_count)." CRLs found.\n\t$error_count had not been updated for atleast $o{'errorHrs'} hours;\n\t$warn_count CRLs have not been updated for atleast $o{'warnHrs'} hours;\n\t$ok_count CRLs have been updated within last $o{'warnHrs'} hours.\n";
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;
}
##---------------------------------------------------------------------
##
## Check_Download_CRL_FetchCRL: Check the process of downloading the CRLs using fetchCRL
##
## parameters :
##  First: 
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'   Directory where CA certs (*.0) can be found 
##     
## Returns 
##   Pointer to metric hash with all the details set
##  
##---------------------------------------------------------------------
sub Check_Download_CRL_FetchCRL{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Download_Certs_FetchCRL()";

    # Step 1: Check for the existance of fetch-crl
    my $fetch_crl_exec =  $o{'caInstallBaseDir'}."/fetch-crl/sbin/fetch-crl";
    if (!(-e $fetch_crl_exec)) {
        &RSVProbeBase::Set_Summary_Metric_Results (2,"ERROR: fetch-crl file (\"$fetch_crl_exec\") does not exist. So CRLs were not downloaded. Setting metric to critical; Type $0 --help for more information...\n");
    }

    # Step 2: Run fetch-crl and check for successful exit
    my $cmd = "$fetch_crl_exec  --loc $o{'certDir'} --out $o{'certDir'} --quiet 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    if ($o{'cmdExitValue'} !=0){
        $status_out .= "ERROR: fetch-crl reported the following errors.\n\n".$o{'cmdOut'};
        $status_code = 2;
    }elsif ($o{'cmdOut'} !~ /^\s*$/ ){
        $status_out .= "WARNING: fetch-crl output the following to stdout/stderr. \n\n". $o{'cmdOut'};
        $status_code = 1;
   }

    # Make a note that we ran fetch-crl
    open FILE, "> $o{'caInstallBaseDir'}/vdt/var/fetch-crl.lastrun";
    print FILE time;
    close FILE;
    
    # Step 3: Recording the result for RSV output
    $status_out .= "OK: No errors were reported by fetch-crl\n" if ($status_code==0);
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;

}
##---------------------------------------------------------------------
##  
## Check_IGTF: Checks the certificates from VDT and OSG cache against IGTF certificates
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'igtfTarballUrl'      Location of IGTF tarballs 
##      'tarballUrl'    Location of certificate tarballs
##      'rpmUrl'    Location of VDT certificate RPMs
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_IGTF{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Check_IGTF()";

    chomp(my $cwd = `pwd`);
    chdir($cwd); 
    # Step 1: Download cert from IGTF
    %o = %{&Get_IGTF_Tar()};
    $status_out .= $o{'status_out'};
    $status_code = 2 if($o{'status_code'}==2);
    $status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
    $status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
    if($status_code!=0){
        # IGTF certs were not correctly downloaded. No point in checking other OSG and VDT packages
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;  
    }
    $o{'status_out'} ="";
    $o{'status_code'}=0;

    # Step 2: Get and Check OSG CA Certificates RPM
    if ($o{'repoName'} =~ /^goc$/i) {
	$o{'cache'} = "osg";
	%o = %{&Get_Check_OSG_RPM()};
	$status_out .= $o{'status_out'};
	$status_code = 2 if($o{'status_code'}==2);
	$status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
	$status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
	$o{'status_out'} ="";
	$o{'status_code'}=0;

	# Step 3: Get and Check OSG CA Certificates Tarballs
	%o = %{&Get_Check_OSG_VDT_Tar()};
	$status_out .= $o{'status_out'};
	$status_code = 2 if($o{'status_code'}==2);
	$status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
	$status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
	$o{'status_out'} ="";
    }
    else {
	# Step 2: Get and Check VDT CA Caertificates RPM
	$o{'cache'} = "vdt";
	%o = %{&Get_Check_VDT_RPM()};
	$status_out .= $o{'status_out'};
	$status_code = 2 if($o{'status_code'}==2);
	$status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
	$status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
	$o{'status_out'} ="";
	$o{'status_code'}=0;

	# Step 3: Get and Check VDT CA Certificates Tarball
	%o = %{&Get_Check_OSG_VDT_Tar()};
	$status_out .= $o{'status_out'};
	$status_code = 2 if($o{'status_code'}==2);
	$status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
	$status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
	$o{'status_out'} ="";
	$o{'status_code'}=0;
    }
    $status_out .= "Certificates included in the $o{'repoName'} repository tarballs and RPMs match the ones in the IGTF package.\n" if ($status_code==0);

    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;  
}

##---------------------------------------------------------------------
##  
## Get_Check_OSG_RPM: Download the IGTF tarball
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'igtfTarballUrl'      Location of IGTF tarballs 
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##      'igtf_cert_dir' Location of downloaded IGTF certificates 
##
##---------------------------------------------------------------------
sub Get_IGTF_Tar{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Get_IGTF_Tar()";
    chomp(my $cwd = `pwd`);

    # Step 1: Create a temporary directory for downloading certificate 
    my  $igtf_working_dir = tempdir("osg-rsv-cacerts-igtf-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($igtf_working_dir);

    my $ret_code = 0;
    my $cmd = "wget $o{'igtfTarballUrl'} 2>&1";

    # Step 2: Get the index.html file to figure out version number
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    $cmd = "cat $igtf_working_dir/index.html |  grep -P '\\\"igtf-preinstalled-bundle-classic-\\d+\\.\\d+\\.tar\\.gz\\\"'";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);
    my $out = $o{'cmdOut'};
    my ($major,$minor) = $out =~ /igtf-preinstalled-bundle-classic-(\d+)\.(\d+)/;
    
    # Step 3: Download and untar the 3 IGTF tarballs
    
    $cmd = "wget $o{'igtfTarballUrl'}/igtf-preinstalled-bundle-classic-$major.$minor.tar.gz 2>&1 && tar zxf igtf-preinstalled-bundle-classic-$major.$minor.tar.gz";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    $cmd = "wget $o{'igtfTarballUrl'}/igtf-preinstalled-bundle-mics-$major.$minor.tar.gz 2>&1 && tar zxf igtf-preinstalled-bundle-mics-$major.$minor.tar.gz";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    $cmd = "wget $o{'igtfTarballUrl'}/igtf-preinstalled-bundle-slcs-$major.$minor.tar.gz 2>&1 && tar zxf igtf-preinstalled-bundle-slcs-$major.$minor.tar.gz";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    if($ret_code != 0) {
        $status_out = "Error when downloading necessary IGTF file from '$o{'igtfTarballUrl'}'.\n";
        $status_code = 2;
    }

    # Record where the IGTF certs are
    $o{'igtf_cert_dir'} = $igtf_working_dir;
    $o{'status_code'} = $status_code;
    $o{'status_out'} = $status_out;

    chdir($cwd); 
    return \%o;
}
##---------------------------------------------------------------------
##  
## Get_Check_OSG_RPM: Get the OSG RPMs and check its md5sum against IGTF certificates
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'rpmUrl'    Location of OSG certificate RPMs
##      'igtf_cert_dir'      Location of downloaded IGTF certificates 
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##      'osg_rpm_cert_dir' : Where the downloaded certs are located
##
##---------------------------------------------------------------------
sub Get_Check_OSG_RPM{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Get_Check_OSG_RPM()";
    chomp(my $cwd = `pwd`);

    # Download files from OSG RPM and extract it
    my  $osgrpm_working_dir = tempdir("osg-rsv-cacerts-osgrpm-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($osgrpm_working_dir);

    my $ret_code = 0;
    my $cmd = "wget $o{'rpmUrl'} 2>&1";

    # Step 1: Get the index.html file to figure out version number
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    $cmd = "cat index.html |  grep -P '\\\"osg-ca-certs-\\d+\\.\\d+-\\d+\\.noarch\\.rpm\\\"'";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);
    my $out = $o{'cmdOut'};
## AG: CHeck regex
#    my ($major,$minor, $sub) = $out =~ /"osg-ca-certs-(\d+)\.(\d+)-(\d+)/;
    my ($major,$minor, $sub) = $out =~ /osg-ca-certs-(\d+)\.(\d+)-(\d+)/;

    # Step 2: Download and get files from rpm
    $cmd = "wget ". $o{'rpmUrl'} ."/osg-ca-certs-$major.$minor-$sub.noarch.rpm 2>&1 && rpm2cpio osg-ca-certs-$major.$minor-$sub.noarch.rpm | cpio -idm 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);


    if($ret_code != 0) {
        $status_out .= "Error when processing/downloading necessary OSG CA RPMs '$o{'rpmUrl'}'.\n";
        $status_code = 2;
    }elsif(! $o{'igtf_cert_dir'}){
        # The IGTF directory to make comparison against is not defined. 
        # So we will just download the OSG RPMs and will not make md5sum comparison.
        # Do Nothing.
    }else{
        # Step 3: OSG RPM files have been downloaded. Now check the md5sum
        $o{'local_dir'} = "$osgrpm_working_dir/etc/grid-security/certificates";
        $o{'local_cache'} = "OSG RPM";
        %o = %{&Check_Md5sum(\%o)};
        $status_out .= $o{'status_out'};
        $status_code = 2 if($o{'status_code'}==2);
        $status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
        $status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
    }
    $o{'osg_rpm_cert_dir'} = "$osgrpm_working_dir/etc/grid-security/certificates";
    $o{'status_code'} = $status_code;
    $o{'status_out'} = $status_out;
    
    chdir($cwd); 
    return \%o;
}
##---------------------------------------------------------------------
##  
## Get_Check_VDT_RPM: Get the VDT RPMs and check its md5sum against IGTF certificates
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'rpmUrl'    Location of VDT certificate RPMs
##      'igtf_cert_dir'      Location of downloaded IGTF certificates 
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##      'osg_rpm_cert_dir' : Where the downloaded certs are located
##
##---------------------------------------------------------------------
sub Get_Check_VDT_RPM{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Get_Check_VDT_RPM()";
    chomp(my $cwd = `pwd`);

    # Download files from OSG RPM and extract it
    my  $vdtrpm_working_dir = tempdir("osg-rsv-cacerts-vdtrpm-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($vdtrpm_working_dir);

    my $ret_code = 0;
    my $cmd = "wget $o{'rpmUrl'} 2>&1";

    # Step 1: Get the index.html file to figure out version number
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    $cmd = "cat index.html |  grep -P '\\\"vdt-ca-certs-\\d+-\\d+\\.noarch\\.rpm\\\"'";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);
    my @values = split /\n/, $o{'cmdOut'};

    # The last line has the latest certificate
    my $out = $values[$#values];

    my ($major,$minor) = $out =~ /"vdt-ca-certs-(\d+)-(\d+)\.noarch\.rpm"/;

    # Step 2: Download and get files from rpm
    $cmd = "wget ". $o{'rpmUrl'} ."/vdt-ca-certs-$major-$minor.noarch.rpm 2>&1 && rpm2cpio vdt-ca-certs-$major-$minor.noarch.rpm | cpio -idm 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    if($ret_code != 0) {
        $status_out .= "Error when processing/downloading necessary VDT CA RPMs from '$o{'rpmUrl'}'.\n";
        $status_code = 2;
    }elsif(! $o{'igtf_cert_dir'}){
        # The IGTF directory to make comparison against is not defined. 
        # So we will just download the VDT RPMs and will not make md5sum comparison.
        # Do Nothing.
    }else{
        # Step 3: VDT RPM files have been downloaded. Now check the md5sum
        $o{'local_dir'} = "$vdtrpm_working_dir/etc/grid-security/certificates";
        $o{'local_cache'} = "VDT RPM";
        %o = %{&Check_Md5sum(\%o)};
        $status_out .= $o{'status_out'};
        $status_code = 2 if($o{'status_code'}==2);
        $status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
        $status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
    }
    $o{'osg_rpm_cert_dir'} = "$vdtrpm_working_dir/etc/grid-security/certificates";
    $o{'status_code'} = $status_code;
    $o{'status_out'} = $status_out;
    
    chdir($cwd); 
    return \%o;
}
##---------------------------------------------------------------------
##  
## Get_Check_OSG_VDT_Tar: Get the OSG/VDT certificate tarcalls and check its md5sum against IGTF certificates
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'tarballUrl'    Location of certificate tarball to be downloaded and examined
##      'igtf_cert_dir'      Location of downloaded IGTF certificates. (If not set just download tarball)
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##      'osg_tar_cert_dir' : Where the downloaded certs are located
##
##---------------------------------------------------------------------
sub Get_Check_OSG_VDT_Tar{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Get_Check_OSG_VDT_Tar()";

    my $cache = $o{'cache'};
    chomp(my $cwd = `pwd`);

    # Download files from OSG RPM and extract it
    my  $tar_working_dir = tempdir("osg-rsv-cacerts-$cache-tar-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($tar_working_dir);

    my $ret_code = 0;
    my $cmd = "wget $o{'tarballUrl'} 2>&1";

    # Step 1: Get the description file to figure out what tarball to download
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);


    $cmd = "cat ".basename($o{'tarballUrl'})." |  grep -P 'tarball='";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);
    chomp(my $url = (split /=/, $o{'cmdOut'})[1]);

    # Step 2: Download and get files from tarball
    $cmd = "wget $url 2>&1 && tar zxf ".basename($url)." 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    $ret_code = $o{'cmdExitValue'} if($ret_code==0);

    if($ret_code != 0) {
        $status_out .= "Error when processing/downloading necessary $cache CA certificate tarball from '$o{'tarballUrl'}'.\n";
        $status_code = 2;
    }elsif(! $o{'igtf_cert_dir'}){
        # The IGTF directory to make comparison against is not defined. 
        # So we will just download the tarballs and will not make md5sum comparison.
        # This path is ued when we just want to download the OSG CA tarballs
        # Do Nothing.
    }else{
        # Step 3: OSG/VDT tar files have been downloaded. Now check the md5sum
        $o{'local_dir'} = "$tar_working_dir/certificates";
        $o{'local_cache'} = uc($cache)." tarball";
        %o = %{&Check_Md5sum(\%o)};
        $status_out .= $o{'status_out'};
        $status_code = 2 if($o{'status_code'}==2);
        $status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
        $status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
    }
    $o{$cache.'_tar_cert_dir'} = "$tar_working_dir/certificates";
    $o{'status_code'} = $status_code;
    $o{'status_out'} = $status_out;
    
    chdir($cwd); 
    return \%o;
}

##---------------------------------------------------------------------
##  
## Check_Md5sum: Compare md5sum of certificate in OSG/VDT tarball/rpm against
##               md5sum of the corresponding IGTF certificates
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'local_dir'    Location of certificates to be examined
##      'igtf_cert_dir'    Location of the IGTF certificates.
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##
##---------------------------------------------------------------------
sub Check_Md5sum{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Check_Md5sum()";

    chomp(my $cwd = `pwd`);

    my $igtf_working_dir = $o{'igtf_cert_dir'};
    my $local_dir = $o{'local_dir'};

    chdir($igtf_working_dir);
    my $cmd = "ls -1 *.0";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    my @files = split /\n/, $o{'cmdOut'};

    foreach my $file (@files){
        if(! -e "$local_dir/$file"){
            $status_code = 1 if ($status_code!= 2);
            $status_out .= "$o{'local_cache'}: IGTF has a certificate file '$file' that is missing from $o{'local_cache'}.\n";
            next;
        }
        $cmd = "md5sum $file";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my $igtf_md5 = (split / /, $o{'cmdOut'})[0];

        $cmd = "md5sum $local_dir/$file";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        my $local_md5 = (split / /, $o{'cmdOut'})[0];

        if($igtf_md5 != $local_md5){
            $status_code = 2;
            $status_out .= " $o{'local_cache'}: IGTF has a differnt version of certificate file '$file' than $o{'local_cache'}.\n";
        }
    }

    $o{'status_code'} = $status_code;
    $o{'status_out'} = $status_out;

    chdir($cwd); 
    return \%o;
}


##---------------------------------------------------------------------
##  
## Edg_Check_CA_DN: Check if the certificate directory contains all CAs needed
##                  by the DNs listed in the grid-mapfile (generated by edg-mkgridmap)
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'osgTar'    Location of OSG certificate tarball.
##      'certDir'   Location of the local certificates. 
##     
## Returns 
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##
##---------------------------------------------------------------------
sub Edg_Check_CA_DN{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    my $cert_dir = "";
    $o{'callingRoutine'} = "Edg_Check_CA_DN()";

    chomp(my $cwd = `pwd`);
    chdir($cwd);

    # Step 1: Download cert from OSG tarball
    if ($o{'certDir'}){
        $cert_dir = $o{'certDir'};
    }else{
        $o{'cache'} = "osg";
        &Get_Check_OSG_VDT_Tar();
        $status_out .= $o{'status_out'};
        $status_code = 2 if($o{'status_code'}==2);
        $status_code = 1 if($o{'status_code'}==1 && $status_code !=2); # Change status code to warning only if we don't already have error
        $status_code = 3 if($o{'status_code'}==3 && $status_code ==0); # Change status code to Unknown only if we don't already have error/warning
        if($status_code!=0){
            # OSG certs were not correctly downloaded. No point in checking the DNs.
            &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
            return \%metric;  
        }
        $cert_dir =  $o{'osg_tar_cert_dir'};
        $o{'status_out'} ="";
        $o{'status_code'}=0;
    }

    # Step 2: Run edg-mkdirgmap (assumes edg-mkdridmap has been downloaded and has been configured with VO list from GOC)
    my $cmd =  "export GRIDMAP=".$o{'edgVdtInstallBaseDir'}."/edg/etc/gridmap-file;  export X509_USER_CERT=/etc/grid-security/http/httpcert.pem; export X509_USER_KEY=/etc/grid-security/http/httpkey.pem; ".$o{'edgVdtInstallBaseDir'}."/edg/sbin/edg-mkgridmap";
    &RSVProbeBase::Run_Command ($cmd, "backtick"); 

    # Currently no errorcode or stdout is being returned. We assume it ran successfully
    # We might be able to get some output from the log file

    # Step 3: Get the VO/User ID names and VOMS
    my $edgconf = $o{'edgVdtInstallBaseDir'}."/edg/etc/edg-mkgridmap.conf";
    #Doesnot check for missing conf file. Not a big problem for centralized probe
    open FILE, $edgconf;
    my %voms;
    my %uservomap;
    my $vo;
    while (<FILE>){
        next if (/^\s*$/);
        next if (/^\s*#-/);
        if (/^# USER-VO-MAP\s+(\S+)\s*/){  
            $vo = $1;
        }
        if (/^\s*group\s+(\S+)\s*(\S+)/){  
            $voms{$vo}= $1;
            $uservomap{$2}=$vo;
        }
    }
    close FILE;

    # Step 4: For each DN in gridmap file see if there is a appropriate CA.
    opendir(CERTDIR,"$cert_dir");
    # Doesnot through up error is $cert_dir is missing.
    my @filenames = readdir(CERTDIR);
    closedir(CERTDIR);

    my @hashes;
    my @subjectregexes;
    my @subjecthashes;
    my %canames;
    
    for (@filenames) {
        if (/(.*)\.signing_policy/) {
            my $hash = $1;
            open POLICY, "<$cert_dir/$_";
            push(@hashes, $hash);
            while (<POLICY>) {
                if (/access_id_CA\s*X509\s*(.*)/) {
                    $canames{$hash} = $1;
                }
                if (/pos_rights\s*globus\s*CA:sign/) {
                    # shrug
                }
                if (/cond_subjects\s*globus\s(.*)/) {
                    my @subjects = split(/[\'\"]+/,$1);
                    for (@subjects) {
                        if (!/^\s*$/) {
                            if (/\*/) {
                                s/\*/\.\*/;       # convert to perl regex
                            }
                            push(@subjectregexes, $_);
                            push(@subjecthashes, $hash);
                        }
                    }
                }
            }
            close(POLICY);
        }
    }
    # Step 5: Find CAs that match DNs in gridmap file
    my @dns_without_ca;
    my $gridmap = $o{'edgVdtInstallBaseDir'}."/edg/etc/gridmap-file";
    open GRIDMAP, "<$gridmap" ;
    my $output;
    while (<GRIDMAP>) {
        chomp;
        /\s*"(.*)"\s+(\S*)\s*/;
        my $dn = $1;  
        my $username = $2;
        #my @tmp = (split /"/, $_);
        #my $dn = $tmp[1];
        #my $username = $tmp[2] =~ /\s*(\S*)\s*/;
        #print "$username\n";
        my $dn_exist = 0;
        for (my $i=0; $i<=$#subjectregexes && !$dn_exist; $i++) {
                           # print "$dn: $subjectregexes[$i]\n" if($i==$#subjectregexes-1);# if( $dn =~ m/irisgrid/ &&  $subjectregexes[$i] =~ m/irisgrid/ );
            if ($dn =~ m/$subjectregexes[$i]/i) {
                $dn_exist=1;
            }
        }
        if(!$dn_exist){
            my $voname = $uservomap{$username};
            my $vomsloc = $voms{$voname};
            $output->{$vomsloc}->{'vo'}= $voname;
            $output->{$vomsloc}->{$dn} = $dn;
            $status_code = 2;
            #$status_out .= "No CA found for the DN: $dn, $vo\n";
            #$status_out .= "\tDN came from VO: $voname \n\tvoms server: $vomsloc\n";
        }
    }
    for my $voms (keys %{$output}){
        $status_out .= "\nVO NAME: ".$output->{$voms}->{'vo'}." VOMS Server: ".$voms."\n";
        $status_out .= "\tDNs either misspelled of with missing CAs:\n";
        for my $dn (keys %{$output->{$voms}}){
            next if ($dn =~ /^vo$/);
            $status_out .= "\t\t$dn\n";
        }
    }
    $status_out .= "CAs for all user DNs were found.\n"  if ($status_code==0);
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;
}

##---------------------------------------------------------------------
##  
## Check_VOMS: Check if the VOMS server return VO list correctly
##
## parameters :
##  First:
##   %Probe hash
##  Second:
##   %metric hash
##  Third:
##   %local hash containing
##
## Returns
##   Pointer to local hash with all the details set including
##      'status_code' : Status code relating to download and md5sum checks
##      'status_out'  : Results from the download and md5sum checks
##
##---------------------------------------------------------------------

sub Check_VOMS{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = ""; # Compile detailed data for output by RSV
    $o{'callingRoutine'} = "Check_VOMS()";

    #Step 1: Locate eng-mkgridmap configuration file and scripts
    my $edg_conf = "$o{'edgInstallBaseDir'}/edg/etc/edg-mkgridmap.conf";
    my $edg_pl = "$o{'edgInstallBaseDir'}/edg/libexec/edg-mkgridmap/edg-mkgridmap.pl";
    return \%{&RSVProbeBase::Set_Summary_Metric_Results (3,"Config file '$edg_conf' does not exist")} if (!-e $edg_conf);
    return \%{&RSVProbeBase::Set_Summary_Metric_Results (3,"Script '$edg_pl' does not exist")} if (!-e $edg_pl);

    open EDG, "<$edg_conf" or return \%{&RSVProbeBase::Set_Summary_Metric_Results (3,"Could not open '$edg_conf' config file")};

    # Step 2: Download the DN list from the  VOs using  edg-mkgridmap
    my $working_dir = tempdir("rsvprobe-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    while (<EDG>){
        chomp;
        next if (/^\s*$/ || /^\s*#/);
        my $vo = (split /\s+/,$_)[2];
        my $vo_conf = "$working_dir/$vo-edg-mkgridmap.conf";
        my $vo_out = "$working_dir/$vo.map";
        open TMPCONF, ">$vo_conf"  or return \%{&RSVProbeBase::Set_Summary_Metric_Results (3,"Could write temporary config file $vo_conf")};
        print TMPCONF "$_";
        close TMPCONF;
        #ececute edg-mkgridmap on each VOs VOMS server
        my $env = "export EDG_LOCATION=$o{'edgInstallBaseDir'}/edg; export EDG_LOCATION_VAR=$o{'edgInstallBaseDir'}/edg/var; export GRIDMAP=$vo_out.map; export CERTDIR=$o{'edgInstallBaseDir'}/globus/TRUSTED_CA; export X509_USER_CERT=/etc/grid-security/rsvcert.pem; export X509_USER_KEY=/etc/grid-security/rsvkey.pem"; #TODO: Take RSV CERT and KEY from arguments

        my $cmd ="source $o{'edgInstallBaseDir'}/setup.sh; $env ; $edg_pl --conf $vo_conf --output $vo_out 2>&1";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
        if ($o{'cmdExitValue'} !=0){
            # VOMS Server returned an error
            $status_code = 2;
            $status_out .= "Error encountered when downloading DNs for VO $vo\n";
            #, from voms server at : ";
            #open TMPCONF, $vo_conf; 
            #while(<TMPCONF>) {chomp; $status_out .= $_;}
            #close TMPCONF;
            $status_out .= "\n\tError Code: $o{'cmdExitValue'}\n\tDetails: $o{'cmdOut'}\n";
        }

    }
    close EDG;

    $status_out .= "OK: All VOMS servers were contacted successfully\n" if ($status_code==0);
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;

}

##############################Site Level Probes ###############################
##---------------------------------------------------------------------
##  
## Check_Freshness_Local_CRL: Checks the last time when the CRLs were successfully downloaded
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'   Directory where CA certs (*.0) can be found 
##      'errorHrs'  Number hours since the failing downloads before an error is issued
##      'warnHrs'   Number hours since the failing downloads before a warning is issued
##      'type'      Value can be 'osg' or 'egee', to identify the OSG and EGEE CRL Mertics
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_Freshness_Local_CRL{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = "Security Probe Version: $site_rsv_probe_version\n"; # Compile detailed data for output by RSV
    my %source;
    my %source_newhash;
    my %found_crls;
    my $itb = 0;
    my $ca_format_type = 0;
    my $cmd;
    my @contents;
    my $type = 0; #openssl v < 1.

    $o{'callingRoutine'} = "Check_Freshness_Local_CRL()";

    # Step 1: Get the list of Certs included in OSG from GOC website.
    chomp(my $cwd = `pwd`);
    my $working_dir = tempdir("osgrsv-crl`-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($working_dir);
    my $local_url="http://software.grid.iu.edu/pacman/cadist/INDEX.txt";
    #Check if the file CA cers are installed from ITB
    my $ca_version_script= "$o{'PROBE_DIR_LOCAL'}/worker-scripts/ca_version.sh";
    if (!$o{'localCE'}){
        $cmd = "-s  $ca_version_script \"$o{'certDir'}\" 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
    }else{
        $cmd = "$ca_version_script \"$o{'certDir'}\" 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }
    @contents = split /\n/, $o{'cmdOut'};

    if ($contents[0] =~ /ITB/i) {
        $itb=1;
        #$local_url="http://software-itb.grid.iu.edu/pacman/cadist/INDEX.txt";
    }
    $ca_format_type=$contents[1];
    if($itb==1 && $ca_format_type==0){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/INDEX.txt";
    }elsif($itb==1 && $ca_format_type==1){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/INDEX-new.txt";
    }elsif($itb==0 && $ca_format_type==0){
        $local_url="http://software.grid.iu.edu/pacman/cadist/INDEX.txt";
    }elsif($itb==0 && $ca_format_type==1){
        $local_url="http://software.grid.iu.edu/pacman/cadist/INDEX-new.txt";
    }

    $cmd = "wget $local_url 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    chdir($cwd); 
    if ($o{'cmdExitValue'} !=0){
        # Could not download the CA list from OSG. Setting test value as Unknown
        $status_code = 3;
        $status_out .= " Could not download the CA list from OSG ($local_url). Unable to test CRLs.";
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;
    }
    my $ca_index_file = "$working_dir/".basename($local_url);

    open FILE, "< $ca_index_file" or &RSVProbeBase::Set_Summary_Metric_Results (3,"The downloaded CA list from OSG could not be opened. Unable to test CRLs.") && return \%metric; 
    @contents = <FILE>;  
    foreach my $line (@contents) {
        next if($line =~ /^Hash/i);
        next if($line =~ /^--/i);
        next if($line =~ /^\s+$/i); #Empty lines
        next if($line =~ /^#/i); #allow comments in future
        last if($line =~ /^Sources/i); #Reached end of file
        my @line_content = split /\s+/, $line;
        my $hash = $line_content[0];
        $source{$hash}=$line_content[$#line_content];
        if ($ca_format_type==1){
	     # New format. Also consider a new hash
             my $new_hash=$line_content[1];
             $source_newhash{$new_hash}=$line_content[$#line_content];
        }
    }
    close FILE;
 
    # Step 2: Get and Check time stamps on the CRL files to ensure that it has been recently downloaded
    my $missing_count = 0;
    if (!$o{'localCE'}){
        $cmd = "-s  $o{'workerScriptFile'} \"$o{'certDir'}/*.r0\" 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
    }else{
        $cmd = "$o{'workerScriptFile'} \"$o{'certDir'}/*.r0\" 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }

    
    #$cmd = "ls -1 $o{'certDir'}/*.r0";
    #&RSVProbeBase::Run_Command ($cmd, "backtick");
    my @crl_files = split /\n/, $o{'cmdOut'};
    if ($crl_files[$#crl_files] != 0){
        &RSVProbeBase::Set_Summary_Metric_Results (3,"Could not calculate md5sums of your CA file at $o{'hostName'}:$o{'certDir'}/*.r0.");
        return \%metric;
    }

    my $error_count = my $warn_count = my $ok_count = 0;

    for (my $i=0; $i<$#crl_files;$i++){   
        my ($local_crl_file, $last_update) = split /\s/, $crl_files[$i];
 
        chomp($local_crl_file);
        chomp(my $local_hash = (split(/\.r0/,basename($local_crl_file)))[0]);
        # List of CRLs found.
        $found_crls{$local_hash} = $local_hash;


        #next if (!exists $source{$local_hash}); 
        # Ignore CRLs not from OSG.
        next if ($ca_format_type==0 && !exists $source{$local_hash});
        next if ($ca_format_type==1 && !(exists $source{$local_hash} || exists $source_newhash{$local_hash}));

        #next if ($o{'type'} =~ /egee/i && $source{$local_hash} !~ m/I/ ); 
        #For EGEE test we want to check only IGTF CAs
        if (exists $source_newhash{$local_hash}){
            # Assuming that the hash for CRL files will be either md5 or sha1 not both
            $type=1;
            next if ($o{'type'} =~ /egee/ &&  $source_newhash{$local_hash} !~ m/I/ ); 
        }
        if (exists $source{$local_hash}){
            next if ($o{'type'} =~ /egee/ && $source{$local_hash} !~ m/I/ );
        }
        

        #my $last_update = (stat($local_crl_file))[9];
        my $now = time();
        if($now >= $last_update + $o{'errorHrs'}*60*60){
            $status_code = 2;
            $status_out .= "ERROR: CRL file for CA with hash '$local_hash' has not been updated for since ".localtime($last_update)."\n";
            $error_count++;
        }elsif($now >= $last_update + $o{'warnHrs'}*60*60){
            $status_code = 1 if($status_code!=2);
            $status_out .= "WARNING: CRL file for CA with hash '$local_hash' has not been updated for since ".localtime($last_update)."\n";
            $warn_count++;
        }else{
            #$status_out .= "OK: CRL file for CA with hash '$local_hash' was last downloaded on ".localtime($last_update)."\n" if ($o{'verbose'});
            $ok_count++;
        }

    }

    # Step 3: Check if any CRLs are missing.
    my $missing_count = 0;
    if ($type==0){
       #MD5 hashes observed
       for my $local_hash ( keys %source ) {
            next if ($o{'type'} =~ /^egee$/i &&  $source{$local_hash} !~ /I/ ); # Ignore non IGTF CAs for wlcg probe
            next if (exists $found_crls{$local_hash}); # CRL was present. 
            next if (! -e "$o{'certDir'}/$local_hash.0"); # CA is not present 
            $status_code = 1 if($status_code!=2);
            $status_out .= "MISSING: CRL file for '$local_hash' is missing. OSG policy requires CRL for every CA distributed by OSG.\n";
            $missing_count++;
        }
    }elsif($type == 1){
        #Sha1 hashes observed
       for my $local_hash ( keys %source_newhash ) {
            next if ($o{'type'} =~ /^egee$/i &&  $source_newhash{$local_hash} !~ /I/ ); # Ignore non IGTF CAs for wlcg probe
            next if (exists $found_crls{$local_hash}); # CRL was present. 
            next if (! -e "$o{'certDir'}/$local_hash.0"); # CA is not present 
            $status_code = 1 if($status_code!=2);
            $status_out .= "MISSING: CRL file for '$local_hash' is missing. OSG policy requires CRL for every CA distributed by OSG.\n";
            $missing_count++;
        }

    }
    
	# Step 4: See if the warning should be escalated to an error
    my $now = time();
    my $last_update;
    if ($status_code==0){
        # Remove error file if exists 
        if (-e $o{'errorFile'}){
            $cmd = "rm  $o{'errorFile'}";
            &RSVProbeBase::Run_Command ($cmd, "backtick");
            if ($o{'cmdExitValue'} !=0){
                $status_out .= "Could not delete the error file (".$o{'errorFile'}."). Please delete it by hand to avoid potential future problems.\n";
            }
        }
    }elsif ($status_code==1){
        if (-e $o{'errorFile'}){
            open FILE, "< $o{'errorFile'}" or $status_out .= "Could not record error file ('".$o{'errorFile'}."') indicating CA file is out of sync. This probe may never escalate to an error stage. \n";
            my @tmp_lines = <FILE>;
            chomp($last_update = $tmp_lines[0]);
            close FILE;
            if ($last_update != "" && $now > $last_update + $o{'errorHrs'}*60*60){
                # Escalate warning to error
                $status_code = 2;
                $status_out .= "Escalating WARNING to ERROR.";
            }
        }else{
            # Out of sync for the first time. Create error record.
            open FILE, "> $o{'errorFile'}" or $status_out .= "Could not record error file indicating CA file is out of sync. This probe may never escalate to an error stage. \n";
            print FILE time;
            close FILE;
        }   
    }
    
    # Step 5: Recording the result for RSV output
    $status_out .= "OK: All CRLs have been recently updated\n" if ($status_code==0);
    $status_out .= ($error_count+$warn_count+$ok_count)." CRLs tested.\n\t$error_count had not been updated for atleast $o{'errorHrs'} hours;\n\t$warn_count CRLs have not been updated for atleast $o{'warnHrs'} hours;\n\t$ok_count CRLs have been updated with the last $o{'warnHrs'} hours.\n";
	$status_out .="\t $missing_count CRLs are missing.\n" if ($missing_count !=0);
	&RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;
}
##---------------------------------------------------------------------
##  
## Check_Local_CA: Checks the local CA directory md5sum with OSG central md5sums
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'   Directory where CA certs (*.0) can be found # Not used any morw
##      'errorHrs'  Number hours since the failing downloads before an error is issued
##      'errorFile'  Error file to be used to record results
##      'type'      Value can be 'osg' or 'egee', to identify the OSG and EGEE CRL Mertics
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_Local_CA{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = "Security Probe Version: $site_rsv_probe_version\n"; # Compile detailed data for output by RSV
    my %source;
    my %found_cas;
    my %md5;
    my @error_hash;
    my @egee_error_hash;
    my $cmd;
    my @contents;
    my $itb=0;
    my $ca_format_type=0;

    $o{'callingRoutine'} = "Check_Local_CA()";

    # Step 1: Download the md5sums for CAs in the OSG/ITB
    chomp(my $cwd = `pwd`);
    my $working_dir = tempdir("osgrsv-ca`-XXXXXX", TMPDIR => 1, CLEANUP => 1);
    chdir($working_dir);
    my $local_url="http://software.grid.iu.edu/pacman/cadist/cacerts_md5sum.txt";
    #Check if the file CA cers are installed from ITB
    my $ca_version_script= "$o{'PROBE_DIR_LOCAL'}/worker-scripts/ca_version.sh";

    if (!defined $o{'localCE'}){
        $cmd = "-s  $ca_version_script \"$o{'REMOTE_ENV'}{'OSG_LOCATION'}\" 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
    }else{
        $cmd = "$ca_version_script \"$o{'VDT_LOCATION_LOCAL'}\" 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }
    @contents = split /\n/, $o{'cmdOut'};

    if ($contents[0] =~ /ITB/i) {
        $itb=1;
    }
    $ca_format_type=$contents[1];
    # Get the list of CAs installed on remote CE and their md5sums
    if($itb==1 && $ca_format_type==0){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/cacerts_md5sum.txt";
    }elsif($itb==1 && $ca_format_type==1){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/cacerts_md5sum-new.txt";
    }elsif($itb==0 && $ca_format_type==0){
        $local_url="http://software.grid.iu.edu/pacman/cadist/cacerts_md5sum.txt";
    }elsif($itb==0 && $ca_format_type==1){
        $local_url="http://software.grid.iu.edu/pacman/cadist/cacerts_md5sum-new.txt";
    }

    if ($contents[$#contents] != 0){
        &RSVProbeBase::Set_Summary_Metric_Results (3,"Could not calculate md5sums of your CA file from $o{'hostName'}.");
        return \%metric;
    }
    my %file_md5sum = ();
    for (my $i=2; $i<$#contents;$i++){
        my @tmp = split /\s+/, $contents[$i];
        $file_md5sum{(split(/\./,basename($tmp[1])))[0]} = $tmp[0];
    }


    # Download the ms5sum file from OSG/ITB cache
    $cmd = "wget $local_url 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    my $local_md5_file = "$working_dir/".basename($local_url);
    chdir($cwd); 
    if ($o{'cmdExitValue'} !=0){
        # Could not download the CA list from OSG/ITB Cache. Setting test value as Unknown
        $status_code = 3;
        $status_out .= " Could not download the md5sum for CA list from OSG ($local_url). Unable to verify CAs.";
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;
    }
    open FILE, "< $local_md5_file" or &RSVProbeBase::Set_Summary_Metric_Results (3,"The downloaded md5sum file from OSG could not be opened. Unable to verify CAs.") && return \%metric; 
    @contents = <FILE>;
    foreach my $line (@contents) {
        chomp($line);
        my @values = split /\s+/, $line;
        chomp(my $local_hash = (split(/\./,$values[1]))[0]);
        $md5{$local_hash} = $values[0];
    }
    close FILE;


    # Step 2: Get the list of Certs included in OSG from GOC website.
    chdir($working_dir);
    if($itb==1 && $ca_format_type==0){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/INDEX.txt";
    }elsif($itb==1 && $ca_format_type==1){
        $local_url="http://software-itb.grid.iu.edu/pacman/cadist/INDEX-new.txt";
    }elsif($itb==0 && $ca_format_type==0){
        $local_url="http://software.grid.iu.edu/pacman/cadist/INDEX.txt";
    }elsif($itb==0 && $ca_format_type==1){
        $local_url="http://software.grid.iu.edu/pacman/cadist/INDEX-new.txt";
    }

    my $cmd = "wget $local_url 2>&1";
    &RSVProbeBase::Run_Command ($cmd, "backtick");
    chdir($cwd); 
    if ($o{'cmdExitValue'} !=0){
        # Could not download the CA list from OSG. Setting test value as Unknown
        $status_code = 3;
        $status_out .= " Could not download the CA list from OSG ($local_url). Unable to verify CAs";
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;
    }
    my $ca_index_file = "$working_dir/".basename($local_url);

    open FILE, "< $ca_index_file" or &RSVProbeBase::Set_Summary_Metric_Results (3,"The downloaded CA list from OSG could not be opened. Unable to verify CAs.") && return \%metric;
    @contents = <FILE>;  
    foreach my $line (@contents) {
        next if($line =~ /^Hash/i);
        next if($line =~ /^--/i);
        next if($line =~ /^\s+$/i); #Empty lines
        next if($line =~ /^\#/i); #allow comments in future
	last if($line =~ /^Sources/i); #Reached end of file

	my @line_content = split /\s+/, $line;
        my $hash = $line_content[0];
	if ($ca_format_type == 1) {
             # New CA format type we use file names
	     $hash =  (split(/\./,$line_content[2]))[0];
        }
        $source{$hash}=$line_content[$#line_content];
    }
    close FILE;

    # Step 3: Check the CAs to ensure that md5sums matchup
    my $error_count = my $warn_count = my $ok_count = 0;

    foreach my $local_hash (keys %file_md5sum) {
        # List of CAs found.
        $found_cas{$local_hash} = $local_hash;
        next if (!exists $md5{$local_hash}); # Ignore CAs not from OSG.
        #next if (!exists $source{$local_hash}); # Ignore CAs not from OSG.

        next if ($o{'type'} =~ /egee/i && $source{$local_hash} !~ m/I/ ); #For EGEE test we want to check only IGTF CAs

        # Calculate md5sum of the CA
        my $local_md5 = $file_md5sum{$local_hash};
        if ($local_md5 != $md5{$local_hash}){
            # We have detected atleast a warning
            $status_code = 1;
            push @error_hash, $local_hash;
        }
    }
    # Step 4: Special Case: For EGEE tests we want to notify of errors if any IGTF CAs are missing.
    my $missing_count = 0;
    if ($o{'type'} =~ /^egee$/i){
        for my $local_hash ( keys %source ) {
            next if ($source{$local_hash} !~ /I/ ); # Ignore non IGTF CAs
            next if (exists $found_cas{$local_hash}); # CA was present. 
            $status_code = 1;
            push @egee_error_hash, $local_hash;
            $missing_count++;
        }
    }
    
    # Step 6: See if the warning should be an error
    my $now = time();
    my $last_update;
    
    if ($status_code==0){
        # Remove error file if exists 
        if (-e $o{'errorFile'}){
            $cmd = "rm  $o{'errorFile'}";
            &RSVProbeBase::Run_Command ($cmd, "backtick");
            if ($o{'cmdExitValue'} !=0){
                $status_out .= "Could not delete the error file (".$o{'errorFile'}."). Please delete it by hand to avoid potential future problems.\n";
            }
        }
    }elsif ($status_code==1){
        if (-e $o{'errorFile'}){
            open FILE, "< $o{'errorFile'}" or $status_out .= "Could not record error file ('".$o{'errorFile'}."') indicating CA file is out of sync. This probe may never escalate to an error stage. \n";
            my @tmp_lines = <FILE>;
            chomp($last_update = $tmp_lines[0]);
            close FILE;
            if ($last_update != "" && $now > $last_update + $o{'errorHrs'}*60*60){
                # Escalate warning to error
                $status_code = 2;
                $status_out .= "ERROR: ";
            }else{
                $status_out .= "WARNING: ";
            }
        }else{
            # Out of sync for the first time. Create error record.
            open FILE, "> $o{'errorFile'}" or $status_out .= "Could not record error file indicating CA file is out of sync. This probe may never escalate to an error stage. \n";
            print FILE time;
            close FILE;
            $status_out .= "WARNING: ";
        }
        $status_out .= "Few of the files in your installations are out of sync with the OSG distribution.\n";
        $status_out .= "\tThe CA that are out of sync are: @error_hash \n";
        $status_out .= "\tPlease ensure that your CA update process (e.g. vdt-update-certs or yum update) is configured and running \n\n";
        $status_out .= "\t$missing_count IGTF CAs are missing and is required for sites that need to conform to EGEE policy.\n";
        $status_out .= "\tList of missing CAs include: @egee_error_hash.\n";
    }


	# Step 6: Recording the result for RSV output
	$status_out .= "OK: CAs are in sync with OSG distribution\n" if ($status_code==0);
	&RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
	return \%metric;
}

##---------------------------------------------------------------------
##  
## Check_Supported_VO: Checks if the local CA directory has all the 
## certificates needed to support the VO in the supported-vo list
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'certDir'   Directory where CA certs (*.0) can be found 
##      'caVoURL'   Location of the file containing the list of CAs needed by VOs
##      'supportedVo'   Location of file containing the list of supported VOs for a site
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_Supported_VO{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = "Security Probe Version: $site_rsv_probe_version\n"; # Compile detailed data for output by RSV
    my $cmd = "";
    # Step 1: Run the probe code remotely/locally and get the result
    if (!$o{'localCE'}){
        $cmd = "-s  $o{'workerScriptFile'} $o{'caVoURL'} $o{'supportedVo'} $o{'certDir'} 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
    }else{
        $cmd = "$o{'workerScriptFile'} $o{'caVoURL'} $o{'supportedVo'} $o{'certDir'} 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }
    if ($o{'cmdOut'} =~ /^$/){
        $status_code = 3;
        $status_out .= "No result returned by running '$cmd'. Quitting.."
    }else {
        ($status_code,$status_out) = split /<split>/, $o{'cmdOut'};
        $status_out = "Security Probe Version: $site_rsv_probe_version\n$status_out";
    }
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
    return \%metric;
}
##---------------------------------------------------------------------
##  
## Check_VO_handshake: Checks if the site is contacting the VOMS
## servers periodically to get an updated VO Member list
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##      'warnHrs'   Number hours after last VO handshake a warning is to be issued
##      'errorHrs'  Number hours after last VO handshake an error is to be issued
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_VO_handshake{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = "Security Probe Version: $site_rsv_probe_version\n"; # Compile detailed data for output by RSV

    $o{'callingRoutine'} = "Check_VO_handshake()";

    # Step 1: Figure out the authentication mechanism used by site (GUMS (full-privilage or compatability) or edg-mkgridmap)
    #TODO: Right now this probe has only the edg condition implemented once GUMS probe is written the detection mechanism will be implemented
   
    # Step 2: Detect when the update mechanism was last run
    # For edg-mkgridmap case
    my $edg_log = "";
    my $cmd ="";
    if (!defined $o{'localCE'}){
        $edg_log =  $o{'REMOTE_ENV'}{'OSG_LOCATION'}."/edg/log/edg-mkgridmap.log";
        $cmd = "-s  $o{'workerScriptFile'} $edg_log 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
     }else{
        $edg_log =  $o{'VDT_LOCATION_LOCAL'}."/edg/log/edg-mkgridmap.log";
        $cmd = "$o{'workerScriptFile'} $edg_log 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }
    my $last_run; 
    ($status_code,$last_run) = split /<split>/, $o{'cmdOut'}; 
    chomp($last_run);
    if ($status_code!=0) {
	$status_out .= "$last_run\n";
    }
    elsif ($last_run =~ /^\s*$/) {
	$status_out .= "UNKNOWN: edg-mkgridmap's log file did not provide us with required information";
	$status_code = 3;
    }    
    ## agopu to Anand: TODO: Your worker script does not appear to check for blank log file  or blank output from grep
    ##  It assumes exit code 0 = ok but the exit code comes from gawk
    ##  so I added above stop gap check - feel free to fix as you see fit.
    ## Also you are not check for exit codes outside of the RSV exit codes (0,1,2,3)
    else {
	my ($date,$time) = split "T", $last_run;
        my ($y,$mon,$d) = split "-", $date;
        my ($h,$min,$s) = split "-", $time;
        $mon = $mon - 1;
        my $last_run_unix = gmt_to_unix_time($mon,$d,$y,$h,$min,$s,1);
        my $now = time();
        if($now > $last_run_unix +  $o{'errorHrs'}*60*60 ){
            $status_out .= "ERROR: edg-mkgridmap has not been run since $last_run. Please check if edg-mkgrimap service is started.\n";
            $status_code = 2;
        }elsif($now > $last_run_unix +  $o{'warnHrs'}*60*60 ){
            $status_out .= "WARNING: edg-mkgridmap has not been run since $last_run.\n";
            $status_code = 1;
        }
	$status_out .= "OK: edg-mkgridmap was last run at $last_run.\n";
    }

    # Step 3: Recording the result for RSV output
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out); 
    return \%metric;

}
##---------------------------------------------------------------------
##  
## Check_VO_handshake_success: Checks if the site is contacting the VOMS
## servers successfully to get an updated VO Member list. Any error produced
## when contacting VOMS server is listed here
##  
## parameters :
##  First:  
##   %Probe hash 
##  Second: 
##   %metric hash 
##  Third: 
##   %local hash containing 
##     
## Returns 
##   Pointer to metric hash with all the details set
##
##---------------------------------------------------------------------
sub Check_VO_handshake_success{
    
    my $status_code = 0; # Return status code as expected by RSV for summaryData
    my $status_out = "Security Probe Version: $site_rsv_probe_version\n"; # Compile detailed data for output by RSV

    $o{'callingRoutine'} = "Check_VO_handshake_success()";

    # Step 1: Figure out the authentication mechanism used by site (GUMS (full-privilage or compatability) or edg-mkgridmap)
    #TODO: Right now this probe has only the edg condition implemented once GUMS probe is written the detection mechanism will be implemented
   
    # Step 2: Gather the output from the log file 
 
    # For edg-mkgridmap case
    my $edg_log =  "";
    my $cmd ="";
    my $cmd_out ="";
    if (!defined $o{'localCE'}){
        $edg_log =  $o{'REMOTE_ENV'}{'OSG_LOCATION'}."/edg/log/edg-mkgridmap.log";
        $cmd = "-s  $o{'workerScriptFile'} $edg_log 2>/dev/null";
        &RSVProbeBase::Globus_Job_Run ($cmd, "backtick");
     }else{
        $edg_log =  $o{'VDT_LOCATION_LOCAL'}."/edg/log/edg-mkgridmap.log";
        $cmd = "$o{'workerScriptFile'} $edg_log 2>/dev/null";
        &RSVProbeBase::Run_Command ($cmd, "backtick");
    }
   
    ($status_code,$cmd_out) = split /<split>/, $o{'cmdOut'};
    if ($status_code != 0){
        # Error in getting the edg log file
        $status_out .= "$cmd_out";
        &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out);
        return \%metric;
    }

    my @log_content = split /\n/, $cmd_out;
    my $last_output = "";
    my $start = 0;
    # I will prefer to use File::ReadBackwards.pm, but that library is not included in default perl
    foreach  my $line (@log_content){
        if ($line =~ /Running edg-mkgridmap/i){
            $last_output = "";
            $start=1
        }
        if ($start){
            $last_output .= $line."\n";
        }
        if ($line =~ /Finished edg-mkgridmap/i){
            $start=0;
        }
    }
    if ($last_output =~ /Exit with error/i){
        $status_out .= "WARNING: Edg-mkgridmap could not download VO list from one or more VOs:\n\n".$last_output;
        $status_code = 1;
    }

    # Step 3: Recording the result for RSV output
    $status_out .= "OK: edg-mkgridmap did not report any errors.\n" if ($status_code==0);
    &RSVProbeBase::Set_Summary_Metric_Results ($status_code,$status_out); 
    return \%metric;

}

################ HELPER FUNCTIONS #####################################

##---------------------------------------------------------------------
##
## gmt_to_unix_time: Convert time from GMT to unix
## parameters  : (short month name, date, year, hour, min, sec, type) type=1 means short_month has month values already;
## Returns : Unix time
##
##---------------------------------------------------------------------
sub gmt_to_unix_time{
    my ($month_s, $date, $year, $hour, $min, $sec, $type) = @_;
    $type = 0 if (! $type);
    my %months = (
        'Jan' => '0',
        'Feb' => '1',
        'Mar' => '2',
        'Apr' => '3',
        'May' => '4',
        'Jun' => '5',
        'Jul' => '6',
        'Aug' => '7',
        'Sep' => '8',
        'Oct' => '9',
        'Nov' => '10',
        'Dec' => '11'
    );
    my $month=$month_s;

    $month = $months{$month_s} if ($type!=1);
    $year-=1900;
    return timegm($sec,$min,$hour,$date,$month,$year);
}


1;
