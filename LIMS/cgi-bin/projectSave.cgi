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

my $projectId = param ('projectId') || '';
my $projectName = param ('name') || '';
my $projectDescription = param('description') || '';

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

if($projectName)
{
	if($projectId)
	{
		my $checkProjectName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'project' AND name LIKE ? AND id != ?");
		$checkProjectName->execute($projectName, $projectId);
		if($checkProjectName->rows < 1)
		{
			my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$checkCreator->execute($projectId);
			my @checkCreator=$checkCreator->fetchrow_array();
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'project'})
			{
				my $updateProject=$dbh->prepare("UPDATE matrix SET name = ?, note = ? WHERE id = ?");
				$updateProject->execute($projectName,$projectDescription,$projectId);
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
	parent.errorPop("The given project name is existing!");
</script>	
END
		}		
	}
	else
	{
		my $checkProjectName = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'project' AND name LIKE ?");
		$checkProjectName->execute($projectName);
		if($checkProjectName->rows < 1)
		{
			my $config = new config;
			my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
			$lastBarcode = $lastBarcode + 1;
			$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
			my $insertProject=$dbh->prepare("INSERT INTO matrix VALUES ('', 'project', ?, '', 1, 1, 1, ?, ?, ?, NOW())");
			$insertProject->execute($projectName,$lastBarcode,$projectDescription,$userName);
			$projectId = $dbh->{mysql_insertid};
			my $setOrder = $dbh->do("UPDATE matrix SET o = $projectId WHERE id = $projectId");
			print header(-cookie=>cookie(-name=>'project',-value=>$projectId));
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
	parent.errorPop("The given project name is existing!");
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
	parent.errorPop("Please give a project name!");
</script>	
END
}

