#! /usr/bin/env perl

=head1 cleanup-rsv.pl

Auxiliary OSG-RSV script that can be used to remove submission files, output files, etc.

For example, you can remove all files related to
a particular host specified on the command line, so that RSV
will not monitor that resource any longer.

=head2 Synopsis

    cleanup-rsv.pl --vdt-install <VDT installation root>
                   --remove-probes <Resource FQDN to remove from RSV monitoring> 
                   --remove-consumers
                   --output-files-only 
                   --reset, --full-reset
                   --help, --usage

=head2 Description

=over 4

=item B<--vdt-install> <VDT installation root>

B<configure_osg_rsv> will look for the root of the VDT installation at
    $VDT_LOCATION.  If you do not have that set you can specify it
    with --vdt-install instead.

=item B<--remove-probes>    - Requires FQDN string

    Above argument takes a FQDN of a host to remove from monitoring 
    (e.g. --remove-probes "host.foo.edu")

    It needs to be the exact same hostname that was specified initially
    at the configure_osg_rsv script execution.

=item B<--remove-consumers>

    This argument causes all of RSV's consumer submission files to be removed.
    Consumer log files will also be removed. 

=item B<--output-files-only>    

    This argument causes all of RSV's local HTML pages to be removed.
    Probe log files will also be removed. These log files and HTML pages
    will be recreated over time when scheduled probes run again.

=item B<--reset>, B<--full-reset>

    This argument causes a full reset of all RSV settings/output files/log files.
    USE WITH EXTREME CAUTION! All existing probe/consumer 
    submission files, output files, for all
    URIs RSV was ever configured for, will be removed.

=item B<--help>, B<--usage>

Print a usage message.

=back 

=cut



use strict;
use Getopt::Long;
use File::Temp;
use File::Basename;


##
## Configuration switches
##
my %o;
my @arr_files_to_remove = ();
my @arr_dirs_to_remove  = ();

## Paths
$o{'VDT_LOCATION'} = $ENV{VDT_LOCATION};
$o{'OSG_RSV_DIR'}       = "$o{'VDT_LOCATION'}/osg-rsv";

$o{'PROBE_SPEC_DIR'}    = "$o{'OSG_RSV_DIR'}/specs";
$o{'HTML_OUTPUT_DIR'}  = "$o{'OSG_RSV_DIR'}/output/html";
$o{'GRATIA_SCRIPT_DIR'} = "$o{'OSG_RSV_DIR'}/output/gratia";
$o{'PROBE_LOG_DIR'}     = "$o{'OSG_RSV_DIR'}/logs/probes";
$o{'CONSUMER_LOG_DIR'}  = "$o{'OSG_RSV_DIR'}/logs/consumers";
$o{'PROBE_SUBMISSION_DIR'}    = "$o{'OSG_RSV_DIR'}/submissions/probes";
$o{'CONSUMER_SUBMISSION_DIR'} = "$o{'OSG_RSV_DIR'}/submissions/consumers";

$o{'CONTACT_ID'}        = "rsv-dev\@opensciencegrid.org";



GetOptions("vdt-install=s"     => \$o{'VDT_LOCATION'},
           "remove-probes=s"   => \$o{'OPT_REMOVE_URI'},
           "remove-consumers"  => \$o{'OPT_REMOVE_CONSUMERS'},
           "output-files-only" => \$o{'OPT_CLEAN_HTML_ONLY'},
           "full-reset|reset"  => \$o{'OPT_FULL_RESET'},
           "help|usage"        => \&usage);
usage() unless (($o{'VDT_LOCATION'}) && 
		(($o{'OPT_REMOVE_URI'}) || ($o{'OPT_CLEAN_HTML_ONLY'}) 
		 || ($o{'OPT_REMOVE_CONSUMERS'}) || ($o{'OPT_FULL_RESET'})));




## Build list of files and directories to remove
##  based on option used

