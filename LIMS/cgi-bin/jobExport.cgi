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

my $totalNumber = 0;
my $totalJobList = '';
my $totalJobPost = '';
my @jobs;
my $jobList=$dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'job' ORDER BY name");
$jobList->execute();
while (my @jobList = $jobList->fetchrow_array())
{
	next if ($jobList[2] =~ /^-/);
	$totalJobList .= ($totalJobList) ? ",\n$jobList[8]" : $jobList[8];
	$totalJobPost .= ($totalJobPost) ? ",\n{\"jobId\":$jobList[2],\"rawAssembled\":$jobList[3],\"insertOrCircularized\":$jobList[4],\"noVector\":$jobList[5],\"gapped\":$jobList[6],\"seqAssigned\":$jobList[7]}" : "{\"jobId\":$jobList[2],\"rawAssembled\":$jobList[3],\"insertOrCircularized\":$jobList[4],\"noVector\":$jobList[5],\"gapped\":$jobList[6],\"seqAssigned\":$jobList[7]}";
	$totalNumber++;
}
print header(-type=>'text/plain',
	-attachment=> "jobList$$.txt",
	);
print <<END;
{
  "page" : 1,
  "records" : $totalNumber,
  "total" : $totalNumber,
  "rows" : [$totalJobList],
  "jobPost" : [$totalJobPost]
}
END
