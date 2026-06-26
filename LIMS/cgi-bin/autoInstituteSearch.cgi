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
	if ($libraryDetails->{'distributorInstitute'})
	{
		if (exists $same->{$libraryDetails->{'distributorInstitute'}})
		{
			next;
		}
		else
		{
			if ($libraryDetails->{'distributorInstitute'} =~ /$keyword/i)
			{
				my %hash;
				$hash{'id'} = $libraryDetails->{'distributorInstitute'};
				$hash{'label'} = $libraryDetails->{'distributorInstitute'};
				$hash{'value'} = $libraryDetails->{'distributorInstitute'};
				push @results, \%hash;
			}
			$same->{$libraryDetails->{'distributorInstitute'}} = 1;
		}
	}
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
