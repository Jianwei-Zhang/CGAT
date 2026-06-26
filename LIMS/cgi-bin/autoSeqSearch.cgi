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
my $assemblyId =  param("assemblyId") || '';
my $extra =  param("extra") || 0;
my @results;
print header('application/json');

if($assemblyId)
{

	if($extra)
	{
		my $asbGenome = $dbh->prepare("SELECT * FROM matrix,link WHERE link.type LIKE 'asbGenome' AND matrix.id = link.child AND link.parent = $assemblyId");
		$asbGenome->execute();
		if ($asbGenome->rows > 0)
		{
			while (my @asbGenome=$asbGenome->fetchrow_array())
			{
				my $sequence=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = $asbGenome[0] AND name LIKE '%$keyword%' LIMIT 20");
				$sequence->execute();
				while (my @sequence = $sequence->fetchrow_array())
				{
					my %hash;
					$hash{'id'} = $sequence[0];
					$hash{'label'} = "$asbGenome[2]:$sequence[2]($sequence[0])";
					$hash{'value'} = $sequence[2];
					push @results, \%hash;
				}
			}
		}
		my $assembly=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$assembly->execute($assemblyId);
		my @assembly = $assembly->fetchrow_array();
		my $target=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$target->execute($assembly[4]);
		my @target = $target->fetchrow_array();
		if($target[1] eq 'genome')
		{
			my $sequence=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = $target[0] AND name LIKE '%$keyword%' LIMIT 20");
			$sequence->execute();
			while (my @sequence = $sequence->fetchrow_array())
			{
				my %hash;
				$hash{'id'} = $sequence[0];
				$hash{'label'} = "*$target[2]:$sequence[2]($sequence[0])";
				$hash{'value'} = $sequence[2];
				push @results, \%hash;
			}
		}
	}
	else
	{
		my $sequence=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblySeq' AND o = $assemblyId AND name LIKE '%$keyword%' LIMIT 20");
		$sequence->execute();
		while (my @sequence = $sequence->fetchrow_array())
		{
			my %hash;
			$hash{'id'} = $sequence[5];
			$hash{'label'} = "$sequence[2]($sequence[5])";
			$hash{'value'} = $sequence[2];
			push @results, \%hash;
		}
	}
}
else
{
	my $sequence=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND name LIKE '%$keyword%' LIMIT 20");
	$sequence->execute();
	while (my @sequence = $sequence->fetchrow_array())
	{
		my %hash;
		$hash{'id'} = $sequence[0];
		$hash{'label'} = "$sequence[2]($sequence[0])";
		$hash{'value'} = $sequence[2];
		push @results, \%hash;
	}
}
my $json = JSON::XS->new->allow_nonref;
my $json_text = $json->encode(\@results);
print $json_text;
