import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import { resolveDefaultBackendExe, resolveRootDirFromFileUrl } from "./dev-bridge-paths.js";

const ROOT_DIR = resolveRootDirFromFileUrl(import.meta.url);
const backendExe =
  process.env.GPM_NEXT_BACKEND_EXE ||
  resolveDefaultBackendExe(ROOT_DIR);

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  plugins: [backendBridgePlugin()],
});

function backendBridgePlugin() {
  return {
    name: "gpm-next-backend-bridge",
    configureServer(server) {
      server.middlewares.use("/api", async (req, res, next) => {
        try {
          const url = new URL(req.url || "", "http://localhost");
          if (req.method === "GET" && url.pathname === "/ping") {
            sendJson(res, 200, {
              ok: true,
              backendExe,
            });
            return;
          }

          if (req.method !== "POST") {
            next();
            return;
          }

          const payload = await readJsonBody(req);

          if (url.pathname === "/import-zip") {
            const result = await importZip(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/import-extracted") {
            const result = await importExtracted(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/import-add-dataset-package") {
            const result = await importAddDatasetPackage(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/open-workspace") {
            const result = await openWorkspace(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-project-initializer-options") {
            const result = await listProjectInitializerOptions(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/initialize-project") {
            const result = await initializeProject(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/update-project") {
            const result = await updateProject(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/delete-project") {
            const result = await deleteProject(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/bootstrap-project-assembly") {
            const result = await bootstrapProjectAssembly(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/auto-assign-chr") {
            const result = await autoAssignChr(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/auto-orient-contigs") {
            const result = await autoOrientContigs(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/set-project-auto-pipeline-done") {
            const result = await setProjectAutoPipelineDone(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-project-chromosomes") {
            const result = await listProjectChromosomes(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-new-sequences") {
            const result = await listNewSequences(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-chr-view-ctgs") {
            const result = await listChrViewCtgs(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-reference-track-members") {
            const result = await listReferenceTrackMembers(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-phased-chr-tracks") {
            const result = await listPhasedChrTracks(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/create-phased-chr-track") {
            const result = await createPhasedChrTrack(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/delete-phased-chr-track") {
            const result = await deletePhasedChrTrack(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/add-ctg-to-phased-chr-track") {
            const result = await addCtgToPhasedChrTrack(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/remove-phased-chr-track-item") {
            const result = await removePhasedChrTrackItem(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/reorder-phased-chr-track-items") {
            const result = await reorderPhasedChrTrackItems(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-deleted-ctgs") {
            const result = await listDeletedCtgs(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/get-ctg-detail") {
            const result = await getCtgDetail(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/restore-deleted-ctg") {
            const result = await restoreDeletedCtg(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-ctg-edit-candidates") {
            const result = await listCtgEditCandidates(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/ctg-editor-action") {
            const result = await runCtgEditorAction(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/get-junction-inspection") {
            const result = await getJunctionInspection(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-export-records") {
            const result = await listExportRecords(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/list-edit-audit-logs") {
            const result = await listEditAuditLogs(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/append-edit-audit-log") {
            const result = await appendEditAuditLog(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/clear-edit-audit-logs") {
            const result = await clearEditAuditLogs(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/runtime-settings-get") {
            const result = await getRuntimeSettings(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/runtime-settings-set") {
            const result = await setRuntimeSettings(payload);
            sendJson(res, 200, result);
            return;
          }

          if (url.pathname === "/export-degap-jobs") {
            const result = await exportDegapJobs(payload);
            sendJson(res, 200, result);
            return;
          }

          next();
        } catch (error) {
          sendJson(res, 500, {
            error: String(error?.message || error),
          });
        }
      });
    },
  };
}

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

async function openWorkspace(payload) {
  const { workspaceRoot } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  const projectDbPath = path.join(workspaceRoot, "project.sqlite");
  if (!fs.existsSync(projectDbPath) || !fs.statSync(projectDbPath).isFile()) {
    throw new Error(`workspace missing project.sqlite: ${projectDbPath}`);
  }
  return listProjectInitializerOptions({ workspaceRoot });
}

async function listProjectInitializerOptions(payload) {
  const { workspaceRoot } = payload || {};
  requireString("workspaceRoot", workspaceRoot);

  const output = await runBackend([
    "list-project-initializer-options",
    workspaceRoot,
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const references = [];
  const datasets = [];
  const existingProjects = [];

  for (const line of lines) {
    const refMatch = line.match(/^reference id=(\d+) name=(.*?) species=(.*?) assembly=(.*)$/);
    if (refMatch) {
      const referenceGenomeId = Number(refMatch[1]);
      const name = refMatch[2];
      const speciesName = refMatch[3];
      const assemblyLabel = refMatch[4];
      references.push({
        referenceGenomeId,
        name,
        speciesName,
        assemblyLabel,
        label: name,
      });
      continue;
    }

    const datasetMatch = line.match(
      /^dataset id=(\d+) name=(.*?) assembler=(.*?) assembler_version=(.*?)(?: fasta_available=(\w+) self_alignment_available=(\w+))?$/,
    );
    if (datasetMatch) {
      const datasetId = Number(datasetMatch[1]);
      const name = datasetMatch[2];
      const assembler = datasetMatch[3];
      const assemblerVersion = normalizeNull(datasetMatch[4]);
      datasets.push({
        datasetId,
        name,
        assembler,
        assemblerVersion,
        fastaAvailable: datasetMatch[5] !== "false",
        selfAlignmentAvailable: datasetMatch[6] !== "false",
        label: name,
      });
      continue;
    }

    const projectMatch = line.match(
      /^project id=(\d+) name=(.*?) version=(\d+) reference_id=(\d+) primary_dataset_id=(\d+) support_dataset_ids=(.*?) is_processed=(\w+) auto_pipeline_done=(\w+) auto_check_new_seq=(\w+)(?: phased_assembly_enabled=(\w+))? description=(.*?) created_at=(.*)$/,
    );
    if (projectMatch) {
      const supportDatasetIdsText = projectMatch[6];
      const supportDatasetIds =
        !supportDatasetIdsText || supportDatasetIdsText === "NULL"
          ? []
          : supportDatasetIdsText
              .split(",")
              .map((item) => Number(item.trim()))
              .filter((item) => Number.isFinite(item) && item > 0);
      existingProjects.push({
        projectId: Number(projectMatch[1]),
        projectName: projectMatch[2],
        version: Number(projectMatch[3]),
        referenceGenomeId: Number(projectMatch[4]),
        primaryDatasetId: Number(projectMatch[5]),
        supportDatasetIds,
        isProcessed: projectMatch[7] === "true",
        autoPipelineDone: projectMatch[8] === "true",
        autoCheckNewSeq: projectMatch[9] === "true",
        phasedAssemblyEnabled: projectMatch[10] === "true",
        description: normalizeNull(projectMatch[11]),
        createdAt: projectMatch[12],
      });
    }
  }

  return {
    workspaceRoot,
    references,
    datasets,
    existingProjects,
  };
}

async function initializeProject(payload) {
  const {
    workspaceRoot,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    phasedAssemblyEnabled,
  } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireString("projectName", projectName);
  requireNumber("referenceGenomeId", referenceGenomeId);
  requireNumber("primaryDatasetId", primaryDatasetId);
  const supportIds = Array.isArray(supportDatasetIds) ? supportDatasetIds : [];

  const args = [
    "initialize-project",
    workspaceRoot,
    projectName,
    String(referenceGenomeId),
    String(primaryDatasetId),
  ];

  if (supportIds.length > 0) {
    args.push("--support-dataset-ids", supportIds.join(","));
  }
  if (typeof phasedAssemblyEnabled === "boolean") {
    args.push("--phased-assembly-enabled", phasedAssemblyEnabled ? "true" : "false");
  }

  const output = await runBackend(args);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const record = {};
  for (const line of lines) {
    const [key, ...rest] = line.split("=");
    if (!key || rest.length === 0) {
      continue;
    }
    record[key] = rest.join("=").trim();
  }

  const options = await listProjectInitializerOptions({ workspaceRoot });
  return {
    projectId: Number(record.project_id || 0),
    projectName: record.project_name || projectName,
    version: Number(record.version || 0),
    phasedAssemblyEnabled: record.phased_assembly_enabled === "true",
    existingProjects: options.existingProjects,
  };
}

async function updateProject(payload) {
  const {
    workspaceRoot,
    projectId,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    phasedAssemblyEnabled,
  } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("projectName", projectName);
  requireNumber("referenceGenomeId", referenceGenomeId);
  requireNumber("primaryDatasetId", primaryDatasetId);
  const supportIds = Array.isArray(supportDatasetIds) ? supportDatasetIds : [];

  const args = [
    "update-project",
    workspaceRoot,
    String(projectId),
    projectName,
    String(referenceGenomeId),
    String(primaryDatasetId),
  ];
  if (supportIds.length > 0) {
    args.push("--support-dataset-ids", supportIds.join(","));
  }
  if (typeof phasedAssemblyEnabled === "boolean") {
    args.push("--phased-assembly-enabled", phasedAssemblyEnabled ? "true" : "false");
  }

  const output = await runBackend(args);
  const record = parseKeyValueLines(output.stdout);
  const options = await listProjectInitializerOptions({ workspaceRoot });
  return {
    projectId: Number(record.project_id || projectId),
    projectName: record.project_name || projectName,
    referenceGenomeId: Number(record.reference_genome_id || referenceGenomeId),
    primaryDatasetId: Number(record.primary_dataset_id || primaryDatasetId),
    phasedAssemblyEnabled: record.phased_assembly_enabled === "true",
    isProcessed: String(record.is_processed || "false") === "true",
    existingProjects: options.existingProjects,
  };
}

async function deleteProject(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  await runBackend([
    "delete-project",
    workspaceRoot,
    String(projectId),
  ]);
  return {
    projectId,
    deleted: true,
  };
}

async function bootstrapProjectAssembly(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  const output = await runBackend([
    "bootstrap-project-assembly",
    workspaceRoot,
    String(projectId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    assemblySeqCount: Number(record.assembly_seq_count || 0),
    assemblyCtgCount: Number(record.assembly_ctg_count || 0),
    assemblyMemberCount: Number(record.assembly_member_count || 0),
  };
}

async function autoAssignChr(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const output = await runBackend([
    "auto-assign-chr",
    workspaceRoot,
    String(projectId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    processedCtgCount: Number(record.processed_ctg_count || 0),
    assignedCount: Number(record.assigned_count || 0),
    repositionedCount: Number(record.repositioned_count || 0),
    clearedCount: Number(record.cleared_count || 0),
    skippedManualCount: Number(record.skipped_manual_count || 0),
    noEvidenceCount: Number(record.no_evidence_count || 0),
    refreshedChrCount: Number(record.refreshed_chr_count || 0),
  };
}

async function autoOrientContigs(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const output = await runBackend([
    "auto-orient-contigs",
    workspaceRoot,
    String(projectId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    processedCtgCount: Number(record.processed_ctg_count || 0),
    orientedCtgCount: Number(record.oriented_ctg_count || 0),
    flippedCtgCount: Number(record.flipped_ctg_count || 0),
    noEvidenceCount: Number(record.no_evidence_count || 0),
    skippedManualCount: Number(record.skipped_manual_count || 0),
  };
}

async function setProjectAutoPipelineDone(payload) {
  const { workspaceRoot, projectId, done } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const doneValue = done === undefined ? true : Boolean(done);
  await runBackend([
    "set-project-auto-pipeline-done",
    workspaceRoot,
    String(projectId),
    "--done",
    doneValue ? "true" : "false",
  ]);
  const options = await listProjectInitializerOptions({ workspaceRoot });
  return {
    projectId,
    autoPipelineDone: doneValue,
    existingProjects: options.existingProjects,
  };
}

async function listProjectChromosomes(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  const output = await runBackend([
    "list-project-chromosomes",
    workspaceRoot,
    String(projectId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const record = parseKeyValueLines(output.stdout);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^chr name=(.*?) order=(\d+) length=(\d+) ctg_count=(\d+) placed_bp=(\d+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      chrName: match[1],
      chrOrder: Number(match[2]),
      chrLength: Number(match[3]),
      ctgCount: Number(match[4]),
      placedBp: Number(match[5]),
    });
  }
  return {
    projectId: Number(record.project_id || projectId),
    referenceGenomeId: Number(record.reference_genome_id || 0),
    unplacedCtgCount: Number(record.unplaced_ctg_count || 0),
    unplacedBp: Number(record.unplaced_bp || 0),
    items,
  };
}

async function listNewSequences(payload) {
  const { workspaceRoot, projectId, limit } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  const output = await runBackend([
    "list-new-sequences",
    workspaceRoot,
    String(projectId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^sequence assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) hidden=(\w+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      assemblySeqId: Number(match[1]),
      datasetName: match[2],
      seqName: match[3],
      seqLength: Number(match[4]),
      hidden: match[5] === "true",
    });
  }
  return { items: applyListLimit(items, limit) };
}

async function listChrViewCtgs(payload) {
  const { workspaceRoot, projectId, chrName, datasetId = null } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);

  const args = [
    "list-chr-view-ctgs",
    workspaceRoot,
    String(projectId),
    "--chr-name",
    chrName,
  ];
  if (Number.isFinite(Number(datasetId)) && Number(datasetId) > 0) {
    args.push("--dataset-id", String(Math.trunc(Number(datasetId))));
  }
  const output = await runBackend(args);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^ctg id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+) anchor_start=(\S+) ref_orient=(\S+) mode=(\S+) members=(\d+) bp=(\d+)(?: dataset_id=(\S+) dataset=(.*))?$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      assemblyCtgId: Number(match[1]),
      name: match[2],
      assignedChrName: normalizeToken(match[3]),
      chrOrder: normalizeToken(match[4]),
      anchorStart: normalizeToken(match[5]),
      refOrient: normalizeToken(match[6]),
      placementMode: match[7],
      memberCount: Number(match[8]),
      totalLength: Number(match[9]),
      datasetId: normalizeToken(match[10]),
      datasetName: normalizeToken(match[11]),
    });
  }
  return { items };
}

async function listReferenceTrackMembers(payload) {
  const { workspaceRoot, projectId, chrName } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);

  const output = await runBackend([
    "list-reference-track-members",
    workspaceRoot,
    String(projectId),
    chrName,
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  const memberByOrder = new Map();

  for (const line of lines) {
    const memberMatch = line.match(
      /^member order=(\d+) ref_chr_id=(\d+) name=(.*?) chr=(.*?) start=(\d+) end=(\d+) anchor_start=(\d+) ref_orient=(\S+) bp=(\d+) hits=(\d+)$/,
    );
    if (memberMatch) {
      const item = {
        sourceKind: "ref_segment",
        referenceChrId: Number(memberMatch[2]),
        referenceChrName: memberMatch[4],
        segmentOrder: Number(memberMatch[1]),
        segmentStartBp: Number(memberMatch[5]),
        segmentEndBp: Number(memberMatch[6]),
        name: memberMatch[3],
        anchorStart: Number(memberMatch[7]),
        totalLength: Number(memberMatch[9]),
        refOrient: memberMatch[8],
        hits: [],
      };
      items.push(item);
      memberByOrder.set(item.segmentOrder, item);
      continue;
    }

    const hitMatch = line.match(
      /^hit member_order=(\d+) hit_id=(\d+) dataset_id=(\d+) source_seq_id=(\d+) strand=(\S+) query_start=(\d+) query_end=(\d+) ref_start=(\d+) ref_end=(\d+) block_length=(\d+) mapq=(\d+) ctg_start=(\d+) ctg_end=(\d+)$/,
    );
    if (!hitMatch) {
      continue;
    }
    const parent = memberByOrder.get(Number(hitMatch[1]));
    if (!parent) {
      continue;
    }
    parent.hits.push({
      hitId: Number(hitMatch[2]),
      datasetId: Number(hitMatch[3]),
      sourceSeqId: Number(hitMatch[4]),
      strand: hitMatch[5],
      queryStart: Number(hitMatch[6]),
      queryEnd: Number(hitMatch[7]),
      refStart: Number(hitMatch[8]),
      refEnd: Number(hitMatch[9]),
      blockLength: Number(hitMatch[10]),
      mapq: Number(hitMatch[11]),
      ctgStart: Number(hitMatch[12]),
      ctgEnd: Number(hitMatch[13]),
    });
  }

  return { items };
}

async function listPhasedChrTracks(payload) {
  const { workspaceRoot, projectId, parentChrName } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("parentChrName", parentChrName);
  const output = await runBackend([
    "list-phased-chr-tracks",
    workspaceRoot,
    String(projectId),
    parentChrName,
  ]);
  return parsePhasedChrTracks(output.stdout, projectId, parentChrName);
}

async function createPhasedChrTrack(payload) {
  const { workspaceRoot, projectId, parentChrName } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("parentChrName", parentChrName);
  const output = await runBackend([
    "create-phased-chr-track",
    workspaceRoot,
    String(projectId),
    parentChrName,
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    track: {
      phasedTrackId: Number(record.phased_track_id || 0),
      projectId: Number(record.project_id || projectId),
      parentChrName: record.parent_chr_name || parentChrName,
      haplotypeKey: record.haplotype_key || "",
      label: record.label || "",
      displayOrder: Number(record.display_order || 0),
      items: [],
    },
  };
}

async function deletePhasedChrTrack(payload) {
  const { workspaceRoot, projectId, phasedTrackId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("phasedTrackId", phasedTrackId);
  const output = await runBackend([
    "delete-phased-chr-track",
    workspaceRoot,
    String(projectId),
    String(phasedTrackId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    phasedTrackId: Number(record.phased_track_id || phasedTrackId),
    parentChrName: record.parent_chr_name || "",
    haplotypeKey: record.haplotype_key || "",
    label: record.label || "",
    deleted: record.deleted === "true",
  };
}

async function addCtgToPhasedChrTrack(payload) {
  const { workspaceRoot, projectId, phasedTrackId, assemblyCtgId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("phasedTrackId", phasedTrackId);
  requireNumber("assemblyCtgId", assemblyCtgId);
  const output = await runBackend([
    "add-ctg-to-phased-chr-track",
    workspaceRoot,
    String(projectId),
    String(phasedTrackId),
    String(assemblyCtgId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    item: {
      itemId: Number(record.phased_track_item_id || 0),
      phasedTrackId: Number(record.phased_track_id || phasedTrackId),
      assemblyCtgId: Number(record.assembly_ctg_id || assemblyCtgId),
      displayOrder: Number(record.display_order || 0),
      gapBeforePx: Number(record.gap_before_px || 0),
    },
  };
}

async function removePhasedChrTrackItem(payload) {
  const { workspaceRoot, projectId, phasedTrackItemId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("phasedTrackItemId", phasedTrackItemId);
  const output = await runBackend([
    "remove-phased-chr-track-item",
    workspaceRoot,
    String(projectId),
    String(phasedTrackItemId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    phasedTrackId: Number(record.phased_track_id || 0),
    phasedTrackItemId: Number(record.phased_track_item_id || phasedTrackItemId),
    removed: record.removed === "true",
  };
}

async function reorderPhasedChrTrackItems(payload) {
  const { workspaceRoot, projectId, phasedTrackId, itemIds } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("phasedTrackId", phasedTrackId);
  if (!Array.isArray(itemIds)) {
    throw new Error("itemIds must be an array");
  }
  const output = await runBackend([
    "reorder-phased-chr-track-items",
    workspaceRoot,
    String(projectId),
    String(phasedTrackId),
    itemIds.join(","),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    phasedTrackId: Number(record.phased_track_id || phasedTrackId),
    itemCount: Number(record.item_count || 0),
  };
}

async function listDeletedCtgs(payload) {
  const { workspaceRoot, projectId, chrName, datasetId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  const args = ["list-deleted-ctgs", workspaceRoot, String(projectId)];
  if (typeof chrName === "string" && chrName.trim()) {
    args.push("--chr-name", chrName.trim());
  }
  if (Number.isFinite(Number(datasetId)) && Number(datasetId) > 0) {
    args.push("--dataset-id", String(Math.trunc(Number(datasetId))));
  }
  const output = await runBackend(args);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^deleted_ctg record_id=(\d+) ctg_id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+) anchor_start=(\S+) ref_orient=(\S+) mode=(\S+) members=(\d+) bp=(\d+) deleted_at=(\S+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      deletedCtgRecordId: Number(match[1]),
      assemblyCtgId: Number(match[2]),
      name: match[3],
      assignedChrName: normalizeToken(match[4]),
      chrOrder: normalizeToken(match[5]),
      anchorStart: normalizeToken(match[6]),
      refOrient: normalizeToken(match[7]),
      placementMode: match[8],
      memberCount: Number(match[9]),
      totalLength: Number(match[10]),
      deletedAt: match[11],
    });
  }
  return { items };
}

async function getCtgDetail(payload) {
  const { workspaceRoot, projectId, assemblyCtgId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("assemblyCtgId", assemblyCtgId);

  const output = await runBackend([
    "get-ctg-detail",
    workspaceRoot,
    String(projectId),
    String(assemblyCtgId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const head = lines.find((line) => line.startsWith("ctg id="));
  if (!head) {
    throw new Error("missing ctg detail head");
  }
  const headMatch = head.match(
    /^ctg id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+) anchor_start=(\S+) ref_orient=(\S+) mode=(\S+)$/,
  );
  if (!headMatch) {
    throw new Error(`invalid ctg detail head: ${head}`);
  }
  const members = [];
  for (const line of lines) {
    const nextFormat = line.match(
      /^member id=(\d+) order=(\d+) assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) orient=(\S+) range=(\d+)\.\.(\d+) left_end_type=(\S+) right_end_type=(\S+) hidden=(\w+) join_prev=(\S+) gap_prev=(\S+)$/,
    );
    if (nextFormat) {
      members.push({
        assemblyCtgMemberId: Number(nextFormat[1]),
        memberOrder: Number(nextFormat[2]),
        assemblySeqId: Number(nextFormat[3]),
        datasetName: nextFormat[4],
        seqName: nextFormat[5],
        seqLength: Number(nextFormat[6]),
        orient: nextFormat[7],
        sourceStart: Number(nextFormat[8]),
        sourceEnd: Number(nextFormat[9]),
        leftEndType: nextFormat[10],
        rightEndType: nextFormat[11],
        hidden: nextFormat[12] === "true",
        joinTypeToPrev: nextFormat[13],
        gapSizeToPrev: normalizeToken(nextFormat[14]),
      });
      continue;
    }

    const oldFormat = line.match(
      /^member order=(\d+) assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) orient=(\S+) range=(\d+)\.\.(\d+) hidden=(\w+) join_prev=(\S+) gap_prev=(\S+)$/,
    );
    if (!oldFormat) {
      continue;
    }
    members.push({
      assemblyCtgMemberId: null,
      memberOrder: Number(oldFormat[1]),
      assemblySeqId: Number(oldFormat[2]),
      datasetName: oldFormat[3],
      seqName: oldFormat[4],
      seqLength: Number(oldFormat[5]),
      orient: oldFormat[6],
      sourceStart: Number(oldFormat[7]),
      sourceEnd: Number(oldFormat[8]),
      leftEndType: "normal",
      rightEndType: "normal",
      hidden: oldFormat[9] === "true",
      joinTypeToPrev: oldFormat[10],
      gapSizeToPrev: normalizeToken(oldFormat[11]),
    });
  }

  return {
    assemblyCtgId: Number(headMatch[1]),
    name: headMatch[2],
    assignedChrName: normalizeToken(headMatch[3]),
    chrOrder: normalizeToken(headMatch[4]),
    anchorStart: normalizeToken(headMatch[5]),
    refOrient: normalizeToken(headMatch[6]),
    placementMode: headMatch[7],
    members,
  };
}

async function listCtgEditCandidates(payload) {
  const { workspaceRoot, projectId, assemblyCtgId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("assemblyCtgId", assemblyCtgId);

  const output = await runBackend([
    "list-ctg-edit-candidates",
    workspaceRoot,
    String(projectId),
    String(assemblyCtgId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const moveTargetCtgs = [];
  const addSeqCandidates = [];

  for (const line of lines) {
    const moveMatch = line.match(/^move_target id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+)$/);
    if (moveMatch) {
      moveTargetCtgs.push({
        assemblyCtgId: Number(moveMatch[1]),
        name: moveMatch[2],
        assignedChrName: normalizeToken(moveMatch[3]),
        chrOrder: normalizeToken(moveMatch[4]),
      });
      continue;
    }
    const addMatch = line.match(
      /^add_seq assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) hidden=(\w+)$/,
    );
    if (addMatch) {
      addSeqCandidates.push({
        assemblySeqId: Number(addMatch[1]),
        datasetName: addMatch[2],
        seqName: addMatch[3],
        seqLength: Number(addMatch[4]),
        hidden: addMatch[5] === "true",
      });
    }
  }
  return {
    moveTargetCtgs,
    addSeqCandidates,
  };
}

async function restoreDeletedCtg(payload) {
  const { workspaceRoot, projectId, deletedCtgRecordId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("deletedCtgRecordId", deletedCtgRecordId);

  const output = await runBackend([
    "restore-deleted-ctg",
    workspaceRoot,
    String(projectId),
    String(deletedCtgRecordId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    deletedCtgRecordId: Number(record.deleted_ctg_record_id || deletedCtgRecordId),
    assemblyCtgId: Number(record.assembly_ctg_id || 0),
    restoredMemberCount: Number(record.restored_member_count || 0),
    refreshedChrCount: Number(record.refreshed_chr_count || 0),
  };
}

async function runCtgEditorAction(payload) {
  const { workspaceRoot, projectId, action, args } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("action", action);
  const normalized = action.trim().toLowerCase();
  const commandArgs = buildCtgEditorCommandArgs(normalized, workspaceRoot, projectId, args || {});
  const output = await runBackend(commandArgs);
  const record = parseKeyValueLines(output.stdout);
  return {
    action: normalized,
    ...record,
  };
}

async function getJunctionInspection(payload) {
  const {
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("leftAssemblyCtgId", leftAssemblyCtgId);
  requireNumber("rightAssemblyCtgId", rightAssemblyCtgId);

  const args = [
    "get-junction-inspection",
    workspaceRoot,
    String(projectId),
    String(leftAssemblyCtgId),
    String(rightAssemblyCtgId),
  ];
  if (Number.isFinite(Number(minAlignmentLength)) && Number(minAlignmentLength) > 0) {
    args.push("--min-align-length", String(Math.trunc(Number(minAlignmentLength))));
  }
  if (Number.isFinite(Number(minMapq)) && Number(minMapq) > 0) {
    args.push("--min-mapq", String(Math.trunc(Number(minMapq))));
  }
  const output = await runBackend(args);
  return parseJunctionInspection(output.stdout);
}

async function listExportRecords(payload) {
  const { workspaceRoot, projectId, limit } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const resolvedLimit = Number.isFinite(limit) ? Math.trunc(limit) : 50;
  const output = await runBackend([
    "list-export-records",
    workspaceRoot,
    String(projectId),
    "--limit",
    String(Math.max(1, resolvedLimit)),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^record id=(\d+) project_id=(\d+) export_type=(\S+) reference_chr_id=(\S+) assembly_ctg_id=(\S+) output_path=(\S+) created_at=(\S+) note=(.*)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      id: Number(match[1]),
      projectId: Number(match[2]),
      exportType: match[3],
      referenceChrId: normalizeToken(match[4]),
      assemblyCtgId: normalizeToken(match[5]),
      outputPath: match[6],
      createdAt: match[7],
      note: normalizeToken(match[8]),
    });
  }
  return { items };
}

async function listEditAuditLogs(payload) {
  const { workspaceRoot, projectId, limit } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const resolvedLimit = Number.isFinite(limit) ? Math.trunc(limit) : 200;
  const output = await runBackend([
    "list-edit-audit-logs",
    workspaceRoot,
    String(projectId),
    "--limit",
    String(Math.max(1, resolvedLimit)),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^log id=(\d+) project_id=(\d+) category=(\S+) action=(.*?) detail=(.*?) created_at=(\S+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      id: Number(match[1]),
      projectId: Number(match[2]),
      category: match[3],
      action: match[4],
      detail: normalizeNullableText(match[5]),
      createdAt: match[6],
    });
  }
  return { items };
}

async function appendEditAuditLog(payload) {
  const { workspaceRoot, projectId, category, action, detail } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("category", category);
  requireString("action", action);
  const args = [
    "append-edit-audit-log",
    workspaceRoot,
    String(projectId),
    category,
    action,
  ];
  if (typeof detail === "string" && detail.trim() !== "") {
    args.push("--detail", detail.trim());
  }
  const output = await runBackend(args);
  const record = parseKeyValueLines(output.stdout);
  return {
    id: Number(record.id || 0),
    projectId: Number(record.project_id || projectId),
    category: record.category || category,
    action: record.action || action,
    detail: typeof detail === "string" && detail.trim() ? detail.trim() : null,
    createdAt: record.created_at || "",
  };
}

async function clearEditAuditLogs(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const output = await runBackend([
    "clear-edit-audit-logs",
    workspaceRoot,
    String(projectId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    deletedCount: Number(record.deleted_count || 0),
  };
}

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

function buildCtgEditorCommandArgs(action, workspaceRoot, projectId, args) {
  const base = [workspaceRoot, String(projectId)];
  switch (action) {
    case "rename-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      requireString("args.newName", args.newName);
      return ["rename-ctg", ...base, String(args.assemblyCtgId), args.newName];
    case "flip-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      return ["flip-ctg", ...base, String(args.assemblyCtgId)];
    case "delete-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      return ["delete-ctg", ...base, String(args.assemblyCtgId)];
    case "restore-deleted-ctg":
      requireNumber("args.deletedCtgRecordId", args.deletedCtgRecordId);
      return ["restore-deleted-ctg", ...base, String(args.deletedCtgRecordId)];
    case "reorder-members":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      if (!Array.isArray(args.assemblySeqIds) || args.assemblySeqIds.length === 0) {
        throw new Error("args.assemblySeqIds must be a non-empty array");
      }
      return [
        "reorder-members",
        ...base,
        String(args.assemblyCtgId),
        args.assemblySeqIds.map((value) => String(value)).join(","),
      ];
    case "add-seq-to-ctg":
      requireNumber("args.targetAssemblyCtgId", args.targetAssemblyCtgId);
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return [
        "add-seq-to-ctg",
        ...base,
        String(args.targetAssemblyCtgId),
        String(args.assemblySeqId),
      ];
    case "append-ctg":
      requireNumber("args.targetAssemblyCtgId", args.targetAssemblyCtgId);
      requireNumber("args.sourceAssemblyCtgId", args.sourceAssemblyCtgId);
      return [
        "append-ctg",
        ...base,
        String(args.targetAssemblyCtgId),
        String(args.sourceAssemblyCtgId),
      ];
    case "split-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      requireNumber("args.breakAfterMemberId", args.breakAfterMemberId);
      requireString("args.newName", args.newName);
      return [
        "split-ctg",
        ...base,
        String(args.assemblyCtgId),
        String(args.breakAfterMemberId),
        args.newName,
      ];
    case "remove-seq-from-ctg":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      return ["remove-seq-from-ctg", ...base, String(args.assemblyCtgMemberId)];
    case "set-join-type-to-prev":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      requireString("args.joinTypeToPrev", args.joinTypeToPrev);
      if (args.gapSizeToPrev !== undefined && args.gapSizeToPrev !== null) {
        requireNumber("args.gapSizeToPrev", args.gapSizeToPrev);
      }
      return args.gapSizeToPrev === undefined || args.gapSizeToPrev === null
        ? [
            "set-join-type-to-prev",
            ...base,
            String(args.assemblyCtgMemberId),
            args.joinTypeToPrev,
          ]
        : [
            "set-join-type-to-prev",
            ...base,
            String(args.assemblyCtgMemberId),
            args.joinTypeToPrev,
            "--gap-size-to-prev",
            String(args.gapSizeToPrev),
          ];
    case "set-gap-size-to-prev":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      requireNumber("args.gapSizeToPrev", args.gapSizeToPrev);
      return [
        "set-gap-size-to-prev",
        ...base,
        String(args.assemblyCtgMemberId),
        String(args.gapSizeToPrev),
      ];
    case "flip-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["flip-seq", ...base, String(args.assemblySeqId)];
    case "hide-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["hide-seq", ...base, String(args.assemblySeqId)];
    case "show-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["show-seq", ...base, String(args.assemblySeqId)];
    case "set-seq-range":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      requireNumber("args.sourceStart", args.sourceStart);
      requireNumber("args.sourceEnd", args.sourceEnd);
      return [
        "set-seq-range",
        ...base,
        String(args.assemblySeqId),
        String(args.sourceStart),
        String(args.sourceEnd),
      ];
    case "set-end-type":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      requireString("args.leftEndType", args.leftEndType);
      requireString("args.rightEndType", args.rightEndType);
      return [
        "set-end-type",
        ...base,
        String(args.assemblySeqId),
        args.leftEndType,
        args.rightEndType,
      ];
    default:
      throw new Error(`unsupported ctg editor action: ${action}`);
  }
}

function parsePhasedChrTracks(stdout, fallbackProjectId, fallbackParentChrName) {
  const lines = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const record = parseKeyValueLines(stdout);
  const tracks = [];
  let currentTrack = null;
  for (const line of lines) {
    const trackMatch = line.match(
      /^track id=(\d+) parent_chr_name=(.*?) haplotype_key=(.*?) label=(.*?) display_order=(\d+) item_count=(\d+)$/,
    );
    if (trackMatch) {
      currentTrack = {
        phasedTrackId: Number(trackMatch[1]),
        projectId: Number(record.project_id || fallbackProjectId),
        parentChrName: trackMatch[2],
        haplotypeKey: trackMatch[3],
        label: trackMatch[4],
        displayOrder: Number(trackMatch[5]),
        items: [],
      };
      tracks.push(currentTrack);
      continue;
    }

    const itemMatch = line.match(
      /^item id=(\d+) phased_track_id=(\d+) assembly_ctg_id=(\d+) display_order=(\d+) gap_before_px=(\d+)$/,
    );
    if (!itemMatch || !currentTrack) {
      continue;
    }
    currentTrack.items.push({
      itemId: Number(itemMatch[1]),
      phasedTrackId: Number(itemMatch[2]),
      assemblyCtgId: Number(itemMatch[3]),
      displayOrder: Number(itemMatch[4]),
      gapBeforePx: Number(itemMatch[5]),
    });
  }
  return {
    projectId: Number(record.project_id || fallbackProjectId),
    parentChrName: record.parent_chr_name || fallbackParentChrName,
    tracks,
  };
}

function parseJunctionInspection(stdout) {
  const lines = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const record = parseKeyValueLines(stdout);
  const report = {
    projectId: Number(record.project_id || 0),
    assignedChrName: normalizeToken(record.assigned_chr_name),
    placementRelation: record.placement_relation || "unknown",
    overlapBp: normalizeToken(record.overlap_bp),
    gapBp: normalizeToken(record.gap_bp),
    sameDataset: record.same_dataset === "true",
    evidenceSource: record.evidence_source || "unknown",
    evidenceHitCount: Number(record.evidence_hit_count || 0),
    left: {
      assemblyCtgId: Number(record.left_ctg_id || 0),
      name: normalizeToken(record.left_name),
      anchorStart: normalizeToken(record.left_anchor),
      anchorEnd: normalizeToken(record.left_end),
      spanLength: Number(record.left_span || 0),
    },
    right: {
      assemblyCtgId: Number(record.right_ctg_id || 0),
      name: normalizeToken(record.right_name),
      anchorStart: normalizeToken(record.right_anchor),
      anchorEnd: normalizeToken(record.right_end),
      spanLength: Number(record.right_span || 0),
    },
    hits: [],
  };

  for (const line of lines) {
    const hit = line.match(
      /^hit query_ctg_id=(\d+) query_id=(\d+) query_name=(.*?) subject_ctg_id=(\d+) subject_id=(\d+) subject_name=(.*?) strand=(\S+) q=(\d+)\.\.(\d+) s=(\d+)\.\.(\d+) mapq=(\d+) identity_pct=([0-9.]+) align_length=(\d+) mismatch_count=(\S+) gap_open_count=(\S+) evalue=(\S+) bit_score=(\S+) origin=(\S+)$/,
    );
    if (hit) {
      report.hits.push({
        queryAssemblyCtgId: Number(hit[1]),
        querySourceSeqId: Number(hit[2]),
        querySourceSeqName: hit[3],
        subjectAssemblyCtgId: Number(hit[4]),
        subjectSourceSeqId: Number(hit[5]),
        subjectSourceSeqName: hit[6],
        strand: hit[7],
        queryStart: Number(hit[8]),
        queryEnd: Number(hit[9]),
        subjectStart: Number(hit[10]),
        subjectEnd: Number(hit[11]),
        mapq: Number(hit[12]),
        identityPct: Number(hit[13]),
        alignLength: Number(hit[14]),
        mismatchCount: normalizeToken(hit[15]),
        gapOpenCount: normalizeToken(hit[16]),
        evalue: normalizeToken(hit[17]),
        bitScore: normalizeToken(hit[18]),
        evidenceOrigin: hit[19],
      });
      continue;
    }
    const legacyHit = line.match(
      /^hit query_id=(\d+) query_name=(.*?) subject_id=(\d+) subject_name=(.*?) strand=(\S+) q=(\d+)\.\.(\d+) s=(\d+)\.\.(\d+) identity_pct=([0-9.]+) align_length=(\d+) mismatch_count=(\S+) gap_open_count=(\S+) evalue=(\S+) bit_score=(\S+) origin=(\S+)$/,
    );
    if (!legacyHit) {
      continue;
    }
    report.hits.push({
      querySourceSeqId: Number(legacyHit[1]),
      querySourceSeqName: legacyHit[2],
      subjectSourceSeqId: Number(legacyHit[3]),
      subjectSourceSeqName: legacyHit[4],
      strand: legacyHit[5],
      queryStart: Number(legacyHit[6]),
      queryEnd: Number(legacyHit[7]),
      subjectStart: Number(legacyHit[8]),
      subjectEnd: Number(legacyHit[9]),
      identityPct: Number(legacyHit[10]),
      alignLength: Number(legacyHit[11]),
      mismatchCount: normalizeToken(legacyHit[12]),
      gapOpenCount: normalizeToken(legacyHit[13]),
      evalue: normalizeToken(legacyHit[14]),
      bitScore: normalizeToken(legacyHit[15]),
      evidenceOrigin: legacyHit[16],
    });
  }
  return report;
}

function runBackend(args) {
  const env = buildBackendEnv();
  return new Promise((resolve, reject) => {
    const child = spawn(backendExe, args, {
      cwd: path.resolve(ROOT_DIR, ".."),
      stdio: ["ignore", "pipe", "pipe"],
      env,
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      reject(error);
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `backend command failed (code=${code})\nargs=${args.join(" ")}\n${stderr || stdout}`,
          ),
        );
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function buildBackendEnv() {
  return { ...process.env };
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let text = "";
    req.on("data", (chunk) => {
      text += chunk.toString();
    });
    req.on("end", () => {
      if (!text) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(text));
      } catch (error) {
        reject(new Error(`invalid json body: ${error.message}`));
      }
    });
    req.on("error", (error) => {
      reject(error);
    });
  });
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(payload);
}

function requireString(name, value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`missing required field: ${name}`);
  }
}

function requireNumber(name, value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`missing required number field: ${name}`);
  }
}

function normalizeNull(value) {
  return value === "NULL" ? null : value;
}

function normalizeToken(value) {
  if (value === "NULL") {
    return null;
  }
  if (/^-?\d+$/.test(value)) {
    return Number(value);
  }
  return value;
}

function applyListLimit(items, limit) {
  const normalizedItems = Array.isArray(items) ? items : [];
  const normalizedLimit = Number(limit);
  if (!Number.isFinite(normalizedLimit) || normalizedLimit < 0) {
    return normalizedItems;
  }
  return normalizedItems.slice(0, normalizedLimit);
}

function parseKeyValueLines(stdout) {
  const record = {};
  const lines = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    if (line.startsWith("stage=")) {
      continue;
    }
    const keyPattern = /([A-Za-z0-9_]+)=/g;
    const matches = Array.from(line.matchAll(keyPattern));
    if (matches.length === 0) {
      continue;
    }
    for (let index = 0; index < matches.length; index += 1) {
      const current = matches[index];
      const next = matches[index + 1];
      const key = current[1];
      const valueStart = current.index + current[0].length;
      const valueEnd = next ? next.index : line.length;
      const value = line.slice(valueStart, valueEnd).trim();
      record[key] = value;
    }
  }
  return record;
}

function parseJsonObject(value) {
  try {
    const parsed = JSON.parse(String(value || "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function normalizeNullableText(value) {
  if (value === "NULL") {
    return null;
  }
  return value;
}
