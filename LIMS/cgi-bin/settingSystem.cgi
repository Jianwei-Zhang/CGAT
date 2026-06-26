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

my $commoncfg = readConfig("main.conf");
my $config = new config;

print header;

my $configId = param("configId");
my $fieldValue = param("fieldValue");

if ($role eq "admin"){
	$config->updateFieldValueWithId($configId, $fieldValue) if(defined $configId && defined $fieldValue);
}elsif ($role eq "regular"){
	print <<eof;
	<h2>Error</h2>
	You can not make system changes!
	<script type="text/javascript">
		errorPop('You can not make system changes!');
	</script>
eof
    exit;
}else{

	print <<eof;
	<h2>Error</h2>
	This role: $role should not be assigned!~
	<script type="text/javascript">
		errorPop('This role: $role should not be assigned!~');
	</script>
eof
    exit;
}

