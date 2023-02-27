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
if(!$userId)
{
	print header;
	print <<eof;
	<h2>Error</h2>
	Please <a onclick="openDialog('login.cgi');">login</a> first!
	<script type="text/javascript">
		openDialog('login.cgi');
		loadingHide();
	</script>
eof
    exit;
}

my $commoncfg = readConfig("main.conf");

print header(-cookie=>cookie(-name=>'menu',-value=>5));

my $user = new user;
my $config = new config;
my $userConfig = new userConfig;
my $active = 0;

my $userDetail = $user->getAllFieldsWithUserId($userId);
my $role = $userDetail->{"role"};
my $configRes = $config->getAllFields();
my %systemConfig = ();
my %userConfig = ();

foreach my $configHash ( @$configRes )
{
	my $type = $configHash->{"type"};
	my $fieldName = $configHash->{"fieldName"};
	$systemConfig{$type}{$fieldName}{"id"} = $configHash->{"id"};
	$systemConfig{$type}{$fieldName}{"fieldDefault"} = $configHash->{"fieldDefault"};	
	$systemConfig{$type}{$fieldName}{"fieldValue"} = $configHash->{"fieldValue"};	
	$systemConfig{$type}{$fieldName}{"fieldDescription"} = $configHash->{"fieldDescription"};	
	$systemConfig{$type}{$fieldName}{"weight"} = $configHash->{"weight"};
	if ($type eq "Site" || $type eq "Permission")
	{
		#do nothing;
	}
	else
	{
		$userConfig{$fieldName} = $userConfig->getFieldValueWithUserIdAndConfigId($userId,$systemConfig{$type}{$fieldName}{"id"});
	}
}

my $typeList = '';
my $settingDetails = '';

