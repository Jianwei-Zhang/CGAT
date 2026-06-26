#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
my $pid = param('pid') || '';;

my $kill = `kill $pid` if ($pid);
print header;
print $kill;

