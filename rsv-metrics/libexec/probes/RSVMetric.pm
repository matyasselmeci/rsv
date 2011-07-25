#!/usr/bin/env perl

sub print_output_header {
    print "RSV BRIEF RESULTS:\n";
}

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

sub dump_debug {
    if(defined($ENV{OSG_LOCATION})) {
        print STDERR "$ENV{OSG_LOCATION}\n";
    }

    print STDERR `/usr/bin/env`;
    return;
}

1;