if ($role eq "admin")
{
	$active = cookie('setting') || 0;
	$typeList .= <<eof;
	<li><a href="user.cgi">Users</a></li>
	<li><a href="group.cgi">Group</a></li>
eof

	foreach my $type (sort keys %systemConfig){
		#skip Profile, Permission
		next if ($type eq "Profile");
		next if ($type eq "Permission");

		$typeList .= <<eof;
		<li><a href="#setting$type$$">$type</a></li>
eof
		if ($type eq "Site")
		{
			$settingDetails .= <<eof;
			<div id="setting$type$$" style="padding: 0 .1em;">
			<script type="text/javascript">
			\$( "#settingTable$type$$" ).dataTable({
				"paging": false,
				"ordering":  false
			});
			</script>
			<table class='display' id="settingTable$type$$">
			<thead>
			<tr>
				<th style="text-align: right;"><b>Site settings</b></th>
				<th style="text-align: left;">(for administrator only)</th>
			</tr>
			</thead>
			<tbody>
eof
		}
		else
		{
			$settingDetails .= <<eof;
			<div id="setting$type$$" style="padding: 0 .1em;">
			<script type="text/javascript">
			\$( "#settingTable$type$$" ).dataTable({
				"paging": false,
				"ordering":  false
			});
			</script>
			<table class='display' id="settingTable$type$$">
			<thead>
			<tr>
				<th style="text-align: right;"><b>$type</b></th>
				<th style="text-align: left;">Your settings</th>
				<th style="text-align: left;">System Default</th>
			</tr>
			</thead>
			<tbody>
eof
		}
		my $rownumber = 0;

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
			<tr id="settingRow$type$rownumber">
				<td style="text-align: right;"><b>$systemConfig{$type}{$fieldName}{"fieldDescription"}</b></td>
eof

			if ($type eq "Site")
			{
				if($inputType eq "textarea")
				{
					$settingDetails .= <<eof;
					<td><textarea rows="3" class="text ui-widget-content ui-corner-all" name="system$fieldName" style="width:40%;" onchange="updateSystemConfig($configId, this.value)">$fieldValue</textarea></td></tr>
eof
				}
				elsif($inputType eq "number"){
					$settingDetails .= <<eof;
					<td><select name="system$fieldName" onchange="updateSystemConfig($configId, this.value)">
eof
					my @inputOptions = split(/,/, $inputOptions);
					foreach my $optionValue (sort {$a <=> $b} @inputOptions){
						if($optionValue eq $fieldValue){
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
					<td><input type="text" class="datepicker text ui-widget-content ui-corner-all" name="system$fieldName" value="$fieldValue" onchange="updateSystemConfig($configId, this.value)" /></td></tr>
eof
				}
				else{
					$settingDetails .= <<eof;
					<td><input type="text" class="text ui-widget-content ui-corner-all" name="system$fieldName" value="$fieldValue" onchange="updateSystemConfig($configId, this.value)" /></td></tr>
eof
				}
			}
			else
			{
				if($inputType eq "textarea")
				{
					$settingDetails .= <<eof;
					<td><textarea rows="3" class="text ui-widget-content ui-corner-all" name="user$fieldName" style="width:40%;" onchange="updateUserConfig($configId, this.value)">$userConfig{$fieldName}</textarea></td>
					<td><textarea rows="3" class="text ui-widget-content ui-corner-all" name="system$fieldName" style="width:40%;" onchange="updateSystemConfig($configId, this.value)">$fieldValue</textarea></td></tr>
eof
				}
				elsif($inputType eq "number"){
					$settingDetails .= <<eof;
					<td><select name="user$fieldName" onchange="updateUserConfig($configId, this.value)">
eof
					my @inputOptions = split(/,/, $inputOptions);
					foreach my $optionValue (sort {$a cmp $b} @inputOptions){
						if($optionValue eq $userConfig{$fieldName}){
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
					</select></td>
					<td><select name="system$fieldName" onchange="updateSystemConfig($configId, this.value)">
eof
					foreach my $optionValue (sort {$a cmp $b} @inputOptions){
						if($optionValue eq $fieldValue){
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
					<td><input type="text" class="datepicker text ui-widget-content ui-corner-all" name="user$fieldName" value="$userConfig{$fieldName}" onchange="updateUserConfig($configId, this.value)" /></td>
					<td><input type="text" class="datepicker text ui-widget-content ui-corner-all" name="system$fieldName" value="$fieldValue" onchange="updateSystemConfig($configId, this.value)" /></td></tr>
eof
				}
				else{
					$settingDetails .= <<eof;
					<td><input type="text" class="text ui-widget-content ui-corner-all" name="user$fieldName" value="$userConfig{$fieldName}" onchange="updateUserConfig($configId, this.value)" /></td>
					<td><input type="text" class="text ui-widget-content ui-corner-all" name="system$fieldName" value="$fieldValue" onchange="updateSystemConfig($configId, this.value)" /></td></tr>
eof
				}
			}
		}

		$settingDetails .= <<eof;
			</tbody>
			</table>
		</div>
eof
	}
}
else
{
	foreach my $type (sort keys %systemConfig){
		#skip Profile, Site, Permission
		next if ($type eq "Profile");
		next if ($type eq "Site");
		next if ($type eq "Permission");

		$typeList .= <<eof;
		<li><a href="#setting$type$$">$type</a></li>
eof
		$settingDetails .= <<eof;
			<div id="setting$type$$" style="padding: 0 .1em;">
			<script type="text/javascript">
			\$( "#settingTable$type$$" ).dataTable({
				"paging": false,
				"ordering":  false
			});
			</script>
			<table class='display' id="settingTable$type$$">
			<thead>
			<tr>
				<th style="text-align: right;"><b>$type</b></th>
				<th style="text-align: left;">Your settings</th>
				<th style="text-align: left;">System Default</th>
			</tr>
			</thead>
			<tbody>
eof
		my $rownumber = 0;

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
			<tr id="settingRow$type$rownumber">
				<td style="text-align: right;"><b>$systemConfig{$type}{$fieldName}{"fieldDescription"}</b></td>
eof


			$fieldValue = escapeHTML($fieldValue);
			$fieldValue =~ s/\n/<br>/g;
			if($inputType eq "textarea")
			{
				$settingDetails .= <<eof;
				<td><textarea rows="3" class="text ui-widget-content ui-corner-all" name="user$fieldName" style="width:40%;" onchange="updateUserConfig($configId, this.value)">$userConfig{$fieldName}</textarea></td>
				<td>$fieldValue</td></tr>
eof
			}
			elsif($inputType eq "number"){
				$settingDetails .= <<eof;
				<td><select name="user$fieldName" onchange="updateUserConfig($configId, this.value)">
eof
				my @inputOptions = split(/,/, $inputOptions);
				foreach my $optionValue (sort {$a <=> $b} @inputOptions){
					if($optionValue eq $userConfig{$fieldName}){
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
				</select></td>
				<td>$fieldValue</td></tr>
eof
			}
			elsif($inputType eq "date"){
				$settingDetails .= <<eof;
				<td><input type="text" class="datepicker text ui-widget-content ui-corner-all" name="user$fieldName" value="$userConfig{$fieldName}" onchange="updateUserConfig($configId, this.value)" /></td>
				<td>$fieldValue</td></tr>
eof
			}
			else{
				$settingDetails .= <<eof;
				<td><input type="text" class="text ui-widget-content ui-corner-all" name="user$fieldName" value="$userConfig{$fieldName}" onchange="updateUserConfig($configId, this.value)" /></td>
				<td>$fieldValue</td></tr>
eof
			}
		}

		$settingDetails .= <<eof;
			</tbody>
			</table>
		</div>
eof
	}
}

print <<eof;
<div id="settingTabs">
	<ul>$typeList</ul>
	$settingDetails
</div>
<script type="text/javascript">
\$( "#settingTabs" ).tabs({active: $active}).addClass( "ui-tabs-vertical ui-helper-clearfix" );

\$( "#settingTabs li" ).removeClass( "ui-corner-top" ).addClass( "ui-corner-left" );

function updateSystemConfig(configId, value){
	\$.ajax({
	   type: "POST",
	   url: "settingSystem.cgi",
	   data: "configId="+configId+"&fieldValue="+encodeURIComponent(value),
	   success: function() {
			informationPop('System settings have been saved.');
	   }
	 });
}

function updateUserConfig(configId, value){
	\$.ajax({
	   type: "POST",
	   url: "settingUser.cgi",
	   data: "configId="+configId+"&fieldValue="+encodeURIComponent(value),
	   success: function() {
	   		informationPop('Your settings have been saved.');
	   }
	 });
}

loadingHide();
datepickerInit();

</script>
eof

