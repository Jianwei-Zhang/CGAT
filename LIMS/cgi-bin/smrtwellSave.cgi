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

my $smrtwellId = param ('smrtwellId') || '';
my $smrtwellName = param ('name') || '';
my $paclibId = param ('paclibId') || '';
my $cellNumber = param ('cellNumber') || '1';
my $movieLength = param ('movieLength') || '0';
my $condition = param ('condition') || '0';
my $smrtrunId = param ('smrtrunId') || '';

my $json = JSON::XS->new->allow_nonref;
my $smrtwellDetails;
$smrtwellDetails->{'loadingName'} = param ('loadingName') || '';
$smrtwellDetails->{'comments'} = param ('comments') || '';
$smrtwellDetails->{'concentration'} = param ('concentration') || '0';
$smrtwellDetails->{'polRatio'} = param ('polRatio') || '';
$smrtwellDetails->{'chemistry'} = param ('chemistry') || 'P5';
$smrtwellDetails->{'customizedMovieLength'} = param ('customizedMovieLength') || '';
#$smrtwellDetails->{'customizedMovieLength'} = '' if($movieLength);
$smrtwellDetails->{'customizedCondition'} = param ('customizedCondition') || '';
#$smrtwellDetails->{'customizedCondition'} = '' if($condition);

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

unless($smrtwellDetails->{'loadingName'})
{
	my $paclib = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$paclib->execute($paclibId);
	my @paclib=$paclib->fetchrow_array();
	my $paclibToSample=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$paclibToSample->execute($paclib[6]);
	my @paclibToSample = $paclibToSample->fetchrow_array();
	if($paclibToSample[0])
	{
		my $sampleToService=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$sampleToService->execute($paclibToSample[6]);
		my @sampleToService = $sampleToService->fetchrow_array();
		if($sampleToService[0])
		{
			my $serviceToProject=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$serviceToProject->execute($sampleToService[6]);
			my @serviceToProject = $serviceToProject->fetchrow_array();
			$smrtwellDetails->{'loadingName'} = "$serviceToProject[2]$sampleToService[2]$paclibToSample[2]$paclib[2]";
		}
	}
}


