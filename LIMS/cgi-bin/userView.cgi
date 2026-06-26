#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use config;
use userConfig;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};
my $role = $userDetail->{"role"};

my $commoncfg = readConfig("main.conf");

print header();

my $config = new config;
my $userConfig = new userConfig;

my $userViewId = param("userId");

if ($role eq "admin" || $userId eq $userViewId){
	my $userDetail = $user->getAllFieldsWithUserId($userViewId);
	my $role = $userDetail->{"role"};
	my $configRes = $config->getAllFields();
	my %systemConfig = ();
	my %userConfig = ();
	
	foreach my $configHash ( @$configRes ){
		my $type = $configHash->{"type"};
		my $fieldName = $configHash->{"fieldName"};
		$systemConfig{$type}{$fieldName}{"id"} = $configHash->{"id"};
		$systemConfig{$type}{$fieldName}{"fieldDefault"} = $configHash->{"fieldDefault"};	
		$systemConfig{$type}{$fieldName}{"fieldValue"} = $configHash->{"fieldValue"};	
		$systemConfig{$type}{$fieldName}{"fieldDescription"} = $configHash->{"fieldDescription"};	
		$systemConfig{$type}{$fieldName}{"weight"} = $configHash->{"weight"};
		$userConfig{$fieldName} = $userConfig->getFieldValueWithUserIdAndConfigId($userViewId,$systemConfig{$type}{$fieldName}{"id"}) if ($type ne "Site");
	}
	my $settingDetails = <<eof;
	<table class="display" id="userDetails$$">
	<thead style="display: none;">
	<tr><th>Key</th><th>Value</th></tr>
	</thead>
	<tbody>
	<tr>
		<td style="text-align: right;"><b>Username</b></td>
		<td>$userDetail->{"userName"} (id: $userViewId)</td>
	</tr>
	<tr>
		<td style="text-align: right;"><b>Role</b></td>
		<td>$userDetail->{"role"}</td>
	</tr>
	<tr>
		<td style="text-align: right;"><b>Registration</b></td>
		<td>$userDetail->{"creation"}</td>
	</tr>
eof

	my $rownumber = 0;
	my $type = "Profile";
	foreach my $fieldName (sort { $systemConfig{$type}{$a}{"weight"} <=> $systemConfig{$type}{$b}{"weight"} } keys % { $systemConfig{$type} } )
	{
		my $fieldDefault = $systemConfig{$type}{$fieldName}{"fieldDefault"};
		my ($inputType, $inputOptions, $inputDefault) = split(/:/, $fieldDefault);
		my $fieldValue = $systemConfig{$type}{$fieldName}{"fieldValue"};
		if( !defined $fieldValue || !$fieldValue ){
			$fieldValue =  $inputDefault;
		}
		my $configId = $systemConfig{$type}{$fieldName}{"id"};
		$rownumber++;
		$settingDetails .= <<eof;
		<tr id="userDetailRow$rownumber">
			<td style="text-align: right;"><b>$systemConfig{$type}{$fieldName}{"fieldDescription"}</b></td>
			<td>$userConfig{$fieldName}</td>
		</tr>
eof
	}
	$settingDetails .= <<eof;
		</tbody>
		</table>
eof
	print <<eof;
	<div id="settingDetails$$"  name="settingDetails$$">
	$settingDetails
	</div>
	<script type="text/javascript">
		\$( "#userDetails$$" ).dataTable({
			"dom": 'lfrtip',
			"scrollCollapse": false,
			"paging": false,
			"searching": false,
			"ordering": false,
			"info": false
		});
		\$('#dialog').dialog("option", "title", "User profile");
		\$( "#dialog" ).dialog( "option", "buttons", [{ text: "Edit", click: function() { closeDialog();openDialog("userEdit.cgi?userId=$userViewId"); } } ,{ text: "Print", click: function() {printDiv('settingDetails$$'); } },  { text: "OK", click: function() {closeDialog(); } } ] );
	</script>
eof
}
