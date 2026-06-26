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

my $seqId = param ('seqId') || '';

my $sequence = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
$sequence->execute($seqId);
my @sequence=$sequence->fetchrow_array();
print header;
print <<END;
<input class='ui-widget-content ui-corner-all' name="chr" id="editSeqChr" size="2" type="text" maxlength="2" value="$sequence[6]"  placeholder="Chromosome number" onBlur="loaddiv('seqChr$seqId','seqChrSave.cgi?seqId=$seqId&chr='+this.value)"/>
END
