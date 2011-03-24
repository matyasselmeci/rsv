#!/usr/bin/env perl -w

###############################################################################
##
## Copyright 2009, The Trustees of Indiana University. 
##
## Open Science Grid Operations Team, Indiana University
## Original Authors: Arvind Gopu (http://peart.ucs.indiana.edu)
##                  and Thomas Wang
##
## This Perl module will have basic functions used by OSG Resournce
##  and Service Validation (RSV) probes
##
## DISAMBIGUATION
## * There are two main hashes used in this perl module (as well as, by all
##   the probes: probe hash and metric hash. 
##  - The metric hash primarily has details related to a particular metric
##    though it might include some additional information like a system command
##    exit value -- that's, again, specific to that metric
##  - The probe hash contains most everything else that's relevant to all 
##    metrics in a probe or possibly all the probes.
##  - In this perl module, %o is used for the probe's hash; and 
##    %metric is used for metric hashes.
##
## KNOWN BUGS
## <<1>> The Run_Command () routine has a bug that might leave zombies/stray 
##   processes if a child process times out and is killed. It appears to be 
##   well known problem in Perl programming circles with no easy fix. 
## <<2>> The Run_Command () routine has a bug where in, the cmdOut is not
##   set properly in certainly situations if the system() option is used.
##
## REFERENCES
## [[1]] RSV Documentation Home
##   http://rsv.grid.iu.edu/documentation/
## [[2]] WLCG Specifications
##   https://twiki.cern.ch/twiki/bin/view/LCG/GridMonitoringProbeSpecification
## [[3]] Example Gratia record uploading script
##   http://rsv.grid.iu.edu/documentation/example-gratia-script.html 
## [[4]] Developing Probes - Intro
##   https://twiki.grid.iu.edu/twiki/bin/view/MonitoringInformation/WriteYourOwnRSVProbe
##
################################################################################

package RSVProbeBase;

use strict;
use File::Basename;
use Getopt::Long qw(GetOptions);
use Date::Manip  qw(ParseDate UnixDate Date_Cmp);
use XML::Simple;
use Data::Dumper qw(Dumper);
use POSIX qw(strftime);

################################################################################
###### Global Variables ###########
################################################################################

## Global hash to store probe's details
our %o = ("verbose"         => 0,
	  "detailsDataTrim" => 1,
	  "multimetric"     => 0,
	  "localprobe"      => 0,
	  "cleanUp"         => 1 
	  );

## Global hash to store metric's details    
our %metric;

## These are the standard options accepted by all probes
## Additional options can be passed along in an array to Get_Options ()
our @options   = ("uri|u=s",
		  "metric|m=s",
		  "virtual-organization|v=s",
		  "timeout|t=i",
		  "list-metric|l",
		  "vdt-location=s",
		  "print-local-time",
		  "proxy|x=s",
		  "x=s",
		  "warning|w=i",
		  "critical|c=i",
		  "extra-globus-rsl=s",
		  "generate-gratia-script|ggs",
		  "gratia-script-loc|gsl=s",
		  "gratia-config-file|gmpcf=s",
		  "python-loc=s",
		  "generate-text-file",
		  "text-file-loc=s",
		  "trim-details!",
		  "cleanup!",
		  "version",
		  "help|h",
		  "verbose+"
		  ) ;

## This hash maps options listed in the @options array to elements in the 
##  probe %o hash. 
## Allows for flexible keys that are not dependant on the options element
##  itself
## By default, additional options passed to Get_Options are assigned into %o as-is

our %optionmap = (
		  "uri"                   => \$o{'serviceUri'},
		  "u"                     => \$o{'serviceUri'},
		  "metric"                => \$o{'metric'},
		  "m"                     => \$o{'metric'},
		  "virtual-organization"  => \$o{'virtualorganization'},
		  "v"                     => \$o{'virtualorganization'},
		  "timeout"               => \$o{'timeout'},
		  "t"                     => \$o{'timeout'},
		  "list-metric"           => sub { if ($o{'multimetric'} != 1) { &List_Summary_Metric(); exit 0;} else { $o{'listmetric'} = 1; }},
		  "l"                     => sub { if ($o{'multimetric'} != 1) { &List_Summary_Metric(); exit 0;} else { $o{'listmetric'} = 1; }},
		  "vdt-location"          => \$o{'VDT_LOCATION_LOCAL'},
		  "print-local-time"      => \$o{'printLocalTimezone'},
		  "proxy"                 => \$o{'proxyFile'},
		  "x"                     => \$o{'proxyFile'},
		  "warning"               => \$o{'proxyExpiryWarningHours'},
		  "critical"              => \$o{'proxyExpiryMinimumHours'},
		  "w"                     => \$o{'proxyExpiryWarningHours'},
		  "c"                     => \$o{'proxyExpiryMinimumHours'},
		  "extra-globus-rsl"      => \$o{'extraGlobusRsl'},
		  "generate-gratia-script"=> \$o{'generateGratiaScript'},
		  "ggs"                   => \$o{'generateGratiaScript'},
		  "gratia-script-loc"     => \$o{'gratiaLocationDir'},
		  "gsl"                   => \$o{'gratiaLocationDir'},
		  "gratia-config-file"    => \$o{'gratiaMetricProbeConfigFile'},
		  "gmpcf"                 => \$o{'gratiaMetricProbeConfigFile'},
		  "python-loc"            => \$o{'pythonToUse'},
		  "generate-text-file"    => \$o{'generateTextFile'},
		  "text-file-loc"         => \$o{'textFileLocationDir'},
		  "trim-details"          => \$o{'detailsDataTrim'},
		  "cleanup"               => \$o{'cleanUp'},
		  "version"               => sub { &Version(); exit 0; },
#		  "help"                  => \$o{'help'}, 
		  "help"                  => sub { &Print_Usage(); exit 0; },
		  "h"                     => sub { &Print_Usage(); exit 0; },
		  "verbose"               => \$o{'verbose'}
		  );


## Set verbose flag by default if environment variable is set.
$o{'verbose'} = $ENV{'RSV_VERBOSE'} if ($ENV{'RSV_VERBOSE'});



################################################################################
###### Sub routines begin ###########
################################################################################

## AG: Need comments

sub Extra_CLI_Option {
    my $extra_option = $_[0];
    my $hashkey      = $_[1] if ($_[1]);

    &Verbose2 ("Adding [$extra_option] to @ options\n");
    push ( @options, $extra_option);

    $extra_option = $1            if ($extra_option =~ /(.*)=.*/);
    $hashkey      = $extra_option if (!defined($hashkey)); 
    &Verbose2 ("\t Adding [$extra_option] to % optionmap with value $hashkey\n");
    $optionmap{$extra_option} = \$o{$hashkey};

    foreach my $element (@options) {
        &Verbose2 (" In @ option element -- " . $element ."\n");
    }
    foreach my $key (sort keys %optionmap) {
        &Verbose2 ("In % optionmap hash - GOT OPT -- $key: $optionmap{$key}\n");
    }
}

## AG: Need comments

sub Get_Options {
    ## Copy ARGV for misc purposes 
    @{$o{'ARGV'}} = @ARGV;

    ## Get options provided into optionsmap hash -- which references %o
    Getopt::Long::GetOptions(\%optionmap, @options) 
	or &Print_Usage ();

    ## Print data we got via GetOptions
    foreach my $key (sort keys %o) {
        &Verbose2 ("In % o hash - GOT OPT -- $key: $o{$key}\n");
    }
}

sub Run {
    $o{'callingRoutine'} = $o{'probeName'}."::Run() ";
    &main::Run();     ## Call back Run () function in probe
    &Print_Metric (); ## Calling this here in case probe did not 
}

################################################################################
##
## SUB-ROUTINE
##  Init ()
##
## FUNCTION:
##
## This routine initializes the probe's hash with relevant key values, 
##  including system commands, default values for various keys used by 
##  different probes and their metrics. 
## This will likely be the first function call in any probe that uses this perl
##  module.
##
## NOTES:
## 1) It uses key VDT_LOCATION_LOCAL to store the location of VDT on the
##    the monitoring host; as opposed to key VDT_LOCATION which will point
##    to VDT location on a remote host that might be monitored by a metric
## 2) Has sub-sections: one for system commands like ping, ls, etc., then
##    a section for local environment type stuff, then one for Gratia
##    script generation related details, then a large section of probe-specific
##    assignments.
##
##
## ARGUMENTS: 
##  First arg: Our hash (i.e probe's hash)
##   (above arg is not used in any way right now; for possible future use)
##   So far, there are three types of keys: 
##          ___Cmd, ____Hours,___Seconds, ___Dir, ___Testfile
##     and env variable type stuff
##         ENV_LOCAL, VDT_LOCATION_LOCAL, 
##         OSG_WN_TMP, OSG_APP, OSG_DATA, OSG_GRID
##
## CALLS:
##  Get_Timestamp (\%o, $type_string)
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to same hash filled in with all the good stuff (i.e commands, etc.)
##
################################################################################

