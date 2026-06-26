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
print header;
if (!$userId)
{
	print <<eof;
	<script type="text/javascript">
		closeDialog();
		errorPop("Login before sending an email.");
	</script>
	
eof
	exit;
}

my $commoncfg = readConfig("main.conf");

my $user = new user;
my $userConfig = new userConfig;
my $toUserId = param("userId");

my $toUserName = $user->getUserName($toUserId) if ($toUserId);
my $userEmail = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"email") if ($userId);
my $userFullName = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"firstName")." ".$userConfig->getFieldValueWithUserIdAndFieldName($userId,"lastName") if ($userId);

print <<eof;
		<FORM NAME="emailToUserForm$$" id="emailToUserForm$$" action="userEmail.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	    <input type="hidden" id="toUserId" name="toUserId" value="$toUserId"/>
	    <b>From</b> $userFullName (<a title="Your email address will be visible to the recipient.">$userEmail</a>)<br>
	    <b>Subject:</b><br>
	    <INPUT type="text" name="subject" value="" class="text ui-widget-content ui-corner-all" style="width:80%;"><br>
	    <b>Compose your email:</b><br>
	    <textarea name="emailBody" rows="8" class="text ui-widget-content ui-corner-all" style="width:100%;"></textarea>
		</FORM>
<script type="text/javascript">
	\$('#dialog').dialog("option", "title", "Send email to $toUserName");
	\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Send", click: function() { submitForm('emailToUserForm$$'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
</script>
eof
