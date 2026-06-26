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

my $serviceId = param ('serviceId') || '';
my $projectId = param('projectId') || '';
my $serviceName = param ('name') || '';
$serviceName =~ s/[^a-zA-Z0-9]//g; #remove non-word characters
my $serviceType = param ('serviceType') || '0';
my $sampleType = param ('sampleType') || '0';
my $paymentStatus = param ('paymentStatus') || '0';
my $status = param ('status') || '0';

my $serviceDetails;
$serviceDetails->{'serviceTypeOther'} = param ('serviceTypeOther') || '';
#$serviceDetails->{'serviceTypeOther'} = '' if ($serviceType);
$serviceDetails->{'amount'} = param ('amount') || '';
$serviceDetails->{'assembly'} = param ('assembly') || '';
$serviceDetails->{'analysis'} = param ('analysis') || '';
$serviceDetails->{'serviceNote'} = param ('serviceNote') || '';
$serviceDetails->{'genus'} = param ('genus') || '';
$serviceDetails->{'species'} = param ('species') || '';
$serviceDetails->{'subspecies'} = param ('subspecies') || '';
$serviceDetails->{'commonName'} = param ('commonName') || '';
$serviceDetails->{'genomeSize'} = param ('genomeSize') || '';
$serviceDetails->{'paymentType'} = param ('paymentType') || '0';
$serviceDetails->{'poNumber'} = param ('poNumber') || '';
#$serviceDetails->{'poNumber'} = '' if ($paymentType ne '3');
$serviceDetails->{'invoice'} = param ('invoice') || '';
$serviceDetails->{'paymentDate'} = param ('paymentDate') || '';
$serviceDetails->{'piName'} = param ('piName') || '';
$serviceDetails->{'piEmail'} = param ('piEmail') || '';
$serviceDetails->{'institution'} = param ('institution') || '';
$serviceDetails->{'contactName'} = param ('contactName') || '';
$serviceDetails->{'contactPhone'} = param ('contactPhone') || '';
$serviceDetails->{'contactEmail'} = param ('contactEmail') || '';
$serviceDetails->{'contactAddress'} = param ('contactAddress') || '';
$serviceDetails->{'submitDate'} = param ('submitDate') || '';
$serviceDetails->{'submitPerson'} = param ('submitPerson') || '';
$serviceDetails->{'startDate'} = param ('startDate') || '';
$serviceDetails->{'endDate'} = param ('endDate') || '';
$serviceDetails->{'comments'} = param ('comments') || '';

my $json = JSON::XS->new->allow_nonref;
$serviceDetails = $json->encode($serviceDetails);

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


if($serviceName && $projectId)
{
	if($serviceId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($serviceId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'service'})
		{
			if ($serviceName ne $checkCreator[2])
			{
				my $checkServiceName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'service' AND name LIKE ? AND z = ?");
				$checkServiceName->execute($serviceName,$projectId);
				if($checkServiceName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Service name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}

			my $updateService=$dbh->prepare("UPDATE matrix SET
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
			$updateService->execute(
				$serviceName,
				$serviceType,
				$sampleType,
				$paymentStatus,
				$projectId,
				$status,
				$serviceDetails,
				$userName,
				$serviceId);
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
		my $checkServiceName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'service' AND name LIKE ? AND z = ?");
		$checkServiceName->execute($serviceName,$projectId);
		if($checkServiceName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Service name exists. Please enter another one!");
</script>	
END
			exit;
		}

		my $insertService=$dbh->prepare("INSERT INTO matrix VALUES ('', 'service', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertService->execute(
			$serviceName,
			$serviceType,
			$sampleType,
			$paymentStatus,
			$projectId,
			$status,
			$serviceDetails,
			$userName);
		$serviceId = $dbh->{mysql_insertid};
		print header(-cookie=>[cookie(-name=>'service',-value=>$serviceId),cookie(-name=>'library',-value=>0)]);
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
	parent.errorPop("Please give a service code!");
</script>	
END
}