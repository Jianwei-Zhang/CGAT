#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw(warningsToBrowser fatalsToBrowser);
use lib "lib/";
use lib "lib/pangu";
use pangu;
use userCookie;
my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);
$userCookie->deleteCookie(cookie('cid'));

# set a new cookie that expires NOW
my $setCookie = cookie(-name=>'cid', -value=>'', -expires=>'now');
print header(-cookie=>$setCookie);
#reload main page after logout
print <<eof;
	<div style="clear:left;"><a onclick="openDialog('login.cgi')"><span class="ui-icon ui-icon-power" style="float: left; margin-right: .3em;"></span>Login</a></div>
	<div style="clear:left;"><a onclick="openDialog('register.cgi')"><span class="ui-icon ui-icon-person" style="float: left; margin-right: .3em;"></span>Register</a></div>
	<div style="clear:left;"><a onclick="openDialog('passForgot.cgi')"><span class="ui-icon ui-icon-locked" style="float: left; margin-right: .3em;"></span>Forgot Your Password?</a></div>
	<script type="text/javascript">
		\$( "#menu" ).tabs("option","active",0).tabs( "load", 0 );
	</script>
eof
