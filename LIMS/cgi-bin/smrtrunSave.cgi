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

my $smrtrunId = param ('smrtrunId') || '';
my $smrtrunName = param ('name') || '';
$smrtrunName =~ s/\s//g;
my $smrtcell = param ('smrtcell') || '8';
my $status = param ('status') || '0';
my $smrtrunDetails;
$smrtrunDetails->{'comments'} = param ('comments') || '';
my $json = JSON::XS->new->allow_nonref;
$smrtrunDetails = $json->encode($smrtrunDetails);

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


if($smrtrunName)
{
	if($smrtrunId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($smrtrunId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'smrtrun'})
		{
			if ($smrtrunName ne $checkCreator[2])
			{
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
			}
			my $totalCellNumber = 0;
			my $checkCellNumber = $dbh->prepare("SELECT SUM(x) FROM matrix WHERE container LIKE 'smrtwell' AND z = ?");
			$checkCellNumber->execute($smrtrunId);
			my @checkCellNumber=$checkCellNumber->fetchrow_array();
			$totalCellNumber = $checkCellNumber[0] if($checkCellNumber[0]);
			if($totalCellNumber > $smrtcell)
			{
				print header;
				print <<END;
<script>
	parent.errorPop("The SMRTCell number ($smrtcell) you entered is smaller than the number of cells ($totalCellNumber) in the run!");
</script>	
END
				exit;
			}

			my $updateSmrtrun=$dbh->prepare("UPDATE matrix SET
				name = ?,
				o = ?,
				barcode = ?,
				note = ?,
				creator = ?,
				creationDate = NOW()
				WHERE id = ?");
			$updateSmrtrun->execute(
				$smrtrunName,
				$smrtcell,
				$status,
				$smrtrunDetails,
				$userName,
				$smrtrunId);
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
		print header;
		print <<END;
<script>
	parent.errorPop("Please provide SMRT Run Id!");
</script>	
END
		exit;
	}
}
else
{
	print header;
	print <<END;
<script>
	parent.errorPop("Please give a smrtrun name!");
</script>	
END
}