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

my $assemblyId = param ('assemblyId') || '';
my $assemblyName = param ('name') || '';
my $assemblyStatus = param ('status') || '';
my $targetId = param ('targetId') || '';
my $fpcOrAgpId = param ('fpcOrAgpId') || '0';
my $refGenomeId = param ('refGenomeId') || '0';
my @extraId = param ('extraId');

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

if($assemblyName)
{
	if($assemblyId)
	{
		my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkCreator->execute($assemblyId);
		my @checkCreator=$checkCreator->fetchrow_array();
		if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'assembly'})
		{
			my $assemblyDetails = decode_json $checkCreator[8];
			$assemblyDetails->{'autoCheckNewSeq'} = param ('autoCheckNewSeq') || '0';
			$assemblyDetails->{'description'} =  param('description') || '';
			my $json = JSON::XS->new->allow_nonref;
			$assemblyDetails = $json->encode($assemblyDetails);
			$checkCreator[7] = $assemblyStatus if ($assemblyStatus);
			my $updateAssembly=$dbh->prepare("UPDATE matrix SET name = ?, y = ?, z = ?, barcode = ?, note = ? WHERE id = ?");
			$updateAssembly->execute($assemblyName,$refGenomeId,$fpcOrAgpId,$checkCreator[7],$assemblyDetails,$assemblyId);
			my $deleteAsbGenomeLink = $dbh->do("DELETE FROM link WHERE parent = $assemblyId AND type LIKE 'asbGenome'");
			foreach(@extraId)
			{
				my $insertLink = $dbh->do("INSERT INTO link VALUES ($assemblyId,$_,'asbGenome')");
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
	parent.errorPop("Not a valid user!");
</script>	
END
		}
	}
	else
	{
		my $assemblyDetails;
		$assemblyDetails->{'autoCheckNewSeq'} = param ('autoCheckNewSeq') || '0';
		$assemblyDetails->{'description'} =  param('description') || '';
		my $json = JSON::XS->new->allow_nonref;
		$assemblyDetails = $json->encode($assemblyDetails);
		my $version = 1;
		my $checkAssembly = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assembly' AND x = ?");
		$checkAssembly->execute($targetId);
		if($checkAssembly->rows < 1)
		{
			my $insertAssembly=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assembly', ?, ?, ?, ?, ?, 0, ?, ?, NOW())");
			$insertAssembly->execute($assemblyName,$version,$targetId,$refGenomeId,$fpcOrAgpId,$assemblyDetails,$userName);
			$assemblyId = $dbh->{mysql_insertid};
			foreach(@extraId)
			{
				my $insertLink = $dbh->do("INSERT INTO link VALUES ($assemblyId,$_,'asbGenome')");
			}
			print header(-cookie=>cookie(-name=>'assembly',-value=>$assemblyId));
			print <<END;
<script>
	parent.refresh("menu");
</script>	
END
		}
		else
		{
			while(my @checkAssembly=$checkAssembly->fetchrow_array())
			{
				$version = $checkAssembly[3] if ($checkAssembly[3] > $version);
			}
			$version++;
			my $insertAssembly=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assembly', ?, ?, ?, ?, ?, 0, ?, ?, NOW())");
			$insertAssembly->execute($assemblyName,$version,$targetId,$refGenomeId,$fpcOrAgpId,$assemblyDetails,$userName);
			$assemblyId = $dbh->{mysql_insertid};
			foreach (@extraId)
			{
				my $insertLink = $dbh->do("INSERT INTO link VALUES ($assemblyId,$_,'asbGenome')");
			}
			print header(-cookie=>cookie(-name=>'assembly',-value=>$assemblyId));
			print <<END;
<script>
	parent.refresh("menu");
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
	parent.errorPop("Please give an assembly name!");
</script>	
END
}