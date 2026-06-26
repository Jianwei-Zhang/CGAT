#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use JSON::XS;
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
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

print header(-cookie=>cookie(-name=>'setting',-value=>1));
my $config = new config;
my $userConfig = new userConfig;

if ($role eq "admin"){
	my $configGroupsPerPage = $config->getFieldDefaultWithFieldName("groupsPerPage");
	my $groupsPerPage = $userConfig->getFieldValueWithUserIdAndFieldName($userId,"groupsPerPage");
	my ($inputType, $lengthMenu, $inputDefault) = split(/:/, $configGroupsPerPage);
	print <<eof;
	<div class='ui-state-highlight ui-corner-all' style='padding: 0 .7em;'>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='openDialog("groupNew.cgi")'>New group</button>
		<button style='float: right; margin-top: .3em; margin-right: .3em;' onclick='refresh("settingTabs")'>Refresh</button>
	<h2>Group</h2>
	</div>

	<table id="groupTable$$" class="display">
	<thead>
		<tr>
		<th>No.</th>
		<th>Group</th>
		<th>Users</th>
		<th>Management Permissions</th>
		</tr>
	</thead>
	<tbody>
eof
	my $rownumber = 0;

	my $allGroup=$dbh->prepare("SELECT * FROM matrix WHERE container Like 'group'");
	$allGroup->execute();
	while (my @allGroup = $allGroup->fetchrow_array())
	{
		my $relatedUsers = '';
		my $relatedUser=$dbh->prepare("SELECT * FROM link WHERE type LIKE 'group' AND parent = $allGroup[0]");
		$relatedUser->execute();
		while (my @relatedUser = $relatedUser->fetchrow_array())
		{
			my $relatedUserDetail = $user->getAllFieldsWithUserId($relatedUser[1]);
			$relatedUsers .= "<li class='ui-state-highlight'><a onclick='openDialog(\"userView.cgi?userId=$relatedUser[1]\")'>$relatedUserDetail->{'userName'}</a></li>";
		}

		my $groupDetails = decode_json $allGroup[8];
		$groupDetails->{'permission'} = '' unless (exists $groupDetails->{'permission'});
		$groupDetails->{'description'} = '' unless (exists $groupDetails->{'description'});
		$groupDetails->{'description'} = escapeHTML($groupDetails->{'description'});
		$groupDetails->{'description'} =~ s/\n/<br>/g;
		my $permissionList = '';
		for(split (",",$groupDetails->{'permission'}))
		{
			$permissionList .= "<li class='ui-state-default'>". $config->getFieldDescription($_) . "</li>";
		}
		$rownumber++;
		print <<eof;
		<tr id="groupRow$rownumber">
			<td style="white-space: nowrap; text-overflow:ellipsis; overflow:hidden;text-align:center">$rownumber</td>
			<td><a onclick='openDialog("groupEdit.cgi?groupId=$allGroup[0]")'><b>$allGroup[2]</b></a><hr><sub>$groupDetails->{'description'}</sub></td>
			<td><ul class='gridGroupList'>$relatedUsers</ul></td>
			<td><ul class='gridGroupList'>$permissionList</ul></td>
		</tr>
eof
	}
	print	<<eof;
	</tbody>
	</table>
	<style>
		.gridGroupList { list-style-type: none; display:inline-block;margin: 0; padding: 0; width: 100%; }
		.gridGroupList li { margin: 3px 3px 3px 0; padding: 1px; float: left; width: 80px; text-align: center; }
	</style>
	<script type="text/javascript">
	buttonInit();
	\$( "#groupTable$$" ).dataTable({
		"scrollCollapse": true,
		"paging": true,
		"order": [ 1, 'asc' ],
		"lengthMenu": [ $lengthMenu ],
		"pageLength": $groupsPerPage,
		"columnDefs": [
		{ "orderable": false, "targets": [0,-2,-1] }
	  ]
	});
	</script>
eof
}

