#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS; #JSON::XS is recommended to be installed for handling JSON string of big size 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use userCookie;

#my $userCookie = new userCookie;
#my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
#exit if (!$userId);

#my $user = new user;
#my $userDetail = $user->getAllFieldsWithUserId($userId);
#my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $sequence = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence'");
$sequence->execute();
while (my @sequence =  $sequence->fetchrow_array())
{
	print "$sequence[0]\n";
	my $sequenceDetails = decode_json $sequence[8];
}