sub Init {

    ## First step: call probe level Init function to set probe specific stuff
    &main::Init();

    ################################################
    ## General system commands
    ## Set below stuff using CONFIG FILE?? AG?
    ################################################
    ######## Commands used in most probes, and their arguments ########
    $o{'hostnameCmd'}   = "/bin/hostname";
    $o{'systemDateCmd'} = "/bin/date";   
    $o{'shCmd'}         = "/bin/sh";     
    $o{'lsCmd'}         = "/bin/ls";     
    $o{'catCmd'}        = "/bin/cat";     
    $o{'rmCmd'}         = "/bin/rm";     
    $o{'grepCmd'}       = "/bin/grep";     
    $o{'envCmd'}        = "/usr/bin/env";     ## For Get_Remote_Env() 
    $o{'sleepCmd'}      = "/bin/sleep";   ## For Test_Job_Manager() 
    $o{'diffCmd'}       = "/usr/bin/diff";## For Diff_Files()
    $o{'pingCmd'}       = "/bin/ping";    ## For PING-HOST-PROBE, others
    $o{'wgetCmd'}       = "/usr/bin/wget";    ## For HTTP-HOST-PROBE, others
    $o{'opensslCmd'}    = "/usr/bin/openssl"; ## For CERTIFICATE-EXPIRY-PROB
    $o{'perlCmd'}       = "/usr/bin/perl"; ## JOB-MANAGER-AVAILABLE-PROBE
    $o{'slashTmp'}      = "/tmp/";

    ################################################
    ## Local environment type stuff -- get local CE/CE_Client install location
    ################################################

    ################################################
    ## Set probe name and version keys
    ################################################
    $o{'probeName'}    = &basename($0);
    
    ## Set the version of WLCG probe specifications we are following currently
    $o{'probeSpecificationVersion'} = "0.91";

    $o{'detailsDataMaxLength'} = 512;
    ## Default timeout for individual command executions. 
    ##  NOTE: Not for probe itself; though it should probably be, per intuition?
    $o{'timeout'}   = 600;
    $o{'proxyFile'} = "/tmp/x509up_u$>";

    ## Grab local VDT location from %ENV hash
    $o{'VDT_LOCATION_LOCAL'} = $ENV{'VDT_LOCATION'};

    ## For PING-HOST-PROBE
    $o{'pingCount'}   = 1;
    $o{'pingTimeout'} = 3;

    ## For CERTIFICATE-EXPIRY-LOCAL-PROBE         ## First, the hostcertfile
    $o{'localCertificates'}{'org.osg.local.hostcert-expiry'}      = "/etc/grid-security/hostcert.pem";
    $o{'localCertificates'}{'org.osg.local.containercert-expiry'} = "/etc/grid-security/containercert.pem";
    $o{'localCertificates'}{'org.osg.local.httpcert-expiry'}      = "/etc/grid-security/http/httpcert.pem";
    ## Using Threshold below for all three certs to check for warning status?
    $o{'certWarningHours'}  = 168;

    ## For CACERTS-EXPIRY-PROBE         
    $o{'cacertsDir'}          = 
	"$o{'VDT_LOCATION_LOCAL'}/globus/share/certificates"; 
    $o{'cacertsWarningHours'} = 48;

    $o{'proxyExpiryWarningHours'}   = 6; 
    $o{'proxyExpiryMinimumHours'} = 3; 

    ## For CLASSAD-VALID-PROBE
    $o{'classadRessCollectorHost'} = "osg-ress-1.fnal.gov";

    ## For GLOBUS jobs
    $o{'validBatchJobStatuses'} = "ACTIVE OR DONE OR PENDING"; ## ." OR UNSUBMITTED" ## AG?? 
    $o{'globusJobStatusDelaySeconds'} = 60;
    $o{'gridftpDelaySeconds'} = 60;

    ## For OSG-DIRECTORIES-PROBE (local); various dir permissions expected
    ## Is this directory's expected permission CRITICAL? ; also is dir required or recommended
    ##
    ### 2009-03-09 Based on https://twiki.grid.iu.edu/twiki/bin/view/ReleaseDocumentation/SitePlanning
    ###  Name      Required?                   Purpose
    ###  OSG_APP    Yes                         Store applications used by multiple jobs
    ###	 OSG_DATA   No, but highly recommended  Store data used by jobs
    ###	 OSG_GRID   No                          Location of worker node client
    ### Plus of course, OSG_LOCATION
    ##

    $o{'osgDirectory'}{'OSG_LOCATION'}{'isCritical'} = "true";  $o{'osgDirectory'}{'OSG_LOCATION'}{'isRequired'} = "true";
    # $o{'osgDirectory'}{'OSG_GRID'}{'isCritical'}     = "false"; $o{'osgDirectory'}{'OSG_GRID'}{'isRequired'}     = "false";
    $o{'osgDirectory'}{'OSG_APP'}{'isCritical'}      = "false"; $o{'osgDirectory'}{'OSG_APP'}{'isRequired'}      = "true";
    $o{'osgDirectory'}{'OSG_DATA'}{'isCritical'}     = "false"; $o{'osgDirectory'}{'OSG_DATA'}{'isRequired'}     = "false";
    ##
    $o{'osgDirectory'}{'OSG_LOCATION'}{'permission'} = "775 1775 2775 755 1755 2755";# "[012467]755";
    # $o{'osgDirectory'}{'OSG_GRID'}{'permission'}     = "755";
    $o{'osgDirectory'}{'OSG_APP'}{'permission'}      = "777 1777 2777 775 1775 2775 755 1755 2755";
    $o{'osgDirectory'}{'OSG_DATA'}{'permission'}     = "777 1777 2777 775 1775 2775";

    ## GUMS-AUTHORIZATION-VALIDATION-PROBE - defaults that can be changed in the configuration
    ## AG: Need to change first one to a GOC maintained URL
    $o{'osgFqanMapfileUrl'}       = "http://software.grid.iu.edu/pacman/tarballs/vo-package/gums-fqan.txt";
    $o{'availPoolAccountsThresh'} = 10;
    $o{'checkEachPoolAccount'}    = 0;
    $o{'osgGocLevelGumsFqanFile'} = $o{'slashTmp'}. "/osg-goc-level-gums-fqan.txt";
    $o{'siteLevelGumsFqanFile'}   = $o{'slashTmp'}. "/site-level-gums-fqan.txt";

    ## For GRIDFTP
    $o{'globusurlcopyServiceType'} = "gsiftp";
    $o{'globusurlcopyPortNumber'}  = 2811; 
    $o{'gridftpDestinationDir'} = $o{'slashTmp'};

    ## SRM STUFF
    $o{'srmServiceType'} = "srm";
    $o{'srmPortNumber'}  = 8443; 
    $o{'srmProtocolVersion'} = 2;
    $o{'srmWebservicePath'}  = "srm/managerv".$o{'srmProtocolVersion'};

   
    ## Print some verbosity info 
    &Verbose ("\n $o{'probeName'}--Init ():\n\t");
    foreach my $key (sort keys(%o)) {
	&Verbose("$key: [$o{$key}]\n\t");
    }
    &Verbose ("\n");

    ## Process command line parameters
    &Get_Options();

    ## Check if -m is provided in case of multimetric probe
    &Check_Multimetric ();

    ## Get timestamp in UTC
    &Get_Timestamp();

    ## Break serviceUri in to separate bits
    &Parse_ServiceUri ();
    
    ## Process serviceURI for hostName, etc.; copy stuff from %o to metric hash
    &Init_Metric ();

    &Init_Dependencies ();
}


## AG: Need comments

sub Init_Dependencies {

    ## Quit if VDT_LOCATION is not set unless help/list-metric options are used
    &Exit_Error (3,"ERROR:\t \$VDT_LOCATION not set, probe cannot ".
	    "continue!\n\t Ensure you have run your OSG client or .".
	    "CE's setup.(c)sh.\n\t Type 'perl $o{'probeName'} -h' ".
	    "for more information.\n\n") 		     
	if (($o{'VDT_LOCATION_LOCAL'} eq "") && 
	    (!(defined($o{'help'}) || defined($o{'listmetric'}))));

    ## Otherwise, continue.
    $o{'PROBE_DIR_LOCAL'}    = 
	$o{'VDT_LOCATION_LOCAL'}."/osg-rsv/bin/probes/";

    ################################################
    ## Gratia records related stuff
    ################################################
    ## Where's the ProbeConfig file that defines Gratia collector, etc.
    $o{'pythonToUse'} = "/usr/bin/python"
	if (!(defined($o{'pythonToUse'}))); ## Pass using --python-path
    $o{'gratiaMetricProbeConfigFile'} = 
	"$o{'VDT_LOCATION_LOCAL'}/gratia/probe/metric/ProbeConfig"
	if (!(defined($o{'gratiaMetricProbeConfigFile'})));
    ## Python script (temporary) that'll be generated to send Gratia record
    $o{'gratiaLocationDir'} = "$o{'slashTmp'}" 
	if (!(defined($o{'gratiaLocationDir'})));

    ## Text output file if need be
    $o{'textFileLocationDir'} = "$o{'slashTmp'}" 
	if (!(defined($o{'textFileLocationDir'})));
    

    ## For CERTIFICATE-EXPIRY-LOCAL-PROBE
    $o{'certWarningSeconds'}= $o{'certWarningHours'}*60*60; #Convert
    ## For CACERTS-EXPIRY-PROBE   
    $o{'cacertsWarningSeconds'}=$o{'cacertsWarningHours'}*60*60;#Convert
    ## For CLASSAD-VALID-PROBE
    $o{'classadWorkerScriptFile'} = "$o{'PROBE_DIR_LOCAL'}worker-scripts/classad-valid-probe-worker.sh" if (!defined ($o{'classadWorkerScriptFile'}));
    $o{'proxyExpiryWarningSeconds'} = 
	$o{'proxyExpiryWarningHours'}*60*60;          ## Convert to seconds
    $o{'proxyExpiryMinimumSeconds'} = 
	$o{'proxyExpiryMinimumHours'}*60*60;

    
    ## GLOBUS STUFF
    ## Set $X509_USER_PROXY if provided, so globus cmds will pick up this proxy
    $ENV{'X509_USER_PROXY'} = $ENV{'X509_PROXY_FILE'} = $o{'proxyFile'};
    $o{'globusrunCmd'}= "$o{'VDT_LOCATION_LOCAL'}/globus/bin/globusrun";
    $o{'gridproxyinfoCmd'}= 
	"$o{'VDT_LOCATION_LOCAL'}/globus/bin/grid-proxy-info";
    $o{'globusjobrunCmd'}           = 
	"$o{'VDT_LOCATION_LOCAL'}/globus/bin/globus-job-run";
    $o{'globusjobsubmitCmd'} = "$o{'VDT_LOCATION_LOCAL'}/globus/bin/globus-job-submit";
    $o{'globusjobstatusCmd'} = "$o{'VDT_LOCATION_LOCAL'}/globus/bin/globus-job-status";
    $o{'globusjobcleanCmd'}  = "$o{'VDT_LOCATION_LOCAL'}/globus/bin/globus-job-clean";
    ## Gridftp
    $o{'globusurlcopyCmd'}      =
	"$o{'VDT_LOCATION_LOCAL'}/globus/bin/globus-url-copy";
    ## Globus-WS
    $o{'globusrunwsCmd'}           = 
	"$o{'VDT_LOCATION_LOCAL'}/globus/bin/globusrun-ws";

    ## For GRIDFTP
    $o{'globusurlcopyTestfile'} = 
         $o{'PROBE_DIR_LOCAL'}. "/gridftp-probe-test-file" 
	 if (!defined($o{'globusurlcopyTestfile'})); 

    ## For SRM-*-PROBEs
    if ($o{'srmClientType'} eq "lbnl") { 
	$o{'srmClientDir'}       = $o{'VDT_LOCATION_LOCAL'}."/srm-client-lbnl/"
	    if (!defined($o{'srmClientDir'})); 
	## For SRM-PING-PROBE 
	$o{'srmpingCmd'}      =
	    "$o{'srmClientDir'}/bin/srm-ping";
	## For SRMCP-SRM-PROBE 
	$o{'srmlsCmd'}         =
	    "$o{'srmClientDir'}/bin/srm-ls";
	$o{'srmgriftpcopyCmd'}         =
	    "$o{'srmClientDir'}/bin/gridftplist";
	$o{'srmcpCmd'}         =
	    "$o{'srmClientDir'}/bin/srm-copy";
	$o{'srmrmCmd'}         =
	    "$o{'srmClientDir'}/bin/srm-rm";
	$o{'srmadvisorydeleteCmd'}         =
	    "$o{'srmClientDir'}/bin/srm-advisory-delete";
    } else   {
	$o{'srmClientDir'}       = $o{'VDT_LOCATION_LOCAL'}."/srm-client-fermi/"
	    if (!defined($o{'srmClientDir'})); 
	## For SRM-PING-PROBE 
	$o{'srmpingCmd'}      =
	    "$o{'srmClientDir'}/bin/srmping";
	## For SRMCP-SRM-PROBE 
	$o{'srmlsCmd'}         =
	    "$o{'srmClientDir'}/bin/srmls";
	$o{'srmgriftpcopyCmd'}         =
	    "$o{'srmClientDir'}/bin/gridftplist";
	$o{'srmcpCmd'}         =
	    "$o{'srmClientDir'}/bin/srmcp";
	$o{'srmrmCmd'}         =
	    "$o{'srmClientDir'}/bin/srmrm";
	$o{'srmadvisorydeleteCmd'}         =
	    "$o{'srmClientDir'}/bin/srm-advisory-delete";
    }

    $o{'srmcpTestfile'}    = "$o{'PROBE_DIR_LOCAL'}"."storage-probe-test-file"
	if (!(defined($o{'srmcpTestfile'})));


    ## For OSG-DIRECTORIES-PROBE (local); various dir permissions expected
    ## Default worker script to use
    $o{'osgdirectoriesWorkerScriptFile'}      = 
      "$o{'PROBE_DIR_LOCAL'}/worker-scripts/osg-directories-probe-CE-permissions-worker" 
	if (!defined($o{'osgdirectoriesWorkerScriptFile'}));

    ## For GRATIA-CONFIG-PROBE
    $o{'gratiaConfigProbeWorkerScriptFile'}   =
      "$o{'PROBE_DIR_LOCAL'}/worker-scripts/gratia-config-probe-helper" 
	if (!defined($o{'gratiaConfigProbeWorkerScriptFile'}));
	
    ## GUMS-AUTHORIZATION-VALIDATION-PROBE - defaults that can be changed in the configuration
    $o{'gumsWorkerScript'}        = "$o{'PROBE_DIR_LOCAL'}/worker-scripts/gums-authorization-validator-probe-worker.sh"; 
}

