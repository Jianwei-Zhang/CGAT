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

my $fpcId = param ('fpcId') || '';
if ($fpcId)
{
	my $bacContig;
	my $bacLeft;
	my $bacRight;
	my $bacRemark;
	my $bacShotgun;
	my $bacPicked;
	my $contig;
	my $seedBac;
	my $contigEnd;

	my $getFpcClones = $dbh->prepare("SELECT * FROM matrix WHERE container LIKE 'fpcClone' AND o = ? ORDER BY name");
	$getFpcClones->execute($fpcId);
	if($getFpcClones->rows < 1)
	{
		print header(-type=>'text/html',-status=>'402 No valid FPC ID Found');
		exit;
	}
	else
	{
		while(my @getFpcClones = $getFpcClones->fetchrow_array())
		{
			next if($getFpcClones[8] !~ /Map/);
			for (split /\n/,$getFpcClones[8])
			{
				if(/Map /)
				{
					my $mapline=$';
					if ($mapline =~ / Ends Left /)
					{
						$bacContig->{$getFpcClones[2]} = $`;
						$bacLeft->{$getFpcClones[2]} = $';
						$bacContig->{$getFpcClones[2]} =~ s/[^a-zA-Z0-9]//g;
					}
					if ($mapline =~ / Ends Right /)
					{
						$bacRight->{$getFpcClones[2]}=$';
			
						if ($bacRight->{$getFpcClones[2]} =~ / /)
						{
							$bacRight->{$getFpcClones[2]}=$`;
						}
					}
				}
				if(/Remark /)
				{
					$bacRemark->{$getFpcClones[2]} .= ($bacRemark->{$getFpcClones[2]}) ? ",$'" : $';
				}
				if(/Shotgun /)
				{
					$bacShotgun->{$getFpcClones[2]} = $';
				}
			}
			$bacPicked->{$getFpcClones[2]} = $getFpcClones[5];
			push @{$contig->{$bacContig->{$getFpcClones[2]}}}, $getFpcClones[2];
			if (exists $seedBac->{$bacContig->{$getFpcClones[2]}})
			{
				$contigEnd->{$bacContig->{$getFpcClones[2]}} = $bacRight->{$getFpcClones[2]} if ($contigEnd->{$bacContig->{$getFpcClones[2]}} < $bacRight->{$getFpcClones[2]});
				if($bacLeft->{$seedBac->{$bacContig->{$getFpcClones[2]}}} == $bacLeft->{$getFpcClones[2]})
				{
					$seedBac->{$bacContig->{$getFpcClones[2]}} = $getFpcClones[2] if ($bacRight->{$seedBac->{$bacContig->{$getFpcClones[2]}}} < $bacRight->{$getFpcClones[2]});
				}
				if($bacLeft->{$seedBac->{$bacContig->{$getFpcClones[2]}}} > $bacLeft->{$getFpcClones[2]})
				{
					$seedBac->{$bacContig->{$getFpcClones[2]}} = $getFpcClones[2];
				}
			}
			else
			{
				$seedBac->{$bacContig->{$getFpcClones[2]}} = $getFpcClones[2];
				$contigEnd->{$bacContig->{$getFpcClones[2]}} = $bacRight->{$getFpcClones[2]};
			}
		}

		print header(-type=>'text/plain',
		-attachment=>'fpcMTPCloneList.txt',
		);
		my $lessNumber = 5;
		print "#please note: We will skip contigs containing BACs less than $lessNumber.\n";
		print "Order\tBAC\tPicked\tCTG\tcloneNumber\tLeft\tRight\tRemark\tShotgun\n";
		foreach my $ctgId (map { $_->[0] } sort { $a->[1] <=> $b->[1] } map  { [$_, $_=~/(\d+)/] } keys %$contig)
		{
			next if @{$contig->{$ctgId}} < $lessNumber;#skip MTP for contig containing less BACs.
			my $cloneNumber = @{$contig->{$ctgId}};
			my $cloneOrder = 1;
			print "$cloneOrder\t$seedBac->{$ctgId}\t$bacPicked->{$seedBac->{$ctgId}}\t$bacContig->{$seedBac->{$ctgId}}\t$cloneNumber\t$bacLeft->{$seedBac->{$ctgId}}\t$bacRight->{$seedBac->{$ctgId}}\t$bacRemark->{$seedBac->{$ctgId}}\t$bacShotgun->{$seedBac->{$ctgId}}\n";
			my $followBac;
			do{
				$followBac = '';
				foreach my $nextBac (@{$contig->{$ctgId}})
				{
					next if ($bacLeft->{$nextBac} > $bacRight->{$seedBac->{$ctgId}});
					next if ($bacRight->{$nextBac} < $bacRight->{$seedBac->{$ctgId}});
					if ($followBac ne '')
					{
						$followBac = $nextBac if ($bacRight->{$nextBac} > $bacRight->{$followBac});				
					}
					else
					{
						$followBac = $nextBac;
					}
				}
				$seedBac->{$ctgId} = $followBac;
				$cloneOrder++;
				if($contigEnd->{$ctgId} eq $bacRight->{$followBac})
				{
					print "$cloneOrder\t*$seedBac->{$ctgId}\t$bacPicked->{$seedBac->{$ctgId}}\t$bacContig->{$seedBac->{$ctgId}}\t$cloneNumber\t$bacLeft->{$seedBac->{$ctgId}}\t$bacRight->{$seedBac->{$ctgId}}\t$bacRemark->{$seedBac->{$ctgId}}\t$bacShotgun->{$seedBac->{$ctgId}}\n";		
				}
				else
				{
					print "$cloneOrder\t$seedBac->{$ctgId}\t$bacPicked->{$seedBac->{$ctgId}}\t$bacContig->{$seedBac->{$ctgId}}\t$cloneNumber\t$bacLeft->{$seedBac->{$ctgId}}\t$bacRight->{$seedBac->{$ctgId}}\t$bacRemark->{$seedBac->{$ctgId}}\t$bacShotgun->{$seedBac->{$ctgId}}\n";		
				}
			} until ($contigEnd->{$ctgId} eq $bacRight->{$followBac});
		}
	}
}
else
{
	print header(-type=>'text/html',-status=>'402 Invalid operation');
}

