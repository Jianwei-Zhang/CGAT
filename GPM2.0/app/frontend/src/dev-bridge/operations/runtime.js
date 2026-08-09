import {
  parseJsonObject,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createRuntimeOperations(runtime) {
  const { runBackend } = runtime;

async function getRuntimeSettings(payload) {
  const { workspaceRoot } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  const output = await runBackend(["get-runtime-settings", workspaceRoot]);
  const record = parseKeyValueLines(output.stdout);
  return {
    updatedAt: record.updated_at || "",
    degapWorkspaceSettings: parseJsonObject(record.degap_workspace_settings_json),
    source: "workspace_db",
  };
}

async function setRuntimeSettings(payload) {
  const { workspaceRoot, degapWorkspaceSettings } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  const args = ["update-runtime-settings", workspaceRoot];
  if (degapWorkspaceSettings && typeof degapWorkspaceSettings === "object" && !Array.isArray(degapWorkspaceSettings)) {
    args.push("--degap-workspace-settings-json", JSON.stringify(degapWorkspaceSettings));
  }

  const output = await runBackend(args);
  const record = parseKeyValueLines(output.stdout);
  return {
    updatedAt: record.updated_at || "",
    degapWorkspaceSettings: parseJsonObject(record.degap_workspace_settings_json),
    source: "workspace_db",
  };
}

async function exportDegapJobs(payload) {
  const { workspaceRoot, projectId, outputDir, settings, jobs } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("outputDir", outputDir);
  const output = await runBackend([
    "export-degap-jobs",
    workspaceRoot,
    String(projectId),
    outputDir,
    "--settings-json",
    JSON.stringify(settings && typeof settings === "object" && !Array.isArray(settings) ? settings : {}),
    "--jobs-json",
    JSON.stringify(Array.isArray(jobs) ? jobs : []),
  ]);
  const record = parseKeyValueLines(output.stdout);
  const scripts = [];
  for (const line of output.stdout.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)) {
    const match = line.match(
      /^script job_id=(.*?) script_path=(.*?) out_path=(.*?) seqleft_path=(.*?) seqright_path=(.*?) ctg_path=(.*)$/,
    );
    if (!match) {
      continue;
    }
    scripts.push({
      jobId: match[1],
      scriptPath: match[2],
      outPath: match[3],
      seqleftPath: match[4],
      seqrightPath: match[5],
      ctgPath: match[6],
    });
  }
  return {
    outputDir: record.output_dir || outputDir,
    manifestPath: record.manifest_path || "",
    prepareScriptPath: record.prepare_script_path || "",
    scripts,
  };
}

  return {
    getRuntimeSettings,
    setRuntimeSettings,
    exportDegapJobs,
  };
}
