import { requireString } from "../contracts.js";

export function createImportOperations(runtime) {
  const { runBackend } = runtime;

async function importZip(payload) {
  const { zipPath, workspaceRoot } = payload || {};
  requireString("zipPath", zipPath);
  requireString("workspaceRoot", workspaceRoot);
  const output = await runBackend(["import-zip", zipPath, workspaceRoot]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const stages = [];
  let workspaceRootResolved = "";
  let bundleRoot = "";
  let projectDbPath = "";

  for (const line of lines) {
    const stageMatch = line.match(/^stage=(.*?) detail=(.*)$/);
    if (stageMatch) {
      stages.push(`${stageMatch[1]}：${stageMatch[2]}`);
      continue;
    }
    if (line.startsWith("workspace_root=")) {
      workspaceRootResolved = line.slice("workspace_root=".length);
      continue;
    }
    if (line.startsWith("bundle_root=")) {
      bundleRoot = line.slice("bundle_root=".length);
      continue;
    }
    if (line.startsWith("project_db_path=")) {
      projectDbPath = line.slice("project_db_path=".length);
      continue;
    }
  }

  return {
    workspaceRoot: workspaceRootResolved || workspaceRoot,
    bundleRoot,
    projectDbPath,
    stages,
    message: "导入完成（dev bridge 实口）。",
  };
}

async function importExtracted(payload) {
  const { extractedPath } = payload || {};
  requireString("extractedPath", extractedPath);
  const output = await runBackend(["import-extracted", extractedPath]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const stages = [];
  let workspaceRootResolved = "";
  let bundleRoot = "";
  let projectDbPath = "";

  for (const line of lines) {
    const stageMatch = line.match(/^stage=(.*?) detail=(.*)$/);
    if (stageMatch) {
      stages.push(`${stageMatch[1]}：${stageMatch[2]}`);
      continue;
    }
    if (line.startsWith("workspace_root=")) {
      workspaceRootResolved = line.slice("workspace_root=".length);
      continue;
    }
    if (line.startsWith("bundle_root=")) {
      bundleRoot = line.slice("bundle_root=".length);
      continue;
    }
    if (line.startsWith("project_db_path=")) {
      projectDbPath = line.slice("project_db_path=".length);
      continue;
    }
  }

  return {
    workspaceRoot: workspaceRootResolved,
    bundleRoot,
    projectDbPath,
    stages,
    message: "已导入解压目录（dev bridge 实口）。",
  };
}

async function importAddDatasetPackage(payload) {
  const { workspaceRoot, zipPath } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireString("zipPath", zipPath);
  const output = await runBackend([
    "import-add-dataset-package",
    zipPath,
    workspaceRoot,
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const stages = [];
  let workspaceRootResolved = "";
  let datasetId = null;
  let datasetName = "";

  for (const line of lines) {
    const stageMatch = line.match(/^stage=(.*?) detail=(.*)$/);
    if (stageMatch) {
      stages.push(`${stageMatch[1]}：${stageMatch[2]}`);
      continue;
    }
    if (line.startsWith("workspace_root=")) {
      workspaceRootResolved = line.slice("workspace_root=".length);
      continue;
    }
    if (line.startsWith("dataset_id=")) {
      datasetId = Number(line.slice("dataset_id=".length));
      continue;
    }
    if (line.startsWith("dataset_name=")) {
      datasetName = line.slice("dataset_name=".length);
    }
  }

  const workspaceRootFinal = workspaceRootResolved || workspaceRoot;
  const options = await listProjectInitializerOptions({ workspaceRoot: workspaceRootFinal });
  return {
    workspaceRoot: workspaceRootFinal,
    ...options,
    stages,
    datasetId,
    datasetName,
    message: "数据集追加包已导入项目区（dev bridge 实口）。",
  };
}

  return {
    importZip,
    importExtracted,
    importAddDatasetPackage,
  };
}
