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

my $libraryId = param ('libraryId') || '';
my %yesOrNo = ( 0=>'No', 1=>'Yes' );
my %status = ( active=>'Active', inactive=>'Inactive', deleted=>'Deleted' );
print header;
if ($libraryId)
{
	my $library=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$library->execute($libraryId);
	my @library = $library->fetchrow_array();
	my $libraryDetails = decode_json $library[8];

	$libraryDetails->{'comments'} = escapeHTML($libraryDetails->{'comments'});
	$libraryDetails->{'orderPageComments'} = escapeHTML($libraryDetails->{'orderPageComments'});
	$libraryDetails->{'comments'} =~ s/\n/<br>/g;
	$libraryDetails->{'orderPageComments'} =~ s/\n/<br>/g;
	$libraryDetails->{'commonName'} = ($libraryDetails->{'commonName'}) ? "($libraryDetails->{'commonName'})" : "";
	if($library[4])
	{
		my $checkVector = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkVector->execute($library[4]);
		my @checkVector=$checkVector->fetchrow_array();
		$library[4] = $checkVector[2];
	}
	if($library[5])
	{
		my $checkSource = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$checkSource->execute($library[5]);
		my @checkSource=$checkSource->fetchrow_array();
		$library[5] = "<tr><td style='text-align:right'><b>Rearraying source</b></td>
						<td>$checkSource[2]</td>
					</tr>";
	}
	else
	{
		$library[5] = "";
	}
	print <<END;
	<div id='viewLibraryTabs$$'>
				<ul>
				<li><a href='#viewLibraryTabs-1'>General</a></li>
				<li><a href='#viewLibraryTabs-2'>Specs</a></li>
				<li><a href='#viewLibraryTabs-3'>Status</a></li>
				</ul>
				<div id='viewLibraryTabs-1'>
					<table>
					<tr><td style='text-align:right;width:200px;'><b>Library Name</b></td>
						<td>$library[2]<sup class='ui-state-disabled'>(Library id: $libraryId)</sup>
						<br><sup class='ui-state-disabled'>Last changed by $library[9] on $library[10]</sup></td>
					</tr>
					<tr><td style='text-align:right'><b>Nickname</b></td>
						<td>$libraryDetails->{'nickname'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Library type</b></td>
						<td>$libraryDetails->{'type'}</td>
					</tr>
					$library[5]
					<tr><td style='text-align:right'><b>Plate format</b></td>
						<td>$libraryDetails->{'format'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Distributor institute</b></td>
						<td>$libraryDetails->{'distributorInstitute'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Ref. to publication</b></td>
						<td>$libraryDetails->{'refToPublication'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Provided by</b></td>
						<td>$libraryDetails->{'providedBy'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Organization</b></td>
						<td>$libraryDetails->{'organization'}</td>
					</tr>
					<tr><td style='text-align:right;width:200px;'><b>Genus Species Subspecies</b><br>(Common Name)</td>
						<td>$libraryDetails->{'genus'} $libraryDetails->{'species'} $libraryDetails->{'subspecies'}<br>$libraryDetails->{'commonName'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Cultivar</b></td>
						<td>$libraryDetails->{'cultivar'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Genome equivalents</b></td>
						<td>$libraryDetails->{'genomeEquivalents'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Genome size</b></td>
						<td>$libraryDetails->{'genomeSize'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Genome type</b></td>
						<td>$libraryDetails->{'genomeType'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Tissue</b></td>
						<td>$libraryDetails->{'tissue'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Treatment</b></td>
						<td>$libraryDetails->{'treatment'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Development stage</b></td>
						<td>$libraryDetails->{'developmentStage'}</td>
					</tr>
					</table>		
				</div>
				<div id='viewLibraryTabs-2'>
					<table>
					<tr><td style='text-align:right;width:200px;'><b># of plates</b></td>
						<td>$library[3]</td>
					</tr>
					<tr><td style='text-align:right'><b># of filters</b></td>
						<td>$libraryDetails->{'nofFilters'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Average insert size</b></td>
						<td>$libraryDetails->{'averageInsertSize'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Standard deviation</b></td>
						<td>$libraryDetails->{'standardDeviation'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Vector</b></td>
						<td>$library[4]</td>
					</tr>
					<tr><td style='text-align:right'><b>Host</b></td>
						<td>$libraryDetails->{'host'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Enzyme 5' prime</b></td>
						<td>$libraryDetails->{'enzymeFivePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Enzyme 3' prime</b></td>
						<td>$libraryDetails->{'enzymeThreePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>End seq primer 5' prime</b></td>
						<td>$libraryDetails->{'endSeqFivePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>End seq primer 3' prime</b></td>
						<td>$libraryDetails->{'endSeqThreePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Cloning linker 5' prime</b></td>
						<td>$libraryDetails->{'cloningFivePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Cloning linker 3' prime</b></td>
						<td>$libraryDetails->{'cloningThreePrime'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Antibiotic</b></td>
						<td>$libraryDetails->{'antibiotic'}</td>
					</tr>
					</table>
				</div>
				<div id='viewLibraryTabs-3'>
					<table>
					<tr><td style='text-align:right;width:200px;'><b>Status</b></td>
						<td>$status{$libraryDetails->{'status'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is external?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isExternal'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is public?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isPublic'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is finished?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isFinished'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is library for sale?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isLibraryForSale'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is filter for sale?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isFilterForSale'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is clone for sale?</b></td>
						<td>$yesOrNo{$libraryDetails->{'isCloneForSale'}}</td>
					</tr>
					<tr><td style='text-align:right'><b>Is library for sequencing?</b></td>
						<td>$yesOrNo{$library[7]}</td>
					</tr>
					<tr><td style='text-align:right'><b>Order page comments</b></td>
						<td>$libraryDetails->{'orderPageComments'}</td>
					</tr>
					<tr><td style='text-align:right;width:200px;'><b>Library was made on</b></td>
						<td>$libraryDetails->{'dateLibraryWasMade'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Library was autoclaved on</b></td>
						<td>$libraryDetails->{'dateLibraryWasAutoclaved'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Date entered the system</b></td>
						<td>$library[10]</td>
					</tr>
					<tr><td style='text-align:right'><b>Archive start date</b></td>
						<td>$libraryDetails->{'archiveStartDate'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Archive end date</b></td>
						<td>$libraryDetails->{'archiveEndDate'}</td>
					</tr>
					<tr><td style='text-align:right'><b>Comments</b></td>
						<td>$libraryDetails->{'comments'}</td>
					</tr>
					</table>
				</div>
			</div>
	<script>
	\$( "#viewLibraryTabs$$" ).tabs();
	\$('#dialog').dialog("option", "title", "View Library");
	\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Edit", click: function() { closeDialog();openDialog("libraryEdit.cgi?libraryId=$libraryId"); } }, { text: "OK", click: function() {closeDialog(); } } ] );
	</script>
END
}
else
{
	print '402 Invalid operation';
	exit;
}
