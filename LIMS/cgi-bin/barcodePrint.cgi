#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 
use DBI;
use lib "lib/";
use lib "lib/pangu";
use pangu;
use PDF::API2;
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

my @items = param ('items');
my $pdf = PDF::API2->new();
$pdf->mediabox('Letter'); #612 * 792 (72dpi) -> 8.5 * 11 in
my $font = $pdf->corefont('Helvetica');


if(@items)
{
	my $count= param ('blankLabel') || 0;
	my $col = 5;
	my $row = 17;
	my $labelPerPage = $col * $row;
	my $pageNumber;
	my $rowNumber;
	my $colNumber;
	my $page;
	for (sort {$a <=> $b} @items)
	{
		$count++;
		my $item = $dbh->prepare("SELECT * FROM matrix WHERE id = ?");
		$item->execute($_);
		my @item=$item->fetchrow_array();
		my $humanReadable = 'NA';
		if($item[1] eq "plate")
		{
			my $setLabelPrinted = $dbh->do("UPDATE matrix SET o = 1 WHERE id = $item[0]");
			my $plateToLibrary=$dbh->prepare("SELECT * FROM matrix WHERE id = ?");
			$plateToLibrary->execute($item[6]);
			my @plateToLibrary = $plateToLibrary->fetchrow_array();
			$humanReadable = "$plateToLibrary[2]$item[2].$item[4]";
		}
		else
		{
			$humanReadable = "$item[1]-$item[2]";
		}


		$pageNumber = int (($count - 1) / $labelPerPage);
		$page->{$pageNumber} = $pdf->page unless (exists $page->{$pageNumber});
		$colNumber = ($count-1) % $col;
		$rowNumber = int (($count - 1) / $col);
		my $currentRowOnPage = $rowNumber % $row;
		# Add text to the page
		my $barcodeText = $page->{$pageNumber}->text();
		$barcodeText->font($font, 6);
		$barcodeText->translate(60+102.6*$colNumber, 760-45*$currentRowOnPage);
		# left/right margin: 54, cell width: 93.6, cell space: 9, cell left padding: 6 -> 54+(93.6+9)*$colNumber+6 = 60+102.6*$colNumber
		# top/bottom margin: 18, cell height: 36, cell space: 9, cell top padding: 8, font size: 6 -> 792-18-8-6-(36+9)*$currentRowOnPage = 760-45*$currentRowOnPage
		$barcodeText->text($item[7]);
		# Add barcode to the page
		my $barcode = $pdf->xo_3of9(
			-code => $item[7],
			-zone => 10,
			-umzn => 0,
			-lmzn => 0,
			-font => $font,
			-fnsz => 8,
		);
		$barcode->{'-docompress'} = 0;
		my $gfx = $page->{$pageNumber}->gfx();
		$gfx->formimage($barcode,60+102.6*$colNumber, 750-45*$currentRowOnPage, 0.75);

		# Add text to the page
		my $text = $page->{$pageNumber}->text();
		$text->font($font, 6);
		$text->translate(60+102.6*$colNumber, 744-45*$currentRowOnPage);
		# left/right margin: 54, cell width: 93.6, cell space: 9, cell left padding: 6 -> 54+(93.6+9)*$colNumber+6 = 60+102.6*$colNumber
		# top/bottom margin: 18, cell height: 36, cell space: 9, cell top padding: 8, font size: 6, barcode space: 16 -> 792-18-8-6-16-(36+9)*$currentRowOnPage = 744-45*$currentRowOnPage
		$text->text($humanReadable);
	}
	print header(-type=>'application/octet-stream',
	-attachment=> "barcodeLabel$$.pdf",
	);
	print $pdf->stringify;
}
else
{
	print header;
	print <<END;
<script>
	parent.errorPop("Please check items first!");
</script>	
END
}