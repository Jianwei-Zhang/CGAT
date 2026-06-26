package userCookie;

use Query;

# Class inheritance
our @ISA = "Query";
use strict;

# Class attributes
my @Everyone;

# Constructor and initialization
sub new {
	my $class = shift;
	my $self = {@_};
	$self = $class->SUPER::new();
	return $self;
}

sub insertCookie{
	my $self = shift;
	my $cid = shift;
	my $userId = shift;
	my $remoteAddress = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("insert into userCookie values(?, ?, current_timestamp(), ?)") or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($cid, $userId, $remoteAddress) or die "execute failed: " . $sth->errstr();
	return 1;
}

sub deleteCookie{
	my $self = shift;
	my $cid = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("DELETE FROM userCookie WHERE cookie = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($cid) or die "execute failed: " . $sth->errstr();
	return 1;
}

sub deleteCookieByUserId{
	my $self = shift;
	my $userId = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("DELETE FROM userCookie WHERE userId = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userId) or die "execute failed: " . $sth->errstr();
	return 1;
}

sub checkCookie{
	my $self = shift;
	my $cid = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT userId FROM userCookie WHERE cookie = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($cid) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	if($sth->rows > 0)
	{
		return $res->{userId};
	}
	else
	{
		return 0;
	}
}

1;