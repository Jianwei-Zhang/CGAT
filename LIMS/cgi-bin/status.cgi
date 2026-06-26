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

if ($userId)
{
	if(cookie('rememberMe'))
	{
		my $cookieId = cookie('cid');
		my $setCookie = cookie(-name=>'cid', -value=>$cookieId, -expires=>'+7d'); # extend another 7 days but will expire in 7 days if no activities
		my $rememberMe = cookie(-name=>'rememberMe', -value=>1, -expires=>'+365d');
		print header(-cookie=>[$setCookie,$rememberMe]);
	}
	else
	{
		print header;
	}
	my $user = new user;
	my $userDetail = $user->getAllFieldsWithUserId($userId);
	my $userName = $userDetail->{"userName"};
	print <<eof;
	<div style="clear:left;">Welcome, <a onclick='openDialog("userView.cgi?userId=$userId")'><b>$userName</b></a>! </div>
	<div style="clear:left;"><a onclick="loaddiv('login','logout.cgi')"><span class="ui-icon ui-icon-power" style="float: left; margin-right: .3em;"></span>Logout</a></div>
	<div style="clear:left;"><a onclick="openDialog('passChange.cgi')"><span class="ui-icon ui-icon-key" style="float: left; margin-right: .3em;"></span>Change your password?</a></div>
eof
}
else
{
	print header;
	print  <<eof;
	<div style="clear:left;"><a onclick="openDialog('login.cgi')"><span class="ui-icon ui-icon-power" style="float: left; margin-right: .3em;"></span>Login</a></div>
	<div style="clear:left;"><a onclick="openDialog('register.cgi')"><span class="ui-icon ui-icon-person" style="float: left; margin-right: .3em;"></span>Register</a></div>
	<div style="clear:left;"><a onclick="openDialog('passForgot.cgi')"><span class="ui-icon ui-icon-locked" style="float: left; margin-right: .3em;"></span>Forgot your password?</a></div>
eof
}