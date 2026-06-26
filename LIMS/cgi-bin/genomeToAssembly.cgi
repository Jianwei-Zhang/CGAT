#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $commoncfg = readConfig("main.conf");
my $dbh=DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}",$commoncfg->{USERNAME},$commoncfg->{PASSWORD});

my $genomeId = param ('genomeId') || '';
print header;
if($genomeId)
{
	my $relatedAssemblies = '';
	my $relatedAssembly=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'assembly' AND (x = $genomeId OR y = $genomeId)");
	$relatedAssembly->execute();
	while (my @relatedAssembly = $relatedAssembly->fetchrow_array())
	{
#			$relatedAssemblies .= (length $relatedAssembly[2] > 12) ? "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssembly[0]\")' title='$relatedAssembly[2]'>" . substr($relatedAssembly[2],0,12 )."...</a> " : "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssembly[0]\")' title='$relatedAssembly[2]'>" . $relatedAssembly[2] ."</a> ";
			$relatedAssemblies .= "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssembly[0]\")' title='$relatedAssembly[2]'>" . $relatedAssembly[2] ."</a> ";
	}
	my $relatedAssemblyByExtra=$dbh->prepare("SELECT * FROM matrix,link WHERE link.type LIKE 'asbGenome' AND link.parent = matrix.id AND link.child = ?");
	$relatedAssemblyByExtra->execute($genomeId);
	while (my @relatedAssemblyByExtra = $relatedAssemblyByExtra->fetchrow_array())
	{
#		$relatedAssemblies .= (length $relatedAssemblyByExtra[2] > 12) ? "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssemblyByExtra[0]\")' title='$relatedAssemblyByExtra[2]'>" . substr($relatedAssemblyByExtra[2],0,12 )."...</a> " : "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssemblyByExtra[0]\")' title='$relatedAssemblyByExtra[2]'>" . $relatedAssemblyByExtra[2] ."</a> ";
		$relatedAssemblies .= "<a onclick='openDialog(\"assemblyView.cgi?assemblyId=$relatedAssemblyByExtra[0]\")' title='$relatedAssemblyByExtra[2]'>" . $relatedAssemblyByExtra[2] ."</a> ";
	}
	print $relatedAssemblies;
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