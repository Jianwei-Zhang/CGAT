#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use config;
use userConfig;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};
my $role = $userDetail->{"role"};

print header;

my $userConfig = new userConfig;
my $userViewerId = param("userId");

if ($role eq "admin" || $userId eq $userViewerId){
	my $configId = param("configId");
	my $fieldValue = param("fieldValue");
	$userConfig->updateFieldValueWithUserIdAndConfigId($userViewerId, $configId, $fieldValue) if(defined $configId && defined $fieldValue);
	print <<eof;
	<script type="text/javascript">
		informationPop('User profile has been added.');
		refresh("settingTabs");
	</script>
eof
}
