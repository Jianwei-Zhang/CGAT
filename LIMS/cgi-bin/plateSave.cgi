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

my $plateId = param ('plateId') || '';
my $libraryId = param ('libraryId') || '';
my $plateName = param ('name') || '';
my $plateNofPlates = param ('nofPlates') || 0;
my $plateDescription = param('description') || '';

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

my $library=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
$library->execute($libraryId);
my @library = $library->fetchrow_array();
if($library[5])
{
	unless($plateDescription)
	{
		print header;
		print <<END;
<script>
	parent.errorPop("Please provide rearraying source clones!");
</script>	
END
		exit;		
	}
}

if ($plateNofPlates =~ /\D/)
{
	print header;
	print <<END;
<script>
	parent.errorPop("Number of plates is not a valid value!");
</script>	
END
}
else
{
	if($plateName)
	{
		if($plateId)
		{
			my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$checkCreator->execute($plateId);
			my @checkCreator=$checkCreator->fetchrow_array();
			if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'plate'})
			{
				my $updatePlate=$dbh->prepare("UPDATE matrix SET note = ? WHERE id = ?");
				$updatePlate->execute($plateDescription,$plateId);
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
			for(my $i = 1; $i <= $plateNofPlates; $i++)
			{
				my $config = new config;
				my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
				$lastBarcode = $lastBarcode + 1;
				$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
				my $insertPlate=$dbh->prepare("INSERT INTO matrix VALUES ('', 'plate', ?, '', 0, 0, ?, ?, ?, ?, NOW())");
				$insertPlate->execute($plateName,$libraryId,$lastBarcode,$plateDescription,$userName);
				$plateId = $dbh->{mysql_insertid};
				$plateName =  sprintf "%0*d", 4, $plateName + 1;
			}
			my $updateLibrary=$dbh->do("UPDATE matrix SET
				o = o + $plateNofPlates
				WHERE id = $libraryId");

			print header(-cookie=>cookie(-name=>'library',-value=>$libraryId));
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
	parent.errorPop("Please give a plate name!");
</script>	
END
	}
}
