#!/usr/bin/perl -w
#
# pangulogo.cgi
#
# This script is to create pangu LOGO in a PNG pic
use strict;
use GD;
use GD::Text::Wrap;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
my $style=param("style") || '0';
my $unit=param("unit") || '8';
my $panguText='Pangu';
my $panguTextLength=length $panguText;

if($unit < 2)
{
	$unit=2;
}

my $imgwidth = $unit*8;
unless($style > 0)
{
	$imgwidth = $unit*(8 + $panguTextLength * 5);
}

my $imgheight = $unit * 8;

# create a new image
my $im = new GD::Image($imgwidth,$imgheight);

# allocate some colors
my $white = $im->colorAllocate(255,255,255);
my $black = $im->colorAllocate(0,0,0);       

my $uared = $im->colorAllocate(204,0,51);
my $uablue =  $im->colorAllocate(0,51,102);

# make the background transparent and interlaced
$im->transparent($white);
$im->interlaced('true');

#draw head, filling with uablue

my $polyhead = new GD::Polygon;

#1
$polyhead->addPt($unit * 4 - 1, $unit * 0);
$polyhead->addPt($unit * 4, $unit * 0);
#2
$polyhead->addPt($unit * 5 - 1, $unit * 1 - 1);
$polyhead->addPt($unit * 5 - 1, $unit * 1);
#3
$polyhead->addPt($unit * 4, $unit * 2 - 1);
$polyhead->addPt($unit * 4 - 1, $unit * 2 - 1);
#4
$polyhead->addPt($unit * 3, $unit * 1);
$polyhead->addPt($unit * 3, $unit * 1 - 1);

$im->filledPolygon($polyhead,$uablue);


#$im->filledArc($unit * 4, $unit * 1.5, $unit * 2, $unit * 2, 0, 360, $uablue);

# draw the "W" polygon, filling it with uared color
my $polyw = new GD::Polygon;

#1
$polyw->addPt(0, $unit * 2);
$polyw->addPt(1, $unit * 2);

#2
$polyw->addPt($unit * 2 - 1, $unit * 2);
$polyw->addPt($unit * 2, $unit * 2);

#3
$polyw->addPt($unit * 3-1, $unit * 3 - 1);
$polyw->addPt($unit * 3, $unit * 3 - 1);

#4
$polyw->addPt($unit * 4 - 1, $unit * 2);
$polyw->addPt($unit * 4, $unit * 2);

#5
$polyw->addPt($unit * 5 - 1, $unit * 3 - 1);
$polyw->addPt($unit * 5, $unit * 3 - 1);

#6
$polyw->addPt($unit * 6 - 1, $unit * 2);
$polyw->addPt($unit * 6, $unit * 2);

#7
$polyw->addPt($unit * 8 - 1, $unit * 2);

#8
$polyw->addPt($unit * 5, $unit * 5 - 1);
$polyw->addPt($unit * 5 - 1, $unit * 5 - 1);

#9
$polyw->addPt($unit * 4, $unit * 4);
$polyw->addPt($unit * 4 - 1, $unit * 4);

#10
$polyw->addPt($unit * 3, $unit * 5 - 1);
$polyw->addPt($unit * 3 - 1, $unit * 5 - 1);


$im->filledPolygon($polyw,$uared);
#there is an internal bug in GD module when using the above "filledPolygon" method
#so i replace it with below two methods to realize the same function
#$im->polygon($polyw,$uared);
#$im->fill($unit*2+1,$unit*2+1,$uared);


#draw legs, filling with uablue

my $polyLeftLeg = new GD::Polygon;
#1
$polyLeftLeg->addPt($unit * 3 - 1, $unit * 5);
$polyLeftLeg->addPt($unit * 3, $unit * 5);
#2
$polyLeftLeg->addPt($unit * 4 - 1, $unit * 6 - 1);
$polyLeftLeg->addPt($unit * 4 - 1, $unit * 6);
#3
$polyLeftLeg->addPt($unit * 3, $unit * 7 - 1);
$polyLeftLeg->addPt($unit * 3 - 1, $unit * 7 - 1);
#4
$polyLeftLeg->addPt($unit * 2, $unit * 6);
$polyLeftLeg->addPt($unit * 2, $unit * 6 - 1);
$im->filledPolygon($polyLeftLeg,$uablue);


my $polyRightLeg = new GD::Polygon;
#1
$polyRightLeg->addPt($unit * 5 - 1, $unit * 5);
$polyRightLeg->addPt($unit * 5, $unit * 5);
#2
$polyRightLeg->addPt($unit * 6 - 1, $unit * 6 - 1);
$polyRightLeg->addPt($unit * 6 - 1, $unit * 6);
#3
$polyRightLeg->addPt($unit * 5, $unit * 7 - 1);
$polyRightLeg->addPt($unit * 5 - 1, $unit * 7 - 1);
#4
$polyRightLeg->addPt($unit * 4, $unit * 6);
$polyRightLeg->addPt($unit * 4, $unit * 6 - 1);
$im->filledPolygon($polyRightLeg,$uablue);

#draw feet, filling with uablue

my $polyLeftFeet = new GD::Polygon;
#1
$polyLeftFeet->addPt($unit * 3 - 1, $unit * 7);
$polyLeftFeet->addPt($unit * 3, $unit * 7);
#2
$polyLeftFeet->addPt($unit * 4 - 1, $unit * 8 - 1);
#3
$polyLeftFeet->addPt($unit * 2, $unit * 8 - 1);
$im->filledPolygon($polyLeftFeet,$uablue);


my $polyRightFeet = new GD::Polygon;
#1
$polyRightFeet->addPt($unit * 5 - 1, $unit * 7);
$polyRightFeet->addPt($unit * 5, $unit * 7);
#2
$polyRightFeet->addPt($unit * 6 - 1, $unit * 8 - 1);
#3
$polyRightFeet->addPt($unit * 4, $unit * 8 - 1);
$im->filledPolygon($polyRightFeet,$uablue);

#print Pangu
my $panguTextWrap = GD::Text::Wrap->new( $im,
      line_space  => $unit,
      color       => $black,
      text        => $panguText,
  );
$panguTextWrap->font_path('fonts');
$panguTextWrap->set_font('ariblk', $unit*5); #Arial Black, 4X of unit font size
$panguTextWrap->set(align => 'left');
$panguTextWrap->draw($unit*8,$unit);

#print fig in png
print "Content-type:image/png\n\n";
# make sure we are writing to a binary stream
binmode STDOUT;
print $im->png;
