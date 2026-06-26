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
my $assemblySeqId = param ('assemblySeqId') || '';
my $scrollLeft = param ('scrollLeft') || '0';
if ($assemblySeqId)
{
	my $assemblyCtgOfSeq = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND MATCH (note) AGAINST (?)");
	$assemblyCtgOfSeq->execute($assemblySeqId);
	my @assemblyCtgOfSeq = $assemblyCtgOfSeq->fetchrow_array();

	my $assemblyAllCtgList=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ?");
	$assemblyAllCtgList->execute($assemblyCtgOfSeq[3]);
	my $assemblySeqList;
	my $occupiedCtg;
	my $maxCtgNumber = 0;
	while(my @assemblyAllCtgList = $assemblyAllCtgList->fetchrow_array())
	{
		if($assemblyAllCtgList[0] eq $assemblyCtgOfSeq[0])
		{
			my $i = 1;
			my @seqList = split ",", $assemblyAllCtgList[8];
			$assemblyAllCtgList[8] = '';
			for (@seqList)
			{
				if($i == 1)
				{
					$html =~ s/\$firstSeq/$_/g;
					$assemblyAllCtgList[8] = ($_ =~ /\($assemblySeqId\)/) ? "$_,BREAK" : $_;
					$assemblySeqList .= ($_ =~ /^-/) ? "<li title='Hidden Sequence' class='ui-state-highlight": "<li class='ui-state-default";
					$assemblySeqList .= " ctgEnds' id='$_'>$i. ";
					$_ =~ s/[^a-zA-Z0-9]//g;
					my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
					$assemblySeq->execute($_);
					my @assemblySeq = $assemblySeq->fetchrow_array();
					$assemblySeqList .= "$assemblySeq[2]($assemblySeq[5])</li>";
					$assemblySeqList .= "<li class='ui-state-error' id='BREAK'><span class='ui-icon ui-icon-scissors'></span>Break From Here</li>" if($_ == $assemblySeqId);
				}
				else
				{
					$html =~ s/\$lastSeq/$_/g if ($i == @seqList);
					$assemblyAllCtgList[8] .= ($_ =~ /\($assemblySeqId\)/) ? ",BREAK,$_" : ",$_";
					$assemblySeqList .= "<li class='ui-state-error' id='BREAK'><span class='ui-icon ui-icon-scissors'></span>Break From Here</li>" if($_ =~ /\($assemblySeqId\)/);
					$assemblySeqList .= ($_ =~ /^-/) ? "<li title='Hidden Sequence' class='ui-state-highlight" : "<li class='ui-state-default";
					$assemblySeqList .= ($i == @seqList) ? " ctgEnds' id='$_'>$i. " : "' id='$_'>$i. ";
					$_ =~ s/[^a-zA-Z0-9]//g;
					my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
					$assemblySeq->execute($_);
					my @assemblySeq = $assemblySeq->fetchrow_array();
					$assemblySeqList .= "$assemblySeq[2]($assemblySeq[5])</li>";
				}
				$i++;
			}
			if($i < 3)
			{
				print header;
				print <<END;
		<script>
		closeDialog();
		errorPop("You can NOT break a singleton!");
		</script>	
END
				exit;
			}
			$html =~ s/\$assemblyCtgId/$assemblyCtgOfSeq[0]/g;
			$html =~ s/\$assemblyCtg/$assemblyAllCtgList[2]/g;
			$html =~ s/\$scrollLeft/$scrollLeft/g;
			$html =~ s/\$assemblySeqs/$assemblyAllCtgList[8]/g;
			$html =~ s/\$assemblySeqList/$assemblySeqList/g;
			$html =~ s/\$\$/$$/g;
		}
		$maxCtgNumber = $assemblyAllCtgList[2] if ($assemblyAllCtgList[2] > $maxCtgNumber);
		$occupiedCtg->{$assemblyAllCtgList[2]} = 1;
	}
	my $newCtgList = '';
	for (my $j = 1; $j <= $maxCtgNumber + 1; $j++)
	{
		$newCtgList .= "<option value='$j'>Ctg$j</option>" if (!exists $occupiedCtg->{$j});
	}
	$html =~ s/\$newCtgList/$newCtgList/g;
	print header(-cookie=>cookie(-name=>'assemblyCtg',-value=>$assemblyCtgOfSeq[0]));
	print $html;
}
else
{
	print header(-type=>'text/html',-status=>'402 Invalid operation');
	exit;
}


__DATA__
	<form id="breakAssemblyCtg$assemblyCtgId" name="breakAssemblyCtg$assemblyCtgId" action="assemblyCtgBreak.cgi" enctype="multipart/form-data" method="post" target="hiddenFrame">
	<input name="assemblyCtgId" id="breakAssemblyCtgId" type="hidden" value="$assemblyCtgId" />
	<input name="assemblySeqs" id="breakAssemblySeqs" type="hidden" value="$assemblySeqs" />
	<input name="scrollLeft" id="breakAssemblyScrollLeft" type="hidden" value="$scrollLeft" />
	<table>
	<tr><td style='text-align:right'><label for="breakAssemblySeqs"><b>Sequences</b></label></td>
	<td><ul id="sortable$$">$assemblySeqList</ul></td>
	<td style="vertical-align:bottom"><label for="breakAssemblyNewCtgName"><b>Assign New Contig As</b></label><select class='ui-widget-content ui-corner-all' name="newCtgName" id="breakAssemblyNewCtgName">$newCtgList</select></td>
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
      items: "li:not(.ctgEnds)",
      cancel: ".ui-state-default,.ui-state-highlight",
      stop: function(event, ui) {
        $('#breakAssemblySeqs').val('$firstSeq,' + $( "#sortable$$" ).sortable( "toArray" ) + ',$lastSeq');
    }
    });
$( "#sortable" ).disableSelection();
$('#dialog').dialog("option", "title", "GPM Breaker: Ctg$assemblyCtg");
$( "#dialog" ).dialog( "option", "buttons", [ { text: "Break", click: function() { submitForm('breakAssemblyCtg$assemblyCtgId'); } }, { text: "Cancel", click: function() {closeDialog();} } ] );
</script>