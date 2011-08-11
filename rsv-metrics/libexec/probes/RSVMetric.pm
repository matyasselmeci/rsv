#!/usr/bin/env perl

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


# Print debugging information to STDERR
sub dump_debug {
    if(defined($ENV{OSG_LOCATION})) {
        print STDERR "$ENV{OSG_LOCATION}\n";
    }

    print STDERR `/usr/bin/env`;
    return;
}

1;
