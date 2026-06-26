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
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $itemId = param ('itemId') || '';
my $commentType = param ('commentType') || 0;
my $commentDetails;
$commentDetails->{'description'} = param ('description') || '';
my $json = JSON::XS->new->allow_nonref;
$commentDetails = $json->encode($commentDetails);

print header;

if($itemId)
{
	my $checkComment = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'comment' AND o = ?");
	$checkComment->execute($itemId);
	if($checkComment->rows > 0)
	{
		my $updateComment=$dbh->prepare("UPDATE matrix SET x = ?, note = ?,creator = ?,creationDate = NOW() WHERE container LIKE 'comment' AND o = ?");
		$updateComment->execute($commentType,$commentDetails,$userName,$itemId);
	}
	else
	{
		my $insertComment=$dbh->prepare("INSERT INTO matrix VALUES ('', 'comment', 'noTitle', ?, ?, 0, 0, 0, ?, ?, NOW())");
		$insertComment->execute($itemId,$commentType,$commentDetails,$userName);
		print <<END;
<script>
	parent.refresh("menu");
</script>
END
	}
		print <<END;
<script>
	parent.closeDialog();
	parent.openDialog("comment.cgi?itemId=$itemId");
</script>
END
}
else
{
	print <<END;
<script>
	parent.errorPop("Please give an item Id!");
</script>	
END
}