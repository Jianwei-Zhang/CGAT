#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

undef $/;# enable slurp mode
my $html = <DATA>;

print header;
print $html;

__DATA__
<form id="jobImport" name="jobImport" action="jobImport.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
<h3>Import job list from a file:</h3>
	<table>
	<tr><td style='text-align:right'><label for="jobImportFile"><b>Job List File</b></label></td><td><input name="jobFile" id="jobImportFile" type="file" /></td></tr>
	<tr><td style='text-align:left' colspan='2'><label for="newJobReplace"><b>Are you going to replace any existing jobs in database?</b></label></td></tr>
	<tr><td style='text-align:right'></td>
		<td>
		<div id="newJobReplace">
			<input type="radio" id="newJobReplaceRadio2" name="replace" value="1"><label for="newJobReplaceRadio2">Yes</label>
			<input type="radio" id="newJobReplaceRadio1" name="replace" value="0" checked="checked"><label for="newJobReplaceRadio1">No</label>
		</div>
	</td></tr>
	</table>
</form>
<script>
$('#dialog').dialog("option", "title", "Import Job List");
$( "#newJobReplace" ).buttonset();
$( "#dialog" ).dialog( "option", "buttons", [{ text: "Import", click: function() { submitForm('jobImport'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
</script>