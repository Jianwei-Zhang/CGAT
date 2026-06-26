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

my @vectors = param ('vectors');
my $vectorName = param ('vectorName') || '';

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

for(@vectors)
{
	unless($_ == $vectorName)
	{
		my $vector = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$vector->execute($_);
		my @vector=$vector->fetchrow_array();
		if($vector[9] eq $userName || exists $userPermission->{$userId}->{'vector'})
		{
			my $deleteVector=$dbh->do("DELETE FROM matrix WHERE id = $_");
			my $updateLibrary=$dbh->do("UPDATE matrix SET
				x = $vectorName
				WHERE container LIKE 'library' AND x = $vector[0]");
		}
		else
		{
			print <<END;
<script>
	parent.errorPop("Not a valid user!");
</script>	
END
			exit;
		}
	}
}
print <<END;
<script>
	parent.closeDialog();
	parent.refresh("general");
</script>	
END
