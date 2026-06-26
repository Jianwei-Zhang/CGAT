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
my $excluded = param("excluded") || '';
my $forAssembly = param("forAssembly") || '0';
my $asReference = param("asReference") || '0';
my @results;
print header('application/json');

my $genome=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genome' AND name LIKE '%$keyword%' LIMIT 20");
$genome->execute();
while (my @genome = $genome->fetchrow_array())
{
	my %hash;
	next if ($genome[0] eq $excluded);
	if ($forAssembly)
	{
		next if ($genome[4] < 1); #remove not for assembly
	}
	if ($asReference)
	{
		next if ($genome[5] < 1); #remove not for reference
	}
	$hash{'id'} = $genome[0];
	$hash{'label'} = "$genome[2]($genome[0])";
	$hash{'value'} = $genome[2];
	push @results, \%hash;
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
