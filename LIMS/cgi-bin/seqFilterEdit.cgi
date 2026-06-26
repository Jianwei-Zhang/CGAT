#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use JSON::XS;
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
my $sequenceDetails = decode_json $sequence[8];
$sequenceDetails->{'filter'} = '' unless (exists $sequenceDetails->{'filter'});

print header;
print <<END;
<input class='ui-widget-content ui-corner-all' name="filter" id="editSeqFilter" size="32" type="text" maxlength="32" value="$sequenceDetails->{'filter'}"  placeholder="Sequence Filter" onBlur="loaddiv('seqFilter$seqId','seqFilterSave.cgi?seqId=$seqId&filter='+this.value)"/>
END
