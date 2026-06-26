#!/usr/bin/perl -w
#
# Author: Jianwei Zhang, Arizona Genomics Institute, May. 2010
#
# Purpose: shared routines for Pangu.
package pangu;
use strict;
use CGI qw(:standard);
use Exporter;
use lib "lib/pangu";
our (@EXPORT,@ISA);
@ISA = qw(Exporter);


@EXPORT = ("readConfig",
"randomId",
"randomString",
"timeConvert",
"multiLineSeq",
"reverseComplement",
"reverseComplementIUPAC",
"getCreationTime",
"fileNameConvertion",
"fileSizeReadable",
"commify",
"timestamp",
"secToDay");


########################################################################################
sub readConfig
{
    my $cfgfile = shift;
    $cfgfile = 'main.conf' if (!defined $cfgfile or $cfgfile eq '');
    if (open F, $cfgfile)
    {
    	my $cfgdata;
        while (my $line = <F>)
        {
            next if ($line =~ /^\#/);
            $line =~ s/\s+$//;
            if ($line =~ /(\S+)\s*=\s*([^\#]*)/)
            {
                my $name = $1;
                my $val = $2;
                $val =~ s/\s+$//;
                $cfgdata->{$name} = $val;
            }
            elsif ($line =~ /(\S+)\s*=\s*$/)
            {
                my $name = $1;
                $cfgdata->{$name} = "";
            }
        }
        return $cfgdata;
    }
    else
    {
        print STDERR "Can't open $cfgfile : please check your settings.\n";
        exit;
    }
}
#usage of readConfig
#
#      readConfig("main.conf");
#
#sample of main.conf
#
#        #perlscripts common configuration
#        ##MySQL database params
#        USERNAME = username
#        PASSWORD = password
#        DATABASE = database
#        DBHOST = host.domain.name.edu #MySQL host
#
#all configuration values will be saved to hash "%commoncfg"
#

sub randomId {
    # This routine generates a 32-character random string
    # out of letters and numbers.
    my $rid = "";
    my $alphas = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    my @alphary = split(//, $alphas);
    foreach my $i (1..32) {
       my $letter = $alphary[int(rand(@alphary))];
       $rid .= $letter;
    }
    return $rid;
}
sub randomString {
    my($length) = @_;
    if ($length eq "" or $length < 3) {
        $length = 6;            # make it at least 6 chars long.
    }
    my @letters = ('a'..'z', 'A'..'Z', '0'..'9');
    my $randstr = "";
    foreach my $i (0..$length-1) {
      $randstr .= $letters[int(rand(@letters))];
    }
    return $randstr;
}

sub timeConvert{
	my $time = shift;
	if($time <10){
		$time = "0" . $time;
	}
	return $time;
}

sub multiLineSeq
{ #split a long sequence to multi-line
	my ($readSequence, $lineLength) = @_;
	my $multiLineSeq;
	$readSequence =~ s/\s//g;
	for (my $position=0;$position < length($readSequence); $position +=$lineLength)
	{
		$multiLineSeq .= substr($readSequence,$position,$lineLength)."\n";
	}
	return $multiLineSeq;
}
#usage of multiLineSeq
#
#      &multiLineSeq($sequence,80);


sub reverseComplement {
	my $dna = shift;

	# reverse the DNA sequence
	my $revcomp = reverse($dna);

	# complement the reversed DNA sequence
	$revcomp =~ tr/ACGTacgt/TGCAtgca/;
	return $revcomp;
}

sub reverseComplementIUPAC {
	my $dna = shift;

	# reverse the DNA sequence
	my $revcomp = reverse($dna);

	# complement the reversed DNA sequence
	$revcomp =~ tr/ABCDGHMNRSTUVWXYabcdghmnrstuvwxy/TVGHCDKNYSAABWXRtvghcdknysaabwxr/;
	return $revcomp;
}

sub getCreationTime{

		my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
		$year += 1900;
		$mon ++;
		$sec = timeConvert($sec);
		$min = timeConvert($min);
		$hour = timeConvert($hour);
		$mday = timeConvert($mday);
		$mon = timeConvert($mon);
		my $creation = "$year-$mon-$mday $hour:$min:$sec";
		return $creation;
}

sub fileNameConvertion{
	my $fileName = shift;
	$fileName =~ tr/|;,!@#$()<>\\"'`~{}[]=+&^ \t/_/;
	return $fileName;
}

sub fileSizeReadable{
	my $fileSize = shift;
	my @sizeUnit = ("bytes", "K", "M", "G", "T");
	for(my $i = scalar(@sizeUnit) -1; $i>0; $i--){ 
		if( int ($fileSize/ (1024 ** $i) ) ){
			$fileSize = sprintf("%.2f", $fileSize/ (1024 ** $i)) . $sizeUnit[$i];
			last;
		}
	}
	return $fileSize;
}

sub commify {
	local $_  = shift;
	1 while s/^(-?\d+)(\d{3})/$1,$2/;
	return $_;
}

sub timestamp
{
  return scalar localtime(time());
}

sub secToDay
{
  my $secondsnumber=shift;
  $secondsnumber =~ s/\D//g;
  my $minutesnumber = int $secondsnumber/60;
  my $leftseconds = $secondsnumber % 60;
  if($minutesnumber >= 1)
  {
    my $hoursnumber = int $minutesnumber/60;
    my $leftminutes = $minutesnumber  % 60;
    if($hoursnumber >=1)
    {
      my $daysnumber = int $hoursnumber/24;
      my $lefthours = $hoursnumber % 24;
      if($daysnumber >= 1)
      {
        if($lefthours == 0)
        {
          if($leftminutes == 0)
          {
            if($leftseconds == 0)
            {
              return $daysnumber."d";
            }
            else
            {
              return $daysnumber."d ".$leftseconds."s";
            }
          }
          else
          {
            if($leftseconds == 0)
            {
              return $daysnumber."d ".$leftminutes."m";
            }
            else
            {
              return $daysnumber."d ".$leftminutes."m ".$leftseconds."s";
            }
          }
        }
        else
        {
          if($leftminutes == 0)
          {
            if($leftseconds == 0)
            {
              return $daysnumber."d ".$lefthours."h";
            }
            else
            {
              return $daysnumber."d ".$lefthours."h ".$leftseconds."s";
            }
          }
          else
          {
            if($leftseconds == 0)
            {
              return $daysnumber."d ".$lefthours."h ".$leftminutes."m";
            }
            else
            {
              return $daysnumber."d ".$lefthours."h ".$leftminutes."m ".$leftseconds."s";
            }
          }
        }
      }
      else
      {
        if($leftminutes == 0)
        {
          if($leftseconds == 0)
          {
            return $hoursnumber."h";
          }
          else
          {
            return $hoursnumber."h ".$leftseconds."s";
          }
        }
        else
        {
          if($leftseconds == 0)
          {
            return $hoursnumber."h ".$leftminutes."m";
          }
          else
          {
            return $hoursnumber."h ".$leftminutes."m ".$leftseconds."s";
          }
        }
      }
    }
    else
    {
      if($leftseconds == 0)
      {
        return $minutesnumber."m";
      }
      else
      {
        return $minutesnumber."m ".$leftseconds."s";
      }
    }
  }
  else
  {
    return $secondsnumber."s";
  }
}

#usage of secToDay
#
#      this will change seconds nubmer to d h m s format
#      &secToDay($seconds); non-numberic characters will be ignored

1;