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

print header(-cookie=>cookie(-name=>'setting',-value=>0));

my $config = new config;
my $userConfig = new userConfig;

if ($role eq "admin"){
	my $configUsersPerPage = $config->getFieldDefaultWithFieldName("usersPerPage");
	my $usersPerPage = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"usersPerPage");
	my ($inputType, $lengthMenu, $inputDefault) = split(/:/, $configUsersPerPage);
	print <<eof;
	<div class='ui-state-highlight ui-corner-all' style='padding: 0 .7em;'>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='openDialogForm("userDeleteForm.cgi","userList$$")'>Delete</button>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='openDialogForm("userRoleForm.cgi","userList$$")'>Change role</button>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='openDialog("userNew.cgi")'>New user</button>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='refresh("settingTabs")'>Refresh</button>
	<h2>Users</h2>
	</div>

	<form id="userList$$" name="userList$$">
	<table id="userTable$$" class="display">
	<thead>
		<tr>
		<th>
			<input type='checkbox' id='checkAllBox$$' name='checkAllBox$$' value='Check all' checked='checked' onClick='checkAll(\"userId\");return false;' title='Check all'>
			<input type='checkbox' id='uncheckAllBox$$' name='uncheckAllBox$$' value='Uncheck all' onClick='uncheckAll(\"userId\");return false;' title='Uncheck all'>
		</th>
		<th>Username</th>
		<th>Role</th>
		<th>Full name</th>
		<th>Email</th>
		<th>Registration</th>
		<th>Status</th>
		</tr>
	</thead>
	<tbody>
eof
	my $rownumber = 0;
	my $allUsers = $user->getAllFieldsOfUser();
	foreach my $individualUser (@$allUsers){
		my $userName = $individualUser->{"userName"};
		my $userEmail = $userConfig->getFieldValueWithUserIdAndFieldName($individualUser->{"id"},"email");
		my $userFullName = $userConfig->getFieldValueWithUserIdAndFieldName($individualUser->{"id"},"firstName")." ".$userConfig->getFieldValueWithUserIdAndFieldName($individualUser->{"id"},"lastName");
		$rownumber++;
		my $userCheckbox="";
		my $userStatus="";
		my $userRole="";
		my $rowStyle="";
		my $rowClass="";
		if($individualUser->{"role"} eq "deleted")
		{
			$rowStyle = "text-decoration: line-through;";
			$rowClass = "ui-state-error";
			$userCheckbox = <<eof;
			<input type="checkbox" id="userId$rownumber$$" name="userId" value="$individualUser->{"id"}"/><label for="userId$rownumber$$">$rownumber</label>
eof
			$userRole = <<eof;
			<a onclick='openDialog("userRoleForm.cgi?userId=$individualUser->{"id"}")'><span class="ui-icon ui-icon-person" title="Deleted user" style="float:left;"></span>Deleted user</a>
eof
			$userStatus = <<eof;
			<td><span class="ui-icon ui-icon-cancel" title="Deleted user" style="float:left;"></span></td>
eof
		}
		else
		{
			$userCheckbox = <<eof;
			<input type="checkbox" id="userId$rownumber$$" name="userId" value="$individualUser->{"id"}"/><label for="userId$rownumber$$">$rownumber</label>
eof
			if($individualUser->{"role"} eq "admin")
			{
				$rowClass = "ui-state-highlight";
				$userRole = <<eof;
				<a onclick='openDialog("userRoleForm.cgi?userId=$individualUser->{"id"}")'><span class="ui-icon ui-icon-person" title="Administrator" style="float:left;"></span>Administrator</a>
eof
			}
			else
			{
				$userRole = <<eof;
				<a onclick='openDialog("userRoleForm.cgi?userId=$individualUser->{"id"}")'><span class="ui-icon ui-icon-person" title="Regular user" style="float:left;"></span>Regular user</a>
eof
			}

			if(length($individualUser->{"activation"}) == 18)
			{
				$rowClass = "ui-state-disabled";
				$userStatus = <<eof;
				<td><span class="ui-icon ui-icon-circle-plus" onclick="loaddiv('hiddenDiv','userActivate.cgi?activation=$individualUser->{"activation"}')" title="New and inactive user, click to activate this user." style="float:left;"></span></td>
eof
			}
			elsif(length($individualUser->{"activation"}) == 20)
			{
				$rowClass = "ui-state-disabled";
				$userStatus = <<eof;
				<td><span class="ui-icon ui-icon-circle-minus" onclick="loaddiv('hiddenDiv','userActivate.cgi?userId=$individualUser->{"id"}')" title="Inactive user, click to activate this user." style="float:left;"></span></td>
eof
			}
			else
			{
				if($individualUser->{"id"} eq $userId)
				{
					$userStatus = <<eof;
					<td><span class="ui-icon ui-icon-circle-check" title="You are an active user." style="float:left;"></span></td>
eof
				}
				else
				{
					$userStatus = <<eof;
					<td><span class="ui-icon ui-icon-circle-check" onclick="loaddiv('hiddenDiv','userDeactivate.cgi?userId=$individualUser->{"id"}')" title="Active user, click to deactivate this user." style="float:left;"></span></td>
eof
				}
			}
		}
		print <<eof;
		<tr id="userRow$rownumber" class="$rowClass" style="$rowStyle">
			<td style="white-space: nowrap; text-overflow:ellipsis; overflow:hidden;text-align:center">$userCheckbox</td>
			<td><a onclick='openDialog("userView.cgi?userId=$individualUser->{"id"}")'><b>$userName</b></a></td>
			<td>$userRole</td>
			<td>$userFullName</td>
			<td><a onclick='openDialog("userEmailForm.cgi?userId=$individualUser->{"id"}")' title="Send an email">$userEmail</a></td>
			<td>$individualUser->{"creation"}</td>
			$userStatus
		</tr>
eof
	}
	print	<<eof;
	</tbody>
	</table>
	</form>
	<script type="text/javascript">
	buttonInit();

	\$( "#userTable$$" ).dataTable({
		"scrollCollapse": true,
		"paging": true,
		"order": [ 1, 'asc' ],
		"lengthMenu": [ $lengthMenu ],
		"pageLength": $usersPerPage,
		"columnDefs": [
		{ "orderable": false, "targets": [0,2,-1] }
	  ]
	});

	</script>
eof
}

