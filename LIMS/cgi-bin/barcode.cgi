#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use GD::Barcode;
my $code = param('code') || '*No code*';;
my $noText = param('notext') || 0;
my $height = param('height') || 24;
my $type = param('type') || 'Code39';
binmode(STDOUT);
print header('image/png');
print GD::Barcode->new($type, uc $code)->plot(NoText=>$noText, Height => $height)->png;