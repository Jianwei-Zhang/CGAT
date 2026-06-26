#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
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
my $role = $userDetail->{"role"};

print header;

if ($role eq "admin"){	
	my @userIDs = param("changeUserList");
	foreach my $changeUserId (@userIDs){
		next if($changeUserId == $userId);
		$user->changeUserRole($changeUserId);
	}
	print <<eof;
	<script type="text/javascript">
		parent.closeDialog();
		parent.informationPop('User role has been changed.');
		parent.refresh("settingTabs");
	</script>
eof
}
