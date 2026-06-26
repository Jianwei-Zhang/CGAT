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

my $assemblySeqId = param ('assemblySeqId') || '';
my $scrollLeft = param ('scrollLeft') || '0';
print header;

if($assemblySeqId)
{
	my $assemblyCtgOfSeq = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND MATCH (note) AGAINST (?)");
	$assemblyCtgOfSeq->execute($assemblySeqId);
	my @assemblyCtgOfSeq = $assemblyCtgOfSeq->fetchrow_array();
	my @newCloneList;
	foreach (split ",", $assemblyCtgOfSeq[8])
	{
		if(/($assemblySeqId)/)
		{
			if(/^-/)
			{
				$_ =~ s/-//g;
				push @newCloneList, $_;
			}
			else
			{
				push @newCloneList, "-$_";
			}
		}
		else
		{
			push @newCloneList, $_;
		}
	}
	my $newCloneList = join ",", @newCloneList;
	my $updateAssemblyCtg=$dbh->do("UPDATE matrix SET note = '$newCloneList' WHERE id = $assemblyCtgOfSeq[0]");

	print <<END;
<script>
	parent.closeViewer();
	parent.openViewer("assemblyCtgView.cgi?assemblyCtgId=$assemblyCtgOfSeq[0]&highlight=$assemblySeqId&scrollLeft=$scrollLeft");
	//parent.refresh("menu");
</script>	
END
}
else
{
	print <<END;
<script>
	parent.errorPop("Not a valid operation!");
</script>	
END
}