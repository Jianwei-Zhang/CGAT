import { normalizeWorkflowError } from "../contracts.js";

export function createTauriAssemblyOperations({ invokeCommand }) {
async function listChrViewCtgsTauri({ workspaceRoot, projectId, chrName, datasetId = null }) {
  const result = await invokeWorkflowCommand("list_chr_view_ctgs", {
    workspaceRoot,
    projectId,
    chrName,
    datasetId,
  });
  return {
    items: result.items || [],
  };
}

async function listReferenceTrackMembersTauri({ workspaceRoot, projectId, chrName }) {
  const result = await invokeWorkflowCommand("list_reference_track_members", {
    workspaceRoot,
    projectId,
    chrName,
  });
  return {
    items: result.items || [],
  };
}

async function listPhasedChrTracksTauri({ workspaceRoot, projectId, parentChrName }) {
  const result = await invokeWorkflowCommand("list_phased_chr_tracks", {
    workspaceRoot,
    projectId,
    parentChrName,
  });
  return {
    projectId: result.projectId || projectId,
    parentChrName: result.parentChrName || parentChrName,
    tracks: result.tracks || [],
  };
}

async function createPhasedChrTrackTauri({ workspaceRoot, projectId, parentChrName }) {
  return invokeWorkflowCommand("create_phased_chr_track", {
    workspaceRoot,
    projectId,
    parentChrName,
  });
}

async function deletePhasedChrTrackTauri({ workspaceRoot, projectId, phasedTrackId }) {
  return invokeWorkflowCommand("delete_phased_chr_track", {
    workspaceRoot,
    projectId,
    phasedTrackId,
  });
}

async function addCtgToPhasedChrTrackTauri({
  workspaceRoot,
  projectId,
  phasedTrackId,
  assemblyCtgId,
}) {
  return invokeWorkflowCommand("add_ctg_to_phased_chr_track", {
    workspaceRoot,
    projectId,
    phasedTrackId,
    assemblyCtgId,
  });
}

async function removePhasedChrTrackItemTauri({
  workspaceRoot,
  projectId,
  phasedTrackItemId,
}) {
  return invokeWorkflowCommand("remove_phased_chr_track_item", {
    workspaceRoot,
    projectId,
    phasedTrackItemId,
  });
}

async function reorderPhasedChrTrackItemsTauri({
  workspaceRoot,
  projectId,
  phasedTrackId,
  itemIds,
}) {
  return invokeWorkflowCommand("reorder_phased_chr_track_items", {
    workspaceRoot,
    projectId,
    phasedTrackId,
    itemIds,
  });
}

async function listDeletedCtgsTauri({ workspaceRoot, projectId, chrName = "", datasetId = null }) {
  const result = await invokeWorkflowCommand("list_deleted_ctgs", {
    workspaceRoot,
    projectId,
    chrName: String(chrName || "").trim() || null,
    datasetId: Number.isFinite(Number(datasetId)) && Number(datasetId) > 0 ? Math.trunc(Number(datasetId)) : null,
  });
  return {
    items: result.items || [],
  };
}

async function restoreDeletedCtgTauri({ workspaceRoot, projectId, deletedCtgRecordId }) {
  return invokeWorkflowCommand("restore_deleted_ctg", {
    workspaceRoot,
    projectId,
    deletedCtgRecordId,
  });
}

async function getCtgDetailTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  return invokeWorkflowCommand("get_ctg_detail", {
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });
}

async function listCtgEditCandidatesTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  const result = await invokeWorkflowCommand("list_ctg_edit_candidates", {
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });
  return {
    moveTargetCtgs: result.moveTargetCtgs || [],
    addSeqCandidates: result.addSeqCandidates || [],
  };
}

async function runCtgEditorActionTauri({ workspaceRoot, projectId, action, args }) {
  return invokeWorkflowCommand("run_ctg_editor_action", {
    workspaceRoot,
    projectId,
    action,
    args,
  });
}

async function getJunctionInspectionTauri({
  workspaceRoot,
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
  minAlignmentLength = null,
  minMapq = null,
}) {
  return invokeWorkflowCommand("get_junction_inspection", {
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  });
}

async function getTrackPairwiseEvidenceTauri({
  workspaceRoot,
  projectId,
  topAssemblyCtgIds,
  bottomAssemblyCtgIds,
  minAlignmentLength = null,
  minMapq = null,
}) {
  return invokeWorkflowCommand("get_track_pairwise_evidence", {
    workspaceRoot,
    projectId,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    minAlignmentLength,
    minMapq,
  });
}

async function appendEditAuditLogTauri({ workspaceRoot, projectId, category, action, detail }) {
  return invokeCommand("append_edit_audit_log", {
    workspaceRoot,
    projectId,
    category,
    action,
    detail,
  });
}

async function invokeWorkflowCommand(command, args) {
  try {
    return await invokeCommand(command, args);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: command,
    });
  }
}

  return {
    listChrViewCtgs: listChrViewCtgsTauri,
    listReferenceTrackMembers: listReferenceTrackMembersTauri,
    listPhasedChrTracks: listPhasedChrTracksTauri,
    createPhasedChrTrack: createPhasedChrTrackTauri,
    deletePhasedChrTrack: deletePhasedChrTrackTauri,
    addCtgToPhasedChrTrack: addCtgToPhasedChrTrackTauri,
    removePhasedChrTrackItem: removePhasedChrTrackItemTauri,
    reorderPhasedChrTrackItems: reorderPhasedChrTrackItemsTauri,
    listDeletedCtgs: listDeletedCtgsTauri,
    restoreDeletedCtg: restoreDeletedCtgTauri,
    getCtgDetail: getCtgDetailTauri,
    listCtgEditCandidates: listCtgEditCandidatesTauri,
    runCtgEditorAction: runCtgEditorActionTauri,
    getJunctionInspection: getJunctionInspectionTauri,
    getTrackPairwiseEvidence: getTrackPairwiseEvidenceTauri,
    appendEditAuditLog: appendEditAuditLogTauri,
  };
}
