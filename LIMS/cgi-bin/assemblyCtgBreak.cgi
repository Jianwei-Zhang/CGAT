#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});
my $assemblyCtgId = param ('assemblyCtgId') || '';
my $assemblySeqs = param ('assemblySeqs') || '';
my $newCtgName = param ('newCtgName') || '';
my $scrollLeft = param ('scrollLeft') || '0';

print header;

if($assemblyCtgId && $assemblySeqs && $newCtgName)
{
	my $checkAssemblyCtg = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkAssemblyCtg->execute($assemblyCtgId);
	if($checkAssemblyCtg->rows < 1)
	{
		print <<END;
<script>
	parent.errorPop("Not a valid operation!");
</script>	
END
	}
	else
	{
		my @checkAssemblyCtg = $checkAssemblyCtg->fetchrow_array();
		my ($headSeqs,$tailSeqs) = split ",BREAK,",$assemblySeqs;
		my $updateAssemblyCtg=$dbh->prepare("UPDATE matrix SET note = ? WHERE id = ?");
		$updateAssemblyCtg->execute($headSeqs,$assemblyCtgId);
		my $assemblyCtgLength = 0;
		for (split ",", $headSeqs)
		{
			/^-/ and next;
			$_ =~ s/[^a-zA-Z0-9]//g;
			my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$assemblySeq->execute($_);
			my @assemblySeq = $assemblySeq->fetchrow_array();
			my $assemblySeqStart;
			my $assemblySeqEnd;
			if($assemblySeq[8])
			{
				($assemblySeqStart,$assemblySeqEnd) = split ",",$assemblySeq[8];
			}
			else
			{
				$assemblySeqStart = 1;
				$assemblySeqEnd = $assemblySeq[6];
				my $updateAssemblySeq=$dbh->do("UPDATE matrix SET note = '$assemblySeqStart,$assemblySeqEnd' WHERE id = $assemblySeq[0]");
			}
			  	$assemblyCtgLength += $assemblySeqEnd - $assemblySeqStart + 1;
		}
		my $updateAssemblyCtgLength=$dbh->do("UPDATE matrix SET barcode = $assemblyCtgLength WHERE id = $assemblyCtgId");
		my $updateAssemblyCtgOrder=$dbh->do("UPDATE matrix SET y = y + 1 WHERE container LIKE 'assemblyCtg' AND o = $checkAssemblyCtg[3] AND x = $checkAssemblyCtg[4] AND y > $checkAssemblyCtg[5]");

		my $insertAssemblyCtg=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assemblyCtg', ?, ?, ?, ?, ?, 0, ?, ?, NOW())");
		$insertAssemblyCtg->execute($newCtgName,$checkAssemblyCtg[3],$checkAssemblyCtg[4],$checkAssemblyCtg[5]+1,$checkAssemblyCtg[6]+$assemblyCtgLength,$tailSeqs,$userName);
		my $newAssemblyCtgId = $dbh->{mysql_insertid};
		my $newAssemblyCtgLength = 0;
		for (split ",", $tailSeqs)
		{
			/^-/ and next;
			$_ =~ s/[^a-zA-Z0-9]//g;
			my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$assemblySeq->execute($_);
			my @assemblySeq = $assemblySeq->fetchrow_array();
			my $assemblySeqStart;
			my $assemblySeqEnd;
			if($assemblySeq[8])
			{
				($assemblySeqStart,$assemblySeqEnd) = split ",",$assemblySeq[8];
			}
			else
			{
				$assemblySeqStart = 1;
				$assemblySeqEnd = $assemblySeq[6];
				my $updateAssemblySeq=$dbh->do("UPDATE matrix SET note = '$assemblySeqStart,$assemblySeqEnd' WHERE id = $assemblySeq[0]");
			}
			  	$newAssemblyCtgLength += $assemblySeqEnd - $assemblySeqStart + 1;
		}
		my $updateNewAssemblyCtgLength=$dbh->do("UPDATE matrix SET barcode = $newAssemblyCtgLength WHERE id = $newAssemblyCtgId");
		print <<END;
<script>
parent.closeDialog();
parent.refresh("menu");
parent.closeViewer();
parent.openViewer("assemblyCtgView.cgi?assemblyCtgId=$assemblyCtgId&scrollLeft=$scrollLeft");
</script>	
END
	}
}
else
{
	print <<END;
<script>
	parent.errorPop("Not a valid operation!");
</script>	
END
}