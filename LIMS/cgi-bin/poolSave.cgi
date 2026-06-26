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

my $poolId = param ('poolId') || '';
my $poolName = param ('name') || '';
my $poolClones = param('poolClones') || '';
my $poolJobs = param('poolJobs') || '';
my $comments = param('comments') || '';
my @jobIds = split /\D+/, $poolJobs;
my @clones = split /\s+/, $poolClones;
my $libraryId = param('libraryId') || '';

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

if($poolName && $poolClones)
{
	if($poolId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($poolId);
		my @checkCreator=$checkCreator->fetchrow_array();
		my $checkPoolName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'pool' AND name LIKE ? AND x = ? AND id != ?");
		$checkPoolName->execute($poolName, $checkCreator[4], $poolId);
		if($checkPoolName->rows < 1)
		{
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'pool'})
			{
				my $updatePool=$dbh->prepare("UPDATE matrix SET name = ?, note = ? WHERE id = ?");
				$updatePool->execute($poolName,$comments,$poolId);
				my $deleteLinkPool=$dbh->do("DELETE FROM link WHERE parent = $poolId AND type LIKE 'poolJob'");
				if(@jobIds)
				{
					foreach (@jobIds)
					{
						$_ =~ s/^0+//;
						my $insertLink=$dbh->do("INSERT INTO link VALUES ($poolId,'$_','poolJob')");
					}
				}
				my $deleteLinkPoolClone=$dbh->do("DELETE FROM link WHERE parent = $poolId AND type LIKE 'poolClone'");
				if(@clones)
				{
					foreach (@clones)
					{
						my $insertLink=$dbh->do("INSERT INTO link VALUES ($poolId,'$_','poolClone')");
					}
				}
				print <<END;
<script>
parent.closeDialog();
parent.refresh("viewLibraryTabs$checkCreator[4]");
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
	parent.errorPop("The given pool name is existing!");
</script>	
END
		}
	}
	else
	{
		my $checkPoolName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'pool' AND name LIKE ? AND x = ?");
		$checkPoolName->execute($poolName,$libraryId);
		if($checkPoolName->rows < 1)
		{
			my $config = new config;
			my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
			$lastBarcode = $lastBarcode + 1;
			$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
			my $insertPool=$dbh->prepare("INSERT INTO matrix VALUES ('', 'pool', ?, '', ?, 0, 0, ?, ?, ?, NOW())");
			$insertPool->execute($poolName,$libraryId,$lastBarcode,$comments,$userName);
			$poolId = $dbh->{mysql_insertid};
			my $setOrder = $dbh->do("UPDATE matrix SET o = $poolId WHERE id = $poolId");
			if(@jobIds)
			{
				foreach (@jobIds)
				{
					$_ =~ s/^0+//;
					my $insertLink=$dbh->do("INSERT INTO link VALUES ($poolId,'$_','poolJob')");
				}
			}
			if(@clones)
			{
				foreach (@clones)
				{
					my $insertLink=$dbh->do("INSERT INTO link VALUES ($poolId,'$_','poolClone')");
				}
			}
			print <<END;
<script>
parent.closeDialog();
parent.refresh("viewLibraryTabs$libraryId");
</script>	
END
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("The given pool name is existing!");
</script>	
END
		}
	}
}
else
{
	print <<END;
<script>
	parent.errorPop("Please give a pool name and clone list!");
</script>	
END
}