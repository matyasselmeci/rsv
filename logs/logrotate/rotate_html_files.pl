#!/usr/bin/env perl
use strict;

my $conf_file = "$ENV{VDT_LOCATION}/osg-rsv/logs/logrotate/rotate_html_files.conf";
my $state_file = "$ENV{VDT_LOCATION}/osg-rsv/logs/logrotate/rotate_html_files.state";

print "Beginning rotation of RSV HTML files\n";
print "logrotate conf file -> $conf_file\n";
print "logrotate state file -> $state_file\n";
print "Look in the .err file for logrotate verbose output.\n\n";

# Rotate the html files
print `$ENV{VDT_LOCATION}/logrotate/sbin/logrotate --force --verbose -s $state_file $conf_file`;

# 
# Now build the old.html page
#

# Get the location of the html files - this is configurable so we have to read it from the conf file
my $html_dir;
if(open(CONF, "<", $conf_file)) {
    my @lines = <CONF>;
    my $html_dir = "";
    foreach my $line (reverse @lines) {
        if($line =~ /HTML_DIRECTORY=(\S+)/) {
            $html_dir = $1;
            last;
        }
    }
    
    if(!$html_dir) {
        print "Cannot determine HTML directory, no archive html page will be created.\n";
    }
    else {
        print "Found the html directory ($html_dir) - generating an archive html page.\n";
        if(open(HTML, ">", "$html_dir/old.html")) {
            print HTML "<html><head><title>Old RSV html results</title></head><body>\n";
            print HTML "<p><a href='index.html'>Current results</a>\n";
            foreach my $file (`ls -1 $html_dir/*/*.[0-9].html`) {
                chomp($file);
                if($file =~ m|/([^/]+)/([^/]+)\s*$|) {
                    my ($host, $file) = ($1, $2);
                    print HTML "<p>$host - <a href='$host/$file'>$file</a>\n";
                }
            }
            print HTML "</body></html>\n";
            close(HTML);
        }
    }
}


# Clear the index.html page - we don't want to rotate this one because the links will be invalid, but
# we'll keep around one copy for troubleshooting purposes
if($html_dir) {
    system("mv $html_dir/index.html $html_dir/index.html.old");
}

# "Reset" the conf file by copying in the template that has no logs to rotate
# This is done to prevent junk from accumulating forever in the conf file.
# We delete it here, because it gets re-created by html-consumer
system("rm $conf_file");


