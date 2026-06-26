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

my $asbProjectId = param ('asbProjectId') || '';
my $asbProjectName = param ('name');
my $asbProjectDescription = param('description') || '';
my @targetId = param ('targetId');

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

if($asbProjectName)
{
	if($asbProjectId)
	{
		my $checkAsbProjectName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'asbProject' AND name LIKE ? AND id != ?");
		$checkAsbProjectName->execute($asbProjectName, $asbProjectId);
		if($checkAsbProjectName->rows < 1)
		{
			my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$checkCreator->execute($asbProjectId);
			my @checkCreator=$checkCreator->fetchrow_array();
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'asbProject'})
			{
				my $updateAsbProject=$dbh->prepare("UPDATE matrix SET name = ?, note = ? WHERE id = ?");
				$updateAsbProject->execute($asbProjectName,$asbProjectDescription,$asbProjectId);
				my $deleteAsbProjectLink = $dbh->do("DELETE FROM link WHERE parent = $asbProjectId AND type LIKE 'asbProject'");
				for(@targetId)
				{
					my $insertLink = $dbh->do("INSERT INTO link VALUES ($asbProjectId,$_,'asbProject')");
				}
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
	parent.errorPop('Not a valid user!');
</script>	
END
			}
		}
		else
		{
			print header;
			print <<END;
<script>
	parent.errorPop('The given Assembly Project name is existing!');
</script>	
END
		}		
	}
	else
	{
		my $checkAsbProjectName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'asbProject' AND name LIKE ?");
		$checkAsbProjectName->execute($asbProjectName);
		if($checkAsbProjectName->rows < 1)
		{
			my $insertAsbProject=$dbh->prepare("INSERT INTO matrix VALUES ('', 'asbProject', ?, '', 1, 1, 1, 0, ?, ?, NOW())");
			$insertAsbProject->execute($asbProjectName,$asbProjectDescription,$userName);
			$asbProjectId = $dbh->{mysql_insertid};
			for(@targetId)
			{
				my $insertLink = $dbh->do("INSERT INTO link VALUES ($asbProjectId,$_,'asbProject')");
			}
			print header(-cookie=>cookie(-name=>'asbProject',-value=>$asbProjectId));
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
	parent.errorPop('The given Assembly Project name is existing!');
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
	parent.errorPop('Please give an Assembly Project name!');
</script>	
END
}