################################################################################
##
## SUB-ROUTINE
##  Init_Metric ()
##
## FUNCTION:
##
## This routine initializes a metric's hash with relevant key values, 
##  including serviceUri, gatheredAt and timestamp. Some of the values are
##  copied over from the probe's hash for easier maintanence of data integrity 
## This will likely be the second function call in any probe that uses this perl
##  module; it will be called multiple times in probes with multiple metrics.
##
## NOTES:
## 1) Assigns different keys dependending on whether a probe is a local one
##    or a remote one.
##
## ARGUMENTS: 
##  First arg: 
##   Our hash (i.e probe's hash) 
##  Second arg: 
##   Metric hash
##
## CALLS:
##  Get_Timestamp (\%o, $type_string)
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to same metric hash filled in with info from probe's hash
##
################################################################################

sub Init_Metric {

    ## First, copy some of "our" hash content into metric's hash
    $metric{'metricName'} = $o{'metric'} if (!$metric{'metricName'});
    $metric{'timestamp'}  = $o{'timestamp'};

    ## Set some other defaults if not set -- these 3 things will be printed by -l switch
    $metric{'probeType'}       = "OSG-CE" if (!(defined($metric{'probeType'}))); 
    $metric{'enableByDefault'} = "true" if (!(defined($metric{'enableByDefault'}))); 
    $metric{'metricInterval'}  =  int(rand(60)). " */2 * * *" if (!(defined($metric{'metricInterval'}))); 

    ## Set 'gatheredAt' to hostname of machine probe is being run on
    # &Verbose (" Initialize_Metric () hostname CMD: [$o{'hostnameCmd'} -f];"  );
    #my $local_hostname = `$o{'hostnameCmd'} -f`; chomp($local_hostname);
    #&Verbose ("\n\t CMD OUT: [$local_hostname]\n"  );

    ##    $metric{'gatheredAt'}   = $ENV{'HOSTNAME'}; # local_hostname;
    $metric{'gatheredAt'}   = `$o{'hostnameCmd'} -f`;
    $metric{'gatheredAt'} =~ s/\s*$//s; ## Remove trailing spaces/newlines

    ## NEW: Strings UNKNOWN,CRITICAL,WARNING and OK
    ##  OLD not used any more: UNKNOWN=3; 2=CRITICAL ; 1=WARNING ; 0=OK
    $metric{'metricStatus'} = "UNKNOWN";

    ## Special case: For local probes
    if ($o{'localprobe'} == 1) {
	$metric{'localprobe'} = $o{'localprobe'};
	$o{'hostName'} = $metric{'hostName'}   = $metric{'gatheredAt'};
	$metric{'serviceType'}= "other-local" 
	    if ($metric{'serviceType'} eq "");
	$metric{'serviceUri'} = $metric{'hostName'}.":".
         $metric{'portNumber'} if (defined($metric{'portNumber'}));
	$metric{'serviceUri'} = $metric{'serviceUri'}."/".
        $metric{'serviceType'} if (defined($metric{'serviceType'}));
    }

    &Verbose ("\n\t Timestamp: [$metric{'timestamp'}] gatheredAt: [$metric{'gatheredAt'}]\n\t serviceURI: [$metric{'serviceUri'}]\t ServiceType: [$metric{'serviceType'}]\n\t Hostname: [$metric{'hostName'}] Port: [$metric{'portNumber'}]  localprobe?:[$metric{'localprobe'}]\n\n" );
}






################################################################################
##
## SUB-ROUTINE
##  Check_Multimetric
##
## FUNCTION:
##
## This routine checks if -m switch is provided for a multimetric probe
##
## NOTES:
##
## ARGUMENTS: 
##
## CALLS:
##   Print_Usage ()
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None (might exit with value 0 if some conditions are met)
##
################################################################################

sub Check_Multimetric {
    if (($o{'multimetric'} == 1) && (!defined ($o{'metric'}))) {
	print "\nERROR: This probe requires you to specify a metric using the".
	    " -m <metric>\n option. See Usage information below ... \n";
	&Print_Usage()  && exit 1;
    }
}





################################################################################
##
## SUB-ROUTINE
##  List_Summary_Metric ()
##
## FUNCTION:
##
## This routine lists a particular metric in a format specified in the WLCG
##  specs [[2]], it'll likely be called by Process_Informational_Arguments (),
##
## NOTES:
## 1) For a status metric the following three field are mandatory:
##
##  Field 	Description
##  serviceType The serviceType 
##  metricName 	The name of the metric. 
##  metricType 	This should be the constant value 'status'
##
##
## ARGUMENTS: 
##  First arg: 
##   Hash containing metric details to be printed
##
## OUTPUT: Prints  description of the supported metrics on STDOUT
##
## RETURN: 
##  None
##
################################################################################

sub List_Summary_Metric {
    print qq (serviceType: $metric{'serviceType'}
metricName: $metric{'metricName'}
metricType: $metric{'metricType'}
probeType: $metric{'probeType'}
enableByDefault: $metric{'enableByDefault'}
metricInterval: $metric{'metricInterval'}
EOT
);
}



################################################################################
##
## SUB-ROUTINE
##  Set_Name_Revision ()
##
##  Quickly set probe name and version keys
##
## ARGUMENTS: 
##
## OUTPUT: None
##
## RETURN: 
##  Reference to probe's hash with probeName and revision set.
##
################################################################################

sub Set_Name_Revision {
    $o{'revision'}      =~ s/(.Revision: | .$)//g;
}




################################################################################
##
## SUB-ROUTINE
##  Print_Usage ()
##
## FUNCTION:
##
## This routine prints usage information; it accumlates information from various
##  hash key values from the probe's hash. 
## It also uses special keys: 'helpIntro' and 'helpOptions' that can be set in
##  each probe to provide an introduction to that probe and also to specify
##  any additional switches that probe might take.
##
## NOTES:
## 1) Prints slightly different infoamtion dependending on whether a probe 
##    is a local one or a remote one.
##
## ARGUMENTS: 
##  First arg: 
##   Reference to probe's hash 
##  Second arg: 
##   Reference to metric'shash
##
## OUTPUT: Prints usage information
##
## RETURN: 
##  None
##
################################################################################

