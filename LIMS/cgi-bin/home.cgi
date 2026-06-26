#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
my $commoncfg = readConfig("main.conf");
print header(-cookie=>cookie(-name=>'menu',-value=>0));

open (HOME, "$commoncfg->{HTMLDIR}/home.html") or die "can't open HOME: $!";
while (<HOME>)
{
	print $_;
}
close (HOME);

