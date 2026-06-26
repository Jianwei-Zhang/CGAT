#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS;
use DBI;
use Bio::SeqIO;
use File::Basename;
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

my $genomeId = param ('genomeId') || '';
my @seqIds = param ('seqId');
my $genomeName = param ('name') || '';
my $forAssembly = param ('forAssembly') || '0';
my $asReference = param ('asReference') || '0';
my $libraryId = param ('libraryId') || '0';
my $genomeDescription = param('description') || '';

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

if($genomeId)
{
	my $genome = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$genome->execute($genomeId);
	my @genome=$genome->fetchrow_array();

	unless($genome[9] eq $userName || exists $userPermission->{$userId}->{'genome'})
	{
		print <<END;
<script>
	parent.errorPop("Not a valid user!");
</script>	
END
		exit;
	}

	if(scalar(@seqIds) == $genome[3])
	{
		print <<END;
<script>
	parent.errorPop("You can NOT select all sequences!");
</script>	
END
		exit;
	}
	else
	{
		if(scalar(@seqIds) > 0)
		{
			if($genomeName)
			{
				my $checkGenomeName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genome' AND name LIKE ?");
				$checkGenomeName->execute($genomeName);
				if($checkGenomeName->rows < 1)
				{
					my $insertGenome=$dbh->prepare("INSERT INTO matrix VALUES ('', 'genome', ?, 0, ?, ?, ?, 0, ?, ?, NOW())");
					$insertGenome->execute($genomeName,$forAssembly,$asReference,$libraryId,$genomeDescription,$userName);
					my $splitGenomeId = $dbh->{mysql_insertid};
					foreach (@seqIds)
					{
						my $updateSequence = $dbh->do("UPDATE matrix SET x = $splitGenomeId WHERE id = $_");
						my $updateSequencePiece = $dbh->do("UPDATE matrix SET x = $splitGenomeId WHERE o = 97 AND barcode = $_");
					}

					my $seqNumber = 0;
					my $countGenomeSequence = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = $genomeId");
					$countGenomeSequence->execute();
					$seqNumber = $countGenomeSequence->rows;
					my $updateGenome = $dbh->do("UPDATE matrix SET o = $seqNumber, barcode = 1, creationDate = NOW() WHERE id = $genomeId");

					my $countSplitGenomeSequence = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = $splitGenomeId");
					$countSplitGenomeSequence->execute();
					$seqNumber = $countSplitGenomeSequence->rows;
					my $updateGenome = $dbh->do("UPDATE matrix SET o = $seqNumber, barcode = 1, creationDate = NOW() WHERE id = $splitGenomeId");
					print <<END;
<script>
	parent.closeDialog();
	parent.refresh("general");
</script>	
END
				}
				else
				{
					print <<END;
<script>
	parent.errorPop("The given genome name is existing!");
</script>	
END
					exit;
				}
			}
			else
			{
				print <<END;
<script>
	parent.errorPop("Please give a new genome name!");
</script>	
END
			exit;
			}
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("You should select at least ONE sequence!");
</script>	
END
			exit;
		}
	}
}
else
{
	print <<END;
<script>
	parent.errorPop("Please give a source genome!");
</script>	
END
}


