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
	my $dialogTitle = (@userIDs > 1) ? 'Delete the below users' : 'Delete the below user';
	my $userList='';
	foreach my $deleteUserId (@userIDs){
		my $userName = $user->getUserName($deleteUserId);
		if($deleteUserId == $userId)
		{
			$userList .= <<eof;
			<input type="checkbox" id="deleteUser$deleteUserId" name="deleteUserList" value="$deleteUserId" disabled="disabled"/><label for="deleteUser$deleteUserId">$userName (You can't delete yourself!)</label><br>
eof
		}
		else
		{
			$userList .= <<eof;
			<input type="checkbox" id="deleteUser$deleteUserId" name="deleteUserList" value="$deleteUserId" checked="checked"/><label for="deleteUser$deleteUserId">$userName</label><br>
eof
		}
	}
	print <<eof;
	<form name="deleteUserForm$$" id="deleteUserForm$$" action="userDelete.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	$userList
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "$dialogTitle");
		\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Delete", click: function() { submitForm('deleteUserForm$$'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
}
