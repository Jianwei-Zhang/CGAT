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

my $commoncfg = readConfig("main.conf");

print header;

unless(defined param('oldpass'))
{
	print <<eof;
	<p>All form fields are required.</p>
	<form name="changePasswordForm" id="changePasswordForm" action="passChange.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<p><b>Old password</b> <input type="password" id="oldpass" name="oldpass" class="text ui-widget-content ui-corner-all"></p>
	<p><b>New password</b> <input type="password" id="newpass1" name="newpass1" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Re-enter new password</b> <input type="password" id="newpass2" name="newpass2" class="text ui-widget-content ui-corner-all"></p>
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "Change password");
		\$('#dialog').dialog("option", "buttons", [{ text: "Change password", click: function() { submitForm('changePasswordForm'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
	exit;
}

my $oldpass = param('oldpass');
my $newpass1 = param('newpass1');
my $newpass2 = param('newpass2');

# a little redundant error checking to be sure they typed the same
# new password twice:
if ($newpass1 ne $newpass2)
{
	print <<eof;
	<h2>Error</h2>
	You didn't type the same thing for both new password fields. Please check it and try again.
	<script type="text/javascript">
		parent.errorPop("You didn't type the same thing for both new password fields. Please check it and try again.");
	</script>
eof
    exit;
}

my $user = new user;

# now encrypt the old password and see if it matches what's in the database
if (!$user->checkPassword($userId,$oldpass))
{
	print <<eof;
	<h2>Error</h2>
	Your old password is incorrect.
	<script type="text/javascript">
		parent.errorPop("Your old password is incorrect.");
	</script>
eof
    exit;
}

$user->updatePassword($userId,$newpass1);
# Finally we print out a thank-you page telling the user what
# we've done.
print <<eof;
<script type="text/javascript">
	parent.informationPop("Your password has been changed sucessfully!");
	parent.closeDialog();
</script>
eof
