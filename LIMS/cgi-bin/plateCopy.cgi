#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
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

my $libraryId = param ('libraryId') || '';
my $originalCopy = param ('originalCopy') || '';
my $newCopy = param ('newCopy') || '';

print header;
if($libraryId)
{
	my $originalPlate=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'plate' AND z = ? AND x = ? ORDER BY o");
	$originalPlate->execute($libraryId,$originalCopy);
	while (my @originalPlate = $originalPlate->fetchrow_array())
	{
		my $config = new config;
		my $lastBarcode = $config->getFieldValueWithFieldName("barcode");
		$lastBarcode = $lastBarcode + 1;
		$config->updateFieldValueWithFieldName("barcode",$lastBarcode);
		my $insertPlate=$dbh->prepare("INSERT INTO matrix VALUES ('', 'plate', ?, '', ?, ?, ?, ?, ?, ?, NOW())");
		$insertPlate->execute($originalPlate[2],$newCopy,$originalCopy,$originalPlate[6],$lastBarcode,$originalPlate[8],$userName);
		my $plateId = $dbh->{mysql_insertid};
		my $setOrder = $dbh->do("UPDATE matrix SET o = $plateId WHERE id = $plateId");
	}
	print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
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
