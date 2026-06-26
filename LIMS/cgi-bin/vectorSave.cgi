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

my $vectorId = param ('vectorId') || '';
my $vectorName = param ('name') || '';
my $vectorDescription = param('description') || '';

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

print header;

if($vectorName)
{
	if($vectorId)
	{
		my $checkVectorName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'vector' AND name LIKE ? AND id != ?");
		$checkVectorName->execute($vectorName, $vectorId);
		if($checkVectorName->rows < 1)
		{
			my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$checkCreator->execute($vectorId);
			my @checkCreator=$checkCreator->fetchrow_array();
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'vector'})
			{
				my $updateVector=$dbh->prepare("UPDATE matrix SET name = ?, note = ? WHERE id = ?");
				$updateVector->execute($vectorName,$vectorDescription,$vectorId);
				print <<END;
<script>
parent.closeDialog();
parent.refresh("general");
</script>	
END
			}
			else
			{
				print <<END;
<script>
	parent.errorPop("Not a valid user!");
</script>	
END
			}
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("The given vector name is existing!");
</script>	
END

		}
	}
	else
	{
		my $checkVectorName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'vector' AND name LIKE ?");
		$checkVectorName->execute($vectorName);
		if($checkVectorName->rows < 1)
		{
			my $config = new config;
			my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
			$lastBarcode = $lastBarcode + 1;
			$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
			my $insertVector=$dbh->prepare("INSERT INTO matrix VALUES ('', 'vector', ?, '', 0, 0, 0, ?, ?, ?, NOW())");
			$insertVector->execute($vectorName,$lastBarcode,$vectorDescription,$userName);
			$vectorId = $dbh->{mysql_insertid};
			my $setOrder = $dbh->do("UPDATE matrix SET o = $vectorId WHERE id = $vectorId");
			print <<END;
<script>
	parent.closeDialog();
	parent.refresh("general");
</script>	
END
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("The given vector name is existing!");
</script>	
END
		}
	}
}
else
{
	print <<END;
<script>
	parent.errorPop("Please give a vector name!");
</script>	
END
}

