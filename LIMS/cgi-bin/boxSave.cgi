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

my $boxId = param ('boxId') || '';
my $freezerId = param ('freezerId') || '';
my $boxName = param ('name') || '';
my $boxX = param('x');
$boxX =~ s/\D//g;
$boxX = 1 unless ($boxX);
my $boxY = param('y');
$boxY =~ s/\D//g;
$boxY = 1 unless ($boxY);
my $boxZ = param('z');
$boxZ =~ s/\D//g;
$boxZ = 1 unless ($boxZ);
my $boxDescription = param('description') || '';

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

if($boxName && $freezerId)
{
	if($boxId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($boxId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'box'})
		{
			if ($boxName ne $checkCreator[2] || $freezerId ne $checkCreator[3])
			{
				my $checkBoxName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'box' AND name LIKE ? AND o = ?");
				$checkBoxName->execute($boxName,$freezerId);
				if($checkBoxName->rows > 0)
				{
					print header;
					print <<END;
<script>
	parent.errorPop("Box name exists. Please enter another one!");
</script>	
END
					exit;
				}
			}
			my $updateBox=$dbh->prepare("UPDATE matrix SET name = ?, o = ?, x = ?, y = ?, z = ?, note = ? WHERE id = ?");
			$updateBox->execute($boxName,$freezerId,$boxX,$boxY,$boxZ,$boxDescription,$boxId);
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
		my $checkBoxName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'box' AND name LIKE ? AND o = ?");
		$checkBoxName->execute($boxName,$freezerId);
		if($checkBoxName->rows > 0)
		{
			print header;
			print <<END;
<script>
	parent.errorPop("Box name exists. Please enter another one!");
</script>	
END
			exit;
		}
		my $config = new config;
		my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
		$lastBarcode = $lastBarcode + 1;
		$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
		my $insertBox=$dbh->prepare("INSERT INTO matrix VALUES ('', 'box', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertBox->execute($boxName,$freezerId,$boxX,$boxY,$boxZ,$lastBarcode,$boxDescription,$userName);
		$boxId = $dbh->{mysql_insertid};
				
		print header(-cookie=>cookie(-name=>'box',-value=>$boxId));
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
	parent.errorPop("Please give a box name!");
</script>	
END
}

