# Class for storing data about a user
package user;

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

# Utility methods that access data on user table
sub getIdWithUserName {
	my $self = shift;
	my $userName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT id FROM user WHERE userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{id};
	
}

sub getUserName {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT userName FROM user WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{userName};	
}

sub getRole {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT role FROM user WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{role};
}

sub countUser {
	my $self = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("
	SELECT COUNT(*) AS numberOfRecords 
	FROM user 
	WHERE 1
	") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute() or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{numberOfRecords};
}


sub getAllFieldsOfUser {
	my $self = shift;
	my $startRecord = shift;
	my $numRecoredReturned = shift;
	my $sth;
	my $query = "SELECT * FROM user ORDER BY userName";
	if(defined $startRecord){
		$query .= " LIMIT $startRecord, $numRecoredReturned"
	}

	$sth = $self->{_conn}->dbh->prepare($query) or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute() or die "execute failed: " . $sth->errstr();
	my $res;
	while (my $row = $sth->fetchrow_hashref()) {
		push(@$res, $row)
	}	
	return $res;	
}

sub getAllFieldsWithUserName {
	my $self = shift;
	my $userName = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT * FROM user WHERE userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref();
	$sth->finish();	
	return $res;
}

sub getAllFieldsWithUserId {
	my $self = shift;
	my $userId = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare("SELECT * FROM user WHERE id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
	$sth->execute($userId) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref();
	return $res;
}

# Insert a record
sub insertUser{
	my $self = shift;
	my $userName = shift;
	my $password = shift;	
	my $role = shift;	
	my $activation = shift;	
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"INSERT INTO user (userName, password, role, creation, activation)
		 VALUES (?, MD5(?), ?, NOW(), ?)"	 
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userName, $password, $role, $activation) or die "execute failed: " . $sth->errstr();
	my $res = $self->{_conn}->dbh->{mysql_insertid};
	return $res;
}

# Delete an existing record
sub deleteUser {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"DELETE FROM user
		 WHERE id=?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

# mark "Deleted" of an user
sub markDeleteUser {
	my $self = shift;
	my $id = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE user
		SET role = 'deleted'
		WHERE id=?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

sub changeUserRole {
	my $self = shift;
	my $id = shift;
	my $role = $self->getRole($id);
	my $sth;
	if ($role eq "regular")
	{
		$sth = $self->{_conn}->dbh->prepare(
			"UPDATE user
			SET role = 'admin'
			WHERE id=?"
		) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	}
	else
	{
		$sth = $self->{_conn}->dbh->prepare(
			"UPDATE user
			SET role = 'regular'
			WHERE id=?"
		) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	}
	$sth->execute($id) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}


sub activateUser{
	my $self = shift;
	my $activation = shift;	
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE user
		 SET activation = NOW()
		 WHERE activation = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($activation) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

sub deactivateUser{
	my $self = shift;
	my $userId = shift;	
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE user
		 SET activation = CONCAT ('-',activation)
		 WHERE id = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userId) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

sub reactivateUser{
	my $self = shift;
	my $userId = shift;	
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE user
		 SET activation = NOW()
		 WHERE id = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
# 	$sth = $self->{_conn}->dbh->prepare(
# 		"UPDATE user
# 		 SET activation = SUBSTRING(activation, -19)
# 		 WHERE id = ?"
# 	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userId) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

sub checkPassword {
	my $self = shift;
	my $userNameOrId = shift;
	my $password = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"SELECT * FROM user
		WHERE (userName = ? OR id = ?)
		AND password = MD5(?)
		AND length(activation) = 19
		AND role != 'deleted'"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($userNameOrId,$userNameOrId,$password) or die "execute failed: " . $sth->errstr();
	my $res = $sth->fetchrow_hashref;
	return $res->{id};
}

sub updatePassword {
	my $self = shift;
	my $userNameOrId = shift;
	my $password = shift;
	my $sth;
	$sth = $self->{_conn}->dbh->prepare(
		"UPDATE user
		 SET password = MD5(?)
		 WHERE userName = ?
		 OR id = ?"
	) or die "prepare failed: " . $self->{_conn}->dbh->errstr();
	$sth->execute($password, $userNameOrId, $userNameOrId) or die "execute failed: " . $sth->errstr();
	return $sth->rows;
}

# Utility methods that access data in other table
# 
# sub get_process_id {
# 	my $self = shift;
# 	my $id = shift;
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare("
# 	SELECT process.id 
# 	FROM user 
# 	JOIN process 
# 	ON	user.id = process.userId 
# 	WHERE user.id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($id) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }
# 
# sub get_fileId {
# 	my $self = shift;
# 	my $id = shift;
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare("
# 	SELECT fileUser.fileId 
# 	FROM user 
# 	JOIN fileUser 
# 	ON	user.id = fileUser.userId 
# 	WHERE user.id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($id) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }
# 
# sub get_projectId {
# 	my $self = shift;
# 	my $id = shift;
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare("
# 	SELECT projectUser.projectId 
# 	FROM user 
# 	JOIN projectUser 
# 	ON	user.id = projectUser.userId 
# 	WHERE user.id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($id) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;	
# }
# 
# sub get_pipelineId {
# 	my $self = shift;
# 	my $id = shift;
# 	my $sth;
# 
# 	$sth = $self->{_conn}->dbh->prepare("
# 	SELECT pipelineUser.pipelineId 
# 	FROM user 
# 	JOIN pipelineUser 
# 	ON	user.id = pipelineUser.userId 
# 	WHERE user.id = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($id) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	$sth->finish();	
# 	return $res;
# 	
# }
# 
# sub get_all_fields_of_pipeline_with_userName {
# 	my $self = shift;
# 	my $userName = shift;	
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare(
# 		"SELECT pipelineUser.pipelineId, pipelineUser.permission, pipeline.pipelineName, pipeline.version 
# 		FROM user
# 		JOIN pipelineUser
# 		ON user.id = pipelineUser.userId
# 		JOIN pipeline
# 		ON pipelineUser.pipelineId = pipeline.id
# 		WHERE user.userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }
# 
# sub get_all_fields_of_process_with_userName {
# 	my $self = shift;
# 	my $userName = shift;	
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare(
# 		"SELECT process.programId, process.userId, process.pipelineId, process.pid, process.creation, process.id
# 		FROM user
# 		JOIN process
# 		ON user.id = process.userId
# 		WHERE user.userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }
# 
# sub get_all_fields_of_file_with_userName {
# 	my $self = shift;
# 	my $userName = shift;	
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare(
# 		"SELECT fileUser.fileId, fileUser.permission, file.fileName, file.pathId, file.fileType, file.creation
# 		FROM user
# 		JOIN fileUser
# 		ON user.id = fileUser.userId
# 		JOIN file
# 		ON fileUser.fileId = file.id
# 		WHERE user.userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }
# 
# sub get_all_fields_of_project_with_userName {
# 	my $self = shift;
# 	my $userName = shift;	
# 	my $sth;
# 	$sth = $self->{_conn}->dbh->prepare(
# 		"SELECT projectUser.projectId, projectUser.permission, project.projectName, project.description, project.creation
# 		FROM user
# 		JOIN projectUser
# 		ON user.id = projectUser.userId
# 		JOIN project
# 		ON projectUser.projectId = project.id
# 		WHERE user.userName = ?") or die "prepare failed: " . $self->{_conn}->dbh->errstr();;
# 	$sth->execute($userName) or die "execute failed: " . $sth->errstr();
# 	my $res;
# 	while (my $row = $sth->fetchrow_hashref()) {
# 
# 		push(@$res, $row)
# 	}	
# 	return $res;
# }

1;
