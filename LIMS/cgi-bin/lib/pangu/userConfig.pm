# Class for storing data about a user
package userConfig;

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
sub getUserId {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT userId FROM userConfig WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{userId};	
}

sub getConfigId {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT configId FROM userConfig WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{configId};
	
}

sub getFieldValue {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldValue FROM userConfig WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{fieldValue};
}

sub getUserIdWithEmail {
	my $self = shift;
	my $email = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"SELECT userId FROM userConfig
		JOIN config
		WHERE userConfig.configId = config.id
		AND config.type = 'Profile'
		AND config.fieldName = 'email'
		AND userConfig.fieldValue = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($email) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{userId};
}

sub getFieldValueWithUserIdAndConfigId {
	my $self = shift;
	my $userId = shift;
	my $configId = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT fieldValue FROM userConfig WHERE userId = ? AND configid = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userId,$configId) or die "execute failed: " . $sth->errstr();
	if($sth->rows > 0)
	{
		my $res = $sth->fetchrow_hashref;
		return $res->{fieldValue};
	}
	else
	{
		$sth = $self->{_conn}->dbh->prepare("SELECT fieldValue FROM config WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
		$sth->execute($configId) or die "execute failed: " . $sth->errstr();
		my $res = $sth->fetchrow_hashref;
		my $fieldValue = $res->{fieldValue};
		$sth = $self->{_conn}->dbh->prepare(
			"INSERT INTO userConfig (userId, configId, fieldValue)
			 VALUES (?, ?, ?)"	 
		) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
		$sth->execute($userId, $configId, $fieldValue ) or die "execute failed: " . $sth->errstr();
		return $fieldValue;
	}
}

sub getFieldValueWithUserIdAndFieldName {
	my $self = shift;
	my $userId = shift;
	my $fieldName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT userConfig.fieldValue AS userConfigValue FROM userConfig JOIN config WHERE userId = ? AND config.id = userConfig.configId AND config.fieldName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userId,$fieldName) or die "execute failed: " . $sth->errstr();
	if($sth->rows > 0)
	{
		my $res = $sth->fetchrow_hashref;
		return $res->{userConfigValue};
	}
	else
	{
		$sth = $self->{_conn}->dbh->prepare("SELECT id,fieldValue FROM config WHERE fieldName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
		$sth->execute($fieldName) or die "execute failed: " . $sth->errstr();
		my $res = $sth->fetchrow_hashref;
		my $configId = $res->{id};
		my $fieldValue = $res->{fieldValue};
		$sth = $self->{_conn}->dbh->prepare(
			"INSERT INTO userConfig (userId, configId, fieldValue)
			 VALUES (?, ?, ?)"
		) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
		$sth->execute($userId, $configId, $fieldValue ) or die "execute failed: " . $sth->errstr();
		return $fieldValue;
	}
}

sub getUserConfigIdWithUserId {
	my $self = shift;
	my $userId = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT id FROM userConfig WHERE userId = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userId) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{id};
}


sub insertRecord{
	my $self = shift;
	my $userId = shift;
	my $configId = shift;
	my $fieldValue = shift;
	my $sth;

	$sth = $self->{_conn}->dbh->prepare(
		"INSERT INTO userConfig (userId, configId, fieldValue)
		 VALUES (?, ?, ?)"	 
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userId, $configId, $fieldValue ) or die "execute failed: " . $sth->errstr();
}


sub updateFieldValueWithUserIdAndConfigId{
	my $self = shift;
	my $userId = shift;
	my $configId = shift;
	my $fieldValue = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE userConfig
		 SET fieldValue = ?
		 WHERE userId = ?
		 AND configId = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($fieldValue, $userId, $configId) or die "execute failed: " . $sth->errstr();
}


1;