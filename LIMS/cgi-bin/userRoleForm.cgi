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

my $commoncfg = readConfig("main.conf");

print header;

if ($role eq "admin"){	
	my @userIDs = param("userId");
	if(@userIDs < 1)
	{
		print <<eof;
	<script type="text/javascript">
		closeDialog();
		errorPop("Please select at least one user!");
	</script>
eof
		exit;
	}
	my $dialogTitle = (@userIDs > 1) ? 'Change role of the below users' : 'Change role of the below user';
	my $userList='';
	foreach my $changeUserId (@userIDs){
		my $userDetail = $user->getAllFieldsWithUserId($changeUserId);
		my $userName = $userDetail->{"userName"};
		my $userRole = $userDetail->{"role"};

		my $changeDirection = "(Regular user to Administrator)";
		$changeDirection = "(Administrator to Regular user)" if ($userRole eq "admin");
		$changeDirection = "(Recover to Regular user)" if ($userRole eq "deleted");
		
		if($changeUserId == $userId)
		{
			$userList .= <<eof;
			<input type="checkbox" id="changeUser$changeUserId" name="changeUserList" value="$changeUserId" disabled="disabled"/><label for="changeUser$changeUserId">$userName (You can't change the role of yourself!)</label><br>
eof
		}
		else
		{
			$userList .= <<eof;
			<input type="checkbox" id="changeUser$changeUserId" name="changeUserList" value="$changeUserId" checked="checked"/><label for="changeUser$changeUserId">$userName $changeDirection</label><br>
eof
		}
	}
	print <<eof;
	<form name="changeUserForm$$" id="changeUserForm$$" action="userRole.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	$userList
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "$dialogTitle");
		\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Change", click: function() { submitForm('changeUserForm$$'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
}
