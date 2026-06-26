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
my $userViewerId = param("userId");

if ($role eq "admin" || $userId eq $userViewerId){
	my $userDetail = $user->getAllFieldsWithUserId($userViewerId);
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
		$userConfig{$fieldName} = $userConfig->getFieldValueWithUserIdAndConfigId($userViewerId,$systemConfig{$type}{$fieldName}{"id"}) if ($type ne "Site");
	}
	my $settingDetails = <<eof;
	<table class="display" id="userEdit$$">
	<thead style="display: none;">
	<tr>
		<th>Key</th>
		<th>Value</th>
	</tr>
	</thead>
	<tbody>
	<tr>
		<td style="text-align: right;"><b>Username</b></td>
		<td>$userDetail->{"userName"} (id: $userViewerId)</td>
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
		<tr id="userEditRow$rownumber">
			<td style="text-align: right;"><b>$systemConfig{$type}{$fieldName}{"fieldDescription"}</b></td>
eof

		if($inputType eq "textarea")
		{
			$settingDetails .= <<eof;
			<td><textarea rows="3" class="text ui-widget-content ui-corner-all" style="width:100%;" name="userEdit$fieldName" onchange="userEditSave($userViewerId,$configId, this.value)">$userConfig{$fieldName}</textarea></td></tr>
eof
		}
		elsif($inputType eq "number"){
			$settingDetails .= <<eof;
			<td><select name="userEdit$fieldName" onchange="userEditSave($userViewerId,$configId, this.value)">
eof
			my @input_options = split(/,/, $inputOptions);
			foreach my $optionValue (sort {$a <=> $b} @input_options){
				if($optionValue == $userConfig{$fieldName}){
					$settingDetails .= <<eof;
					<option value="$optionValue" selected="selected">$optionValue</option>
eof
				}else{
					$settingDetails .= <<eof;
					<option value="$optionValue" >$optionValue</option>
eof
				}
			}
			$settingDetails .= <<eof;
			</select></td></tr>
eof
		}
		elsif($inputType eq "date"){
			$settingDetails .= <<eof;
			<td><input type="text" class="datepicker text ui-widget-content ui-corner-all" name="userEdit$fieldName" value="$userConfig{$fieldName}" onchange="userEditSave($userViewerId,$configId, this.value)" /></td></tr>
eof
		}
		else{
			$settingDetails .= <<eof;
			<td><input type="text" class="text ui-widget-content ui-corner-all" name="userEdit$fieldName" value="$userConfig{$fieldName}" style="width:50%;" onchange="userEditSave($userViewerId,$configId, this.value)" /></td></tr>
eof
		}
	}

	$settingDetails .= <<eof;
		</table>
	<script type="text/javascript">
		\$( "#userEdit$$" ).dataTable({
			"dom": 'lfrtip',
			"scrollCollapse": false,
			"paging": false,
			"searching": false,
			"ordering": false,
			"info": false
		});
		\$('#dialog').dialog("option", "title", "Edit user profile");
		\$( "#dialog" ).dialog( "option", "buttons", [{ text: "OK", click: function() {closeDialog(); } } ] );
		function userEditSave(userId, configId, value){
			\$.ajax({
			   type: "POST",
			   url: "userEditSave.cgi",
			   data: "userId="+userId+"&configId="+configId+"&fieldValue="+encodeURIComponent(value),
			   success: function() {
					informationPop('User settings have been saved.');
					refresh("settingTabs");
			   }
			 });
		}
		datepickerInit();
	</script>
eof

	print $settingDetails;
}



