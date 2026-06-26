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

my $genebankId = param ('genebankId') || '';
my $genebankName = param ('name') || '';
$genebankName =~ s/[^a-zA-Z0-9]//g; #remove non-word characters
my $genebankRearrayingSource = param('rearrayingSource') || '';
my $genebankProjectId = param('projectId') || '';
my $genebankIsSequencing = param('isSequencing') || 0;

my $genebankDetails;
$genebankDetails->{'type'} = param('type') || '';
$genebankDetails->{'nickname'} = param('nickname') || '';
$genebankDetails->{'isExternal'} = param('isExternal') || 0;
$genebankDetails->{'nofFilters'} = param('nofFilters') || 0;
$genebankDetails->{'genomeEquivalents'} = param('genomeEquivalents') || '';
$genebankDetails->{'genomeSize'} = param('genomeSize') || '';
$genebankDetails->{'averageInsertSize'} = param('averageInsertSize') || '';
$genebankDetails->{'standardDeviation'} = param('standardDeviation') || '';
$genebankDetails->{'format'} = param('format') || 384;
$genebankDetails->{'status'} = param('status') || 'active';
$genebankDetails->{'distributorInstitute'} = param('distributorInstitute') || '';
$genebankDetails->{'host'} = param('host') || '';
$genebankDetails->{'enzymeFivePrime'} = param('enzymeFivePrime') || '';
$genebankDetails->{'enzymeThreePrime'} = param('enzymeThreePrime') || '';
$genebankDetails->{'endSeqFivePrime'} = param('endSeqFivePrime') || '';
$genebankDetails->{'endSeqThreePrime'} = param('endSeqThreePrime') || '';
$genebankDetails->{'cloningFivePrime'} = param('cloningFivePrime') || '';
$genebankDetails->{'cloningThreePrime'} = param('cloningThreePrime') || '';
$genebankDetails->{'antibiotic'} = param('antibiotic') || '';
$genebankDetails->{'genus'} = param('genus') || '';
$genebankDetails->{'species'} = param('species') || '';
$genebankDetails->{'subspecies'} = param('subspecies') || '';
$genebankDetails->{'commonName'} = param('commonName') || '';
$genebankDetails->{'genomeType'} = param('genomeType') || '';
$genebankDetails->{'tissue'} = param('tissue') || '';
$genebankDetails->{'treatment'} = param('treatment') || '';
$genebankDetails->{'developmentStage'} = param('developmentStage') || '';
$genebankDetails->{'cultivar'} = param('cultivar') || '';
$genebankDetails->{'refToPublication'} = param('refToPublication') || '';
$genebankDetails->{'isPublic'} = param('isPublic') || 0;
$genebankDetails->{'isFinished'} = param('isFinished') || 0;
$genebankDetails->{'isGenebankForSale'} = param('isGenebankForSale') || 0;
$genebankDetails->{'isFilterForSale'} = param('isFilterForSale') || 0;
$genebankDetails->{'isCloneForSale'} = param('isCloneForSale') || 0;
$genebankDetails->{'providedBy'} = param('providedBy') || '';
$genebankDetails->{'organization'} = param('organization') || '';
$genebankDetails->{'comments'} = param('comments') || '';
$genebankDetails->{'orderPageComments'} = param('orderPageComments') || '';
$genebankDetails->{'dateGenebankWasMade'} = param('dateGenebankWasMade') || '0000-00-00';
$genebankDetails->{'dateGenebankWasAutoclaved'} = param('dateGenebankWasAutoclaved') || '0000-00-00';
$genebankDetails->{'archiveStartDate'} = param('archiveStartDate') || '0000-00-00';
$genebankDetails->{'archiveEndDate'} = param('archiveEndDate') || '0000-00-00';

my $json = JSON::XS->new->allow_nonref;
$genebankDetails = $json->encode($genebankDetails);

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


if($genebankName)
{
	if($genebankId)
	{
		if($genebankRearrayingSource)
		{
			my $checkSource = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genebank' AND name LIKE ?");
			$checkSource->execute($genebankRearrayingSource);
			if($checkSource->rows < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Rearraying Source!");
</script>	
END
				exit;
			}
			my @checkSource=$checkSource->fetchrow_array();
			if($checkSource[3] < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Rearraying Source!");
</script>	
END
				exit;
			}
			$genebankRearrayingSource = $checkSource[0];
		}
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($genebankId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'genebank'})
		{
			if ($genebankName ne $checkCreator[2])
			{
				my $checkGenebankName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genebank' AND name LIKE ?");
				$checkGenebankName->execute($genebankName);
				if($checkGenebankName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Genebank name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}

			my $updateGenebank=$dbh->prepare("UPDATE matrix SET
				name = ?,
				x = ?,
				y = ?,
				z = ?,
				barcode = ?,
				note = ?,
				creator = ?,
				creationDate = NOW()
				WHERE id = ?");
			$updateGenebank->execute(
				$genebankName,
				0,
				$genebankRearrayingSource,
				$genebankProjectId,
				$genebankIsSequencing,
				$genebankDetails,
				$userName,
				$genebankId);
			print header;
			print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
</script>	
END
		}
		else
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Not a valid user!");
</script>	
END
		}
	}
	else
	{
		if($genebankRearrayingSource)
		{
			my $checkSource = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genebank' AND name LIKE ?");
			$checkSource->execute($genebankRearrayingSource);
			if($checkSource->rows < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Rearraying Source!");
</script>	
END
				exit;
			}
			my @checkSource=$checkSource->fetchrow_array();
			if($checkSource[3] < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Rearraying Source!");
</script>	
END
				exit;
			}
			$genebankRearrayingSource = $checkSource[0];
		}
		my $checkGenebankName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'genebank' AND name LIKE ?");
		$checkGenebankName->execute($genebankName);
		if($checkGenebankName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Genebank name exists. Please enter another one!");
</script>	
END
			exit;
		}

		my $insertGenebank=$dbh->prepare("INSERT INTO matrix VALUES ('', 'genebank', ?, 0, ?, ?, ?, ?, ?, ?, NOW())");
		$insertGenebank->execute(
			$genebankName,
			0,
			$genebankRearrayingSource,
			$genebankProjectId,
			$genebankIsSequencing,
			$genebankDetails,
			$userName);
		$genebankId = $dbh->{mysql_insertid};
		print header(-cookie=>[cookie(-name=>'genebank',-value=>$genebankId),cookie(-name=>'sample',-value=>0)]);
		print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
</script>	
END
	}
}
else
{
	print header;
	print <<END;
<script>
	parent.errorPop("Please give a genebank name!");
</script>	
END
}