if ($o{'OPT_FULL_RESET'}) {
    @arr_files_to_remove = ($o{'PROBE_SUBMISSION_DIR'}."/*.sub",
			    $o{'CONSUMER_SUBMISSION_DIR'}."/*.sub",
			    $o{'PROBE_LOG_DIR'}."/*",
			    $o{'CONSUMER_LOG_DIR'}."/*",
			    $o{'GRATIA_SCRIPT_DIR'}."/*",
			    $o{'HTML_OUTPUT_DIR'}."/*/*.html* ",
			    $o{'HTML_OUTPUT_DIR'}."/*.html");
    @arr_dirs_to_remove  =  ($o{'HTML_OUTPUT_DIR'}."/*");
    print "\n Request to reset RSV - will remove related files from $o{'OSG_RSV_DIR'}\n";
    $o{'FOOTER'} = 
" You'll have to re-run configure_osg_rsv (with all the applicable options)\n".
" OR configure-osg if you prefer to use that route, to get it working again.\n";
}
elsif ($o{'OPT_REMOVE_URI'}) {
    @arr_files_to_remove = ($o{'PROBE_SUBMISSION_DIR'}."/".$o{'OPT_REMOVE_URI'}."__*.sub",
			    $o{'PROBE_LOG_DIR'}."/".$o{'OPT_REMOVE_URI'}."__*",
			    $o{'HTML_OUTPUT_DIR'}."/".$o{'OPT_REMOVE_URI'}."/*.html* ",
			    $o{'HTML_OUTPUT_DIR'}."/index.html");
    @arr_dirs_to_remove  =  ($o{'HTML_OUTPUT_DIR'}."/".$o{'OPT_REMOVE_URI'});
    print "\n Request to remove $o{'OPT_REMOVE_URI'} related files from $o{'OSG_RSV_DIR'}\n";
    $o{'FOOTER'} = 
" If you ever want this host to be monitored again, you'll have to re-run\n".
" configure_osg_rsv (with all the applicable options) OR configure-osg\n".
" if you prefer to use that route.";
}
elsif ($o{'OPT_REMOVE_CONSUMERS'}) {
    @arr_files_to_remove = ($o{'CONSUMER_SUBMISSION_DIR'}."/*.sub",
			    $o{'CONSUMER_LOG_DIR'}."/*.out",
			    $o{'CONSUMER_LOG_DIR'}."/*.err");
    @arr_dirs_to_remove  =  ();
    print "\n Request to remove all consumer related files from $o{'OSG_RSV_DIR'}\n";
    $o{'FOOTER'} = 
" If you want RSV to generate HTML pages using probe results, and upload\n".
" probe results to the central GOC based collector, then you will have to\n".
" re-run configure_osg_rsv (with the --consumers option) OR configure-osg\n".
" if you prefer to use that route.";
}
elsif ($o{'OPT_CLEAN_HTML_ONLY'}) {
    @arr_files_to_remove = ($o{'PROBE_LOG_DIR'}."/*.out",
			    $o{'PROBE_LOG_DIR'}."/*.err",
			    $o{'HTML_OUTPUT_DIR'}."/*/*.html* ",
			    $o{'HTML_OUTPUT_DIR'}."/*.html");
    @arr_dirs_to_remove  =  ($o{'HTML_OUTPUT_DIR'}."/*");
    print "\n Request to cleanup all local RSV HTML webpages, and related file from $o{'OSG_RSV_DIR'}\n";
    $o{'FOOTER'} = 
" If you still have RSV configured to monitor any resource(s), the files removed\n".
" will be re-created over time, as probes run per the scheduled time line.";
}


print "\n The following files will be removed:\n";
foreach (@arr_files_to_remove) {
    print "  $_\n";
}
print "\n The following directories will be removed:\n";
foreach (@arr_dirs_to_remove) {
    print "  $_\n";
}

## Go to work 
&remove_files () if (&ask() == 1);

print " Done with requested cleanup.\n";
print "\n$o{'FOOTER'}". 
    " \n Contact RSV team by emailing $o{'CONTACT_ID'} if you have any questions.\n\n"; 

exit 0;





## Return 1 if user input is y; 0 if user input is n
sub ask {
    print "\n Continue? (y/n) [n]: ";
    my $answer = <STDIN>; chomp($answer);
    if ((lc($answer) eq 'n') || ($answer =~ /^$/)) {
	print "\n You chose \'n\', will not delete above files, quitting...\n";
	exit 10;
    }
    elsif (lc($answer) eq 'y') {
	print "\n You chose \'y\', deleting above files...\n";
	return 1;
    }
    else {
	print "\n Please Enter \'y\' or \'n\'\n";
	&ask();
    }
}

## Sub routine that removes the files and/or directories
sub remove_files {
    foreach (@arr_files_to_remove) {
	system ("rm -f $_");
    }
    foreach (@arr_dirs_to_remove) {
	system ("rmdir $_");
    }
    return;
}


# Prints the usage information, and exits with a non-zero status code.
# ------------------------------------------------------------------------------
sub usage
{
    if(!$o{'VDT_LOCATION'}) {
        print "ERROR: VDT_LOCATION is not set.\n";
        print "Either set this environment variable, or pass the --vdt-install command line option.\n";
    }
    else {
	print `pod2text $0`;
    }
    exit 1;
}

