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

if($assemblyId)
{
	my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkCreator->execute($assemblyId);
	my @checkCreator=$checkCreator->fetchrow_array();
	if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'assembly'})
	{
		#insert new assembly with new name
		my $version = 1;
		my $checkAssembly = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assembly' AND x = ?");
		$checkAssembly->execute($checkCreator[4]);
		while(my @checkAssembly=$checkAssembly->fetchrow_array())
		{
			$version = $checkAssembly[3] if ($checkAssembly[3] > $version);
		}
		$version++;
		my $insertAssembly=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assembly', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
		$insertAssembly->execute("$checkCreator[2]_copy",$version,$checkCreator[4],$checkCreator[5],$checkCreator[6],$checkCreator[7],$checkCreator[8],$userName);
		my $newAssemblyId = $dbh->{mysql_insertid};

		#add new asbGenome to link
		my $checkAsbGenome = $dbh->prepare("SELECT * FROM link WHERE type LIKE 'asbGenome' AND parent = ?");
		$checkAsbGenome->execute($assemblyId);
		while(my @checkAsbGenome=$checkAsbGenome->fetchrow_array())
		{
			my $insertLink = $dbh->do("INSERT INTO link VALUES ($newAssemblyId,$checkAsbGenome[1],'asbGenome')");
		}

		#copy assemblySeq
		my $assemblySeqOldToNew;
		my $assemblySeqs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblySeq' AND o = ?");
		$assemblySeqs->execute($assemblyId);
		while(my @assemblySeqs = $assemblySeqs->fetchrow_array())
		{
			my $insertAssemblySeq=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assemblySeq', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
			$insertAssemblySeq->execute($assemblySeqs[2],$newAssemblyId,$assemblySeqs[4],$assemblySeqs[5],$assemblySeqs[6],$assemblySeqs[7],$assemblySeqs[8],$userName);
			$assemblySeqOldToNew->{$assemblySeqs[0]} = $dbh->{mysql_insertid};
		}

		#copy assemblyCtg & comments
		my $assemblyCtg=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ?");
		$assemblyCtg->execute($assemblyId);
		while(my @assemblyCtg = $assemblyCtg->fetchrow_array())
		{
			my @assemblySeqList;
			foreach (split ",", $assemblyCtg[8])
			{
				my $assemblySeqId = $_;
				$assemblySeqId =~ /(\d+)/;
				my $newAssemblySeqId = $assemblySeqOldToNew->{$1};
				$assemblySeqId =~ s/$1/$newAssemblySeqId/g;
				push @assemblySeqList, $assemblySeqId;
			}
			my $assemblySeqList = join ",", @assemblySeqList;
			my $insertAssemblyCtg=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assemblyCtg', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
			$insertAssemblyCtg->execute($assemblyCtg[2],$newAssemblyId,$assemblyCtg[4],$assemblyCtg[5],$assemblyCtg[6],$assemblyCtg[7],$assemblySeqList,$userName);
			my $newAssemblyCtgId = $dbh->{mysql_insertid};
			my $checkComment = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'comment' AND o = ?");
			$checkComment->execute($assemblyCtg[0]);
			while(my @checkComment = $checkComment->fetchrow_array())
			{
				my $insertComment=$dbh->prepare("INSERT INTO matrix VALUES ('', 'comment', ?, ?, ?, ?, ?, ?, ?, ?, NOW())");
				$insertComment->execute($checkComment[2],$newAssemblyCtgId,$checkComment[4],$checkComment[5],$checkComment[6],$checkComment[7],$checkComment[8],$userName);
			}			
		}
		print header(-cookie=>cookie(-name=>'assembly',-value=>$newAssemblyId));
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
	parent.errorPop("Check 'Make a copy of this assembly' first!");
</script>
END
}
