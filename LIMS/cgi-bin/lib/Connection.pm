package Connection;
use strict;
use DBI;
use pangu;
my $oneTrueSelf;

sub instance {
	unless (defined $oneTrueSelf) {
		my $type = shift;
		my $this = {};
		my $commoncfg = readConfig("main.conf");
		$this->{_dbh} = DBI->connect("DBI:mysql:$commoncfg->{DATABASE}:$commoncfg->{DBHOST}", $commoncfg->{USERNAME}, $commoncfg->{PASSWORD});
		die "connect failed: " . DBI->errstr() unless $this->{_dbh};
		$oneTrueSelf = bless $this, $type;
	}
	return $oneTrueSelf;
}
sub dbh {
	my $self = shift;
	return $self->{_dbh};
}

1;