if($smrtwellName && $paclibId)
{
	unless ($smrtrunId)
	{
		my $smrtrunName = param ('smrtrunName') || '';
		$smrtrunName =~ s/\s//g;
		unless($smrtrunName)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Please enter SMRT Run Name!");
</script>	
END
			exit;
		}

		my $smrtcell = param ('smrtcell') || '8';
		if($smrtcell < $cellNumber)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("The Cell number ($cellNumber) you entered is greater than the SMRTCell number ($smrtcell)!");
</script>	
END
			exit;
		}

		my $smrtrunDetails;
		$smrtrunDetails->{'comments'} = param ('smrtrunComments') || '';
		$smrtrunDetails = $json->encode($smrtrunDetails);

		my $checkRunName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'smrtrun' AND name LIKE ?");
		$checkRunName->execute($smrtrunName);
		if($checkRunName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Run name exists. Please enter another one!");
</script>	
END
			exit;
		}
		my $insertSmrtrun=$dbh->prepare("INSERT INTO matrix VALUES ('', 'smrtrun', ?, ?, 0, 0, 0, 0, ?, ?, NOW())");
		$insertSmrtrun->execute(
			$smrtrunName,
			$smrtcell,
			$smrtrunDetails,
			$userName);
		$smrtrunId = $dbh->{mysql_insertid};

		my $config = new config;
		my $lastSmrtrun = $config->getFieldValueWithFieldName("smrtrun");
		$lastSmrtrun = $lastSmrtrun + 1;
		$config->updateFieldValueWithFieldName("smrtrun",$lastSmrtrun);
	}

	if($smrtwellId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($smrtwellId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'smrtwell'})
		{
			if($checkCreator[3] ne $paclibId)
			{
				my $paclib = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
				$paclib->execute($paclibId);
				my @paclib=$paclib->fetchrow_array();
				my $paclibToSample=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
				$paclibToSample->execute($paclib[6]);
				my @paclibToSample = $paclibToSample->fetchrow_array();
				if($paclibToSample[0])
				{
					my $sampleToService=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
					$sampleToService->execute($paclibToSample[6]);
					my @sampleToService = $sampleToService->fetchrow_array();
					if($sampleToService[0])
					{
						my $serviceToProject=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
						$serviceToProject->execute($sampleToService[6]);
						my @serviceToProject = $serviceToProject->fetchrow_array();
						$smrtwellDetails->{'loadingName'} = "$serviceToProject[2]$sampleToService[2]$paclibToSample[2]$paclib[2]";
					}
				}
			}

			if ($smrtwellName ne $checkCreator[2])
			{
				my $checkSmrtwellName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'smrtwell' AND name LIKE ? AND z = ?");
				$checkSmrtwellName->execute($smrtwellName,$smrtrunId);
				if($checkSmrtwellName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Well has been occupied. Please select another one!");
</script>	
END
					exit;
				}
			}

			my $smrtrun=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$smrtrun->execute($smrtrunId);
			my @smrtrun = $smrtrun->fetchrow_array();
			my $totalCellNumber = 0;
			my $checkCellNumber = $dbh->prepare("SELECT SUM(x) FROM matrix WHERE container LIKE 'smrtwell' AND z = ? AND id != ?");
			$checkCellNumber->execute($smrtrunId,$smrtwellId);
			my @checkCellNumber=$checkCellNumber->fetchrow_array();
			$totalCellNumber = $checkCellNumber[0] if($checkCellNumber[0]);
			my $availableCell = $smrtrun[3] - $totalCellNumber;
			if($availableCell < $cellNumber)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("No enough space ($availableCell available) for $cellNumber cells!");
</script>	
END
				exit;
			}

			$smrtwellDetails = $json->encode($smrtwellDetails);
			my $updateSmrtwell=$dbh->prepare("UPDATE matrix SET
				name = ?,
				o = ?,
				x = ?,
				y = ?,
				z = ?,
				barcode = ?,
				note = ?,
				creator = ?,
				creationDate = NOW()
				WHERE id = ?");
			$updateSmrtwell->execute(
				$smrtwellName,
				$paclibId,
				$cellNumber,
				$movieLength,
				$smrtrunId,
				$condition,
				$smrtwellDetails,
				$userName,
				$smrtwellId);
			print header;
			print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
	parent.refresh("general");
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
		my $checkSmrtwellName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'smrtwell' AND name LIKE ? AND z = ?");
		$checkSmrtwellName->execute($smrtwellName,$smrtrunId);
		if($checkSmrtwellName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Well has been occupied. Please select another one!");
</script>	
END
			exit;
		}

		my $smrtrun=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$smrtrun->execute($smrtrunId);
		my @smrtrun = $smrtrun->fetchrow_array();
		my $totalCellNumber = 0;
		my $checkCellNumber = $dbh->prepare("SELECT SUM(x) FROM matrix WHERE container LIKE 'smrtwell' AND z = ?");
		$checkCellNumber->execute($smrtrunId);
		my @checkCellNumber=$checkCellNumber->fetchrow_array();
		$totalCellNumber = $checkCellNumber[0] if($checkCellNumber[0]);
		my $availableCell = $smrtrun[3] - $totalCellNumber;
		if($availableCell < $cellNumber)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("No enough space ($availableCell available) for $cellNumber cells!");
</script>	
END
			exit;
		}

		$smrtwellDetails = $json->encode($smrtwellDetails);
		my $insertSmrtwell=$dbh->prepare("INSERT INTO matrix VALUES ('', 'smrtwell', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertSmrtwell->execute(
			$smrtwellName,
			$paclibId,
			$cellNumber,
			$movieLength,
			$smrtrunId,
			$condition,
			$smrtwellDetails,
			$userName);
		$smrtwellId = $dbh->{mysql_insertid};
		print header(-cookie=>cookie(-name=>'smrtwell',-value=>$smrtwellId));
		print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
	parent.refresh("general");
</script>	
END
	}
}
else
{
	print header;
	print <<END;
<script>
	parent.errorPop("Please select a well!");
</script>	
END
}