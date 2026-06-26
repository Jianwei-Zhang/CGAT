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

print header;
my $config = new config;
my $userConfig = new userConfig;
my $author = $config->getFieldValueWithFieldName('AUTHOR');
my $siteName = $config->getFieldValueWithFieldName("SITENAME");

if ($role eq "admin"){
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

	my $newUserId = $user->getIdWithUserName($userName);
	
	if ( defined $newUserId && $newUserId) {
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
	$newUserId = $user->insertUser($userName, $password, "regular", $activation);
	my $activationStatus = $user->activateUser($activation);

	my $configFirstNameId = $config->getConfigIdWithFieldName("firstName");
	my $configLastNameId = $config->getConfigIdWithFieldName("lastName");
	my $configEmailId = $config->getConfigIdWithFieldName("email");
	$userConfig->insertRecord($newUserId,$configFirstNameId,$firstName);
	$userConfig->insertRecord($newUserId,$configLastNameId,$lastName);
	$userConfig->insertRecord($newUserId,$configEmailId,$email);

	print <<eof;
	<script type="text/javascript">
		parent.closeDialog();
		parent.informationPop('New user has been added.');
		parent.refresh("settingTabs");
	</script>
eof

	# ...and send email to the person telling them their new password.
	# be sure to send them the un-encrypted version!
	open(MAIL,"|/usr/sbin/sendmail -t -oi");
	print MAIL "To: $email\n";
	print MAIL "From: $siteName <$author> \n";
	print MAIL "Subject: Welcome to $siteName!\n\n";
	print MAIL <<eof;
Dear $firstName $lastName ($userName),
	
	Welcome to $siteName.
	
	Your account has been created.
	
	Please login at $commoncfg->{HOSTURL}/$commoncfg->{HTDOCS}
	User name: $userName
	Temporary password (case sensitive): $password
	Please change your password immediately after logging in.
	
Best regards,
Dev Team
$siteName
eof
}

