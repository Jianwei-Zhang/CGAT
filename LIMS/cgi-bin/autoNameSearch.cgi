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
my $sth=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library' AND name LIKE '%$keyword%'");
$sth->execute();
while (my @sth = $sth->fetchrow_array())
{
	my $libraryDetails = decode_json $sth[8];
	my %hash;
	$hash{'id'} = $sth[2];
	$hash{'label'} = $sth[2];
	$hash{'value'} = $sth[2];
	$hash{'genomeEquivalents'} = $libraryDetails->{'genomeEquivalents'};
	$hash{'genomeSize'} = $libraryDetails->{'genomeSize'};
	$hash{'averageInsertSize'} = $libraryDetails->{'averageInsertSize'};
	$hash{'standardDeviation'} = $libraryDetails->{'standardDeviation'};
	$hash{'distributorInstitute'} = $libraryDetails->{'distributorInstitute'};
	if($sth[4])
	{
		my $vector=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$vector->execute($sth[4]);
		my @vector = $vector->fetchrow_array();
		$hash{'vector'} = $vector[2];
	}
	else
	{
		$hash{'vector'} = $sth[4];
	}
	$hash{'host'} = $libraryDetails->{'host'};
	$hash{'enzymeFivePrime'} = $libraryDetails->{'enzymeFivePrime'};
	$hash{'enzymeThreePrime'} = $libraryDetails->{'enzymeThreePrime'};
	$hash{'endSeqFivePrime'} = $libraryDetails->{'endSeqFivePrime'};
	$hash{'endSeqThreePrime'} = $libraryDetails->{'endSeqThreePrime'};
	$hash{'cloningFivePrime'} = $libraryDetails->{'cloningFivePrime'};
	$hash{'cloningThreePrime'} = $libraryDetails->{'cloningThreePrime'};
	$hash{'antibiotic'} = $libraryDetails->{'antibiotic'};
	$hash{'genus'} = $libraryDetails->{'genus'};
	$hash{'species'} = $libraryDetails->{'species'};
	$hash{'subspecies'} = $libraryDetails->{'subspecies'};
	$hash{'commonName'} = $libraryDetails->{'commonName'};
	$hash{'genomeType'} = $libraryDetails->{'genomeType'};
	$hash{'tissue'} = $libraryDetails->{'tissue'};
	$hash{'treatment'} = $libraryDetails->{'treatment'};
	$hash{'developmentStage'} = $libraryDetails->{'developmentStage'};
	$hash{'cultivar'} = $libraryDetails->{'cultivar'};
	$hash{'refToPublication'} = $libraryDetails->{'refToPublication'};
	$hash{'providedBy'} = $libraryDetails->{'providedBy'};
	$hash{'organization'} = $libraryDetails->{'organization'};
	push @results, \%hash;
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
