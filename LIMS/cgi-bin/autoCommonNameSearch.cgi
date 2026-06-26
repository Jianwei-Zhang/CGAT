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
my $same;
my $sth=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library'");
$sth->execute();
while (my @sth = $sth->fetchrow_array())
{
	my $libraryDetails = decode_json $sth[8];
	if ($libraryDetails->{'commonName'})
	{
		if (exists $same->{$libraryDetails->{'commonName'}})
		{
			next;
		}
		else
		{
			if ($libraryDetails->{'commonName'} =~ /$keyword/i)
			{
				my %hash;
				$hash{'id'} = $libraryDetails->{'commonName'};
				$hash{'label'} = $libraryDetails->{'commonName'};
				$hash{'value'} = $libraryDetails->{'commonName'};
				push @results, \%hash;
			}
			$same->{$libraryDetails->{'commonName'}} = 1;
		}
	}
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
