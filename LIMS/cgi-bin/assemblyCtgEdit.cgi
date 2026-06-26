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
my $assemblyCtgId = param ('assemblyCtgId') || '';
my $assemblyId = param ('assemblyId') || '';
my $chr = param ('chr') || '0';
my $scrollLeft = param ('scrollLeft') || '0';

if ($assemblyCtgId)
{
	my $assemblyCtgList=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$assemblyCtgList->execute($assemblyCtgId);
	my @assemblyCtgList = $assemblyCtgList->fetchrow_array();
	my $occupiedCtg;
	my $maxCtgNumber = 0;
	my $assemblyAllCtgList=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? ORDER BY name");
	$assemblyAllCtgList->execute($assemblyCtgList[3]);
	while(my @assemblyAllCtgList = $assemblyAllCtgList->fetchrow_array())
	{
		if($assemblyAllCtgList[0] eq $assemblyCtgId)
		{
			my $assemblySeqList = '';
			my $i = 1;
			for (split ",", $assemblyCtgList[8])
			{
				$assemblySeqList .= ($_ =~ /^-/) ? "<li title='Hidden Sequence' class='ui-state-highlight' id='$_'><span class='ui-icon ui-icon-arrowthick-2-n-s'></span>$i. " : "<li class='ui-state-default' id='$_'><span class='ui-icon ui-icon-arrowthick-2-n-s'></span>$i. ";
				$_ =~ s/[^a-zA-Z0-9]//g;
				my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
				$assemblySeq->execute($_);
				my @assemblySeq = $assemblySeq->fetchrow_array();
				$assemblySeqList .= "$assemblySeq[2]($assemblySeq[5])</li>";
				$i++;
			}
			$html =~ s/\$assemblyCtgId/$assemblyCtgId/g;
			$html =~ s/\$assemblyId/$assemblyId/g;
			$html =~ s/\$chr/$chr/g;
			$html =~ s/\$scrollLeft/$scrollLeft/g;
			$html =~ s/\$assemblyCtg/$assemblyAllCtgList[2]/g;
			$html =~ s/\$assemblyChr/$assemblyAllCtgList[4]/g;
			$html =~ s/\$assemblyPosition/$assemblyAllCtgList[6]/g;
			$html =~ s/\$assemblySeqs/$assemblyAllCtgList[8]/g;
			$html =~ s/\$assemblySeqList/$assemblySeqList/g;
			$html =~ s/\$\$/$$/g;
		}
		$maxCtgNumber = $assemblyAllCtgList[2] if ($assemblyAllCtgList[2] > $maxCtgNumber);
		$occupiedCtg->{$assemblyAllCtgList[2]} = 1;
	}
	my $assemblyNameCtg = '';
	for (my $j = 1; $j <= $maxCtgNumber + 1; $j++)
	{
		$assemblyNameCtg .= "<option value='$j'>Ctg$j</option>" if (!exists $occupiedCtg->{$j});
	}
	$html =~ s/\$assemblyNameCtg/$assemblyNameCtg/g;
	my $autoAssemblyCtgSearchUrl = "autoAssemblyCtgSearch.cgi?assemblyId=$assemblyCtgList[3]";
	my $autoSeqSearchUrl = "autoSeqSearch.cgi?assemblyId=$assemblyCtgList[3]&extra=1";
	$html =~ s/\$autoAssemblyCtgSearchUrl/$autoAssemblyCtgSearchUrl/g;
	$html =~ s/\$autoSeqSearchUrl/$autoSeqSearchUrl/g;
	print header(-cookie=>cookie(-name=>'assemblyCtg',-value=>$assemblyCtgId));
	print $html;
}
else
{
	print header(-type=>'text/html',-status=>'402 Invalid operation');
	exit;
}

