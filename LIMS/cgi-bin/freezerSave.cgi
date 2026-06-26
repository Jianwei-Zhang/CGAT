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

my $freezerId = param ('freezerId') || '';
my $roomId = param ('roomId') || '';
my $freezerName = param ('name') || '';
my $freezerX = param('x');
$freezerX =~ s/\D//g;
$freezerX = 1 unless ($freezerX);
my $freezerY = param('y');
$freezerY =~ s/\D//g;
$freezerY = 1 unless ($freezerY);
my $freezerZ = param('z');
$freezerZ =~ s/\D//g;
$freezerZ = 1 unless ($freezerZ);
my $freezerDescription = param('description') || '';

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

if($freezerName && $roomId)
{
	if($freezerId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($freezerId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'freezer'})
		{
			if ($freezerName ne $checkCreator[2] || $roomId ne $checkCreator[3])
			{
				my $checkFreezerName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'freezer' AND name LIKE ? AND o = ?");
				$checkFreezerName->execute($freezerName,$roomId);
				if($checkFreezerName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Freezer name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}
			my $updateFreezer=$dbh->prepare("UPDATE matrix SET name = ?, o = ?, x = ?, y = ?, z = ?, note = ? WHERE id = ?");
			$updateFreezer->execute($freezerName,$roomId,$freezerX,$freezerY,$freezerZ,$freezerDescription,$freezerId);
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
		my $checkFreezerName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'freezer' AND name LIKE ? AND o = ?");
		$checkFreezerName->execute($freezerName,$roomId);
		if($checkFreezerName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Freezer name exists. Please enter another one!");
</script>	
END
			exit;
		}
		my $config = new config;
		my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
		$lastBarcode = $lastBarcode + 1;
		$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
		my $insertFreezer=$dbh->prepare("INSERT INTO matrix VALUES ('', 'freezer', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertFreezer->execute($freezerName,$roomId,$freezerX,$freezerY,$freezerZ,$lastBarcode,$freezerDescription,$userName);
		$freezerId = $dbh->{mysql_insertid};
		print header(-cookie=>cookie(-name=>'freezer',-value=>$freezerId));
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
	parent.errorPop("Please give a freezer name!");
</script>	
END
}

