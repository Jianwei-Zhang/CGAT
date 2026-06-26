#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS; # imports encode_json, decode_json, to_json and from_json.
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $keyword = param("term");
my @results;
print header('application/json');
my $sth=$dbh->prepare("SELECT name FROM matrix WHERE container LIKE 'vector' AND name LIKE '%$keyword%' GROUP BY name");
$sth->execute();
while (my @sth = $sth->fetchrow_array())
{
	my %hash;
	$hash{'id'} = $sth[0];
	$hash{'label'} = $sth[0];
	$hash{'value'} = $sth[0];
	push @results, \%hash;
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
