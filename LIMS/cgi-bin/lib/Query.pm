package Query;
use strict;
use Connection;

sub new {
	my ($type, @params) = @_;
	my $conn = Connection->instance();
	my $this = {};
	$this->{_conn} = $conn;
	bless($this, $type);
	return $this;
}

sub selectAllFromTable {
	my $self = shift;
	my $table = shift;
	my $sth = $self->{_conn}->dbh->prepare("SELECT * FROM $table");
	$sth->execute();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}
	return $res;
}

1;
