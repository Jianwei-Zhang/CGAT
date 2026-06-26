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
my $seqId = param('seqId');
print header;
my $sequence = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
$sequence->execute($seqId);
my @sequence =  $sequence->fetchrow_array();
if($sequence[0])
{
	my $checkAssemblySeq = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblySeq' AND y = ?");
	$checkAssemblySeq->execute($sequence[0]);
	if($checkAssemblySeq->rows > 0)
	{
		print <<END;
<script>
	parent.errorPop("You can NOT revoke a sequence in an assembly!");
</script>	
END
		exit;
	}

	my $updateJob=$dbh->do("UPDATE matrix SET barcode = barcode - 1 WHERE container LIKE 'job' AND (name LIKE '$sequence[4]' OR name LIKE '-$sequence[4]')");	
	my $updateClone=$dbh->do("UPDATE clones SET sequenced = 0 WHERE name LIKE '$sequence[2]' OR origin LIKE '$sequence[2]'");
	my $updateFpcClone=$dbh->prepare("UPDATE matrix SET x = 0 WHERE container LIKE 'fpcClone' AND name LIKE '$sequence[2]'");
	my $updateSequence=$dbh->do("UPDATE matrix SET name = '-$sequence[2]' WHERE id = $sequence[0]");
	my $checkSequence = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND name LIKE ? AND o > 0 AND o < 50 ORDER BY barcode, o, x DESC LIMIT 1");
	$checkSequence->execute($sequence[2]);
	while (my @checkSequence =  $checkSequence->fetchrow_array())
	{
		my $updateClone=$dbh->do("UPDATE clones SET sequenced = $checkSequence[3] WHERE name LIKE '$checkSequence[2]' OR origin LIKE '$checkSequence[2]'");
		my $updateFpcClone=$dbh->prepare("UPDATE matrix SET x = $checkSequence[3] WHERE container LIKE 'fpcClone' AND name LIKE '$checkSequence[2]'");
	}	
}
print <<END;
<script>
	parent.closeDialog();
	parent.openDialog("jobView.cgi?jobId=$sequence[4]")
	parent.refresh("menu");
</script>	
END





