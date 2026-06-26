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
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $user = new user;
my $userDetail = $user->getAllFieldsWithUserId($userId);
my $userName = $userDetail->{"userName"};

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $assemblyCtgId = param ('assemblyCtgId') || '';
my $assemblyCtgNumber = param ('assemblyCtgNumber') || '';
my $assemblyChr = param ('assemblyChr') || '0';
my $assemblyPosition = param ('assemblyPosition') || '0';
$assemblyPosition =~ s/\D//g;
$assemblyPosition = 0 if ($assemblyChr eq 0);
my $assemblySeqs = param ('assemblySeqs') || '';
my $insertSeq = param ('insertSeq') || '';
my $appendCtg = param ('appendCtg') || '0';
my $appendCtgNumber = param ('appendCtgNumber') || '';
$appendCtgNumber =~ s/\D//g;
my $flipCtg = param ('flipCtg') || '0';
my $assemblyId = param ('assemblyId') || '';
my $chr = param ('chr') || '0';
my $scrollLeft = param ('scrollLeft') || '0';

print header;

if($assemblyCtgId && $assemblySeqs)
{
	my $checkAssemblyCtg = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkAssemblyCtg->execute($assemblyCtgId);
	if($checkAssemblyCtg->rows < 1)
	{
		print <<END;
<script>
	parent.errorPop("Not a valid operation!");
</script>	
END
	}
	else
	{
		my @checkAssemblyCtg = $checkAssemblyCtg->fetchrow_array();
		if($insertSeq)
		{
			my $getSequence = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$getSequence->execute($insertSeq);
			my @getSequence = $getSequence->fetchrow_array();
			my $insertAssemblySeq=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assemblySeq', ?, ?, 0, ?, ?, 1, ?, ?, NOW())");
			$insertAssemblySeq->execute($getSequence[2],$checkAssemblyCtg[3],$getSequence[0],$getSequence[5],"1,$getSequence[5]",$userName);
			my $assemblySeqId = $dbh->{mysql_insertid};
			$assemblySeqs .= ",($assemblySeqId)";
		}
		my $updateAssemblyCtg=$dbh->prepare("UPDATE matrix SET name = ?, x = ?, z = ?, note = ? WHERE id = ?");
		$updateAssemblyCtg->execute($assemblyCtgNumber,$assemblyChr,$assemblyPosition,$assemblySeqs,$assemblyCtgId);

		if($appendCtg && $appendCtgNumber && ($appendCtgNumber ne $assemblyCtgNumber))
		{
			my $checkAssemblyCtgToAppend = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? AND name LIKE ?");
			$checkAssemblyCtgToAppend->execute($checkAssemblyCtg[3],$appendCtgNumber);
			my @checkAssemblyCtgToAppend = $checkAssemblyCtgToAppend->fetchrow_array();
			if($flipCtg)
			{
				$checkAssemblyCtgToAppend[8] = join ",", (reverse split ",", $checkAssemblyCtgToAppend[8]);
				foreach (split ",", $checkAssemblyCtgToAppend[8])
				{
					next unless ($_);
					$_ =~ s/[^a-zA-Z0-9]//g;
					my $updateAssemblySeq=$dbh->do("UPDATE matrix SET barcode = barcode * (-1) WHERE id = $_");
				}
			}
			my $updateAssemblyCtg=$dbh->prepare("UPDATE matrix SET barcode = ?,note = ? WHERE id = ?");
			$updateAssemblyCtg->execute($checkAssemblyCtg[7]+$checkAssemblyCtgToAppend[7],"$assemblySeqs,$checkAssemblyCtgToAppend[8]",$assemblyCtgId);
			my $deleteAssemblyCtg=$dbh->do("DELETE FROM matrix WHERE id = $checkAssemblyCtgToAppend[0]");
			#merge comments
			my $checkCommentForAppendCtg=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'comment' AND o = ?");
			$checkCommentForAppendCtg->execute($checkAssemblyCtgToAppend[0]);
			if($checkCommentForAppendCtg->rows > 0)
			{
				my @checkCommentForAppendCtg = $checkCommentForAppendCtg->fetchrow_array();
				my $appendCtgCommentDetails = decode_json $checkCommentForAppendCtg[8];
				$appendCtgCommentDetails->{'description'} = '' unless (exists $appendCtgCommentDetails->{'description'});
				my $checkComment=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'comment' AND o = ?");
				$checkComment->execute($assemblyCtgId);
				if($checkComment->rows > 0)
				{
					my @checkComment = $checkComment->fetchrow_array();
					my $commentDetails = decode_json $checkComment[8];
					$commentDetails->{'description'} = '' unless (exists $commentDetails->{'description'});
					$commentDetails->{'description'} .= "\n".$appendCtgCommentDetails->{'description'};
					my $json = JSON::XS->new->allow_nonref;
					my $newCommentDetails = $json->encode($commentDetails);
					my $updateComment=$dbh->prepare("UPDATE matrix SET note = ? WHERE id = ?");
					$updateComment->execute($newCommentDetails,$checkComment[0]);
					my $deleteComment=$dbh->do("DELETE FROM matrix WHERE container LIKE 'comment' AND o = $checkAssemblyCtgToAppend[0]");
				}
				else
				{
					my $updateComment=$dbh->do("UPDATE matrix SET o = $assemblyCtgId WHERE container LIKE 'comment' AND o = $checkAssemblyCtgToAppend[0]");
				}
			}
		}
		my $assignedChrOrder = 0;
		my $assemblyCtgs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? AND x = ? ORDER BY z");
		$assemblyCtgs->execute($checkAssemblyCtg[3],$assemblyChr);
		while(my @assemblyCtgs = $assemblyCtgs->fetchrow_array())
		{
			my $updateAssemblyCtg=$dbh->do("UPDATE matrix SET y = $assignedChrOrder WHERE id = $assemblyCtgs[0]");
			$assignedChrOrder++;
		}

		if($assemblyId)
		{
			print <<END;
<script>
parent.closeDialog();
parent.closeViewer();
parent.openViewer("assemblyChrView.cgi?assemblyId=$assemblyId&chr=$chr&scrollLeft=$scrollLeft");
</script>	
END
		}
		else
		{
			if($assemblyChr != $checkAssemblyCtg[4] || $appendCtg || $assemblyCtgNumber ne $checkAssemblyCtg[2])
			{
				if($chr)
				{
					print <<END;
<script>
parent.closeDialog();
parent.refresh("menu");
parent.closeViewer();
parent.openViewer("assemblyChrView.cgi?assemblyId=$checkAssemblyCtg[3]&chr=$chr&scrollLeft=$scrollLeft");
</script>	
END
				}
				else
				{
					print <<END;
<script>
parent.closeDialog();
parent.refresh("menu");
parent.closeViewer();
parent.openViewer("assemblyCtgView.cgi?assemblyCtgId=$assemblyCtgId&scrollLeft=$scrollLeft");
</script>	
END
				}
			}
			else
			{
				if($chr)
				{
					print <<END;
<script>
parent.closeDialog();
parent.closeViewer();
parent.openViewer("assemblyChrView.cgi?assemblyId=$checkAssemblyCtg[3]&chr=$chr&scrollLeft=$scrollLeft");
</script>	
END
				}
				else
				{
					print <<END;
<script>
parent.closeDialog();
parent.closeViewer();
parent.openViewer("assemblyCtgView.cgi?assemblyCtgId=$assemblyCtgId&scrollLeft=$scrollLeft");
</script>	
END
				}
			}
		}
	}
}
else
{
	print <<END;
<script>
	parent.errorPop("Not a valid operation!");
</script>	
END
}