__DATA__
	<form id="editAssemblyCtg$assemblyCtgId" name="editAssemblyCtg$assemblyCtgId" action="assemblyCtgSave.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<input name="assemblyCtgId" id="editAssemblyCtgId" type="hidden" value="$assemblyCtgId" />
	<input name="assemblySeqs" id="editAssemblySeqs" type="hidden" value="$assemblySeqs" />
	<input name="assemblyId" id="editAssemblyId" type="hidden" value="$assemblyId" />
	<input name="chr" id="editAssemblyChr" type="hidden" value="$chr" />
	<input name="scrollLeft" id="editAssemblyScrollLeft" type="hidden" value="$scrollLeft" />
	<table>
	<tr><td style='text-align:right'><label for="editAssemblyCtgNumber"><b>Contig</b></label></td>
		<td colspan='2'><select class='ui-widget-content ui-corner-all' name="assemblyCtgNumber" id="editAssemblyCtgNumber"><option value='$assemblyCtg' selected>Ctg$assemblyCtg</option><optgroup label='Rename this contig as'>$assemblyNameCtg</optgroup></select></td>
	</tr>
	<tr><td style='text-align:right'><label for="editAssemblyChr"><b>Chromosome</b></label><br><sup class='ui-state-disabled'>98 for Chloroplast</sup><br><sup class='ui-state-disabled'>99 for Mitochondrion</sup><br><sup class='ui-state-disabled'>100 for Contamination</sup></td>
		<td><input class='ui-widget-content ui-corner-all' name="assemblyChr" id="editAssemblyChr" size="4" type="text" maxlength="3" value="$assemblyChr" /></td>
		<td class='ui-state-highlight ui-corner-all' rowspan='2'>
		<input type='checkbox' id='appendCtg$$' name='appendCtg' value='1'><label for="appendCtg$$"><b>Append <input class='ui-widget-content ui-corner-all' name="appendCtgNumber" id="editAssemblyAppendCtgNumber" size="5" type="text" maxlength="10"> to Ctg$assemblyCtg</b></label><br>
		<input type='checkbox' id='flipCtg$$' name='flipCtg' value='1'><label for="flipCtg$$"><b>Flip the selected contig</b></label></td>
	</tr>
	<tr><td style='text-align:right'><label for="editAssemblyPosition"><b>Estimated Position</b></label></td>
		<td><input class='ui-widget-content ui-corner-all' name="assemblyPosition" id="editAssemblyPosition" size="8" type="text" maxlength="13" value="$assemblyPosition" /></td>
	</tr>
	<tr><td style='text-align:right'><label for="editAssemblySeqs"><b>Sequences</b></label></td>
		<td colspan='2'><ul id="sortable$$" style='white-space: nowrap;'>$assemblySeqList</ul></td>
	</tr>
	<tr><td style='text-align:right'><label for="assemblyInsertSeqLabel"><b>Insert Sequence</b></label></td>
		<td colspan='2'><input name="insertSeqLabel" id="assemblyInsertSeqLabel" size="16" type="text" maxlength="32" VALUE="" placeholder="Insert Seq" onblur="checkSeqBlank()" /><input class='ui-state-highlight ui-corner-all' name="insertSeq" id="assemblyInsertSeq" type="text" placeholder="Insert SeqId" title="Insert SeqId" VALUE="" readonly="readonly"/></td>
	</tr>
	</table>	
	</form>
<style>
#sortable$$ { list-style-type: none; margin: 0; padding: 0; width: 100%; }
#sortable$$ li { margin: 0 3px 3px 3px; padding: 0.4em; padding-left: 1.5em; height: 1.2em; }
#sortable$$ li span { position: absolute; margin-left: -1.3em; }
</style>
<script>
$( "#sortable$$" ).sortable({
      placeholder: "ui-state-error",
      forcePlaceholderSize: true,
      stop: function(event, ui) {
        $('#editAssemblySeqs').val($( "#sortable$$" ).sortable( "toArray" ));
    }
    });
$( "#sortable" ).disableSelection();
$( "#editAssemblyAppendCtgNumber" ).autocomplete({
	source: "$autoAssemblyCtgSearchUrl",
	minLength: 1
	});
$( "#assemblyInsertSeqLabel" ).autocomplete({
	source: "$autoSeqSearchUrl",
	minLength: 2,
	focus: function( event, ui ) {
    	$( "#assemblyInsertSeq" ).val( ui.item.id );
    },
    select: function( event, ui ) {
    	$( "#assemblyInsertSeq" ).val( ui.item.id );
    }
});
function checkSeqBlank(){
	if($( "#assemblyInsertSeqLabel" ).val() == '')
	{
		$( "#assemblyInsertSeq" ).val( '' );
	}
}
$('#dialog').dialog("option", "title", "GPM AssemblyCtg Editor: Ctg$assemblyCtg");
$( "#dialog" ).dialog( "option", "buttons", [ { text: "Save", click: function() { submitForm('editAssemblyCtg$assemblyCtgId'); } }, { text: "Cancel", click: function() {closeDialog();} } ] );
</script>