#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
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

my $assemblyId = param ('assemblyId') || '';
my $assemblyCtgId = param ('assemblyCtgId') || '';
my $chr = param ('chr') || '0';
my $scrollLeft = param ('scrollLeft') || '0';

print header;
if($assemblyId)
{
	my $assembly=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$assembly->execute($assemblyId);
	my @assembly = $assembly->fetchrow_array();

	unless ($assembly[7] == 1 || $assembly[7] == 0) # exit if for frozen or running assembly
	{
		print <<END;
<script>
	parent.closeDialog();
	parent.errorPop("This assembly is running or frozen.");
</script>	
END
		exit;
	}
	my $allAssemblyCtg=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? ORDER BY name");
	$allAssemblyCtg->execute($assemblyId);
	while(my @allAssemblyCtg = $allAssemblyCtg->fetchrow_array())
	{
		my $assemblyCtgLength = 0;
		foreach (split ",", $allAssemblyCtg[8])
		{
			$_ =~ s/[^a-zA-Z0-9]//g;
			my $assemblySeqList=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$assemblySeqList->execute($_);
			my @assemblySeqList = $assemblySeqList->fetchrow_array();
			my $updateAssemblyClone=$dbh->do("UPDATE matrix SET note = '1,$assemblySeqList[6]' WHERE id = $assemblySeqList[0]");
			$assemblyCtgLength += $assemblySeqList[6];
		}
		my $updateAssemblyCtgLength=$dbh->do("UPDATE matrix SET barcode = $assemblyCtgLength WHERE id = $allAssemblyCtg[0]");
	}
	print <<END;
<script>
	parent.closeDialog();
	parent.informationPop("The assembly redundancy has been reset!");
</script>	
END

}
elsif($assemblyCtgId)
{
	my $checkAssemblyCtg = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
	$checkAssemblyCtg->execute($assemblyCtgId);
	if($checkAssemblyCtg->rows < 1)
	{
		print <<END;
<script>
	errorPop("Not a valid operation!");
</script>	
END
	}
	else
	{
		my @checkAssemblyCtg = $checkAssemblyCtg->fetchrow_array();
		my $assemblyCtgLength = 0;

		foreach (split ",", $checkAssemblyCtg[8])
		{
			/^-/ and next;
			$_ =~ s/[^a-zA-Z0-9]//g;
			my $assemblySeqList=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$assemblySeqList->execute($_);
			my @assemblySeqList = $assemblySeqList->fetchrow_array();
			my $updateAssemblyClone=$dbh->do("UPDATE matrix SET note = '1,$assemblySeqList[6]' WHERE id = $assemblySeqList[0]");
			$assemblyCtgLength += $assemblySeqList[6];
		}
		my $updateAssemblyCtgLength=$dbh->do("UPDATE matrix SET barcode = $assemblyCtgLength WHERE id = $checkAssemblyCtg[0]");

		if($chr)
		{
			print <<END;
<script>
closeViewer();
openViewer("assemblyChrView.cgi?assemblyId=$checkAssemblyCtg[3]&chr=$chr&scrollLeft=$scrollLeft");
</script>	
END
		}
		else
		{
			print <<END;
<script>
closeViewer();
openViewer("assemblyCtgView.cgi?assemblyCtgId=$assemblyCtgId&scrollLeft=$scrollLeft");
</script>	
END
		}
	}
}
else
{
	print <<END;
<script>
	errorPop("Not a valid operation!");
</script>	
END
}
