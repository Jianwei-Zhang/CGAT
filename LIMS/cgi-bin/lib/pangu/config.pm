# Class for storing data about a user
package config;

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

# Class accessor methods

# Utility methods
sub getType {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT type FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{type};
}

sub getFieldName {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldName FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldName};
}

sub getFieldDefault {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldDefault FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldDefault};
}

sub getFieldDefaultWithFieldName {
	my $self = shift;
	my $fieldName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldDefault FROM config WHERE fieldName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($fieldName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldDefault};
}


sub getFieldDescription {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldDescription FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldDescription};
}

sub getFieldValue {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldValue FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldValue};
}

sub getConfigIdWithType {
	my $self = shift;
	my $type = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT id FROM config WHERE type = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($type) or die "execute failed: " . $sth->errstr();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}	
	return $res;
}

sub getConfigWithType {
	my $self = shift;
	my $type = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT * FROM config WHERE type = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($type) or die "execute failed: " . $sth->errstr();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}	
	return $res;
}

sub getConfigIdWithFieldName {
	my $self = shift;
	my $fieldName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT id FROM config WHERE fieldName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($fieldName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{id};
}

sub getAllTypes {
	my $self = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT type FROM config WHERE 1 GROUP BY type") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute() or die "execute failed: " . $sth->errstr();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}	
	return $res;
}

sub getFieldValueWithFieldName {
	my $self = shift;
	my $fieldName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldValue FROM config WHERE fieldName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($fieldName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldValue};
}

sub getAllSystemFieldsWithFieldName{
	my $self = shift;
	my $fieldName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("
	SELECT fieldValue, fieldDefault 
	FROM config 
	WHERE fieldName = ?
	") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($fieldName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res;
}

sub getAllFields{
	my $self = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("
	SELECT * 
	FROM config 
	") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute() or die "execute failed: " . $sth->errstr();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}	
	return $res;
}

sub updateFieldValueWithId{
	my $self = shift;
	my $id = shift;
	my $fieldValue = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE config
		 SET fieldValue = ?
		 WHERE id = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($fieldValue, $id) or die "execute failed: " . $sth->errstr();
}

sub updateFieldValueWithFieldName{
	my $self = shift;
	my $fieldName = shift;
	my $fieldValue = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE config
		 SET fieldValue = ?
		 WHERE fieldName = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($fieldValue, $fieldName) or die "execute failed: " . $sth->errstr();
}


1;