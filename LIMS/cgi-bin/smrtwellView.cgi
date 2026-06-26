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

undef $/;# enable slurp mode
my $html = <DATA>;

my $smrtwellId = param ('smrtwellId') || '';
my %movieLength = (
	0=>'Customized:',
	30=>'30 mins',
	45=>'45 mins',
	60=>'60 mins',
	90=>'90 mins',
	120=>'120 mins',
	150=>'150 mins',
	180=>'180 mins',
	240=>'240 mins'
	);
my %chemistry = (
	P4=>'P4',
	P5=>'P5',
	P6=>'P6'
	);
my %condition = (
	0=>'Customized:',
	1=>'100%',
	2=>'75%'
	);

print header;
if ($smrtwellId)
{
	my $smrtwell=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$smrtwell->execute($smrtwellId);
	my @smrtwell = $smrtwell->fetchrow_array();
	my $smrtwellDetails = decode_json $smrtwell[8];
	$smrtwellDetails->{'comments'} = '' unless (exists $smrtwellDetails->{'comments'});
	$smrtwellDetails->{'loadingName'} = '' unless (exists $smrtwellDetails->{'loadingName'});
	$smrtwellDetails->{'concentration'} = '' unless (exists $smrtwellDetails->{'concentration'});
	$smrtwellDetails->{'polRatio'} = '' unless (exists $smrtwellDetails->{'polRatio'});
	$smrtwellDetails->{'chemistry'} = '' unless (exists $smrtwellDetails->{'chemistry'});
	$smrtwellDetails->{'customizedCondition'} = '' unless (exists $smrtwellDetails->{'customizedCondition'});
	$smrtwellDetails->{'customizedMovieLength'} = '' unless (exists $smrtwellDetails->{'customizedMovieLength'});

	$smrtwellDetails->{'comments'} = escapeHTML($smrtwellDetails->{'comments'});
	$smrtwellDetails->{'comments'} =~ s/\n/<br>/g;
	my $smrtrun=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$smrtrun->execute($smrtwell[6]);
	my @smrtrun = $smrtrun->fetchrow_array();

	my $paclib = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$paclib->execute($smrtwell[3]);
	my @paclib=$paclib->fetchrow_array();
	my $paclibDetails = decode_json $paclib[8];
	my $sample;
	my $service;
	my $project;	
	my $paclibToSample=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$paclibToSample->execute($paclib[6]);
	my @paclibToSample = $paclibToSample->fetchrow_array();
	$sample = $paclibToSample[2] if ($paclibToSample[2]);
	if($paclibToSample[0])
	{
		my $sampleToService=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$sampleToService->execute($paclibToSample[6]);
		my @sampleToService = $sampleToService->fetchrow_array();
		$service = $sampleToService[2] if ($sampleToService[2]);
		if($sampleToService[0])
		{
			my $serviceToProject=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$serviceToProject->execute($sampleToService[6]);
			my @serviceToProject = $serviceToProject->fetchrow_array();
			$project = $serviceToProject[2] if ($serviceToProject[2]);
		}
	}

	$html =~ s/\$smrtrunId/$smrtrun[0]/g;
	$html =~ s/\$smrtrunName/$smrtrun[2]/g;
	$html =~ s/\$smrtwellId/$smrtwellId/g;
	$html =~ s/\$smrtwellName/$smrtwell[2]/g;
	$html =~ s/\$comments/$smrtwellDetails->{'comments'}/g;
	$html =~ s/\$smrtwellCellNumber/$smrtwell[4]/g;
	$html =~ s/\$movieLength/$movieLength{$smrtwell[5]}/g;
	if($smrtwell[5] == 0)
	{
		$html =~ s/\$customizedMovieLength/$smrtwellDetails->{'customizedMovieLength'}/g;
	}
	else
	{
		$html =~ s/\$customizedMovieLength//g;
	}
	$html =~ s/\$chemistry/$chemistry{$smrtwellDetails->{'chemistry'}}/g;
	$html =~ s/\$condition/$condition{$smrtwell[7]}/g;
	if($smrtwell[7] == 0)
	{
		$html =~ s/\$customizedCondition/$smrtwellDetails->{'customizedCondition'}/g;
	}
	else
	{
		$html =~ s/\$customizedCondition//g;
	}
	$html =~ s/\$paclibId/$smrtwell[3]/g;
	$html =~ s/\$paclibName/$project > $service > $sample > $paclib[2]/g;
	$html =~ s/\$concentration/$smrtwellDetails->{'concentration'}/g;
	$html =~ s/\$polRatio/$smrtwellDetails->{'polRatio'}/g;
	$html =~ s/\$loadingName/$smrtwellDetails->{'loadingName'}/g;
	$html =~ s/\$smrtwellCreator/$smrtwell[9]/g;
	$html =~ s/\$smrtwellEnteredDate/$smrtwell[10]/g;
	$html =~ s/\$\$/$$/g;

	print $html;
}
else
{
	print '402 Invalid operation';
	exit;
}

__DATA__
<table>
	<tr><td style='text-align:right;white-space: nowrap;'></td>
		<td><a onclick='closeDialog();openDialog("smrtrunView.cgi?smrtrunId=$smrtrunId")' title='View SMRT Run'>SMRT Run $smrtrunName</a></td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellName"><b>Sample Plate Well</b></label></td>
		<td>$smrtwellName</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><b>PacBio Library</b></td>
		<td><a onclick='closeDialog();openDialog("paclibView.cgi?paclibId=$paclibId")' title='View Paclib'>$paclibName</a> <sup class='ui-state-disabled'>(PacBio library id: $paclibId)</sup><br><input class='ui-widget-content ui-corner-all' name="loadingName" id="viewSmrtwellLoadingName" placeholder="Sample Name" title="SMRT Sample Name" size="20" type="text" value="$loadingName" readonly /></td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellCellNumber"><b>Cell number</b></label></td>
		<td>$smrtwellCellNumber</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellMovieLength"><b>Movie length</b></label></td>
		<td>$movieLength $customizedMovieLength</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellConcentration"><b>DNA concentration</b></label></td>
		<td>$concentration nM</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellPolRatio"><b>Polymerase ratio</b></label></td>
		<td>$polRatio</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellChemistry"><b>Chemistry</b></label></td>
		<td>$chemistry</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellCondition"><b>Condition</b></label></td>
		<td>$condition $customizedCondition</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'><label for="viewSmrtwellComments"><b>Comments</b></label></td>
		<td>$comments</td>
	</tr>
	<tr><td style='text-align:right;white-space: nowrap;'></td>
		<td><sup class='ui-state-disabled'>Last changed by $smrtwellCreator on $smrtwellEnteredDate</sup></td>
	</tr>
</table>	
<script>
$('#dialog').dialog("option", "title", "View Well $smrtwellName");
$( "#dialog" ).dialog( "option", "buttons", [{ text: "Edit", click: function() { closeDialog();openDialog("smrtwellEdit.cgi?smrtwellId=$smrtwellId"); } }, { text: "OK", click: function() {closeDialog(); } } ] );
</script>
