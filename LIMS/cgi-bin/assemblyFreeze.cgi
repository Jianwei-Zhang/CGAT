#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS; #JSON::XS is recommended to be installed for handling JSON string of big size 
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

my $assemblyId = param ('assemblyId') || '';

print header;
if($assemblyId)
{
	my $assembly=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$assembly->execute($assemblyId);
	my @assembly = $assembly->fetchrow_array();
	if($assembly[9] eq $userName || exists $userPermission->{$userId}->{'assembly'})
	{
		if ($assembly[7] == 1)
		{
			my $updateAssemblyToFrozen=$dbh->do("UPDATE matrix SET barcode = '2' WHERE id = $assemblyId");
			print <<END;
<script>
	refresh("menu");
	informationPop("This assembly is frozen.");
</script>	
END
		}
		if($assembly[7] == 2)
		{
			my $updateAssemblyToAssembled=$dbh->do("UPDATE matrix SET barcode = '1' WHERE id = $assemblyId");
			print <<END;
<script>
	refresh("menu");
	informationPop("This assembly is unfrozen.");
</script>	
END
		}
	}
	else
	{
			print <<END;
<script>
	errorPop("Not a valid user!");
</script>	
END
	}
}
else
{
	print <<END;
<script>
	errorPop("Please give an assembly id!");
</script>	
END
}
