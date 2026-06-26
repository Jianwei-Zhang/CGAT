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

my $libraryId = param ('libraryId') || '';
my $libraryName = param ('name') || '';
$libraryName =~ s/[^a-zA-Z0-9]//g; #remove non-word characters
my $libraryVector = param('vector') || '';
my $libraryRearrayingSource = param('rearrayingSource') || '';
my $libraryProjectId = param('projectId') || '';
my $libraryIsSequencing = param('isSequencing') || 0;

my $libraryDetails;
$libraryDetails->{'type'} = param('type') || '';
$libraryDetails->{'nickname'} = param('nickname') || '';
$libraryDetails->{'isExternal'} = param('isExternal') || 0;
$libraryDetails->{'nofFilters'} = param('nofFilters') || 0;
$libraryDetails->{'genomeEquivalents'} = param('genomeEquivalents') || '';
$libraryDetails->{'genomeSize'} = param('genomeSize') || '';
$libraryDetails->{'averageInsertSize'} = param('averageInsertSize') || '';
$libraryDetails->{'standardDeviation'} = param('standardDeviation') || '';
$libraryDetails->{'format'} = param('format') || 384;
$libraryDetails->{'status'} = param('status') || 'active';
$libraryDetails->{'distributorInstitute'} = param('distributorInstitute') || '';
$libraryDetails->{'host'} = param('host') || '';
$libraryDetails->{'enzymeFivePrime'} = param('enzymeFivePrime') || '';
$libraryDetails->{'enzymeThreePrime'} = param('enzymeThreePrime') || '';
$libraryDetails->{'endSeqFivePrime'} = param('endSeqFivePrime') || '';
$libraryDetails->{'endSeqThreePrime'} = param('endSeqThreePrime') || '';
$libraryDetails->{'cloningFivePrime'} = param('cloningFivePrime') || '';
$libraryDetails->{'cloningThreePrime'} = param('cloningThreePrime') || '';
$libraryDetails->{'antibiotic'} = param('antibiotic') || '';
$libraryDetails->{'genus'} = param('genus') || '';
$libraryDetails->{'species'} = param('species') || '';
$libraryDetails->{'subspecies'} = param('subspecies') || '';
$libraryDetails->{'commonName'} = param('commonName') || '';
$libraryDetails->{'genomeType'} = param('genomeType') || '';
$libraryDetails->{'tissue'} = param('tissue') || '';
$libraryDetails->{'treatment'} = param('treatment') || '';
$libraryDetails->{'developmentStage'} = param('developmentStage') || '';
$libraryDetails->{'cultivar'} = param('cultivar') || '';
$libraryDetails->{'refToPublication'} = param('refToPublication') || '';
$libraryDetails->{'isPublic'} = param('isPublic') || 0;
$libraryDetails->{'isFinished'} = param('isFinished') || 0;
$libraryDetails->{'isLibraryForSale'} = param('isLibraryForSale') || 0;
$libraryDetails->{'isFilterForSale'} = param('isFilterForSale') || 0;
$libraryDetails->{'isCloneForSale'} = param('isCloneForSale') || 0;
$libraryDetails->{'providedBy'} = param('providedBy') || '';
$libraryDetails->{'organization'} = param('organization') || '';
$libraryDetails->{'comments'} = param('comments') || '';
$libraryDetails->{'orderPageComments'} = param('orderPageComments') || '';
$libraryDetails->{'dateLibraryWasMade'} = param('dateLibraryWasMade') || '0000-00-00';
$libraryDetails->{'dateLibraryWasAutoclaved'} = param('dateLibraryWasAutoclaved') || '0000-00-00';
$libraryDetails->{'archiveStartDate'} = param('archiveStartDate') || '0000-00-00';
$libraryDetails->{'archiveEndDate'} = param('archiveEndDate') || '0000-00-00';

my $json = JSON::XS->new->allow_nonref;
$libraryDetails = $json->encode($libraryDetails);

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


if($libraryName)
{
	if($libraryId)
	{
		if($libraryRearrayingSource)
		{
			my $checkSource = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library' AND name LIKE ?");
			$checkSource->execute($libraryRearrayingSource);
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
			$libraryRearrayingSource = $checkSource[0];
		}
		if($libraryVector)
		{
			my $checkVector = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'vector' AND name LIKE ?");
			$checkVector->execute($libraryVector);
			if($checkVector->rows < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Vector!");
</script>	
END
				exit;
			}
			my @checkVector=$checkVector->fetchrow_array();
			$libraryVector = $checkVector[0];
		}
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($libraryId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'library'})
		{
			if ($libraryName ne $checkCreator[2])
			{
				my $checkLibraryName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library' AND name LIKE ?");
				$checkLibraryName->execute($libraryName);
				if($checkLibraryName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Library name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}

			my $updateLibrary=$dbh->prepare("UPDATE matrix SET
				name = ?,
				x = ?,
				y = ?,
				z = ?,
				barcode = ?,
				note = ?,
				creator = ?,
				creationDate = NOW()
				WHERE id = ?");
			$updateLibrary->execute(
				$libraryName,
				$libraryVector,
				$libraryRearrayingSource,
				$libraryProjectId,
				$libraryIsSequencing,
				$libraryDetails,
				$userName,
				$libraryId);
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
		if($libraryRearrayingSource)
		{
			my $checkSource = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library' AND name LIKE ?");
			$checkSource->execute($libraryRearrayingSource);
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
			$libraryRearrayingSource = $checkSource[0];
		}
		if($libraryVector)
		{
			my $checkVector = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'vector' AND name LIKE ?");
			$checkVector->execute($libraryVector);
			if($checkVector->rows < 1)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("Please give a valid Vector!");
</script>	
END
				exit;
			}
			my @checkVector=$checkVector->fetchrow_array();
			$libraryVector = $checkVector[0];
		}
		
		my $checkLibraryName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'library' AND name LIKE ?");
		$checkLibraryName->execute($libraryName);
		if($checkLibraryName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Library name exists. Please enter another one!");
</script>	
END
			exit;
		}

		my $insertLibrary=$dbh->prepare("INSERT INTO matrix VALUES ('', 'library', ?, 0, ?, ?, ?, ?, ?, ?, NOW())");
		$insertLibrary->execute(
			$libraryName,
			$libraryVector,
			$libraryRearrayingSource,
			$libraryProjectId,
			$libraryIsSequencing,
			$libraryDetails,
			$userName);
		$libraryId = $dbh->{mysql_insertid};
		print header(-cookie=>[cookie(-name=>'library',-value=>$libraryId),cookie(-name=>'sample',-value=>0)]);
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
	parent.errorPop("Please give a library name!");
</script>	
END
}