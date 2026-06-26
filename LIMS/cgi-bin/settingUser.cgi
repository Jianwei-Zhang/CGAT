#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp "fatalsToBrowser"; # send fatal (die, confess) errors to the browser
use lib "lib/";
use lib "lib/pangu";
use pangu;
use user;
use config;
use userConfig;
use userCookie;

my $userCookie = new userCookie;
my $userId = (cookie('cid')) ? $userCookie->checkCookie(cookie('cid')) : 0;
exit if (!$userId);

my $commoncfg = readConfig("main.conf");

print header;
my $user = new user;
my $userConfig = new userConfig;

my $configId = param("configId");
my $fieldValue = param("fieldValue");
$userConfig->updateFieldValueWithUserIdAndConfigId($userId, $configId, $fieldValue) if(defined $configId && defined $fieldValue);
