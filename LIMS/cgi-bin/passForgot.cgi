#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use lib "lib/";
use lib "lib/pangu";
use pangu;
use config;
use user;
use userConfig;

my $config = new config;
my $siteName = $config->getFieldValueWithFieldName("SITENAME");
$siteName = escapeHTML($siteName);

my $commoncfg = readConfig("main.conf");


print header;

unless(defined param('email'))
{
	print  <<eof;
	<p>Please provide your email to reset your password. (A new password will be e-mailed to you.)</p>
	<form name="resetPasswordForm" id="resetPasswordForm" action="passForgot.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<p><b>E-Mail address</b> <input type="text" id="email" name="email" class="text ui-widget-content ui-corner-all"></p>
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "Forget Your Password?");
		\$('#dialog').dialog("option", "buttons", [{ text: "Request New Password", click: function() { submitForm('resetPasswordForm'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
	exit;
}

my $email = param('email');

unless ($email =~ /\w+\@\w+\.\w+/){
	print <<eof;
	<h2>Error</h2>
	Your input doesn't appear to be a valid e-mail address.
	<script type="text/javascript">
		parent.errorPop("Your input doesn't appear to be a valid e-mail address.");
	</script>
eof
    exit;
}

my $userConfig = new userConfig;
my $userId = $userConfig->getUserIdWithEmail($email);
if (! $userId) {
	print <<eof;
	<h2>Error</h2>
	Your e-mail address was not found.
	<script type="text/javascript">
		parent.errorPop('Your e-mail address was not found.');
	</script>
eof
}

# ok, it's a valid user. First, we create a random password.  This uses
# the random password code from chapter 10.
my $randpass = &randomString();

my $user = new user;
# now store it in the database...
$user->updatePassword($userId,$randpass);

# ...and send email to the person telling them their new password.
# be sure to send them the un-encrypted version!
open(MAIL,"|/usr/sbin/sendmail -t -oi");
print MAIL "To: $email\n";
print MAIL "From: webmaster\n";
print MAIL "Subject: Your Password for $siteName has been reset!\n\n";
print MAIL <<eof;
Your Password has been changed. The new password is '$randpass'.

You can login and change your password at
$commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}
eof

print <<eof;
<script type="text/javascript">
	parent.informationPop('Your password has been reset! A new password has been sent to you.');
	parent.closeDialog();
</script>
eof
