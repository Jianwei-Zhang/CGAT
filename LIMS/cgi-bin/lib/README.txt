README for CLASSES in Pangu 



"config" table

METHODS:
new
EXAMPLES:
my $object = new config;

getType(id)
Parameters: "id" in "config" table
return a single value: "type"
EXAMPLES:
my $object = new config;
my $id = 0;
my $res = $object->getType($id);

getFieldName(id)
Parameters: "id" in "config" table
return a single value: "fieldName"
EXAMPLES:
my $object = new config;
my $id = 0;
my $res = $object->getFieldName($id);

getFieldValue(id)
Parameters: "id" in "config" table
return a single value: "fieldValue"
EXAMPLES:
my $object = new config;
my $id = 0;
my $res = $object->getFieldValue($id);


********************************************

"userConfig" table 

METHODS:
new
Example:
my $userConfig = new userConfig;

$userConfig->getUserId($id);
$userConfig->getConfigId($id);
$userConfig->getFieldValue($id);
$userConfig->getUserIdWithEmail($email);
$userConfig->getFieldValueWithUserIdAndConfigId($userId,$configId);
$userConfig->getFieldValueWithUserIdAndFieldName($userId,$fieldName);
$userConfig->getUserConfigIdWithUserId($userId);
$userConfig->insertRecord($userId,$configId,$fieldValue);
$userConfig->updateFieldValueWithUserIdAndConfigId($userId,$configId,$fieldValue);



********************************************

"userCookie" table 

METHODS:
new
Example:
my $userCookie = new userCookie;

$userCookie->insertCookie($cid,$userId,$remoteAddress);
$userCookie->deleteCookie($cid);
$userCookie->deleteCookieByUserId($userId);
$userCookie->checkCookie($cid);



********************************************

"user" table 

METHODS:
new
Example:
my $user = new user;

getIdWithUserName("username")
Parameters: "username"
return a single value: "id" in "user" table
Example:
my $userId = $user->getIdWithUserName("qingju");

getFirstName(id)
Parameters: "id" in user table
return a single value: "firstName"
Example: 
my $user = new user;
my $userId = $user->getIdWithUserName("qingju");
my $res = $user->getFirstName($userId)

getLastName(id)
Parameters: "id" in user table
return a single value: "lastName"
Example:
my $user = new user;
my $userId = $user->getIdWithUserName("qingju");
my $res = $user->getLastName($userId)

getPassword(id)
Parameters: "id" in user table
return a single value: "password"
Example:
my $user = new user;
my $userId = $user->getIdWithUserName("qingju");
my $res = $user->getPassword($userId)






get_process_id(id)
Parameters: "id" in user table
return a reference to an array of "id" in "process" table which corresponds to the argument user "id"
Example:
my $user = new user;
my $user_id = $user->get_id_with_userName("qingju");
my $res = $user->get_process_id($user_id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


get_fileId(id)
Parameters: "id" in user table
return a reference to an array of "fileId" in "fileUser" table
Example:
my $user = new user;
my $user_id = $user->get_id_with_userName("qingju");
my $res = $user->get_fileId($user_id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"fileId"};
}


get_projectId(id)
PARAMETERS: "id" in user table
RETURN VALUE: 
a reference to an array of "projectId" in "projectUser" table
Example:
my $user = new user;
my $user_id = $user->get_id_with_userName("qingju");
my $res = $user->get_projectId($user_id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"projectId"};
}


get_pipelineId(id)
PARAMETERS: "id" in user table
RETURN VALUE:  
a reference to an array of "pipelineId" in "pipelineUser" table
Example:
my $user = new user;
my $user_id = $user->get_id_with_userName("qingju");
my $res = $user->get_pipelineId($user_id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"pipelineId"};
}


******************************************


"document" table

METHODS:
new
EXAMPLES:
my $object = new document;

get_targetId(id)
Parameters: "id" in "help" table
return a single value: "targetId"
EXAMPLES:
my $object = new help;
my $id = 0;
my $res = $object->get_targetId($id);

get_targetType(id)
Parameters: "id" in "help" table
return a single value: "targetType"
EXAMPLES:
my $object = new help;
my $id = 0;
my $res = $object->get_targetType($id);

get_document(id)
Parameters: "id" in "help" table
return a single value: "document"
EXAMPLES:
my $object = new help;
my $id = 0;
my $res = $object->get_document($id);


************************************************

"fileUser" table

