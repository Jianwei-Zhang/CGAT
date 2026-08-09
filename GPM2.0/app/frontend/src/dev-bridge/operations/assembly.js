import {
  normalizeToken,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createAssemblyOperations(runtime) {
  const { runBackend } = runtime;

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

  return {
    listChrViewCtgs,
    listReferenceTrackMembers,
    listPhasedChrTracks,
    createPhasedChrTrack,
    deletePhasedChrTrack,
    addCtgToPhasedChrTrack,
    removePhasedChrTrackItem,
    reorderPhasedChrTrackItems,
  };
}
