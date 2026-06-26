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

print header;

my $user = new user;
my $config = new config;
my $userConfig = new userConfig;
my $author = $config->getFieldValueWithFieldName('AUTHOR');
my $siteName = $config->getFieldValueWithFieldName("SITENAME");

my $toUserId = param("toUserId");
my $toUserName = $user->getUserName($toUserId) if ($toUserId);
my $toUserEmail = $userConfig->getFieldValueWithUserIdAndFieldName($toUserId,"email") if ($toUserId);
my $userEmail = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"email") if ($userId);
my $userFullName = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"firstName")." ".$userConfig->getFieldValueWithUserIdAndFieldName($userId,"lastName") if ($userId);

my $emailBody = "";
$emailBody = param("emailBody") if (param("emailBody"));
my $subject = "Message from $siteName";
$subject = param("subject") if (param("subject"));

if ($toUserEmail !~ /.+\@.+\..+/) {
	print <<eof;
	<script type="text/javascript">
		parent.errorPop("The recipient didn't provide a valid email address.");
	</script>
eof
	exit;
}
if ($userEmail !~ /.+\@.+\..+/) {
	print <<eof;
	<script type="text/javascript">
		parent.errorPop("You didn't provide a valid email address.");
	</script>
eof
	exit;
}
if ($emailBody eq "") {
	print <<eof;
	<script type="text/javascript">
		parent.errorPop("Compose your email before sending it.");
	</script>
eof
	exit;
}

my $mail  = <<eof;
Reply-to: "$userFullName" <$userEmail>
From: "$siteName" <$author>
To: "$toUserName" <$toUserEmail>
Subject: $subject
$emailBody

eof

### Mailing the contents
open(MAIL,"|/usr/sbin/sendmail -t -oi");
print MAIL $mail;
close(MAIL);

print <<eof;
<script type="text/javascript">
	parent.closeDialog();
	parent.informationPop('Your message has been sent out successfully!');
</script>
eof
