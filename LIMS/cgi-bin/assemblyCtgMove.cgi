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

my $assemblyCtgId = param ('assemblyCtgId') || '';
my $assemblyPosition = param ('assemblyPosition') || '0';
my $assemblyId = param ('assemblyId') || '';
my $chr = param ('chr') || '0';
my $scrollLeft = param ('scrollLeft') || '0';

print header;

if($assemblyCtgId)
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
		my $updateAssemblyCtg=$dbh->prepare("UPDATE matrix SET z = ? WHERE id = ?");
		$updateAssemblyCtg->execute($assemblyPosition,$assemblyCtgId);

		my $assignedChrOrder = 0;
		my $assemblyCtgs = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assemblyCtg' AND o = ? AND x= ? ORDER BY z");
		$assemblyCtgs->execute($checkAssemblyCtg[3],$checkAssemblyCtg[4]);
		while(my @assemblyCtgs = $assemblyCtgs->fetchrow_array())
		{
			my $updateAssemblyCtg=$dbh->do("UPDATE matrix SET y = $assignedChrOrder WHERE id = $assemblyCtgs[0]");
			$assignedChrOrder++;
		}

		if($assemblyId)
		{
				print <<END;
<script>
	closeViewer();
	openViewer("assemblyChrView.cgi?assemblyId=$assemblyId&chr=$chr&scrollLeft=$scrollLeft");
</script>	
END
		}
		else
		{
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
}
else
{
	print <<END;
<script>
	errorPop("Not a valid operation!");
</script>	
END
}