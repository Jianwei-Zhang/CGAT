#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS; #JSON::XS is recommended to be installed for handling JSON string of big size 
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

my $assemblyId = param ('assemblyId')|| '';

print header;

if ($assemblyId)
{
	my $assembly=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$assembly->execute($assemblyId);
	my @assembly = $assembly->fetchrow_array();

	unless ($assembly[7] == 1 || $assembly[7] == 0) # exit if for frozen or running assembly
	{
		print <<END;
<script>
	closeDialog();
	parent.errorPop("This assembly is running or frozen.");
</script>	
END
		exit;
	}

	my $deleteEmptyAssemblyCtg = $dbh->prepare("DELETE FROM matrix WHERE container LIKE 'assemblyCtg' AND note = '' AND o = ?");
	$deleteEmptyAssemblyCtg->execute($assemblyId);

	my %assemblySeqToCtg;
	my %seqCount;
	my %hideSeqCtg;
	my %hideCount;
	my $ctgNumber=1;
	my $validateAssemblyCtg=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? ORDER BY name");
	$validateAssemblyCtg->execute($assemblyId);
	while(my @validateAssemblyCtg = $validateAssemblyCtg->fetchrow_array())
	{
		$ctgNumber = $validateAssemblyCtg[2] if ($validateAssemblyCtg[2] > $ctgNumber);
		my $newSeqIdList='';
		foreach (split ",", $validateAssemblyCtg[8])
		{
			# Generate newSeqIdList
			next unless ($_=~/\S/);
			$_  =~ s/^(\-{2,})/-/g;
			my $newSeqId=$_;
			$_ =~ s/[^a-zA-Z0-9]//g;
			my $assemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE id = ? ");
			$assemblySeq->execute($_);			
			my @assemblySeq = $assemblySeq->fetchrow_array();
			if ($assemblySeq->rows > 0)
			{
				my $sequence=$dbh->prepare("SELECT * FROM matrix WHERE id = ? ");
				$sequence->execute($assemblySeq[5]);
				if ($sequence->rows > 0)
				{
					if ($newSeqIdList)
					{
						$newSeqIdList .= ','.$newSeqId;
					}
					else
					{
						$newSeqIdList=$newSeqId;
					}
				}
				else
				{
					my $deleteAssemblySeq=$dbh->do("DELETE FROM matrix WHERE id = $assemblySeq[0]");
					next;
				}
			}

			$hideCount{$_}++ if ($newSeqId =~/^(\-{1,})/ );
			$hideSeqCtg{$_}{$validateAssemblyCtg[2]} = 1 if ($newSeqId =~/^(\-{1,})/ );
			$seqCount{$_}++;
			$assemblySeqToCtg{$_}{$validateAssemblyCtg[2]} = $newSeqId;
		}
		my $updateNewAssemblyCtg=$dbh->prepare("UPDATE matrix SET note = ? WHERE id = ?");
		$updateNewAssemblyCtg->execute($newSeqIdList,$validateAssemblyCtg[0]);
	}
	$ctgNumber++;
	for my $seqInCtg(keys %seqCount)
	{
		if ($seqCount{$seqInCtg}>1)
		{
			my @ctgName=keys %{$assemblySeqToCtg{$seqInCtg}};
			my $realCtg=0;
			if (!exists $hideCount{$seqInCtg} or $hideCount{$seqInCtg} == $seqCount{$seqInCtg})
			{
				for my $ctgName(@ctgName)
				{
					if ($realCtg == 0)
					{
						$realCtg=$ctgName;
					}
					else
					{
						$realCtg=$realCtg > $ctgName ? $realCtg : $ctgName;
						my $deleteAssemblyCtg = $dbh->prepare("DELETE FROM matrix WHERE container LIKE 'assemblyCtg' AND name = ? AND o = ?");
						$deleteAssemblyCtg->execute($realCtg,$assemblyId);
					}
				}
			}
			else
			{
				my $retain=0;
				for my $ctgName(@ctgName)
				{
					if ( !exists $hideSeqCtg{$seqInCtg}{$ctgName} && $retain == 0)
					{
						$retain++;
						next;
					}
					else
					{
						my $deleteAssemblyCtg = $dbh->prepare("DELETE FROM matrix WHERE container LIKE 'assemblyCtg' AND name = ? AND o = ?");
						$deleteAssemblyCtg->execute($ctgName,$assemblyId);
					}
				}
			}
		}
	}

	#assemblySeq does not appears in the assemblyCtg
	my $validateCtgLength;
	my ($validateAssemblySeqStart,$validateAssemblySeqEnd);
	my $validateAssemblySeq=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblySeq' AND o = ?");
	$validateAssemblySeq->execute($assemblyId);
	while (my @validateAssemblySeq = $validateAssemblySeq->fetchrow_array())
	{
		unless (exists $seqCount{$validateAssemblySeq[0]})
		{
			my $filterLength = 0;
			($validateAssemblySeqStart,$validateAssemblySeqEnd) = split ",",$validateAssemblySeq[8];
			my $validateSequence = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$validateSequence->execute($validateAssemblySeq[5]);
			my @validateSequence =  $validateSequence->fetchrow_array();
			my $validateSequenceDetails = decode_json $validateSequence[8];
			$validateSequenceDetails->{'filter'} = '' unless (exists $validateSequenceDetails->{'filter'});
			if ($validateSequenceDetails->{'filter'}) 
			{
				foreach (split ",", $validateSequenceDetails->{'filter'} )
				{
					my ($filterStart,$filterEnd) = split "-", $_;
					next if ($validateAssemblySeqStart > $filterEnd);
					next if ($validateAssemblySeqEnd < $filterStart);
					if ($validateAssemblySeqStart >= $filterStart && $validateAssemblySeqEnd <= $filterEnd)
					{
						$filterLength += $validateAssemblySeqEnd - $validateAssemblySeqStart + 1;
					}
					elsif ($validateAssemblySeqStart >= $filterStart && $validateAssemblySeqStart <= $filterEnd)
					{
						$filterLength += $filterEnd - $validateAssemblySeqStart + 1;
					}
					elsif ($validateAssemblySeqEnd >= $filterStart && $validateAssemblySeqEnd <= $filterEnd)
					{
						$filterLength += $validateAssemblySeqEnd - $filterStart + 1;
					}
					else
					{
						$filterLength += $filterEnd - $filterStart + 1;
					}
				}
			}
			$validateCtgLength += $validateAssemblySeqEnd - $validateAssemblySeqStart + 1 - $filterLength;
			my $insertAssemblyCtg=$dbh->prepare("INSERT INTO matrix VALUES ('', 'assemblyCtg', ?, ?, 0, 0, 0, ?, ?, ?, NOW())");
			$insertAssemblyCtg->execute($ctgNumber,$assemblyId,$validateCtgLength,"($validateAssemblySeq[0])",$userName);
			$ctgNumber++;
		}
	}

	print <<END;
<script>
	parent.informationPop("The assembly has been corrected!");
</script>	
END
	
}
else
{
	print <<END;
<script>
	parent.errorPop("Choose a assemblyId!");
</script>	
END
}
