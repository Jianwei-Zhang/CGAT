#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use SVG;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});
my $assemblyId = param ('assemblyId') || '';

if ($assemblyId)
{
	print header(-cookie=>cookie(-name=>'assembly',-value=>$assemblyId));
	my $assembly=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$assembly->execute($assemblyId);
	my @assembly = $assembly->fetchrow_array();

	my $target=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$target->execute($assembly[4]);
	my @target = $target->fetchrow_array();
	my $assemblySeq;
	my $assemblySeqs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblySeq' AND o = ?");
	$assemblySeqs->execute($assembly[0]);
	while(my @assemblySeqs = $assemblySeqs->fetchrow_array())
	{
		$assemblySeq->{$assemblySeqs[5]} = $assemblySeqs[4];
	}
	my $totalSequenced = 0;
	my $col = 3;
	my $sequenced = "<table width='100%'>";

	if($target[1] eq 'library')
	{
		my $getClones = $dbh->prepare("SELECT * FROM clones WHERE libraryId = ? AND sequenced > 0");
		$getClones->execute($assembly[4]);
		while(my @getClones= $getClones->fetchrow_array())
		{
			my $getSeqs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o < 50 AND name LIKE ? ORDER BY id");
			$getSeqs->execute($getClones[1]);
			while(my @getSeqs = $getSeqs->fetchrow_array())
			{
				next if (exists $assemblySeq->{$getSeqs[0]});
				$getSeqs[5] = commify ($getSeqs[5]);
				if($totalSequenced % $col == 0)
				{
					$sequenced .= "<tr><td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td>";
				}
				elsif($totalSequenced % $col == $col - 1)
				{
					$sequenced .= "<td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td></tr>";
				}
				else
				{
					$sequenced .= "<td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td>";
				}
				$totalSequenced++;
			}
		}
	}
	if($target[1] eq 'genome')
	{
		my $getSeqs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'sequence' AND o = 99 AND x = ? ORDER BY name");
		$getSeqs->execute($assembly[4]);
		while(my @getSeqs = $getSeqs->fetchrow_array())
		{
			next if (exists $assemblySeq->{$getSeqs[0]});
			$getSeqs[5] = commify ($getSeqs[5]);
			if($totalSequenced % $col == 0)
			{
				$sequenced .= "<tr><td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td>";
			}
			elsif($totalSequenced % $col == $col - 1)
			{
				$sequenced .= "<td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td></tr>";
			}
			else
			{
				$sequenced .= "<td><a onclick='closeDialog();openDialog(\"seqView.cgi?seqId=$getSeqs[0]\")' title='$getSeqs[2]'>$getSeqs[2]</a> ($getSeqs[5] bp)</td>";
			}
			$totalSequenced++;
		}
	}
	if($totalSequenced % $col > 0)
	{
		my $colspan = $col - $totalSequenced % $col;
		$sequenced .= "<td colspan='$colspan'></td></tr></table>";
	}
	else
	{
		$sequenced .= "</table>";
	}

	my $title = ($totalSequenced > 1) ? "<h2>$totalSequenced Sequences Available</h2>" : "<h2>$totalSequenced Sequence Available</h2>";
	print "$title$sequenced";
}
else
{
	print header(-type=>'text/html',-status=>'402 Invalid operation');
	exit;
}
