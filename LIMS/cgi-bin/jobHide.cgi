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
my @jobId = param('jobId');
print header;

foreach my $input (sort {$a <=> $b} @jobId)
{
	my $updateJobToHide=$dbh->do("UPDATE matrix SET name = '-$input' WHERE container LIKE 'job' AND name LIKE '$input'");
}
print <<END;
<script>
	parent.closeDialog();
	parent.refresh("menu");
</script>	
END
