#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use userConfig;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});
my $userConfig = new userConfig;
my $SEQTOSEQMINOVERLAP = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"SEQTOSEQMINOVERLAP");
my $SEQTOSEQIDENTITY = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"SEQTOSEQIDENTITY");

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
$html =~ s/\$SEQTOSEQMINOVERLAP/$SEQTOSEQMINOVERLAP/g;
$html =~ s/\$SEQTOSEQIDENTITY/$SEQTOSEQIDENTITY/g;

print header;
print $html;

__DATA__
<form id="blastTwoseq" name="blastTwoseq" action="blastTwoseq.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<input name="assemblyId" id="blastTwoseqAssemblyId" type="hidden" value="$assemblyId" />
	<table>
	<tr>
		<td colspan="3"><label for="blastTwoseqSeqOneLabel"><b>Sequence-1.</b></label><input name="seqOneLabel" id="blastTwoseqSeqOneLabel" size="16" type="text" maxlength="32" VALUE="$seqOneLabel" placeholder="First Seq" onblur="checkSeqBlank()" /><input class='ui-state-highlight ui-corner-all' name="seqOne" id="blastTwoseqSeqOne" type="text" placeholder="First SeqId" title="First SeqId" VALUE="$seqOne" readonly="readonly"/><br>
		<label for="blastTwoseqSeqTwoLabel"><b>Sequence-2.</b></label><input name="seqTwoLabel" id="blastTwoseqSeqTwoLabel" size="16" type="text" maxlength="32" VALUE="$seqTwoLabel" placeholder="Second Seq" onblur="checkSeqBlank()" /><input class='ui-state-highlight ui-corner-all' name="seqTwo" id="blastTwoseqSeqTwo" type="text" placeholder="Second SeqId" title="Second SeqId" VALUE="$seqTwo" readonly="readonly" />
		</td>
	</tr>
	<tr><td><b>Alignment Settings:</b></td><td><input type="checkbox" id="assemblySpeedyMode" name="speedyMode" value="1"><label for="assemblySpeedyMode" title="This will skip 'Check End Match'">Speedy Mode</label><br><input type="checkbox" id="assemblyCheckGood" name="checkGood" value="1"><label for="assemblyCheckGood">Check End Match</label></td><td></td></tr>
	<tr><td style='text-align:right'><input type="checkbox" id="megablastCheckbox" name="megablast" value="megablast" checked="checked"><label for="megablastCheckbox">Megablast</label></td><td style='text-align:right'><label for="blastTwoseqMinOverlap"><b>Minimum Overlap</b></label><br>(length in bp)</td><td><input name="minOverlapBlast" id="blastTwoseqMinOverlap" size="4" type="text" maxlength="6" VALUE="$SEQTOSEQMINOVERLAP" /></td></tr>
	<tr><td></td><td style='text-align:right'><label for="blastTwoseqIdentity"><b>Minimum Identity</b></label><br>(%)</td><td><input name="identityBlast" id="blastTwoseqIdentity" size="4" type="text" maxlength="4" VALUE="$SEQTOSEQIDENTITY" /></td></tr>
	</table>
</form>
<script>
$('#dialog').dialog("option", "title", "BLAST2SEQ Alignment");
$( "#dialog" ).dialog( "option", "buttons", [{ text: "Run BLAST", click: function() { submitForm('blastTwoseq'); } }, { text: "Cancel", click: function() {closeDialog(); } } ] );
$( "#blastTwoseqMinOverlap" ).spinner({
	min: 100,
	max: 99999,
	step: 100,
	start: function( event, ui ) {
		var current = $( "#blastTwoseqMinOverlap" ).spinner( "value" );
		if(current >= 2000)
		{
			$( "#blastTwoseqMinOverlap" ).spinner( "option", "step", 500 );
		}
		else
		{
			$( "#blastTwoseqMinOverlap" ).spinner( "option", "step", 100 );
		}
	}
});
$( "#blastTwoseqIdentity" ).spinner({ min: 90, max: 100});
$( "#blastTwoseqSeqOneLabel" ).autocomplete({
	source: "$autoSeqSearchUrl",
	minLength: 2,
	focus: function( event, ui ) {
    	$( "#blastTwoseqSeqOne" ).val( ui.item.id );
    },
    select: function( event, ui ) {
    	$( "#blastTwoseqSeqOne" ).val( ui.item.id );
    }
});
$( "#blastTwoseqSeqTwoLabel" ).autocomplete({
	source: "$autoSeqSearchUrl",
	minLength: 2,
	focus: function( event, ui ) {
    	$( "#blastTwoseqSeqTwo" ).val( ui.item.id );
    },
    select: function( event, ui ) {
    	$( "#blastTwoseqSeqTwo" ).val( ui.item.id );
    }
});
function checkSeqBlank(){
	if($( "#blastTwoseqSeqOneLabel" ).val() == '')
	{
		$( "#blastTwoseqSeqOne" ).val( '' );
	}
	if($( "#blastTwoseqSeqTwoLabel" ).val() == '')
	{
		$( "#blastTwoseqSeqTwo" ).val( '' );
	}
}
</script>