METHODS:
new
EXAMPLES:
my $object = new fileUser;

get_id_with_userId(userId)
PARAMETERS: "userId" in "fileUser" table
RETURN VALUES: a reference to an array of "id" in "fileUser" table
EXAMPLES:
my $fileUser = new fileUser;
my $userId = 0;
my $res = $fileUser->get_id_with_userId($userId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_fileId(fileId)
PARAMETERS: "fileId" in "fileUser" table
RETURN VALUES: a reference to an array of "id" in "fileUser" table
EXAMPLES:
my $fileUser = new fileUser;
my $fileId = 0;
my $res = $fileUser->get_id_with_fileId($fileId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_userId(id)
PARAMETERS: "id" in "fileUser" table
return a single value: "userId"
EXAMPLES:
my $object = new fileUser;
my $id = 0;
my $res = $object->get_userId($id);


get_fileId(id)
PARAMETERS: "id" in "fileUser" table
RETURN VALUES: a single value: "fileId"
EXAMPLES:
my $object = new fileUser;
my $id = 0;
my $res = $object->get_fileId($id);

get_permission(id)
PARAMETERS: "id" in "fileUser" table
RETURN VALUES: a single value: "permission"
EXAMPLES:
my $object = new fileUser;
my $id = 0;
my $res = $object->get_permission($id);

**************************************************

"projectUser" table

METHODS:
new
EXAMPLES:
my $object = new fileUser;

get_id_with_userId(userId)
PARAMETERS: "userId" in "projectUser" table
RETURN VALUES: a reference to an array of "id" in "projectUser" table
EXAMPLES:
my $object = new projectUser;
my $userId = 0;
my $res = $object->get_id_with_userId($userId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_projectId(projectId)
PARAMETERS: "projectId" in "projectUser" table
RETURN VALUES: a reference to an array of "id" in "projectUser" table
EXAMPLES:
my $object = new projectUser;
my $projectId = 0;
my $res = $object->get_id_with_projectId(($projectId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_userId(id)
PARAMETERS: "id" in "projectUser" table
RETURN VALUES: a single value: "userId"
EXAMPLES:
my $id = 0;
my $res = $object->get_userId($id);

get_projectId(id)
PARAMETERS: "id" in "projectUser" table
RETURN VALUES: a single value: "projectId"
EXAMPLES:
my $object = new projectUser;
my $id = 0;
my $res = $object->get_projectId($id);

get_permission(id)
PARAMETERS: "id" in "projectUser" table
RETURN VALUES: a single value: "permission"
EXAMPLES:
my $object = new projectUser;
my $id = 0;
my $res = $object->get_permission($id);

****************************************************

"pipelineUser" table

METHODS:
new
EXAMPLES:
my $object = new pipelineUser;

get_id_with_pipelineId(pipelineId)
PARAMETERS: "pipelineId" in "pipelineUser" table
RETURN VALUES: a reference to an array of "id" in "pipelineUser" table
EXAMPLES:
my $object = new pipelineUser;
my $pipelineId = 0;
my $res = $object->get_id_with_pipelineId($pipelineId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_userId(userId)
PARAMETERS: "userId" in "pipelineUser" table
RETURN VALUES: a reference to an array of "id" in "pipelineUser" table
EXAMPLES:
my $object = new pipelineUser;
my $userId = 0;
my $res = $object->get_id_with_userId($userId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_userId(id)
PARAMETERS: "id" in "pipelineUser" table
RETURN VALUES: a single value: "userId"
EXAMPLES:
my $object = new pipelineUser;
my $id = 0;
my $res = $object->get_userId($id);

get_permission(id)
PARAMETERS: "id" in "pipelineUser" table
RETURN VALUES: a single value: "permission"
EXAMPLES:
my $object = new pipelineUser;
my $id = 0;
my $res = $object->get_permission($id);

get_pipelineId(id)
PARAMETERS: "id" in "pipelineUser" table
RETURN VALUES: a single value: "pipelineId"
EXAMPLES:
my $object = new pipelineUser;
my $id = 0;
my $res = $object->get_pipelineId($id);


*******************************************************
"project" table

METHODS:
new
EXAMPLES:
my $object = new project;

get_id_with_projectName("projectName")
PARAMETERS: "projectName" in "project" table
RETURN VALUES: a reference to an array of "id" in "project" table
EXAMPLES:
my $object = new project;
my $projectName = "projectName";
my $res = $object->get_id_with_projectName($projectName);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_projectName(id)
PARAMETERS: "id" in "project" table
RETURN VALUES: a single value: "projectName"
EXAMPLES:
my $object = new project;
my $id = 0;
my $res = $object->get_projectName($id);

get_description(id)
PARAMETERS: "id" in "project" table
RETURN VALUES: a single value: "description"
EXAMPLES:
my $object = new project;
my $id = 0;
my $res = $object->get_description($id);

get_creation(id)
PARAMETERS: "id" in "project" table
RETURN VALUES: a single value: "creation"
EXAMPLES:
my $object = new project;
my $id = 0;
my $res = $object->get_creation($id);

get_fileId(id)
PARAMETERS: "id" in "project" table
RETURN VALUES: a reference to an array of "fileId" in "projectFile" table
EXAMPLES:
my $object = new project;
my $id = 0;
my $res = $object->get_file_id($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"fileId"};
}

get_userId(id)
PARAMETERS: "id" in "project" table
RETURN VALUES: a reference to an array of "userId" in "projectUser" table
EXAMPLES:
my $object = new project;
my $id = 0;
my $res = $object->get_userId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"userId"};
}

**************************************************
"process" table

METHODS:
new
EXAMPLES:
my $object = new process;

get_programId(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a single value: "programId"
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_programId($id);

get_userId(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a single value: "userId"
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_userId($id);

get_pipelineId(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a single value: "pipelineId"
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_pipelineId($id);


get_pid(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a single value: "pid"
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_pid($id);


get_creation(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a single value: "creation"
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_creation($id);

get_id_with_pipelineId(pipelineId)
PARAMETERS: "pipelineId" in "process" table
RETURN VALUES: a reference to an array of "id" in "process" table
EXAMPLES:
my $object = new process;
my $pipelineId = 0;
my $res = $object->get_id_with_pipelineId($pipelineId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_userId(userId)
PARAMETERS: "userId" in "process" table
RETURN VALUES: a reference to an array of "id" in "process" table
EXAMPLES:
my $object = new process;
my $userId = 0;
my $res = $object->get_id_with_userId($userId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


get_id_with_programId(programId)
PARAMETERS: "programId" in "process" table
RETURN VALUES: a reference to an array of "id" in "process" table
EXAMPLES:
my $object = new process;
my $programId = 0;
my $res = $object->get_id_with_programId($programId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_pid(pid)
PARAMETERS: "pid" in "process" table
RETURN VALUES: a reference to an array of "id" in "process" table
EXAMPLES:
my $object = new process;
my $pid = 0;
my $res = $object->get_id_with_pid($pid);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_fileId(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a reference to an array of "fileId" in "fileProcess" table
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_fileId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"fileId"};
}

get_parameterId(id)
PARAMETERS: "id" in "process" table
RETURN VALUES: a reference to an array of "parameterId" in "processParameter" table
EXAMPLES:
my $object = new process;
my $id = 0;
my $res = $object->get_parameterId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"parameterId"};
}


***************************************************
"pipeline" table

METHODS:
new
EXAMPLES:
my $object = new pipeline;

get_pipelineName(id)
PARAMETERS: "id" in "pipeline" table
RETURN VALUES: a single value: "pipelineName"
EXAMPLES:
my $object = new pipeline;
my $id = 0;
my $res = $object->get_pipelineName($id);

get_version(id)
PARAMETERS: "id" in "pipeline" table
RETURN VALUES: a single value: "version"
EXAMPLES:
my $object = new pipeline;
my $id = 0;
my $res = $object->get_version($id);

get_userId(id)
PARAMETERS: "id" in "pipeline" table
RETURN VALUES: a reference to an array of "userId" in "pipelineUser" table
EXAMPLES:
my $object = new pipeline;
my $id = 0;
my $res = $object->get_userId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"userId"};
}

get_programId(id)
PARAMETERS: "id" in "pipeline" table
RETURN VALUES: a reference to an array of "programId" in "pipelineProgram" table
EXAMPLES:
my $object = new pipeline;
my $id = 0;
my $res = $object->get_programId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"programId"};
}

get_parameterId(id)
PARAMETERS: "id" in "pipeline" table
RETURN VALUES: a reference to an array of "parameterId" in "pipelineParameter" table
EXAMPLES:
my $object = new pipeline;
my $id = 0;
my $res = $object->get_parameterId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"parameterId"};
}


*************************************************
"pipelineProgram" table

METHODS:
new
EXAMPLES:
my $object = new pipelineProgram;

get_programId(id)
PARAMETERS: "id" in "pipelineProgram" table
RETURN VALUES: a single value: "programId"
EXAMPLES:
my $object = new pipelineProgram;
my $id = 0;
my $res = $object->get_programId($id);

get_pipelineId(id)
PARAMETERS: "id" in "pipelineProgram" table
RETURN VALUES: a single value: "pipelineId"
EXAMPLES:
my $object = new pipelineProgram;
my $id = 0;
my $res = $object->get_pipelineId($id);

get_programOrder(id)
PARAMETERS: "id" in "pipelineProgram" table
RETURN VALUES: a single value: "programOrder"
EXAMPLES:
my $object = new pipelineProgram;
my $id = 0;
my $res = $object->get_programOrder($id);

get_id_with_programId(programId)
PARAMETERS: "programId" in "pipelineProgram" table
RETURN VALUES: a reference to an array of "id" in "pipelineProgram" table
EXAMPLES:
my $object = new pipelineProgram;
my $programId = 0;
my $res = $object->get_id_with_programId($programId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_pipelineId (pipelineId)
PARAMETERS: "pipelineId" in "pipelineProgram" table
RETURN VALUES: a reference to an array of "id" in "pipelineProgram" table
EXAMPLES:
my $object = new pipelineProgram;
my $pipelineId = 0;
my $res = $object->get_id_with_pipelineId($pipelineId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

*******************************************************

"projectFile" table

METHODS:
new
EXAMPLES:
my $object = new projectFile;

get_fileid(id)
PARAMETERS: "id" in "projectFile" table
RETURN VALUES: a single value: "fileid"
EXAMPLES:
my $object = new projectFile;
my $id = 0;
my $res = $object->get_fileid($id);

get_projectid(id)
PARAMETERS: "id" in "projectFile" table
RETURN VALUES: a single value: "projectid"
EXAMPLES:
my $object = new projectid;
my $id = 0;
my $res = $object->get_projectid($id);

get_id_with_fileid (fileid)
PARAMETERS: "fileid" in "projectFile" table
RETURN VALUES: a reference to an array of "id" in "projectFile" table
EXAMPLES:
my $object = new projectFile;
my $fileid = 0;
my $res = $object->get_id_with_fileid($fileid);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_projectid (projectid)
PARAMETERS: "projectid" in "projectFile" table
RETURN VALUES: a reference to an array of "id" in "projectFile" table
EXAMPLES:
my $object = new projectFile;
my $projectid = 0;
my $res = $object->get_id_with_projectid($projectid);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


****************************************************************

"fileProcess" table

METHODS:
new
EXAMPLES:
my $object = new fileProcess;

get_fileid(id)
PARAMETERS: "id" in "fileProcess" table
RETURN VALUES: a single value: "fileid"
EXAMPLES:
my $object = new fileProcess;
my $id = 0;
my $res = $object->get_fileid($id);

get_processId(id)
PARAMETERS: "id" in "fileProcess" table
RETURN VALUES: a single value: "processId"
EXAMPLES:
my $object = new fileProcess;
my $id = 0;
my $res = $object->get_processId($id);

get_IoType(id)
PARAMETERS: "id" in "fileProcess" table
RETURN VALUES: a single value: "IoType"
EXAMPLES:
my $object = new fileProcess;
my $id = 0;
my $res = $object->get_IoType($id);

get_id_with_fileId (fileId)
PARAMETERS: "fileId" in "fileProcess" table
RETURN VALUES: a reference to an array of "id" in "fileProcess" table
EXAMPLES:
my $object = new fileProcess;
my $fileId = 0;
my $res = $object->get_id_with_fileId($fileId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_processId (processId)
PARAMETERS: "processId" in "fileProcess" table
RETURN VALUES: a reference to an array of "id" in "fileProcess" table
EXAMPLES:
my $object = new fileProcess;
my $processId = 0;
my $res = $object->get_id_with_processId($processId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


**************************************************

"processParameter" table

METHODS:
new
EXAMPLES:
my $object = new processParameter;

get_processId (id)
PARAMETERS: "id" in "processParameter" table
RETURN VALUES: a single value: "processId"
EXAMPLES:
my $object = new processParameter;
my $id = 0;
my $res = $object->get_processId ($id);

get_parameterId (id)
PARAMETERS: "id" in "processParameter" table
RETURN VALUES: a single value: "parameterId"
EXAMPLES:
my $object = new processParameter;
my $id = 0;
my $res = $object->get_parameterId($id);

get_parameterValue (id)
PARAMETERS: "id" in "processParameter" table
RETURN VALUES: a single value: "parameterValue"
EXAMPLES:
my $object = new processParameter;
my $id = 0;
my $res = $object->get_parameterValue ($id);

get_id_with_processId (processId)
PARAMETERS: "processId" in "processParameter" table
RETURN VALUES: a reference to an array of "id" in "processParameter" table
EXAMPLES:
my $object = new processParameter;
my $processId = 0;
my $res = $object->get_id_with_processId($processId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_parameterId (parameterId)
PARAMETERS: "parameterId" in "processParameter" table
RETURN VALUES: a reference to an array of "id" in "processParameter" table
EXAMPLES:
my $object = new processParameter;
my $parameterId = 0;
my $res = $object->get_id_with_parameterId($parameterId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


************************************************************
"pipelineParameter" table

METHODS:
new
EXAMPLES:
my $object = new pipelineParameter;

get_pipelineProgramId (id)
PARAMETERS: "id" in "pipelineParameter" table
RETURN VALUES: a single value: "pipelineProgramId"
EXAMPLES:
my $object = new pipelineParameter;
my $id = 0;
my $res = $object->get_pipelineProgramId ($id);

get_parameterId (id)
PARAMETERS: "id" in "pipelineParameter" table
RETURN VALUES: a single value: "parameterId"
EXAMPLES:
my $object = new pipelineParameter;
my $id = 0;
my $res = $object->get_parameterId ($id);

get_parameterValue (id)
PARAMETERS: "id" in "pipelineParameter" table
RETURN VALUES: a single value: "parameterValue"
EXAMPLES:
my $object = new pipelineParameter;
my $id = 0;
my $res = $object->get_parameterValue ($id);

get_id_with_parameterId (parameterId)
PARAMETERS: "parameterId" in "pipelineParameter" table
RETURN VALUES: a reference to an array of "id" in "pipelineParameter" table
EXAMPLES:
my $object = new pipelineParameter;
my $parameterId = 0;
my $res = $object->get_id_with_parameterId($parameterId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_pipelineProgramId (pipelineProgramId)
PARAMETERS: "pipelineProgramId" in "pipelineParameter" table
RETURN VALUES: a reference to an array of "id" in "pipelineParameter" table
EXAMPLES:
my $object = new pipelineParameter;
my $pipelineProgramId = 0;
my $res = $object->get_id_with_pipelineProgramId($pipelineProgramId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


*********************************************************

"program" table

METHODS:
new
EXAMPLES:
my $object = new program;

get_programName (id)
PARAMETERS: "id" in "program" table
RETURN VALUES: a single value: "programName"
EXAMPLES:
my $object = new program;
my $id = 0;
my $res = $object->get_programName ($id);

get_pathId (id)
PARAMETERS: "id" in "program" table
RETURN VALUES: a single value: "pathId"
EXAMPLES:
my $object = new program;
my $id = 0;
my $res = $object->get_pathId ($id);

get_id_with_pathId (pathId)
PARAMETERS: "pathId" in "program" table
RETURN VALUES: a reference to an array of "id" in "program" table
EXAMPLES:
my $object = new program;
my $pathId = 0;
my $res = $object->get_id_with_pathId($pathId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_pipelineId(id)
PARAMETERS: "id" in "program" table
RETURN VALUE: a reference to an array of "pipelineId" in "pipelineProgram" table
Example:
my $object = new program;
my $id = 0;
my $res = $object->get_pipelineId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"pipelineId"};
}

get_parameterId(id)
PARAMETERS: "id" in "program" table
RETURN VALUE: a reference to an array of "parameterId" in "parameter" table
Example:
my $object = new program;
my $id = 0;
my $res = $object->get_parameterId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"parameterId"};
}

get_processId(id)
PARAMETERS: "id" in "program" table
RETURN VALUE: a reference to an array of "processId" in "process" table
Example:
my $object = new program;
my $id = 0;
my $res = $object->get_processId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"processId"};
}


*******************************************************
"file" table

METHODS:
new
EXAMPLES:
my $object = new file;

get_pathId (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a single value: "pathId"
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_pathId ($id);

get_fileName (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a single value: "fileName"
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_fileName ($id);

get_fileType (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a single value: "fileType"
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_fileType ($id);

get_creation (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a single value: "creation"
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_creation ($id);

get_id_with_pathId (pathId)
PARAMETERS: "pathId" in "file" table
RETURN VALUES: a reference to an array of "id" in "file" table
EXAMPLES:
my $object = new file;
my $pathId = 0;
my $res = $object->get_id_with_pathId($pathId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_projectId (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a reference to an array of "projectId" in "projectFile" table
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_projectId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"projectId"};
}

get_userId (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a reference to an array of "userId" in "fileUser" table
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_userId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"userId"};
}

get_processId (id)
PARAMETERS: "id" in "file" table
RETURN VALUES: a reference to an array of "processId" in "fileProcess" table
EXAMPLES:
my $object = new file;
my $id = 0;
my $res = $object->get_processId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"processId"};
}


***************************************************

"parameter" table

METHODS:
new
EXAMPLES:
my $object = new parameter;

get_programId (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "programId"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_programId ($id);

get_parameter (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "parameter"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_parameter ($id);

get_defaultValue (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "defaultValue"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_defaultValue ($id);

get_order (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "order"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_order ($id);

get_enabled (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "enabled"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_enabled ($id);

get_options (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "options"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_options ($id);

get_customized (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a single value: "customized"
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_customized ($id);

get_id_with_programId (programId)
PARAMETERS: "programId" in "parameter" table
RETURN VALUES: a reference to an array of "id" in "parameter" table
EXAMPLES:
my $object = new parameter;
my $programId = 0;
my $res = $object->get_id_with_programId($programId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_processId (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a reference to an array of "processId" in "processParameter" table
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_processId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"processId"};
}

get_pipelineId (id)
PARAMETERS: "id" in "parameter" table
RETURN VALUES: a reference to an array of "pipelineId" in "pipelineParameter" table
EXAMPLES:
my $object = new parameter;
my $id = 0;
my $res = $object->get_pipelineId($id);
foreach my $record_hash ( @$res ){
	print $record_hash->{"pipelineId"};
}


****************************************************
"path" table

METHODS:
new
EXAMPLES:
my $object = new path;

get_path (id)
PARAMETERS: "id" in "path" table
RETURN VALUES: a single value: "path"
EXAMPLES:
my $object = new path;
my $id = 0;
my $res = $object->get_path ($id);

get_creation (id)
PARAMETERS: "id" in "path" table
RETURN VALUES: a single value: "creation"
EXAMPLES:
my $object = new path;
my $id = 0;
my $res = $object->get_creation ($id);


*******************************************************
"programClass" table

METHODS:
new
EXAMPLES:
my $object = new programClass;

get_programId (id)
PARAMETERS: "id" in "programClass" table
RETURN VALUES: a single value: "programId"
EXAMPLES:
my $object = new programClass;
my $id = 0;
my $res = $object->get_programId ($id);

get_classId (id)
PARAMETERS: "id" in "programClass" table
RETURN VALUES: a single value: "classId"
EXAMPLES:
my $object = new programClass;
my $id = 0;
my $res = $object->get_classId ($id);

get_id_with_classId (classId)
PARAMETERS: "classId" in "programClass" table
RETURN VALUES: a reference to an array of "id" in "programClass" table
EXAMPLES:
my $object = new programClass;
my $classId = 0;
my $res = $object->get_id_with_programId($classId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}

get_id_with_programId (programId)
PARAMETERS: "programId" in "programClass" table
RETURN VALUES: a reference to an array of "id" in "programClass" table
EXAMPLES:
my $object = new programClass;
my $programId = 0;
my $res = $object->get_id_with_programId($programId);
foreach my $record_hash ( @$res ){
	print $record_hash->{"id"};
}


***********************************************************
"class" table 

METHODS:
new
EXAMPLES:
my $object = new class;

get_className(id)
PARAMETERS: "id" in "class" table
RETURN VALUES: a single value: "className"
EXAMPLES:
my $object = new class;
my $id = 0;
my $res = $object->get_className($id);

********************************

"help" table:

METHODS:
new
EXAMPLES:
my $object = new help;

get_anchor(id)
Parameters: "id" in "help" table
return a single value: "anchor"
EXAMPLES:
my $object = new help;
my $id = 0;
my $res = $object->get_anchor($id);


