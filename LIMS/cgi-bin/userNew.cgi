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
	print  <<eof;
	<p>All form fields are required.</p>
	<form name="addUserForm" id="addUserForm" action="userSave.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<p><b>Username</b> <input type="text" id="username" name="username" class="text ui-widget-content ui-corner-all"></p>
	<p><b>First name</b> <input type="text" id="firstname" name="firstname" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Last name</b> <input type="text" id="lastname" name="lastname" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Email</b> <input type="text" id="email" name="email" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Password</b> <input type="password" id="password" name="password" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Re-enter password</b> <input type="password" id="repassword" name="repassword" class="text ui-widget-content ui-corner-all"></p>
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "Add a New User");
		\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Add", click: function() { submitForm('addUserForm'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
}
