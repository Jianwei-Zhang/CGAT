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

my $paclibId = param ('paclibId') || '';
my $sampleId = param ('sampleId') || '';
my $paclibName = param ('name') || '';
my $status = param ('status') || 0;

my $paclibDetails;
$paclibDetails->{'libraryDate'} = param('libraryDate') || '';
$paclibDetails->{'shearingInput'} = param('shearingInput') || '0';
$paclibDetails->{'shearingRpm'} = param('shearingRpm') || '0';
$paclibDetails->{'shearingOutput'} = param('shearingOutput') || '0';
$paclibDetails->{'shearingBeadsSteps'} = param('shearingBeadsSteps') || '';
$paclibDetails->{'shearingOperator'} = param('shearingOperator') || '';
$paclibDetails->{'bluepippinInput'} = param('bluepippinInput') || '0';
$paclibDetails->{'bluepippinSize'} = param('bluepippinSize') || '0';
$paclibDetails->{'bluepippinOutput'} = param('bluepippinOutput') || '0';
$paclibDetails->{'bluepippinConcentration'} = param('bluepippinConcentration') || '0';
$paclibDetails->{'bluepippinOperator'} = param('bluepippinOperator') || '';
$paclibDetails->{'description'} = param('description') || '';

my $json = JSON::XS->new->allow_nonref;
$paclibDetails = $json->encode($paclibDetails);

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

my $sample=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
$sample->execute($sampleId);
my @sample = $sample->fetchrow_array();

if($paclibName)
{
	if($paclibId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($paclibId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'paclib'})
		{
			if ($paclibName ne $checkCreator[2])
			{
				my $checkPaclibName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'paclib' AND name LIKE ? AND z = ?");
				$checkPaclibName->execute($paclibName,$sampleId);
				if($checkPaclibName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Paclib name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}

			my $updatePaclib=$dbh->prepare("UPDATE matrix SET name = ?, x = ?, z = ?, note = ? WHERE id = ?");
			$updatePaclib->execute($paclibName,$status,$sampleId,$paclibDetails,$paclibId);
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
		my $checkPaclibName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'paclib' AND name LIKE ? AND z = ?");
		$checkPaclibName->execute($paclibName,$sampleId);
		if($checkPaclibName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Paclib name exists. Please enter another one!");
</script>	
END
			exit;
		}
		my $config = new config;
		my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
		$lastBarcode = $lastBarcode + 1;
		$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
		my $insertPaclib=$dbh->prepare("INSERT INTO matrix VALUES ('', 'paclib', ?, '', ?, '0', ?, ?, ?, ?, NOW())");
		$insertPaclib->execute($paclibName,$status,$sampleId,$lastBarcode,$paclibDetails,$userName);
		$paclibId = $dbh->{mysql_insertid};
		my $setOrder = $dbh->do("UPDATE matrix SET o = $paclibId WHERE id = $paclibId");
		print header(-cookie=>cookie(-name=>'sample',-value=>$sampleId));
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
	parent.errorPop("Please give a paclib name!");
</script>	
END
}