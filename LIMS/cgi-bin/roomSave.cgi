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

my $roomId = param ('roomId') || '';
my $roomName = param ('name') || '';
my $roomX = param('x');
$roomX =~ s/\D//g;
$roomX = 1 unless ($roomX);
my $roomY = param('y');
$roomY =~ s/\D//g;
$roomY = 1 unless ($roomY);
my $roomZ = param('z');
$roomZ =~ s/\D//g;
$roomZ = 1 unless ($roomZ);
my $roomDescription = param('description') || '';

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


if($roomName)
{
	if($roomId)
	{
		my $checkRoomName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'room' AND name LIKE ? AND id != ?");
		$checkRoomName->execute($roomName, $roomId);
		if($checkRoomName->rows < 1)
		{
			my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$checkCreator->execute($roomId);
			my @checkCreator=$checkCreator->fetchrow_array();
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'room'})
			{
				my $updateRoom=$dbh->prepare("UPDATE matrix SET name = ?, x = ?, y = ?, z = ?, note = ? WHERE id = ?");
				$updateRoom->execute($roomName,$roomX,$roomY,$roomZ,$roomDescription,$roomId);
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
			print header;
			print <<END;
<script>
	parent.errorPop("The given room name is existing!");
</script>	
END
		}
	}
	else
	{
		my $checkRoomName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'room' AND name LIKE ?");
		$checkRoomName->execute($roomName);
		if($checkRoomName->rows < 1)
		{
			my $config = new config;
			my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
			$lastBarcode = $lastBarcode + 1;
			$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
			my $insertRoom=$dbh->prepare("INSERT INTO matrix VALUES ('', 'room', ?, '', ?, ?, ?, ?, ?, ?, NOW())");
			$insertRoom->execute($roomName,$roomX,$roomY,$roomZ,$lastBarcode,$roomDescription,$userName);
			$roomId = $dbh->{mysql_insertid};
			my $setOrder = $dbh->do("UPDATE matrix SET o = $roomId WHERE id = $roomId");
			print header(-cookie=>cookie(-name=>'room',-value=>$roomId));
			print <<END;
<script>
	parent.refresh("menu");
</script>
END
		}
		else
		{
			print header;
			print <<END;
<script>
	parent.errorPop("The given room name is existing!");
</script>	
END
		}
	}
}
else
{
	print header;
	print <<END;
<script>
	parent.errorPop("Please give a room name!");
</script>	
END
}