sub Print_Usage {
    ##  Set probe name and version keys
    &Set_Name_Revision();

    ## Print initial probe info per WLCG spec 0.91
    print qq(
$o{'probeName'}
probeVersion: $o{'revision'}
serviceType: $metric{'serviceType'}
serviceVersion: $metric{'serviceVersion'}
probeSpecificationVersion: $o{'probeSpecificationVersion'}
);

    ## Print any additional intro that may be defined in probe (perl script)
    print qq(
$o{'helpIntro'}
) if (defined($o{'helpIntro'}));

    ## Now rest of usage information
    print qq(
USAGE
 $0 <Required Arguments> [Optional Arguments]

PROBE OPTIONS                    DESCRIPTION
);

    ## Print options as required or optional depending on hash key values
    print qq( [-u, --uri <serviceURI>]         Hostname, port and service to run probe on
                                   hostname[:port][/service]
) if ($o{'localprobe'} == 1);

    print qq( -u, --uri <serviceURI>           Hostname, port and service to run probe on
                                   hostname[:port][/service]
) if ($o{'localprobe'} == 0);


    print qq( -m <metric name>                 Metric to run 
) if (defined($o{'multimetric'}));
    print qq( [-m <metric name>]               Metric to run
) if (!(defined($o{'multimetric'})));

    print qq($o{'helpOptions'}
) if (defined($o{'helpOptions'}));


    print qq( [-t, --timeout <\# seconds>]      Timeout in seconds for system calls, for 
	                            eg.: globus job commands
                                    Default: 600 seconds per system call 
 [-l, --list-metric]              List metric(s) per WLCG standards
 [--vdt-location </path/VDT>]     Provide custom \$VDT_LOCATION (non OSG users)
 [--print-local-time]             Print timestamp in system local timezone 
	                            Default: UTC (ISO 8601 format)
);
    print qq( -v <VO name>                     VO that the RSV User Certificate is part of 
						(for use in setting remote dir on SE)
) if (defined($o{'seprobe'}));
    print qq( [-v <VO name>]                   VO to run test against (UNDEFINED)
) if (!(defined($o{'seprobe'})));

    ## Print Grid proxy options if not local probe
    print qq(
GRID PROXY OPTIONS               DESCRIPTION
 [-x, --proxy <cert file>]        Location of Nagios user\'s proxy file
                                    Default: /tmp/x509up_u<uid>
 [-w, --warning  <\# hours>        Warning threshold for cert. lifetime
                                    Default: 6 hours
 [-c, --critical <\#hours>]        Critical threshold for cert. lifetime
                                    Default: 3 hours
  ) if ($o{'localprobe'} == 0);


    ## Print Gratia python script generation options; and other general ones
    print qq(
GRATIA SENDER SCRIPT OPTIONS     DESCRIPTION
 [--ggs, 
  --generate-gratia-script]       Generate Gratia upload python Script
 [--gsl, --gratia-script-loc      Directory to write Gratia upload script 
   <directory location>]	                           Default: /tmp 
 [--gmpcf, gratia-config-file     Metric ProbeConfig file to use
   <file>]                        Default: 
	                          \$VDT_LOCATION/gratia/probe/metric/ProbeConfig
 [--python-loc </path/python>]    Which python to use 

TEXT OUTPUT FILE OPTIONS
 [--generate-text-file]           Generate a text file with probe output
 [--text-file-loc                 Directory to write text file output to
   <directory location>]	                           Default: /tmp 

HELP/DEBUGGING OPTIONS           DESCRIPTION
 [--no-trim-details]              Do not trim detailsData value
 [--no-cleanup]                   Do not clean up temp files, etc.
 [--verbose]                      Provide verbose output
 [--version]                      List revision of probe
 [-h, --help]                     Print this usage information

);
}







################################################################################
##
## SUB-ROUTINE
##  Set_Summary_Metric_Results ()
##
## FUNCTION:
##
## This routine sets metric results for a status metric (probe)
##
## NOTES:
## 1) Only sets {metricStatus,summaryData same as of now}, & detailsData 
## 2) Third arg indicates metric status of OLD WLCG specs; 
##    (0 OK, 1 Warning, 2 Critical, 3 unknown)
##
## ARGUMENTS: 
##  First arg: 
##   % Probe's hash (not used for now)
##
##  Second arg: 
##   % metric hash that output status will entered into
##
##  Third arg: 
##   $integer indicating metric status of OLD WLCG specs; 
##
##  Fourth arg: 
##   $String to be assigned to detailsData
##   NOTE: If this argument is an empty string, then it's NOT set
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash that output status is entered into
##
################################################################################

sub Set_Summary_Metric_Results {
    my $metric_status_int  = $_[0];
    &Set_DetailsData ($_[1]) if ($_[1] ne ""); 

    ## Set summary data per status integer provided (AG: make this a routine?)
    ## NOTE: Not using switch statement -- SLOWs probes down by 4 seconds!
    if ($metric_status_int == 0) {
	$metric{'summaryData'}=$metric{'metricStatus'}="OK";}
    elsif ($metric_status_int == 1) {
	$metric{'summaryData'}=$metric{'metricStatus'}="WARNING";}
    elsif ($metric_status_int == 2) {
	$metric{'summaryData'}=$metric{'metricStatus'}="CRITICAL";}
    else {
	$metric{'summaryData'}=$metric{'metricStatus'}="UNKNOWN";}
    return \%metric;
}







################################################################################
##
## SUB-ROUTINE
##  Print_Metric ()
##
## FUNCTION:
##
## This routine prints metric results for a status metric (probe)
##
## NOTES:
## 1 ) For a status metric the possible fields are listed below:
##
## metricName 	Required   The name of the metric. this be of the 
##                                format <SERVICE>-<METRIC>
## metricType   Optional   Is this a status or a performance metric? 
##                              (OK to add this field - by David C / James C)
## metricStatus Required   A return status code, selected from the status 
##                              codes above
## summaryData 	Optional   A one-line summary for the gathered metric
## detailsData 	Optional   This allows a multi-line detailed entry to be 
##                           provided - it must be the last entry before the EOT
## voName 	Optional   The VO that the metric was gathered for
## hostName 	Optional   The host the LOCAL metric was gathered for
## serviceURI   Optional   The URI of REMOTE service metric was gathered for
## gatheredAt 	Optional   The host the metric was gathered at
## timestamp 	Required   The time the metric was gathered
##
##
## ARGUMENTS: 
##  First arg: 
##   Our hash 
##  Second arg: 
##   Metric hash containing metric details to be printed
##
## CALLS:
##  Generate_Gratia_Sending_Script (\%o,\%metric)
##
## OUTPUT: 
##  Prints results of supported metric on STDOUT
##
## RETURNS:
##  0 if successful
##
################################################################################

sub Print_Metric {

    #############################################################
    ## Common to both status and performance metrics
    #############################################################

    chomp ($metric{'detailsData'});

    ## Trim detailsData if it is too long
    if (($o{'detailsDataTrim'} == 1) && (length ($metric{'detailsData'}) > $o{'detailsDataMaxLength'})) {
	$metric{'detailsData'} = substr($metric{'detailsData'}, 0, $o{'detailsDataMaxLength'}).
	    "\n... Truncated ...\nFor more details,  as \'$ENV{'USER'}\' user:\n".
	    "rsv-control --run --host $o{'hostname'} $o{'probeName'} --verbose 3";
 
    }

    ## Append proxy warning if applicable
    &Append_Proxy_Validity_Warning ();

    ## Create Gratia record (i.e Python script) if that option is chosen 
    ##  before printing metric results on command line -- that way we can 
    ##  also catch Gratia script generation errors 
    if (defined ($o{'generateGratiaScript'})) {
	&Verbose ("generateGratiaScript defined, so creating Gratia record (Python script)\n" );
	&Generate_Gratia_Sending_Script ();
    }
    else {
	&Verbose ("generateGratiaScript NOT defined, so NOT creating Gratia record (Python script)\n\n"  );
    }

    ## Dealing with special case, if a site admin asks for local time zone
    ##  to be printed on HTML pages / STDOUT probe output
    ##
    ## Copy over timestamp from metric key 'timestamp'; then assign
    ##  local time if asked for
    $metric{'timestampToPrint'} = $o{'timestamp'};
    $metric{'timestampToPrint'} = $o{'timestampLocal'} 
                 if (defined($o{'printLocalTimezone'}));


    ## Only handles status metrics as of now
    if ($metric{'metricType'} eq "status") {
	## Print metric in WLCG standard output format to STDOUT; 
	##  detailsData has to be last field before EOT
	##
	## Exception to WLCG specs if local time zone requested specifically
	##
	my $outstring = "metricName: $metric{'metricName'}\n".
	    "metricType: $metric{'metricType'}\n".
	    "timestamp: $metric{'timestampToPrint'}\n";

	$outstring .= "voName: $metric{'voName'}\n" if (defined($metric{'voName'}));

        # siteName is used for Pigeon Tools
        $outstring .= "siteName: $metric{'siteName'}\n" if(defined($metric{'siteName'}));

	$outstring .= "metricStatus: $metric{'metricStatus'}\n".
	    "serviceType: $metric{'serviceType'}\n";
	if ($o{'localprobe'} == 1) {
	    $outstring .= "hostName: $metric{'hostName'}\n";
	} else {
	    $outstring .= "serviceURI: $metric{'serviceUri'}\n".
		"gatheredAt: $metric{'gatheredAt'}\n";
	}
	$outstring .= "summaryData: $metric{'summaryData'}\n".
	  "detailsData: $metric{'detailsData'}\n".
	  "EOT\n";
	print $outstring;

	## Print to file if requested
	if (defined($o{'generateTextFile'})) {
	    &Verbose ("Trying to print text output file\n");
	    $o{'textOutputFile'} = "$o{'textFileLocationDir'}/". 
		$o{'timestampUnixSeconds'} . "-" . $o{'hostName'} . "__".
		$metric{'metricName'}.".record";
	    my $fopen_return_tmp = open (TEXTFILE, 
				 ">$o{'textOutputFile'}");
	    if (defined($fopen_return_tmp)) {
		## text file open succeeded, then write script
		print TEXTFILE  $outstring;
		close (TEXTFILE);
		&Verbose ("Done writing text output file $o{'textOutputFile'}\n");
	    } 
	    else { ## File open failed - Add warning 
		&Verbose ("WARNING: Probe is configured to ".
			  " generate output text file, but could not open ".
			  " gratia script file: $o{'textOutputFile'}\n");
	    }
	}
    }
    ## once metric is printed, exit with acceptable exit code
    &Exit ();
}







################################################################################
##
## SUB-ROUTINE
##  Generate_Gratia_Sending_Script ()
##
## FUNCTION:
##
## Creates Gratia send script (in Python) -- a script that can be executed
##  by doing "python <script name> to send a metric probe
##  record to the Gratia collector (which, by default, is defined in 
##  file pointed to by $o{'gratiaMetricProbeConfigFile'} (i.e $o{})
##
## Uses ProbeConfig file defined by $o{'gratiaMetricProbeConfigFile'} during
##  Initialization unless specified otherwise using command line option
##
## Generated python script assumes PYTHONPATH is set BEFORE it's executed, 
##  to pick up Gratia.py and Metric.py from appropriate locations.
##
## NOTES:
## 1) For example python script, see [[3]]
##
## ARGUMENTS: 
##  First arg: 
##   Our hash 
##  Second arg: 
##   Metric hash containing metric details
##
## CALLS:
##  Escape_String_For_Gratia ();
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Reference to metric hash (with updated detailsData and possibly new status)
##
################################################################################

sub Generate_Gratia_Sending_Script {

    $o{'gratiaSendMetricScriptFile'} = 
	"$o{'gratiaLocationDir'}/". 
	$o{'timestampUnixSeconds'} . "-" . $o{'hostName'} . "-".
	$metric{'metricName'}.".$$.py";

    ## Content for temporary send-gratia-record Python script?
    ## First, common for all probes including local ones
    ##
    ## Escape certain characters that'll be written into Python script
    ##  For eg.: new line chars and double quotes
    my $gratia_script_content = "#! $o{'pythonToUse'}\n".
	"\nimport Gratia\n".
	"import Metric\n\n".
	"if __name__ == '__main__':\n".
	"        Gratia.Initialize(\"". &Escape_String_For_Gratia($o{'gratiaMetricProbeConfigFile'}) . "\")".
	"\n        r = Metric.MetricRecord()\n".
	"        r.MetricName(\"". &Escape_String_For_Gratia($metric{'metricName'}) . "\")\n".
        "        r.MetricType(\"". &Escape_String_For_Gratia($metric{'metricType'}) . "\")\n".
	"        r.MetricStatus(\"". &Escape_String_For_Gratia($metric{'metricStatus'}) . "\")\n".
	"        r.Timestamp(\"". &Escape_String_For_Gratia($metric{'timestamp'}) . "\") # Or could enter it as seconds since epoch\n".
	"        r.ServiceType(\"". &Escape_String_For_Gratia($metric{'serviceType'}) . "\")\n";

    ## Local probe or not -- send different fields accordingly
    if ($o{'localprobe'} == 0) {
	$gratia_script_content .= 
	    "        r.ServiceUri(\"". &Escape_String_For_Gratia($metric{'serviceUri'}) . "\")\n".
	    "        r.GatheredAt(\"". &Escape_String_For_Gratia($metric{'gatheredAt'}) . "\")\n";
    }
    else { ## Yes, local probe
	$gratia_script_content .= 
	    "        r.HostName(\"". &Escape_String_For_Gratia($metric{'hostName'}) . "\")\n";
    }

    ## Rest of the fields
    $gratia_script_content .= 
	"        r.SummaryData(\"". &Escape_String_For_Gratia($metric{'summaryData'}) . "\")\n".
	"        r.DetailsData(\"". &Escape_String_For_Gratia($metric{'detailsData'}) . "\")\n\n".
	"        print Gratia.Send(r)\n";

    &Verbose ( "Going to write python script $o{'gratiaSendMetricScriptFile'} to upload ".
	      " Gratia record with following content:\n$gratia_script_content\n\n");
    
    ## Open Gratia script file and print content 
    my $fopen_return_tmp = open (PYTHONFILE, 
				 ">$o{'gratiaSendMetricScriptFile'}");
    if (defined($fopen_return_tmp)) {
	## Gratia script file open succeeded, then write script
	print PYTHONFILE $gratia_script_content;
	close (PYTHONFILE);
    } 
    else { ## File open failed - Add warning to probe output 
	$metric{'detailsData'} .= "\n WARNING: Probe is configured to ".
	    " generate Send-Gratia Python script, but could not open ".
	    " gratia script file: $o{'gratiaSendMetricScriptFile'}";
    }

    return \%metric;
}




################################################################################
##
## SUB-ROUTINE
##  Escape_String_For_Gratia ()
##
## ARGUMENTS: 
##  First arg: String 
##
## OUTPUT: 
##  None
##
## RETURNS:
##  string after it is escaped for python 
##
## NOTE: It is necessary to escape $ for the Gratia uploader -ag 2010-03-02
## NOTE2: This function was updated per recommendation by James Kupsch of 
##         U.Wisconsin; it still escapes double quotes and $
##        Also, it does not return 'string' - I do not know how that will affect
##         Gratia --agopu 2010-03-02
## 
################################################################################

sub Escape_String_For_Gratia
{
    my $string = shift;

    $string =~ s/\\/\\\\/g;   # escape \'s first, MUST be done first
    $string =~ s/\'/\\\'/g;   # single quotes
    $string =~ s/\"/\\\"/g;   # double quotes
    $string =~ s/\n/\\n/g;    # new-lines, and everything next
    $string =~ s/\s+/ /g;
    $string =~ s/([^[:print:]])/sprintf("\\x%02x", ord $1)/eg;
    $string =~ s/\$/\\\$/g;   # Gratia requires $ to be escaped

    return "$string";
} 


################################################################################
##
## SUB-ROUTINE
##  Version ()
##
## ARGUMENTS: 
##  First arg: String for program name
##  Second arg:String from RCS version number
##
## OUTPUT: 
##  Prints current version of script
##
## RETURNS:
##  None
## 
################################################################################

sub Version {
    print <<EOF;
 $o{'probeName'} v.$o{'revision'}
 OSG GOC [http://www.grid.iu.edu]
EOF
}







################################################################################
##
## SUB-ROUTINE
##  Exit ()
##
## FUNCTION:
##
## Checks 'metricStatus'; and returns 1 if it's UNKNOWN; 0 otherwise
##  Required to be this way according to WLCG specs v 0.91 [[2]]
##
## ARGUMENTS: 
##  First arg: 
##   % Probe's hash (Unused)
##  Second arg: 
##   % Metric's hash containing at least the following key(s):
##     'metricStatus'
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Integer 0 or 1
## 
################################################################################

sub Exit {
    exit 1 if ($metric{'metricStatus'} eq "UNKNOWN");
    exit 0;  ## Otherwise
}






################################################################################
##
## SUB-ROUTINE
##  Do_Unlink () 
##
## FUNCTION:
##
## Unlinks file list provided if it's not empty and --no-cleanup is not specified
##
## ARGUMENTS: 
##  First arg: 
##  $space_separated_list of files to delete
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None
## 
################################################################################

sub Do_Unlink {
    my $files_to_delete   = $_[0];
    
    if ($o{'cleanUp'}==1) {
	## Split space separated list into array; then unlink if list is not empty
	my @arr_tmp = split (/ /, $files_to_delete);
	&Verbose (" Unlink CMD: [unlink @arr_tmp ] ".
	    " since cleanUp flag=[$o{'cleanUp'}]\n" );
	unlink(@arr_tmp) if ($files_to_delete !~ /^\s*$/);
    }
}









################################################################################
##
## SUB-ROUTINE
##  Exit_Error () 
##
## FUNCTION:
##
## Prints an error message with CRITICAL metricStatus and then exits 
##
## ARGUMENTS: 
##  First arg: 
##   % Probe's hash 
##  Second arg: 
##   % Metric's hash containing at least the following key(s):
##     'metricStatus'
##  Third arg: 
##   $status integer -- 1 or 2 (or 3)
##  Fourth arg: 
##   $error_string or warning string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None
## 
################################################################################

sub Exit_Error {
    my $status        = $_[0];
    my $message       = $_[1];

    $message =~ s/\s+$//g;;
    &Set_Summary_Metric_Results ($status, $message);
    &Print_Metric ();
}





################################################################################
##
## SUB-ROUTINE
##  Exit_Error_With_Cleanup () 
##
## FUNCTION:
##
## Cleans up files specified by calling Do_Unlink, and then calls Exit_Error()
##
## ARGUMENTS: 
##  First arg: 
##   % Probe's hash 
##  Second arg: 
##   % Metric's hash containing at least the following key(s):
##     'metricStatus'
##  Third arg: 
##   $status integer -- 1 or 2 (or 3)
##  Fourth arg: 
##   $error_string or warning string
##  Fifth arg: 
##   $space_separated_string (Escape "s) containing files 
##     that we will attempt to clean up
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None
## 
################################################################################

sub Exit_Error_With_Cleanup {
    my $status          = $_[0];
    my $message         = $_[1];
    my $files_to_delete = $_[2];

    &Verbose ( " Exit_Error_With_Cleanup(): files to delete: [$files_to_delete]\n");
    my $rm_cmd_out  = &Do_Unlink(\%o,\%metric, $files_to_delete);
    &Exit_Error ($status, $message);
}







################################################################################
##
## SUB-ROUTINE
##  Get_Timestamp ()
##
## FUNCTION:
## 
## Get timestamp value in ISO 8601 format
##  i.e 2007-05-02T19:54:07Z (T to separate date/time; Z to indicate UTC
##
## Also, set time in local time zone and in Unix seconds since 1970 format
##
## ARGUMENTS: 
##
##  NOTE: Using -u for UTC ... and rest of % stuff for ISO 8601 formatting
##
## OUTPUT: 
##  None
##
## RETURNS:
##  UTC timestamp string; Sets three hash keys
## 
################################################################################

sub Get_Timestamp {
    $o{'timestamp'} = `$o{'systemDateCmd'} -u +%FT%TZ`; 
    $o{'timestamp'} =~ s/\s*$//s; ## Remove trailing spaces/newlines

    $o{'timestampLocal'} = `$o{'systemDateCmd'} +%F\\ %T\\ %Z`;
    $o{'timestampLocal'}  =~ s/\s*$//s; ## Remove trailing spaces/newlines

    $o{'timestampUnixSeconds'} = `$o{'systemDateCmd'} +%s`;
    $o{'timestampUnixSeconds'}  =~ s/\s*$//s; ## Remove trailing spaces/newlines
    
    return $o{'timestamp'};
}








################################################################################
##
## SUB-ROUTINE
##  Parse_ServiceUri ()
##
## FUNCTION:
## 
## Breaks apart a provided serviceUri, into separate bits: 
##  hostName, port, serviceType (as applicable)
##
## ARGUMENTS: 
##  First arg: 
##   %GENERIC_hash  (could be probe hash or metric hash)
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to hash the routine was given initially with additional info
## 
################################################################################

sub Parse_ServiceUri {
    $o{'serviceUri'}   =~ s/\/$//g; ## Get rid of trailing /

    ## NEW: hostname:port/service, hostname/service, hostname:port, hostname
    ##  OLD: service://hostname:port
    ## Separate port number and service if provided
    if (($o{'serviceUri'}=~/:/) &&      ## Both are provided
	($o{'serviceUri'}=~/\//)) {   
	$o{'serviceUri'} =~ /(.*):(.*)\/(.*)/ ;
	$metric{'hostName'} = $o{'hostName'}   = $1;          ## hostname 
	$metric{'portNumber'} = $o{'portNumber'} = $2;          ## port no. 
	$metric{'serviceType'} = $o{'serviceType'}= $3;          ## serviceType
    }
    elsif ($o{'serviceUri'}=~/:/) {     ## Only port provided
	$o{'serviceUri'} =~ /(.*):(.*)/;  
	$metric{'hostName'} = $o{'hostName'}   = $1;          ## hostname 
	$metric{'portNumber'} = $o{'portNumber'} = $2;          ## port no.
    }
    elsif ($o{'serviceUri'}=~/\//) {    ## Only serviceType provided
	$o{'serviceUri'} =~ /(.*)\/(.*)/ ;  
	$metric{'hostName'} = $o{'hostName'}   = $1;          ## hostname part of URI
	$metric{'serviceType'} = $o{'serviceType'}= $2;          ## serviceType
    }
    else {                              ## Only hostname provided
	$metric{'hostName'} = $o{'hostName'}   = $o{'serviceUri'}; 
    }
    $metric{'serviceUri'} = $o{'serviceUri'};
}






################################################################################
##
## SUB-ROUTINE
##  Run_Command () 
##
## FUNCTION:
##
## Execute command (with arguments intact) that's passed along using backtick
##  or system () based on choice passed
## Time out if system call or backtick execution takes more than 'timeout'
##  seconds -- in that case, set relevant information in metric
##
## NOTES:
## 1) Refer to bug <<1>>
## 2) Refer to bug <<2>> :-)
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##
## CALLS:
##  Set_Summary_Metric_Results (\%o,\%metric, integer, "string")
##  Print_Metric ()
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Run_Command {
    my $cmd               =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"
    my $tmp_string        = undef;     ## Used below for verbose output
    
    $o{'callingRoutine'} = "::Run_Command ()";

    ## Reset these for this command run
    ($o{'cmdOut'}, $o{'cmdExitValue'}) = 
	("Command [$cmd] timed out after $o{'timeout'} seconds in RSVProbeBase".
	 "::Run_Command(); bailing now ...",-1);

    &Verbose ("----- Running command via Run_Command() -----\n");
    &Verbose ("CMD: [$cmd]\n");

    ## Eval the system/backtick call ... and then check if it timed out
    eval {
	local $SIG{ALRM} = sub { die "alarm\n" }; 	
	alarm $o{'timeout'}; ## set the alarm for when we want a wakeup
	
	## Run system command or backtick using cmd provided
	if ($method eq "system") {
	    $o{'cmdOut'}       = system($cmd);
	}
	elsif ($method eq "backtick") {
	    $o{'cmdOut'}       = `$cmd`;
	}
	else { 
	    &Exit_Error (3, "Invalid method \"$method\" provided to OSG_RSV_Probe_Bases::Run_Command () by $o{'callingRoutine'}; Bailing now ...");
	}
	$o{'cmdExitValue'} = ($? >> 8); ## Shift return val right
        ## turn the alarm off when the slow thing is finished
	alarm 0;
    };
    $o{'cmdOut'} =~ s/^\s+//; chomp ($o{'cmdOut'});
    
    &Verbose ( "CMD EXIT: [$o{'cmdExitValue'}]\n\t CMD OUT: [$o{'cmdOut'}]\n");

    if ($@) {
 	&Exit_Error (3, "Unknown error in $o{'callingRoutine'} while attempting to executed CMD:\n $cmd\n Was looking for a timeout alarm.\n")
	    unless $@ eq "alarm\n"; ## Catch unexpected errors
	## Command timed out
	&Verbose ( "CMD TIMED OUT after $o{'timeout'} seconds!\n");
	&Exit_Error (3, $o{'cmdOut'});
    }
    &Verbose ( "CMD completed within the $o{'timeout'} second timeout length.\n");
    &Set_Summary_Metric_Results (0,"$o{'cmdOut'}");
    return \%metric;
}




################################################################################
##
## SUB-ROUTINE
##  Verbose () 
##
## FUNCTION:
##
## Prints verbose information on stderr if the verbose flag is set
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   String to be printed
##
## OUTPUT: 
##  string on STDERR
##
## RETURNS:
##  None
## 
################################################################################


sub Verbose  {
    my $string = $_[0];

    if ($o{'verbose'} > 0) {
        my $time = strftime "%Y/%m/%d %H:%M:%S", localtime;
	print STDERR "$time VERBOSE ";
	print STDERR "$o{'callingRoutine'} " if ($o{'callingRoutine'});
	print STDERR $string; 
    }
}

sub Verbose2  {
    my $string = $_[0];
    print STDERR "VERBOSE2 $string" if ($o{'verbose'} > 1);
}





################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Run () 
##
## FUNCTION:
##
## Wrapper for Globus_Job_Run_Error_Code () function - with UNKNOWN as the 
##  error exit status
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Run {
    my $cmd               =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"

    &Globus_Job_Run_Error_Code ($cmd,$method,3);
}



################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Run_Error_Code () 
##
## FUNCTION:
##
## Execute remote globus job using globus-job-run using argument passed
##  using backtick or system () based on choice passed
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##  Fifth arg: 
##   The error code 2 or 3 that will cause printing of UNKNOWN or CRITICAL status
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Run_Error_Code {
    my $cmd        =   $_[0] ;  ## Command string to run
    my $method     =   $_[1] ;  ## "system" or "backtick"
    my $error_code =   $_[2];   ## error code = 2 or 3
    my $extra_rsl  = "";
    $extra_rsl = " -x \"$o{'extraGlobusRsl'}\" " if ( $o{'extraGlobusRsl'});

    $o{'globusjobCmd'} = "$o{'globusjobrunCmd'} $o{'hostName'}/jobmanager-fork $extra_rsl $cmd ";
    &Run_Command ($o{'globusjobCmd'}, "backtick");

    ## Check if globus job submission went through fine, and exit with unknown if it didn't
    ## Try to guess Globus errors, and provide more useful information if possible
    &Exit_Error ( $error_code, "FAILED Attempt to execute remote job:\n [$o{'globusjobCmd'}]\nERROR: $o{'cmdOut'}".&Analyse_Globus_Error())     if ($o{'cmdExitValue'} != 0);
}




################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Status () 
##
## FUNCTION:
##
## Wrapper for Globus_Job_Status_Error_Code () function - with UNKNOWN as the 
##  error exit status
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Status {
    my $cmd               =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"

    &Globus_Job_Status_Error_Code ($cmd,$method,3);
}



################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Status_Error_Code () 
##
## FUNCTION:
##
## Execute remote globus job using globus-job-status using argument passed
##  (job_id) using backtick or system () based on choice passed
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##  Fifth arg: 
##   The error code 2 or 3 that will cause printing of UNKNOWN or CRITICAL status
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Status_Error_Code {
    my $job_id            =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"
    my $error_code        =   $_[2];   ## error code = 2 or 3

    $o{'globusjobCmd'} = "$o{'globusjobstatusCmd'} $o{'globusjobId'} 2>&1";
    &Run_Command ($o{'globusjobCmd'}, "backtick");

    ## Check if globus job submission went through fine, and exit with unknown if it didn't
    ## Try to guess Globus errors, and provide more useful information if possible
    &Exit_Error ( $error_code, "FAILED Attempt to  check status of remote job:\n [$o{'globusjobCmd'}]\nERROR: $o{'cmdOut'}".&Analyse_Globus_Error())
	if ($o{'cmdExitValue'} != 0);
    
    $o{'globusjobStatus'} = $o{'cmdOut'}; ## Copy status
    return \%metric;
}



################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Submit () 
##
## FUNCTION:
##
## Wrapper for Globus_Job_Submit_Error_Code () function - with UNKNOWN as the 
##  error exit status
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Submit {
    my $cmd               =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"
    
    &Globus_Job_Submit_Error_Code ($cmd,$method,3);
}



################################################################################
##
## SUB-ROUTINE
##  Globus_Job_Submit_Error_Code () 
##
## FUNCTION:
##
## Execute remote globus job using globus-job-submit using argument passed
##  using backtick or system () based on choice passed
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##   'callingRoutine'  indicating where this routine was called from
##   'verbose'
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##  Third arg: 
##   String containing command to run including arguments
##  Fourth arg: 
##   The string "system" or "backtick" to indicate what to use
##  Fifth arg: 
##   The error code 2 or 3 that will cause printing of UNKNOWN or CRITICAL status
##  Sixth arg:
##   jobmanager string to use if not same as default; this string will be appended
##   to host string in "host/jobmanager" format
##
## CALLS:
##  Run_Command (. . .)
##  Exit_Error ( integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with updated key-values
## 
################################################################################

sub Globus_Job_Submit_Error_Code {
    my $cmd               =   $_[0] ;  ## Command string to run
    my $method            =   $_[1] ;  ## "system" or "backtick"
    my $error_code        =   $_[2];   ## error code = 2 or 3

    my $extra_rsl  = "";
    $extra_rsl = " -x \"$o{'extraGlobusRsl'}\" " if ( $o{'extraGlobusRsl'});

    $o{'globusjobCmd'} = "$o{'globusjobsubmitCmd'} $o{'hostName'}/$o{'jobManager'} $extra_rsl $cmd ";
    &Run_Command ($o{'globusjobCmd'}, "backtick");

    ## Check if globus job submission went through fine, and exit with unknown if it didn't
    ## Try to guess Globus errors, and provide more useful information if possible
    &Exit_Error ( $error_code, "FAILED Attempt to execute remote job:\n [$o{'globusjobCmd'}]\nERROR: $o{'cmdOut'}".&Analyse_Globus_Error())
	if ($o{'cmdExitValue'} != 0);

    $o{'globusjobId'}  = $o{'cmdOut'};
    return \%metric;
}





################################################################################
##
## SUB-ROUTINE
##  Analyse_Globus_Error ()
##
## ARGUMENTS: 
##  First arg: 
##   %probe's hash containing at least the following key-values
##  Second arg: 
##   %Metric hash containing at least the following key-values:
##     jobManager, cmdOut
##
## CALLS:
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Use 'tip' string
## 
################################################################################

sub Analyse_Globus_Error {
    return "\nTIP: Check hostname; Attempt to ping host; Use only fully qualified domain name for host;\n".
    "Also check if host certificate on remote host has expired." if ($o{'cmdOut'} =~ /Error Code 12/i);
    return "\nTIP: Check if $o{'jobManager'} is offered on the remote Globus host?\n" if ($o{'cmdOut'} =~ /Error Code 93/i);
    return "";
}





################################################################################
##
## SUB-ROUTINE
##  Parse_Xml () 
##
## Expects $o{'cmdOut'} to contain XML output, say, from a worker script
##  This routine parses that XML, and returns a hash reference to 
##  %{$o{'cmdOutHash'}}
##
## ARGUMENTS: 
##  First arg: 
##   OPTIONAL string to be printed in case of an error
##
## CALLS:
##   Exit_Error ()
##   Verbose ()
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Reference to $o{'cmdOutHash'} hash
## 
################################################################################

sub Parse_Xml {
    my $err_string = "";
    $err_string    = $_[0] if ($_[0]);

    ## Now process worker script output from $o{'cmdOut'}
    my $xml = new XML::Simple (KeyAttr=>[]);

    # if data does not start with '<' XMLin will try to look for it as a file RT #6431
    if($o{'cmdOut'} !~ /^\s*</) {
        RSVProbeBase::Exit_Error(3, "$err_string\n" . 
                                 "Output could not be parsed as XML because it does not start " .
                                 "with a '<'.\nOutput:\n" . 
                                 "$o{'cmdOut'}");
    }

    %{$o{'cmdOutHash'}} = %{$xml->XMLin($o{'cmdOut'})}; 
    &Verbose (&Data::Dumper::Dumper($o{'cmdOutHash'}));
    
    &Exit_Error (3,"$err_string\n"."Worker script exit code: $o{'cmdOutHash'}{'ExitCode'}\n".
		 "Worker script error Received via XML stderr element: \n".
		 &Data::Dumper::Dumper($o{'cmdOutHash'}{'StdErr'}{'Error'})) 
	if ($o{'cmdOutHash'}{'ExitCode'} != 0);

    return \%{$o{'cmdOutHash'}}
}

################################################################################
##
## SUB-ROUTINE
##  Parse_Compare_Openssl_Timestamps () (using Unix seconds since 1970)
##
## ARGUMENTS: 
##  First arg: 
##   String containing "notAfter" date 
##
## OUTPUT: 
##  None
##
## RETURNS:
##  integer - difference in timestamp value 
## 
################################################################################

sub Parse_Compare_Openssl_Timestamps {
    my $openssl_cmd_out =   $_[0] ;

    ## Parse relevant part of openssl cmd output Sep 24 19:09:44 2008 GMT
    $openssl_cmd_out =~ /=(.*)/; my $openssl_date = $1;
    ## New order of fields for Date::Manip funcs Sep 24 19:09:44 GMT 2008 
    $openssl_date =~ /(.*)\s+(.*)\s+(.*)\s+(.*)\s+(.*)/ ;
    $openssl_date = "$1 $2 $3 $5 $4";

    ## Convert to seconds (since 1970...)
    my $openssl_date_parsed = ParseDate($openssl_date);
    if (!$openssl_date_parsed) { 
	&Verbose ( " $0 Parse_Compare_Openssl_Timestamps () ".
	  "WARNING: Bad date string: ".
	    "$openssl_date\n" ); }
    my $openssl_date_seconds =  UnixDate($openssl_date_parsed,"%s");
    
    ## Compare two dates; 
    my $date_cmp = $openssl_date_seconds - $o{'timestampUnixSeconds'};
    ## $date_cmp -= 44350400; ## for testing expired cert elsif clause
    
    return $date_cmp;
}




################################################################################
##
## SUB-ROUTINE
##  Test_Certificate ()
##
## ARGUMENTS: 
##  First arg: 
##   $string containing type of cert being tested; possible values 
##     include hostcertFile, containercertFile, httpcertFile
##
##  NOTE: Using -u for UTC ... and rest of % stuff for ISO 8601 formatting
##
##
## CALLS:
##  Run_Command ()
##  Set_Summary_Metric_Results ()
##  Parse_Compare_Openssl_Timestamps ()
##  Print_Metric ()
##
##
## OUTPUT: 
##  None
##
##
## RETURNS:
##  Pointer to metric hash with all the details set
## 
################################################################################

sub Test_Certificate {
    my $certfile = $o{'localCertificates'}{&Get_MetricName()};
    $certfile = $o{&Get_MetricName()} if ($o{&Get_MetricName()});
    $o{'callingRoutine'} = "::Test_Certificate ()";

    ## Check for existence of host/http/container/etc. certfile ... 
    &Exit_Error (3, "Cannot find $certfile.") if (!(-e $certfile)) ;
   
    ## Check if Hostcert has expired using openssl command and system date ##
    my $openssl_cmd = "$o{'opensslCmd'} x509 -in $certfile  -noout -enddate 2>&1 ";
    &Run_Command ($openssl_cmd, "backtick");
    &Exit_Error (2, $o{'cmdOut'}) if ($o{'cmdExitValue'} !=0);

    ## Compare two dates; 
    my $date_cmp = &Parse_Compare_Openssl_Timestamps ($o{'cmdOut'});
    
    ## Check $date_cmp value negative? -- also check if cert is expiring soon
    if ($date_cmp < 0) {
	&Set_Summary_Metric_Results (2, "$certfile expired! Openssl returned $o{'cmdOut'})");
    }
    elsif ($date_cmp <= $o{'certWarningSeconds'}) { 
	&Set_Summary_Metric_Results (1, "$certfile expiring soon! Openssl returned $o{'cmdOut'}");
    } elsif ($date_cmp > $o{'certWarningSeconds'}) {
	&Set_Summary_Metric_Results (0, "$certfile: Openssl returned $o{'cmdOut'}"); 
    }
    &Print_Metric();
}






################################################################################
##
## SUB-ROUTINE
##  Ping_Host ()
##
## FUNCTION:
##
## Execute ping command on remote host and return ping command value (which
##  will be processed by Set_Ping_Metric_Results()
##
## NOTES:
##
## ARGUMENTS: 
##  None
##
## Expects
##   %o hash containing at least the following key-values:
##    'pingCmd'   Ping command including its path
##    'timeOut'   integer (in seconds)
##    'pingCount' integer (number of ping packets)
##  %metric hash containing at least the following key-values:
##    'hostName'  string
##
## CALLS:
##  Run_Command ("cmd string", "method string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to hash that was initially provided as a 2nd argument
## 
################################################################################

sub Ping_Host {
    $o{'callingRoutine'} = "::Ping_Host ()";
    my $ping_cmd = "$o{'pingCmd'} -q -W $o{'pingTimeout'} -c $o{'pingCount'} $o{'hostName'} 1>/dev/null 2>/dev/null";
    ## Not using back-ticks for now, since I am not using output text
    &Run_Command($ping_cmd, "system");

    ## Check if exit value (shifted by 8) is 0,1 or 2..
    if ($o{'cmdExitValue'} == 0) {
	&Set_Summary_Metric_Results (0, "Host $o{'hostName'} is alive and responding to pings!");
    } elsif ($o{'cmdExitValue'} == 1) {
	&Set_Summary_Metric_Results (1, "Host $o{'hostName'} is alive but not responding to pings");
    } elsif ($o{'cmdExitValue'} == 2) {
	&Set_Summary_Metric_Results (2, "Unable to ping host $o{'hostName'}");
    } else {  ## Unknown status here
	&Set_Summary_Metric_Results (3, "ERROR: Cannot execute ping command $metric{'pingCmd'}... Bailing for now");
    }
    ## If a host is not pingable, then all probes would want to print
    ##  and exit right now; also ping probe would be done at this stage
    &Print_Metric () if ((($o{'cmdExitValue'} != 0) && ($o{'cmdExitValue'} != 1)) ||
	    ($o{'probeName'} eq "ping-host-probe"));
}






################################################################################
##
## SUB-ROUTINE
##  Check_Proxy_Validity ()
##
## FUNCTION:
##
## Execute grid-proxy-info command on local proxy and return metric hash
##  with appropriate key-values set.
##
## NOTES
## 1) Use -exists option for exit value; and -valid H:M
##    Exit value 0 if proxy exists and is valid for > H:M; 
##               1 if proxy exists and is valid for < H:M or has EXPIRED!
##               Value other than (0 or 1) --> NO proxy exists
## 2) Use -timeleft option
##    Exit value 0 if proxy exists ; prints timeleft in seconds on STDOUT
##           non 0 if proxy does not exist
##
## 3) FURTHER: Proxy needs to be valid at least for 3 hours for jobs to run 
##    using globus-job-run -- so checking for 3 HOURS MINIMUM or returning
##    as expired; then I could also do threshold check on top of that
##
##
## ARGUMENTS: 
##  First arg: 
##   %hash (non-metric) containing at least the following key-values:
##    'gridproxyinfoCmd'   grid-proxy-info command including its path
##  Second arg: 
##   % metric hash that output status will entered into
##
## CALLS
##  Run_Command (\%o, \%metric, "string", "method")
##  Set_Summary_Metric_Results (\%o,\%metric, integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash including keys:
##    'cmdOut'
##    'cmdExitValue'
##    'checkProxyValidityReturnValue' <-- New KEY; 0 good; 1 warning; 2 expired
## 
################################################################################

sub Check_Proxy_Validity {
    $o{'callingRoutine'} = "::Check_Proxy_Validity ()";

    &Run_Command (" $o{'gridproxyinfoCmd'} -timeleft 2>&1 ", "backtick");

    ## There is no proxy (exit val != 0) or it's expired
    &Exit_Error (3, $o{'cmdOut'}."\nTIP: Does proxy file ". $o{'proxyFile'} ." exist?\n Is it owned by RSV user [". $ENV{'USER'} ."] with 600 permissions?\n")     
	if ($o{'cmdExitValue'} != 0);


    ## grid-proxy-info did not exit with error; so proceed with further tests
    if ($o{'cmdOut'} < $o{'proxyExpiryMinimumSeconds'}) {    
	&Exit_Error (3, "Proxy has expired or is valid for less than the \n minimum required " . $o{'proxyExpiryMinimumSeconds'}/3600 ." hours ... Bailing now\n (Proxy $o{'proxyFile'} has timeleft: " . int($o{'cmdOut'}/60) ." minutes)");
    }

    ## Looks like a valid usable proxy; attach warning code in returnvalue if necessary, and then proceed
    elsif ($o{'cmdOut'} <
	   $o{'proxyExpiryWarningSeconds'}){
	$metric{'proxyValidityWarningMessage'} = "\n (WARNING: Proxy $o{'proxyFile'} is expiring soon in ". int($o{'cmdOut'}/60) . " minutes!)";
    } 
    return \%metric;
}



################################################################################
##
## SUB-ROUTINE
##  Append_Proxy_Validity_Warning ()
##
## FUNCTION:
##
## Little routine that appends a warning to metric's detailsData field if
##  such message's has key is defined
##
## NOTES:
##
## ARGUMENTS: 
##  First arg: 
##   % metric hash that has input, and output status will entered into
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to metric hash with appended warning IF NEED BE about expiring proxy
## 
################################################################################

sub Append_Proxy_Validity_Warning {
    ## Append this string - if it's defined
    $metric{'detailsData'}  .= $metric{'proxyValidityWarningMessage'} 
       if (defined ($metric{'proxyValidityWarningMessage'}));
    return \%metric;
}







################################################################################
##
## SUB-ROUTINE
##  Check_Gram_Authentication ()
##
## FUNCTION:
##
## Execute globusrun -a -r command on remote host and return metric hash
##  with appropriate key-values set.
##
## NOTES
##
## ARGUMENTS: 
##  First arg: 
##   % hash containing at least the following key-values:
##    'globusrunCmd'             globusrun command including its path
##  Second arg: 
##   % metric hash that output status will entered into
##
## CALLS:
##  Run_Command (\%o,\%metric, "cmd string", "method string")
##  Set_Summary_Metric_Results (\%o,\%metric, integer, "string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to hash that output status will entered into
##     'globusrunCmdExitValue'   INCLUDES NEW  element
## 
################################################################################

sub Check_Gram_Authentication {
    
    &Ping_Host ();
    &Check_Proxy_Validity ();

    $o{'callingRoutine'} = "::Check_Gram_Authentication ()";

    &Run_Command (" $o{'globusrunCmd'} -a -r $o{'hostName'} ", "backtick");

    if ($o{'cmdExitValue'} != 0) {
	if ($o{'probeName'} eq "gram-authentication-probe") {
	    ## GRAM auth failed - try globus-url-copy since it usually 
	    ##  provides better diagnosis
	    my $error_string = $o{'cmdOut'};
	    my $gridftp_cmd = "$o{'globusurlcopyCmd'} ".
		" file:///". $o{'globusurlcopyTestfile'}. " ".
		$o{'globusurlcopyServiceType'}. "://". $o{'hostName'} .
		":" . $o{'globusurlcopyPortNumber'}. "/".
		$o{'gridftpDestinationDir'} ."/". $o{'timestampUnixSeconds'}. 
		"-gridftp-probe-test-file-remote.$$ 2>&1";
	    &Run_Command ($gridftp_cmd, "backtick");
	    $error_string .= "\n\nAdditionally tried globus-url-copy hoping for more useful diagnosis:\n". $o{'cmdOut'};
	    &Exit_Error(2, $error_string);
	}
	## Else - If gram auth fails, then lot of metrics would stumble - make those unknown, 
	##  and catch critical in the gram-auth metric above
	&Exit_Error(3, $o{'cmdOut'}); 
    } else {
	&Set_Summary_Metric_Results (0, $o{'cmdOut'});
    }
    return \%metric; 
}






################################################################################
##
## SUB-ROUTINE
##  Get_Remote_Env ()
##
## FUNCTION:
##
## Run globus job on remote host to grab its environment; set appropriate
##  probe hash key-values as required.
##
## NOTES
##
## ARGUMENTS: 
##  First arg: 
##   % hash containing at least the following key-values:
##    'globusrunCmd'          globusrun command including its path
##    'envCmd'                env command including its path
##  Second arg: 
##   % metric hash that output status will entered into
##
## CALLS:
##  Run_Command (\%o,\%metric, "cmd string", "method string")
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Pointer to subhash in %o hash ie.e $o{'REMOTE_ENV'}
## 
################################################################################

sub Get_Remote_Env {
    
    &Ping_Host ();
    &Check_Gram_Authentication();

    $o{'callingRoutine'} = "::Get_Remote_Env ()";
    
    &Globus_Job_Run (" $o{'envCmd'} 2>&1", "backtick");

    my @arr_remote_env = split (/\n/,$o{'cmdOut'});
    foreach my $env_var (@arr_remote_env) {
	&Verbose2 ("Got remote env varialble-value pair [$env_var]\n");
	$env_var =~ s/\s*$//s; ## Remove trailing spaces/newlines
	$env_var =~ /(\S+)=(.*)/;
	&Verbose2 ("Setting % o hash o{$1} to be [$2]\n");
	$o{'REMOTE_ENV'}{$1} = $2;
    }
    
    ## REMOTE SIDE PATHS, etc.: Now set these using above OSG_LOCATION
    ## For OSG-VERSION-PROBE
    $o{'osgversionCmd'} = "$o{'REMOTE_ENV'}{'OSG_LOCATION'}/osg/bin/osg-version";
    ## For VDT-VERSION-PROBE
    $o{'vdtversionCmd'} = "$o{'REMOTE_ENV'}{'OSG_LOCATION'}/vdt/bin/vdt-version -vdt-location $o{'REMOTE_ENV'}{'OSG_LOCATION'}";

    ## For BATCH-SCHEDULERS-AVAILABLE-PROBE
    $o{'globusJobManagerDir'} = "$o{'REMOTE_ENV'}{'OSG_LOCATION'}/globus/lib/perl/Globus/GRAM/JobManager";       
    ## For VO-SUPPORTED-PROBE
    $o{'vosupportedCmd'} = "$o{'catCmd'} $o{'REMOTE_ENV'}{'OSG_LOCATION'}/monitoring/osg-supported-vo-list.txt";

    &Verbose ( "\t OSG_LOCATION: [$o{'REMOTE_ENV'}{'OSG_LOCATION'}];\t osgversionCmd: [$o{'osgversionCmd'}];\n\t vdtversionCmd: [$o{'vdtversionCmd'}];\t globusJobmanagerDir: [$o{'globusJobManagerDir'}];\n\t vosupportedCmd: [$o{'vosupportedCmd'}]\n" );;

    return \%{$o{'REMOTE_ENV'}};
}





################################################################################
##
## SUB-ROUTINE
##  Is_Metric_Defined ()
##
## ARGUMENTS: 
##  First arg: 
##   % hash containing at least the following key-values:
##    'metric'    Metric parameter from command line
##    'verbose'   
##
##  Second arg: 
##   % metric hash that output status will entered into
##
## OUTPUT: 
##  None
##
## RETURNS:
##  Integer 1 = true; 0 = false
## 
################################################################################

sub Is_Metric_Defined {
    my $metric_string =   $_[0];
    $o{'callingRoutine'} = "::Is_Metric_Defined ()";

    &Verbose ( "Testing if [$metric_string] was defined -- Metric defined is [$o{'metric'}]\n");
    return ((!(defined($o{'metric'}))) || 
	    (($o{'metric'} eq $metric_string))); 
}





################################################################################
##
## SUB-ROUTINE
##  Trim ()
##
##  Trim string provided
##
## ARGUMENTS: 
##  First arg: 
##   "True" or "False"
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Trim  {
    my $string = shift;
    $string =~ s/^\s+//;
    $string =~ s/\s+$//;
    return $string;
}





################################################################################
##
## SUB-ROUTINE
##  Set_DetailsDataTrim ()
##
##  Enable/Disable trimming of detailsData
##
## ARGUMENTS: 
##  First arg: 
##   "True" or "False"
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_MultiMetric {
    my $string = shift;
    $o{'multimetric'} = 1 if ($string =~ /True/i);
}





################################################################################
##
## SUB-ROUTINE
##  Append_DetailsData ()
##
##  Appends detailsData field in %metric
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Append_DetailsData {
    my $string = shift;
    $metric{'detailsData'} .= $string if ($string);
    ##$metric{'detailsData'} = sprintf("$metric{'detailsData'}%s",join("", @_));
}



################################################################################
##
## SUB-ROUTINE
##  Set_DetailsDataTrim ()
##
##  Enable/Disable trimming of detailsData
##
## ARGUMENTS: 
##  First arg: 
##   "True" or "False"
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_DetailsDataTrim {
    my $string = shift;
    $o{'detailsDataTrim'} = 0 if ($string =~ /False/i);
}




################################################################################
##
## SUB-ROUTINE
##  Get_DetailsData ()
##
##  Returns hash value
##
## ARGUMENTS: 
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Get_DetailsData {
    return $metric{'detailsData'};
}





################################################################################
##
## SUB-ROUTINE
##  Set_DetailsData ()
##
##  Set detailsData field in %metric
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_DetailsData {
    my $string = shift;
    $metric{'detailsData'} = $string;
}





################################################################################
##
## SUB-ROUTINE
##  Set_MetricName
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_MetricName {
    my $string = shift;
    
    $metric{'metricName'} = $string;
}


################################################################################
##
## SUB-ROUTINE
##  Get_MetricName
##
##  Get %metric hash key value 
##
## ARGUMENTS: 
##  None
##
## OUTPUT: 
##  None
##
## RETURNS:
##  string
## 
################################################################################

sub Get_MetricName {
    return $metric{'metricName'};
}




################################################################################
##
## SUB-ROUTINE
##  Set_MetricStatus
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_MetricStatus {
    my $string = shift;
    
    $metric{'summaryData'} = $metric{'metricStatus'} = $string;
}


################################################################################
##
## SUB-ROUTINE
##  Get_MetricStatus
##
##  Get %metric hash key value 
##
## ARGUMENTS: 
##  None
##
## OUTPUT: 
##  None
##
## RETURNS:
##  string
## 
################################################################################

sub Get_MetricStatus {
    return $metric{'metricStatus'};
}



################################################################################
##
## SUB-ROUTINE
##  Set_MetricType
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_MetricType {
    my $string = shift;
    
    $metric{'metricType'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ServiceType
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ServiceType {
    my $string = shift;
    
    $metric{'serviceType'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ServiceVersion
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ServiceVersion {
    my $string = shift;
    
    $metric{'serviceVersion'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ProbeType
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ProbeType {
    my $string = shift;
    
    $metric{'probeType'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_LocalProbe
##
##  Set %o hash key value to true; it is false by default 
##
## ARGUMENTS: 
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_LocalProbe {
    $o{'localprobe'} = 1;
}




################################################################################
##
## SUB-ROUTINE
##  Set_EnableByDefault
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_EnableByDefault {
    my $string = shift;
    
    $metric{'enableByDefault'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_MetricInterval
##
##  Set %metric hash key value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_MetricInterval {
    my $string = shift;
    
    $metric{'metricInterval'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ProbeRevision
##
##  Set %o hash key-value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ProbeRevision {
    my $string = shift;
    
    $o{'revision'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ProbeSpecVersion
##
##  Set %o hash key-value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ProbeSpecVersion {
    my $string = shift;
    
    $o{'probeSpecificationVersion'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ProbeHelpIntro
##
##  Set %o hash key-value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ProbeHelpIntro {
    my $string = shift;
    
    $o{'helpIntro'} = $string;
}



################################################################################
##
## SUB-ROUTINE
##  Set_ProbeHelpOptions
##
##  Set %o hash key-value using string provided 
##
## ARGUMENTS: 
##  First arg: 
##   $string
##
## OUTPUT: 
##  None
##
## RETURNS:
##  None 
## 
################################################################################

sub Set_ProbeHelpOptions {
    my $string = shift;
    
    $o{'helpOptions'} = $string;
}



################################################################################
## OK done with this perl module!
1;
################################################################################
#  LocalWords:  virtualorganization
