#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS;
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

my %datasetType = (
	0=>'Universal',
	1=>'Species',
	2=>'Picture'
	);

my $itemId = param ('itemId') || '';
print header;
if ($itemId)
{
	my $item=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$item->execute($itemId);
	my @item = $item->fetchrow_array();
	my $itemDetails = decode_json $item[8];
	my $parent=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$parent->execute($item[6]);
	my @parent = $parent->fetchrow_array();	

	my $itemLine = '';
	for (sort {$a <=> $b} keys %$itemDetails)
	{
		$itemDetails->{$_}->{'field'} = '' unless ($itemDetails->{$_}->{'field'});
		$itemDetails->{$_}->{'value'} = '' unless ($itemDetails->{$_}->{'value'});
		$itemDetails->{$_}->{'value'} = escapeHTML($itemDetails->{$_}->{'value'});
		$itemDetails->{$_}->{'value'} =~ s/\n/<br>/g;
		if($itemDetails->{$_}->{'value'} =~ /\.(jpg|jpeg|png|tif|tiff)$/i)
		{
			$itemLine .= "<tr><td style='text-align:right;width:200px;'><b>$itemDetails->{$_}->{'field'}</b></td><td>";
			for (split "\;", $itemDetails->{$_}->{'value'})
			{
				$_ =~ s/^\s+|\s+$//g;
				$itemLine .= "<img src='$commoncfg->{HTDOCS}/data/images/$_'/>";
			}
			$itemLine .= "</td></tr>";
		}
		else
		{
			$itemLine .= ($itemDetails->{$_}->{'value'} =~ /:\/\//) ? "<tr><td style='text-align:right;width:200px;'><b>$itemDetails->{$_}->{'field'}</b></td>
							<td><a href='$itemDetails->{$_}->{'value'}' target='_blank'>$itemDetails->{$_}->{'value'}</a></td>
						</tr>" :
						"<tr><td style='text-align:right;width:200px;'><b>$itemDetails->{$_}->{'field'}</b></td>
							<td>$itemDetails->{$_}->{'value'}</td>
						</tr>";
		}
	}

	my $extraInfo = '';
	my $extraInfoTabs = '';

	my $extraItem=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'record' AND name LIKE ? AND id != ?");
	$extraItem->execute($item[2],$itemId);
	while (my @extraItem = $extraItem->fetchrow_array())
	{
		$extraInfo = "<table><tr><td style='text-align:right'><b>Extras</b></td><td><div id='extraItemTabs$$'><ul>" unless ($extraInfo);
		my $extraItemDetails = decode_json $extraItem[8];
		my $extraParent=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$extraParent->execute($extraItem[6]);
		my @extraParent = $extraParent->fetchrow_array();
		my $extraInfoList = '';
		for (sort {$a <=> $b} keys %$extraItemDetails)
		{
			$extraItemDetails->{$_}->{'field'} = '' unless ($extraItemDetails->{$_}->{'field'});
			$extraItemDetails->{$_}->{'value'} = '' unless ($extraItemDetails->{$_}->{'value'});
			$extraItemDetails->{$_}->{'value'} = escapeHTML($extraItemDetails->{$_}->{'value'});
			$extraItemDetails->{$_}->{'value'} =~ s/\n/<br>/g;
			if($extraItemDetails->{$_}->{'value'} =~ /\.(jpg|jpeg|png|tif|tiff)$/i)
			{
				$extraInfoList .= "<tr><td style='text-align:right;width:200px;'><b>$extraItemDetails->{$_}->{'field'}</b></td><td>";
				for (split "\;", $extraItemDetails->{$_}->{'value'})
				{
					$_ =~ s/^\s+|\s+$//g;
					$extraInfoList .= "<img src='$commoncfg->{HTDOCS}/data/images/$_'/>";
				}
				$extraInfoList .= "</td></tr>";
			}
			else
			{
				$extraInfoList .= ($extraItemDetails->{$_}->{'value'} =~ /:\/\//) ? "<tr><td style='text-align:right;width:200px;'><b>$extraItemDetails->{$_}->{'field'}</b></td>
								<td><a href='$extraItemDetails->{$_}->{'value'}' target='_blank'>$extraItemDetails->{$_}->{'value'}</a></td>
							</tr>" :
							"<tr><td style='text-align:right;width:200px;'><b>$extraItemDetails->{$_}->{'field'}</b></td>
								<td>$extraItemDetails->{$_}->{'value'}</td>
							</tr>";
			}
		}

		$extraInfo .= "<li><a href='#extraItemTabs-$extraItem[0]-$extraParent[0]'>$extraParent[2]</a></li>";
		$extraInfoTabs .= "<div id='extraItemTabs-$extraItem[0]-$extraParent[0]'><table>
			$extraInfoList</table></div>";
		
	}
	$extraInfo .= "</ul>$extraInfoTabs<div></td></tr></table>" if ($extraInfo);


	print <<END;
	<table>
	$itemLine
	</table>
	$extraInfo
	<script>
	\$( "#extraItemTabs$$" ).tabs();
	\$('#dialog').dialog("option", "title", "View $item[1] $item[2] in $parent[1] $parent[2]");
	\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Edit", click: function() { closeDialog();openDialog("itemEdit.cgi?itemId=$itemId"); } }, { text: "OK", click: function() {closeDialog(); } } ] );
	</script>
END
}
else
{
	print '402 Invalid operation';
	exit;
}
