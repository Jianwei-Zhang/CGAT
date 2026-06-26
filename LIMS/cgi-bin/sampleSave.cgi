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

my $sampleId = param ('sampleId') || '';
my $serviceId = param ('serviceId') || '';
my $location = param ('location') || '';
my $sampleName = param ('name') || '';
my $purpose = param ('purpose') || 0;
my $type = param ('type') || 0;
my $status = param ('status') || 0;
my $sampleDetails;
$sampleDetails->{'sampleTypeOther'} = param ('sampleTypeOther') || '';
#$sampleDetails->{'sampleTypeOther'} = '' unless ($type eq '7' || $type eq '0' );
$sampleDetails->{'description'} = param ('description') || '';

my $json = JSON::XS->new->allow_nonref;
$sampleDetails = $json->encode($sampleDetails);

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


if($sampleName)
{
	if($sampleId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($sampleId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'sample'})
		{
			if ($sampleName ne $checkCreator[2])
			{
				my $checkSampleName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sample' AND name LIKE ? AND z = ?");
				$checkSampleName->execute($sampleName,$serviceId);
				if($checkSampleName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Sample name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}
			my $updateSample=$dbh->prepare("UPDATE matrix SET name = ?, o = ?, x = ?, y = ?, z = ?, note = ? WHERE id = ?");
			$updateSample->execute($sampleName,$purpose,$type,$status,$serviceId,$sampleDetails,$sampleId);
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
		my $checkSampleName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sample' AND name LIKE ? AND z = ?");
		$checkSampleName->execute($sampleName,$serviceId);
		if($checkSampleName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Sample name exists. Please enter another one!");
</script>	
END
			exit;
		}
		my $config = new config;
		my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
		$lastBarcode = $lastBarcode + 1;
		$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
		my $insertSample=$dbh->prepare("INSERT INTO matrix VALUES ('', 'sample', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertSample->execute($sampleName,$purpose,$type,$status,$serviceId,$lastBarcode,$sampleDetails,$userName);
		$sampleId = $dbh->{mysql_insertid};

		print header(-cookie=>cookie(-name=>'service',-value=>$serviceId));
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
	parent.errorPop("Please give a sample name!");
</script>	
END
}