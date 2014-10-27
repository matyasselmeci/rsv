#!/usr/bin/env perl

use strict;
use warnings;
use Getopt::Long;


# Process the command line.  There are two standard options that all metrics
# must accept, metric and host.
sub process_command_line {
    my %extra_opts = @_;

    my %options = ();
    my $ret = GetOptions(\%options,
                         "m=s",
                         "u=s",
                         "h",
                         "help",
                         keys(%extra_opts));

    if(!$ret) {
        usage(%extra_opts);
    }
    
    if(defined($options{help}) or defined($options{h})) {
        usage(%extra_opts);
    }

    if(!defined($options{m})) {
        print STDERR "Error: missing required argument -m\n";
        usage(%extra_opts);
    }

    if(!defined($options{u})) {
        print STDERR "Error: missing required argument -u\n";
        usage(%extra_opts);
    }

    return %options;
}


sub usage {
    my %extra_opts = @_;

    print "$0 options:\n";
    print "\t-m=s \t<Required: the metric to run>\n";
    print "\t-u=s \t<Required: the host to monitor>\n";

    foreach my $opt (keys(%extra_opts)) {
        # Try to determine if the arguments should have one dash or two.  It's not
        # a huge deal if we get it wrong - it's just informational.
        my $prefix = "-";
        if($opt =~ /^.[^=]+=?/) {
            $prefix = "--";
        }
        print "\t$prefix$opt \t<$extra_opts{$opt}>\n";
    }

    print "\t-h --help\n";

    exit 1;
}


# Print the required header at the top of an RSV record
sub print_output_header {
    print "RSV BRIEF RESULTS:\n";
}

# Given a list of binaries, exit with a CRITICAL status if
# any of them are not available in the PATH
sub find_binaries {
    my @binaries = @_;

    foreach my $binary (@binaries) {
        if(not which($binary)) {
            print "CRITICAL\n";
            print "$binary is not in PATH\n";
            dump_debug();
            exit 0;
        }
    }
}


# Emulate which command in pure Perl
sub which {
    my ($exe) = @_;

    foreach my $dir (split(/:/, $ENV{PATH})) {
        if (-x "$dir/$exe") {
            $dir =~ s|/+$||;  # Trim trailing slash on dir
	    return "$dir/$exe";
        }
    }
    return "";
}

# quote shell argument
sub shellquote_arg {
  my $arg = shift;
  if ($arg =~ m{[^-/.\w]} || $arg eq '') {
    $arg =~ s/'/'\\''/g;
    $arg = "'$arg'";
  }
  $arg
}

# quote list of shell arguments
sub shellquote {
  my @args = map shellquote_arg($_), @_;
  wantarray ? @args : join(' ', @args);
}

# Print debugging information to STDERR
sub dump_debug {
    if(defined($ENV{OSG_LOCATION})) {
        print STDERR "$ENV{OSG_LOCATION}\n";
    }

    print STDERR `/usr/bin/env`;
    return;
}

1;
