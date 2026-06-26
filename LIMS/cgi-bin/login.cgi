#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use userCookie;
my $commoncfg = readConfig("main.conf");

unless(defined param('username'))
{
	print header;
	my $checkRememberMe = (cookie('rememberMe')) ? 'checked="checked"' : "";
	print <<eof;
	<p>All form fields are required.
	<i>(Please turn on cookies in your browser)</i></p>
	<form name="loginForm$$" id="loginForm$$" action="login.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<p><b>Username</b> <input type="text" id="username" name="username" class="text ui-widget-content ui-corner-all"> <input type="checkbox" id="rememberMe" name="rememberMe" value="1" class="text ui-widget-content ui-corner-all" $checkRememberMe /><label for="rememberMe">Remember me</label></p>
	<p><b>Password</b> <input type="password" id="password" name="password" class="text ui-widget-content ui-corner-all"> <a onclick="closeDialog();openDialog('passForgot.cgi');">Forgot your password?</a></p>
	</form>
	<script type="text/javascript">
		\$('#dialog').dialog("option", "title", "Login!");
		\$('#dialog').dialog("option", "buttons", [{ text: "Login", click: function() { submitForm('loginForm$$'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
	</script>
eof
	exit;
}

my $user = new user;
my $userName = param('username');
my $password = param('password');
my $userId = $user->checkPassword($userName,$password);
unless ($userId)
{
	print header;
	print <<eof;
	<h2>Error</h2>
	You entered a wrong username or password. Or your account has NOT been activated.
	<script type="text/javascript">
		parent.errorPop('You entered a wrong username or password. Or your account has NOT been activated.');
	</script>
eof
    exit;
}
my $cookieId = &randomId;
my $userCookie = new userCookie;
$userCookie->insertCookie($cookieId, $userId, $ENV{REMOTE_ADDR});
my $setCookie = (defined param('rememberMe')) ? cookie(-name=>'cid', -value=>$cookieId, -expires=>'+7d') : cookie(-name=>'cid', -value=>$cookieId); # will expire in 7 days if no activities
my $rememberMe = (defined param('rememberMe')) ? cookie(-name=>'rememberMe', -value=>1, -expires=>'+365d') : cookie(-name=>'rememberMe', -value=>0);
print header(-cookie=>[$setCookie,$rememberMe]);
print <<eof;
	<script type="text/javascript">
		parent.closeDialog();
		parent.loaddiv('login','status.cgi');
		parent.refresh("menu");
	</script>
eof
