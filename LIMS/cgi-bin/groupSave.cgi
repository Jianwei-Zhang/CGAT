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
use userConfig;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};
my $role = $userDetail->{"role"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});


my $config = new config;
my $userConfig = new userConfig;

my $groupId = param ('groupId') || '';
my $groupName = param ('name');
my @userId = param ('userId');
my @permissionId = param ('permissionId');
my $permissionIds = '';
if (@permissionId)
{
	$permissionIds = join ",", @permissionId;
}

my $groupDetails;
$groupDetails->{'description'} = param('description') || '';
$groupDetails->{'permission'} = $permissionIds;

my $json = JSON::XS->new->allow_nonref;
$groupDetails = $json->encode($groupDetails);

print header;

if($role eq "admin")
{
	if($groupName)
	{
		if($groupId)
		{
			my $checkGroupName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'group' AND name LIKE ? AND id != ?");
			$checkGroupName->execute($groupName, $groupId);
			if($checkGroupName->rows < 1)
			{
				my $updateGroup=$dbh->prepare("UPDATE matrix SET name = ?, note = ? WHERE id = ?");
				$updateGroup->execute($groupName,$groupDetails,$groupId);
				my $deleteGroupLink = $dbh->do("DELETE FROM link WHERE parent = $groupId AND type LIKE 'group'");
				for(@userId)
				{
					my $insertLink = $dbh->do("INSERT INTO link VALUES ($groupId,$_,'group')");
				}
				print <<END;
<script>
parent.closeDialog();
parent.refresh("settingTabs");
</script>	
END
			}
			else
			{
				print <<END;
<script>
	parent.errorPop('The given group name is existing!');
</script>	
END
			}		
		}
		else
		{
			my $checkGroupName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'group' AND name LIKE ?");
			$checkGroupName->execute($groupName);
			if($checkGroupName->rows < 1)
			{
				my $insertGroup=$dbh->prepare("INSERT INTO matrix VALUES ('', 'group', ?, '', 1, 1, 1, 0, ?, ?, NOW())");
				$insertGroup->execute($groupName,$groupDetails,$userName);
				$groupId = $dbh->{mysql_insertid};
				for(@userId)
				{
					my $insertLink = $dbh->do("INSERT INTO link VALUES ($groupId,$_,'group')");
				}
				print <<END;
<script>
parent.closeDialog();
parent.refresh("settingTabs");
</script>	
END
			}
			else
			{
				print <<END;
<script>
	parent.errorPop('The given group name is existing!');
</script>	
END
			}
		}
	}
	else
	{
		print <<END;
<script>
	parent.errorPop('Please give a group name!');
</script>	
END
	}

}
else
{
	print <<END;
<script>
	parent.errorPop('Not a valid user!');
</script>	
END
}
