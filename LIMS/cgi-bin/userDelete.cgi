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
	my @userIDs = param("deleteUserList");
	foreach my $deleteUserId (@userIDs){
		next if($deleteUserId == $userId);
		#make "Deleted" user from "user" table -- not really delete an user.
		$user->markDeleteUser($deleteUserId);
		#delete cookie.
		$userCookie->deleteCookieByUserId($deleteUserId);
	}
	print <<eof;
	<script type="text/javascript">
		parent.closeDialog();
		parent.informationPop('User has been deleted.');
		parent.refresh("settingTabs");
	</script>
eof

}
