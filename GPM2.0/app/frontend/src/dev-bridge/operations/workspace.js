import fs from "node:fs";
import path from "node:path";

import {
  applyListLimit,
  mapGrtRecipeToApi,
  normalizeNull,
  parseIdList,
  parseJsonLine,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createWorkspaceOperations(runtime) {
  const { runBackend } = runtime;

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
      /^dataset id=(\d+) name=(.*?) assembler=(.*?) assembler_version=(.*?) contig_count=(\d+) total_length_bp=(\d+) fasta_available=(\w+) self_alignment_available=(\w+)$/,
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
        contigCount: Number(datasetMatch[5]),
        totalLengthBp: Number(datasetMatch[6]),
        fastaAvailable: datasetMatch[7] !== "false",
        selfAlignmentAvailable: datasetMatch[8] !== "false",
        label: name,
      });
      continue;
    }

    const projectMatch = line.match(
      /^project id=(\d+) name=(.*?) version=(\d+) reference_id=(\d+) primary_dataset_id=(\d+) support_dataset_ids=(.*?) is_processed=(\w+) auto_pipeline_done=(\w+) auto_check_new_seq=(\w+) phased_assembly_enabled=(\w+) chr_assignment_min_coverage_percent=([0-9.]+) description=(.*?) created_at=(.*)$/,
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
        chrAssignmentMinCoveragePercent: Number(projectMatch[11]),
        description: normalizeNull(projectMatch[12]),
        createdAt: projectMatch[13],
      });
    }
  }

  return {
    workspaceRoot,
    packageMetadata: parseJsonLine(output.stdout, "package_metadata_json"),
    grtRecipe: mapGrtRecipeToApi(parseJsonLine(output.stdout, "grt_recipe_json")),
    references,
    datasets,
    existingProjects,
  };
}

async function initializeProject(payload) {
  const { workspaceRoot, projectName, phasedAssemblyEnabled = false } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireString("projectName", projectName);
  if (typeof phasedAssemblyEnabled !== "boolean") {
    throw new Error("phasedAssemblyEnabled must be boolean");
  }
  const output = await runBackend([
    "initialize-project",
    workspaceRoot,
    projectName,
    "--phased-assembly-enabled",
    phasedAssemblyEnabled ? "true" : "false",
  ]);
  const record = parseKeyValueLines(output.stdout);

  const options = await listProjectInitializerOptions({ workspaceRoot });
  return {
    projectId: Number(record.project_id || 0),
    projectName: record.project_name || projectName,
    version: Number(record.version || 0),
    referenceGenomeId: Number(record.reference_genome_id || 0),
    primaryDatasetId: Number(record.primary_dataset_id || 0),
    supportDatasetIds: parseIdList(record.support_dataset_ids),
    projectDatasetCount: Number(record.project_dataset_count || 0),
    phasedAssemblyEnabled: record.phased_assembly_enabled === "true",
    chrAssignmentMinCoveragePercent: Number(
      record.chr_assignment_min_coverage_percent || 60,
    ),
    assemblySeqCount: Number(record.assembly_seq_count || 0),
    assemblyCtgCount: Number(record.assembly_ctg_count || 0),
    materializedSourceCardCount: Number(record.materialized_source_card_count || 0),
    grtProjectView: parseJsonLine(output.stdout, "grt_project_view_json"),
    existingProjects: options.existingProjects,
  };
}

async function getGrtProjectView(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  return runGrtJsonCommand(["get-grt-project-view", workspaceRoot, String(projectId)]);
}

async function runGrtJsonCommand(args) {
  const output = await runBackend(args);
  return parseJsonLine(output.stdout, "json");
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

  return {
    openWorkspace,
    listProjectInitializerOptions,
    initializeProject,
    getGrtProjectView,
    updateProject,
    deleteProject,
    bootstrapProjectAssembly,
    autoAssignChr,
    autoOrientContigs,
    setProjectAutoPipelineDone,
    listProjectChromosomes,
    listNewSequences,
  };
}
