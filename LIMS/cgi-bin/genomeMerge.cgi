#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS;
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use config;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my @genomes = param ('genomes');
my $mergedGenomeId = param ('mergedGenomeId') || '';

my $config = new config;
my $userPermission;
my $userInGroup=$dbh->prepare("SELECT * FROM link WHERE type LIKE 'group' AND child = ?");
$userInGroup->execute($userId);
while (my @userInGroup = $userInGroup->fetchrow_array())
{
	my $group = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$group->execute($userInGroup[0]);
	my @group=$group->fetchrow_array();
	my $groupDetails = decode_json $group[8];
	$groupDetails->{'permission'} = '' unless (exists $groupDetails->{'permission'});
	for(split (",",$groupDetails->{'permission'}))
	{
		my $permission = $config->getFieldName($_);
		$userPermission->{$userId}->{$permission} = 1;		
	}
}

print header;

for(@genomes)
{
	my $genomeId = $_;
	unless($genomeId == $mergedGenomeId)
	{
		my $genome = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$genome->execute($genomeId);
		my @genome=$genome->fetchrow_array();
		if($genome[9] eq $userName || exists $userPermission->{$userId}->{'genome'})
		{
			my $updateSequence=$dbh->do("UPDATE matrix SET
				x = $mergedGenomeId
				WHERE container LIKE 'sequence' AND x = $genomeId");
			my $updateAGP=$dbh->do("UPDATE matrix SET
				x = $mergedGenomeId
				WHERE container LIKE 'agp' AND x = $genomeId");
			my $updateAssemblySource=$dbh->do("UPDATE matrix SET
				x = $mergedGenomeId
				WHERE container LIKE 'assembly' AND x = $genomeId");
			my $updateAssemblyRef=$dbh->do("UPDATE matrix SET
				y = $mergedGenomeId
				WHERE container LIKE 'assembly' AND y = $genomeId");

			my $updateAsbProjectLink=$dbh->do("UPDATE link SET
				child = $mergedGenomeId
				WHERE type LIKE 'asbProject' AND child = $genomeId");
			#remove duplicated asbProject
			my $asbProject;
			my $allAsbProjects=$dbh->prepare("SELECT * FROM link WHERE type LIKE 'asbProject'");
			$allAsbProjects->execute();
			while (my @allAsbProjects = $allAsbProjects->fetchrow_array())
			{
				$asbProject->{$allAsbProjects[0]}->{$allAsbProjects[1]} = 1;		
			}
			foreach my $asbProjectId (keys %$asbProject)
			{
				my $deleteAsbProjectLink = $dbh->do("DELETE FROM link WHERE parent = $asbProjectId AND type LIKE 'asbProject'");
				foreach (keys %{$asbProject->{$asbProjectId}})
				{
					my $insertLink = $dbh->do("INSERT INTO link VALUES ($asbProjectId,$_,'asbProject')");
				}
			}

			my $updateAsbGenomeLink=$dbh->do("UPDATE link SET
				child = $mergedGenomeId
				WHERE type LIKE 'asbGenome' AND child = $genomeId");
			#remove duplicated asbGenome
			my $asbGenome;
			my $allAsbGenomes=$dbh->prepare("SELECT * FROM link WHERE type LIKE 'asbGenome'");
			$allAsbGenomes->execute();
			while (my @allAsbGenomes = $allAsbGenomes->fetchrow_array())
			{
				$asbGenome->{$allAsbGenomes[0]}->{$allAsbGenomes[1]} = 1;		
			}
			foreach my $assemblyId (keys %$asbGenome)
			{
				my $deleteAsbGenomeLink = $dbh->do("DELETE FROM link WHERE parent = $assemblyId AND type LIKE 'asbGenome'");
				foreach (keys %{$asbGenome->{$assemblyId}})
				{
					my $insertLink = $dbh->do("INSERT INTO link VALUES ($assemblyId,$_,'asbGenome')");
				}
			}
 			my $deleteGenome=$dbh->do("DELETE FROM matrix WHERE id = $genomeId");

			my $seqNumber = 0;
			my $countGenomeSequence = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = $mergedGenomeId");
			$countGenomeSequence->execute();
			$seqNumber = $countGenomeSequence->rows;
			my $updateGenome = $dbh->prepare("UPDATE matrix SET o = $seqNumber, barcode = 1, note = CONCAT(note, ?),creationDate = NOW() WHERE id = $mergedGenomeId");
			$updateGenome->execute($genome[8]);
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("Not a valid user!");
</script>	
END
			exit;
		}
	}
}
print <<END;
<script>
	parent.closeDialog();
	parent.refresh("general");
</script>	
END
