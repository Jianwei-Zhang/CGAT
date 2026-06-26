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

my $seqId = param ('seqId') || '';
my $seqName = param ('name') || '';

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

if($seqId)
{
	my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkCreator->execute($seqId);
	my @checkCreator=$checkCreator->fetchrow_array();
	if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'sequence'})
	{
		my $updateSequence=$dbh->prepare("UPDATE matrix SET name = ?, creator = ? WHERE id = ?");
		$updateSequence->execute($seqName,$userName,$seqId);
		my $updateAssemblySeq=$dbh->prepare("UPDATE matrix SET name = ? WHERE container LIKE 'assemblySeq' AND y = ?");
		$updateAssemblySeq->execute($seqName,$seqId);
		$seqName = 'no name' unless ($seqName);
		print <<END;
<a id='seqName$seqId$$' onmouseover='editIconShow("seqName$seqId$$")' onmouseout='editIconHide("seqName$seqId$$")' onclick="loaddiv('seqName$seqId','seqNameEdit.cgi?seqId=$seqId')" title="Edit this name">$seqName</a>
END
	}
	else
	{
		$checkCreator[2] = 'no name' unless ($checkCreator[2]);
		print <<END;
<a id='seqName$seqId$$' onmouseover='editIconShow("seqName$seqId$$")' onmouseout='editIconHide("seqName$seqId$$")' onclick='loaddiv('seqName$seqId','seqNameEdit.cgi?seqId=$seqId')' title="Edit this name">$checkCreator[2]</a>
<script>
	errorPop("Not a valid user! No changes take place.");
</script>	
END
	}
}
else
{
	print <<END;
<a class='ui-state-error ui-corner-all'>Error: Not a valid operation!</a>
<script>
	errorPop("Not a valid operation!");
</script>	
END
}