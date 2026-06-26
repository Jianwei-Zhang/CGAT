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
<div id="projectNew" class="ui-widget-content ui-corner-all" style='padding: 0 .7em;'>
	<h3>New project</h3>
	<form id="newProject" name="newProject" action="projectSave.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<table>
	<tr><td style='text-align:right'><label for="newProjectName"><b>Project Name</b></label></td><td><input class='ui-widget-content ui-corner-all' name="name" id="newProjectName" size="40" type="text" maxlength="32" /></td></tr>
	<tr><td style='text-align:right'><label for="newProjectDescription"><b>Description</b></label></td><td><textarea class='ui-widget-content ui-corner-all' name="description" id="newProjectDescription" cols="60" rows="10"></textarea></td></tr>
	<tr><td></td><td><INPUT TYPE="button" VALUE="Save" onclick="submitForm('newProject')"></td></tr>
	</table>
	</form>
</div>
<script>
buttonInit();
loadingHide();
</script>