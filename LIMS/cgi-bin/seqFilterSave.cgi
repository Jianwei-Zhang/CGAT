#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS;
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use config;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $json = JSON::XS->new->allow_nonref;
my $seqId = param ('seqId') || '';
my $filter = param ('filter') || '';

my $config = new config;
my $userPermission;
my $userInGroup=$dbh->prepare("SELECT * FROM link WHERE type LIKE 'group' AND child = ?");
$userInGroup->execute($userId);
while (my @userInGroup = $userInGroup->fetchrow_array())
{
	my $group = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$group->execute($userInGroup[0]);
	my @group=$group->fetchrow_array();
	my $groupDetails = decode_json $group[8];
	$groupDetails->{'permission'} = '' unless (exists $groupDetails->{'permission'});
	for(split (",",$groupDetails->{'permission'}))
	{
		my $permission = $config->getFieldName($_);
		$userPermission->{$userId}->{$permission} = 1;		
	}
}

print header;

if($seqId)
{
	my $checkCreator = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkCreator->execute($seqId);
	my @checkCreator=$checkCreator->fetchrow_array();
	my $sequenceDetails = decode_json $checkCreator[8];
	my $length = $checkCreator[5];
	my %filterStart;
	for my $filterDetail(split /\,/,$filter)
	{
		$filterDetail =~ s/\s+//;
		if($filterDetail !~ /^\d+-\d+/)
		{
			print <<END;
	<input class='ui-widget-content ui-corner-all' name="filter" id="editSeqFilter" size="32" type="text" maxlength="32" value="$filter"  placeholder="Sequence Filter" onBlur="loaddiv('seqFilter$seqId','seqFilterSave.cgi?seqId=$seqId&filter='+this.value)"/>
	<script>
		errorPop("Not a valid format!");	
	</script>	
END
			exit;	
		}
		else
		{
			my ($start,$end) = split /\-/,$filterDetail;
			if($start > $checkCreator[5] or $end > $checkCreator[5] or $start > $end)
			{
				print <<END;
	<input class='ui-widget-content ui-corner-all' name="filter" id="editSeqFilter" size="32" type="text" maxlength="32" value="$filter"  placeholder="Sequence Filter" onBlur="loaddiv('seqFilter$seqId','seqFilterSave.cgi?seqId=$seqId&filter='+this.value)"/>
	<script>
		errorPop("Not a valid format!");	
	</script>	
END
				exit;
			}
			else
			{
				if(exists $filterStart{$start})
				{
					$filterStart{$start} = $end if($filterStart{$start} < $end);
				}
				else
				{
					$filterStart{$start} = $end;
				}
			}
		}
	}

	my @goodStart;
	my ($lastStart,$eachStart);
	my $lastEnd = -1;
	for $eachStart(sort {$a<=>$b} keys %filterStart)
	{
		if ($eachStart > $lastEnd + 1)
		{
			push @goodStart,$eachStart;
			$lastEnd = $filterStart{$eachStart};
			$lastStart = $eachStart;
		}
		else
		{
			$filterStart{$lastStart} = $filterStart{$eachStart} if($filterStart{$eachStart} > $lastEnd);
		}
	}
	my $goodFilter = '';
	foreach (@goodStart){
		$goodFilter .= ($goodFilter) ? ",$_-$filterStart{$_}" : "$_-$filterStart{$_}";
	}
	if($checkCreator[9] eq $userName || exists $userPermission->{$userId}->{'sequence'})
	{
		$sequenceDetails->{'filter'} = $goodFilter;
		my $sequenceDetailsEncoded = $json->encode($sequenceDetails);
		my $updateSequence=$dbh->prepare("UPDATE matrix SET note = ?, creator = ? WHERE id = ?");
		$updateSequence->execute($sequenceDetailsEncoded,$userName,$seqId);
		$sequenceDetails->{'filter'} = 'noFilter' unless ($sequenceDetails->{'filter'});
		print <<END;
<a id='seqFilter$seqId$$' onmouseover='editIconShow("seqFilter$seqId$$")' onmouseout='editIconHide("seqFilter$seqId$$")' onclick="loaddiv('seqFilter$seqId','seqFilterEdit.cgi?seqId=$seqId')" title="Edit this filter">$sequenceDetails->{'filter'}</a>
END
	}
	else
	{
		$sequenceDetails->{'filter'} = 'none' unless ($sequenceDetails->{'filter'});
		print <<END;
<a id='seqFilter$seqId$$' onmouseover='editIconShow("seqFilter$seqId$$")' onmouseout='editIconHide("seqFilter$seqId$$")' onclick="loaddiv('seqFilter$seqId','seqFilterEdit.cgi?seqId=$seqId')" title="Edit this filter">$sequenceDetails->{'filter'}</a>
<script>
	errorPop("Not a valid user! No changes take place.");
</script>	
END
	}
}
else
{
	print <<END;
<a class='ui-state-error ui-corner-all'>Error: Not a valid operation!</a>
<script>
	errorPop("Not a valid operation!");
</script>	
END
}