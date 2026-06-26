#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use userCookie;

my $commoncfg = readConfig("main.conf");
my $user = new user;

if(param('activation'))
{
	my $activation = param('activation');
	if (length ($activation) == 19) #activation code can't be of the same length of activation datetime
	{
		print redirect("$commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}");
		exit;
	}
	my $activationStatus = $user->activateUser($activation);
	if ($activationStatus) {
		print header;
		print <<eof;
		Your account has been activated successfully. (click <a href='$commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}'>here</a> to start!)
		<script type="text/javascript">
			informationPop('User account has been activated.');
			refresh("settingTabs");
		</script>
eof
	}
	else
	{
		print header;
		print "Either you gave a wrong activation code or your account has been activated already. (click <a href='$commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}'>here</a> to start!)";
	}
}
elsif(param("userId"))
{
	my $userCookie = new userCookie;
	my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
	exit if (!$userId);
	my $userDetail = $user->getAllFieldsWithUserId($userId);
	my $userName = $userDetail->{"userName"};
	my $role = $userDetail->{"role"};

	print header;
	my $reactivateUserId = param("userId");
	if ($role eq "admin")
	{	
		$user->reactivateUser($reactivateUserId);
		print <<eof;
		<script type="text/javascript">
			informationPop('User account has been activated.');
			refresh("settingTabs");
		</script>
eof
	}
}
else
{
	print redirect("$commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}");
	exit;
}