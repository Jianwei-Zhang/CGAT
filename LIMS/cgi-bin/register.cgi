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
my $config = new config;
my $siteName = $config->getFieldValueWithFieldName("SITENAME");
$siteName = escapeHTML($siteName);
my $commoncfg = readConfig("main.conf");

print header;

unless(defined param('username'))
{
	print <<eof;
	<p>All form fields are required.</p>
	<form name="registerForm" id="registerForm" action="register.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<p><b>Username</b> <input type="text" id="username" name="username" class="text ui-widget-content ui-corner-all"></p>
	<p><b>First name</b> <input type="text" id="firstname" name="firstname" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Last name</b> <input type="text" id="lastname" name="lastname" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Email</b> <input type="text" id="email" name="email" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Password</b> <input type="password" id="password" name="password" class="text ui-widget-content ui-corner-all"></p>
	<p><b>Re-enter password</b> <input type="password" id="repassword" name="repassword" class="text ui-widget-content ui-corner-all"></p>
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "Register for $siteName!");
		\$('#dialog').dialog("option", "buttons", [{ text: "Register", click: function() { submitForm('registerForm'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
	exit;
}
my $userName = param('username');
my $password = param('password');
my $repassword = param('repassword');
my $firstName = param('firstname');
my $lastName = param('lastname');
my $email = param('email');

# be sure the userName is alphanumeric - no spaces or funny characters
if ($userName !~ /^\w{3,}$/) {
	print <<eof;
	<h2>Error</h2>
	Please use an alphanumeric username at least 3 letters long, with no spaces.
	<script type="text/javascript">
		parent.errorPop('Please use an alphanumeric username at least 3 letters long, with no spaces.');
	</script>
eof
	exit;
}

# be sure their real name isn't blank
if ($firstName eq "" || $lastName eq "") {
	print <<eof;
	<h2>Error</h2>
	Please enter a full name.
	<script type="text/javascript">
		parent.errorPop('Please enter a full name');
	</script>
eof
	exit;
}

# be sure the password isn't blank or shorter than 6 chars
if (length($password) < 6) {
	print <<eof;
	<h2>Error</h2>
	Please enter a password at least 6 characters long.
	<script type="text/javascript">
		parent.errorPop('Please enter a password at least 6 characters long.');
	</script>
eof
	exit;
}

# be sure password match twice
if ($password ne $repassword) {
	print <<eof;
	<h2>Error</h2>
	Password doesn't match.
	<script type="text/javascript">
		parent.errorPop("Password doesn't match.");
	</script>
eof
	exit;
}

# be sure they gave a valid e-mail address
unless ($email =~ /\w+\@\w+\.\w+/) {
	print <<eof;
	<h2>Error</h2>
	Please enter a valid e-mail address.
	<script type="text/javascript">
		parent.errorPop("Please enter a valid e-mail address.");
	</script>
eof
	exit;
}

# check the db first and be sure the userName isn't already registered


my $user = new user;
my $userConfig = new userConfig;

my $userId = $user->getIdWithUserName($userName);

if ( defined $userId && $userId) {
	print <<eof;
	<h2>Error</h2>
	The username '$userName' is already in use. Please choose another one.
	<script type="text/javascript">
		parent.errorPop("The username '$userName' is already in use. Please choose another one.");
	</script>
eof
	exit;
}
my $userEmail = $userConfig->getUserIdWithEmail($email);
if ( defined $userEmail && $userEmail) {
	print <<eof;
	<h2>Error</h2>
	The email '$email' is already in use. Please choose another one.
	<script type="text/javascript">
		parent.errorPop("The email '$email' is already in use. Please choose another one.");
	</script>
eof
	exit;
}
my $activation = &randomString(18);
$userId = $user->insertUser($userName, $password, "regular", $activation);

my $configFirstNameId = $config->getConfigIdWithFieldName("firstName");
my $configLastNameId = $config->getConfigIdWithFieldName("lastName");
my $configEmailId = $config->getConfigIdWithFieldName("email");
$userConfig->insertRecord($userId,$configFirstNameId,$firstName);
$userConfig->insertRecord($userId,$configLastNameId,$lastName);
$userConfig->insertRecord($userId,$configEmailId,$email);

# ...and send email to the person telling them their new password.
# be sure to send them the un-encrypted version!
open(MAIL,"|/usr/sbin/sendmail -t -oi");
print MAIL "To: $email\n";
print MAIL "From: webmaster\n";
print MAIL "Subject: Welcome to $siteName! Please activate your account.\n\n";
print MAIL <<eof;
Dear $firstName $lastName ($userName),

Welcome to $siteName.

Your account needs to be activated through the below link:

$commoncfg->{HOSTURL}/$commoncfg->{CGIBIN}/userActivate.cgi?activation=$activation

Best regards,
Dev Team
$siteName
eof

print <<eof;
	<script type="text/javascript">
		parent.closeDialog();
		parent.informationPop("Account was created successfully! You will get an email for activating your new account.");
	</script>
eof
