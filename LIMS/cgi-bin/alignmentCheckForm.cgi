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

my $assemblyId = param ('assemblyId') || '';
my $seqOne = param ('seqOne') || '';
my $seqTwo = param ('seqTwo') || '';
my $autoSeqSearchUrl = 'autoSeqSearch.cgi';
if($assemblyId)
{
	$autoSeqSearchUrl .= "?assemblyId=$assemblyId";
}
$html =~ s/\$autoSeqSearchUrl/$autoSeqSearchUrl/g;
$html =~ s/\$assemblyId/$assemblyId/g;

if($seqOne)
{
	my $sequenceOne = $dbh->prepare("SELECT * FROM matrix WHERE id =  ?");
	$sequenceOne->execute($seqOne);
	my @sequenceOne = $sequenceOne->fetchrow_array();
	$html =~ s/\$seqOneLabel/$sequenceOne[2]/g;
	$html =~ s/\$seqOne/$seqOne/g;
}
else
{
	$html =~ s/\$seqOneLabel//g;
	$html =~ s/\$seqOne//g;
}

if($seqTwo)
{
	my $sequenceTwo = $dbh->prepare("SELECT * FROM matrix WHERE id =  ?");
	$sequenceTwo->execute($seqTwo);
	my @sequenceTwo = $sequenceTwo->fetchrow_array();
	$html =~ s/\$seqTwoLabel/$sequenceTwo[2]/g;
	$html =~ s/\$seqTwo/$seqTwo/g;
}
else
{
	$html =~ s/\$seqTwoLabel//g;
	$html =~ s/\$seqTwo//g;
}

print header;
print $html;

__DATA__
<form id="alignmentCheck" name="alignmentCheck" action="alignmentCheck.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<input name="assemblyId" id="alignmentCheckAssemblyId" type="hidden" value="$assemblyId" />
	<table>
	<tr>
		<td colspan="2"><label for="alignmentCheckSeqOneLabel"><b>Sequence-1.</b></label><input name="seqOneLabel" id="alignmentCheckSeqOneLabel" size="16" type="text" maxlength="32" VALUE="$seqOneLabel" placeholder="First Seq" onblur="checkBlank()" /><input class='ui-state-highlight ui-corner-all' name="seqOne" id="alignmentCheckSeqOne" type="text" placeholder="First SeqId" title="First SeqId" VALUE="$seqOne" readonly="readonly"/><br>
		<label for="alignmentCheckSeqTwoLabel"><b>Sequence-2.</b></label><input name="seqTwoLabel" id="alignmentCheckSeqTwoLabel" size="16" type="text" maxlength="32" VALUE="$seqTwoLabel" placeholder="Second Seq" onblur="checkBlank()" /><input class='ui-state-highlight ui-corner-all' name="seqTwo" id="alignmentCheckSeqTwo" type="text" placeholder="Second SeqId" title="Second SeqId" VALUE="$seqTwo" readonly="readonly" />
		</td>
	</tr>
	<tr>
		<td colspan="2"><input type="checkbox" id="alignmentHiddenCheckbox" name="hidden" value="2"><label for="alignmentHiddenCheckbox">Including Hidden Alignment (repetitive regions)</label></td>
	</tr>
	<tr>
		<td colspan="2"><input type="checkbox" id="alignmentFilterCheckbox" name="filter" value="1" checked="checked"><label for="alignmentFilterCheckbox">Filter Sequence with the same name</label></td>
	</tr>
	<tr>
		<td colspan="2"><input type="checkbox" id="alignmentCheckRedo" name="redo" value="1"><label for="alignmentCheckRedo">Delete Cached Files</label></td>
	</tr>
	</table>
</form>
<script>
$('#dialog').dialog("option", "title", "Check Alignment");
$( "#dialog" ).dialog( "option", "buttons", [{ text: "Check", click: function() { loadingShow();submitForm('alignmentCheck'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
$( "#alignmentCheckSeqOneLabel" ).autocomplete({
	source: "$autoSeqSearchUrl",
	minLength: 2,
	focus: function( event, ui ) {
    	$( "#alignmentCheckSeqOne" ).val( ui.item.id );
    },
    select: function( event, ui ) {
    	$( "#alignmentCheckSeqOne" ).val( ui.item.id );
    }
});
$( "#alignmentCheckSeqTwoLabel" ).autocomplete({
	source: "$autoSeqSearchUrl",
	minLength: 2,
	focus: function( event, ui ) {
    	$( "#alignmentCheckSeqTwo" ).val( ui.item.id );
    },
    select: function( event, ui ) {
    	$( "#alignmentCheckSeqTwo" ).val( ui.item.id );
    }
});

function checkBlank(){
	if($( "#alignmentCheckSeqOneLabel" ).val() == '')
	{
		$( "#alignmentCheckSeqOne" ).val( '' );
	}
	if($( "#alignmentCheckSeqTwoLabel" ).val() == '')
	{
		$( "#alignmentCheckSeqTwo" ).val( '' );
	}
}
</script>