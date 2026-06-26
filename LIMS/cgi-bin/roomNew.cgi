#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use lib "lib/";
use lib "lib/pangu";
use pangu;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $commoncfg = readConfig("main.conf");

undef $/;# enable slurp mode
my $html = <DATA>;

print header;
print $html;

__DATA__
<div id="roomNew" class="ui-widget-content ui-corner-all" style='padding: 0 .7em;'>
	<h3>New room</h3>
	<form id="newRoom" name="newRoom" action="roomSave.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<table>
	<tr><td style='text-align:right'><label for="newRoomName"><b>Room Name</b></label></td><td><input class='ui-widget-content ui-corner-all' name="name" id="newRoomName" size="40" type="text" maxlength="32" /></td></tr>
	<tr><td style='text-align:right'><label for="newRoomX"><b>Space</b></label></td><td><label for="newRoomX">X:</label><input class='ui-widget-content ui-corner-all' name="x" id="newRoomX" size="4" type="text" maxlength="2" VALUE="10" /> <label for="newRoomY">Y:</label><input class='ui-widget-content ui-corner-all' name="y" id="newRoomY" size="4" type="text" maxlength="2" VALUE="1" /> <label for="newRoomZ">Z:</label><input class='ui-widget-content ui-corner-all' name="z" id="newRoomZ" size="4" type="text" maxlength="2" VALUE="1" /></td></tr>
	<tr><td style='text-align:right'><label for="newRoomDescription"><b>Description</b></label></td><td><textarea class='ui-widget-content ui-corner-all' name="description" id="newRoomDescription" cols="60" rows="10"></textarea></td></tr>
	<tr><td></td><td><INPUT TYPE="button" VALUE="Save" onclick="submitForm('newRoom');"></td></tr>
	</table>
	</form>
</div>
<script>
buttonInit();
loadingHide();
</script>