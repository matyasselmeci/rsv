#!/usr/bin/env perl

# This wrapper script is in place to setup the environment for the  probes
# before they run.  The first argument is the path to the probe to run.
#  The remaining arguments are passed through to the script.

my $script = shift;

foreach my $line (`. $ENV{VDT_LOCATION}/setup.sh; env`) {
    chomp($line);
    next unless($line =~ /^([^=]+)=(.+)$/);
    my ($name, $val) = ($1, $2);

    # Do we want to worry about overriding an environment value?
    $ENV{$name} = $val;
}

exec("$script @ARGV");
