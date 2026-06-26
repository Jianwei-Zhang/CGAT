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

my $location = param ('location');
my @items = param ('items');

print header;

if(@items)
{
	for (@items)
	{
		my $deleteLink=$dbh->do("DELETE FROM link WHERE type LIKE 'box' AND child = $_") if ($location);
		my $insertLink=$dbh->do("INSERT INTO link VALUES ($location,$_,'box')") if ($location);
	}
	print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
	parent.refresh("general");
</script>	
END
}
else
{
	print <<END;
<script>
	parent.errorPop("Please check items first!");
	parent.closeDialog();
</script>	
END
}