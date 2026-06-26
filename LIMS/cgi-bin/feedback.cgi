#!/usr/bin/perl -w
use strict;
use CGI qw(:standard);
use CGI::Carp qw ( fatalsToBrowser ); 

undef $/;# enable slurp mode
my $html = <DATA>;
print header(-cookie=>cookie(-name=>'menu',-value=>6));
print $html;

__DATA__
<p>
<table width="100%" border="0" cellspacing="0" cellpadding="0">
	<tr>
		<td>
			<b>Address</b><br>
			Arizona Genomics Institute<br>
			Thomas W. Keating Bioresearch Bldg.<br>
			1657 E. Helen Street<br>
			Tucson, AZ 85721<br>
			USA<br><br>
			<b>Telephone</b> 520.626.9590<br><br>
			<b><a onclick='openDialog("userEmailForm.cgi?userId=1")' title="Send an email">Email to Webmaster</a></b><br>
			<br>
			<b>The LIMS package is available at </b><br><a href="https://github.com/Jianwei-Zhang/LIMS" target="_blank">https://github.com/Jianwei-Zhang/LIMS</a>
			<br>
			<b>The LIMS Docs are available at </b><br><a href="https://jianwei-zhang.github.io/LIMS/" target="_blank">https://jianwei-zhang.github.io/LIMS/</a>
		</td>
		<td>
			<iframe src="https://www.google.com/maps/embed?pb=!1m14!1m8!1m3!1d53990.806233226765!2d-110.946928!3d32.246635!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x52922b72e420ad26!2sArizona+Genomics+Institute!5e0!3m2!1sen!2sus!4v1396390433027" width="800" height="600" frameborder="0" style="border:0"></iframe>
		</td>
	</tr>
</table>
</p>
<script>
loadingHide();
</script>