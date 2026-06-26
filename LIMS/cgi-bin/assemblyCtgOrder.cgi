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

my $assemblyId = param ('assemblyId') || '';
my $assemblyCtgOrders = param ('assemblyCtgOrders') || '';

print header;

if($assemblyId && $assemblyCtgOrders)
{
	my $order = 1;
	for (split ",",$assemblyCtgOrders)
	{
		my $updateAssemblyCtg=$dbh->do("UPDATE matrix SET y = $order WHERE id = $_ AND o = $assemblyId"); #use $assemblyId for double check
		$order++;
	}
	print <<END;
<script>
	parent.savingHide();
</script>	
END
}
else
{
	print <<END;
<script>
	parent.savingHide();
	parent.errorPop("Not a valid operation!");
</script>	
END
}
