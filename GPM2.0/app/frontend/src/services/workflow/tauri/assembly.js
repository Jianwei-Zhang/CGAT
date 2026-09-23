export function createTauriAssemblyOperations({ invokeCommand }) {
async function listChrViewCtgsTauri({ workspaceRoot, projectId, chrName, datasetId = null }) {
  const result = await invokeCommand("list_chr_view_ctgs", {
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
  const result = await invokeCommand("list_reference_track_members", {
    workspaceRoot,
    projectId,
    chrName,
  });
  return {
    items: result.items || [],
  };
}

async function listPhasedChrTracksTauri({ workspaceRoot, projectId, parentChrName }) {
  const result = await invokeCommand("list_phased_chr_tracks", {
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
  return invokeCommand("create_phased_chr_track", {
    workspaceRoot,
    projectId,
    parentChrName,
  });
}

async function deletePhasedChrTrackTauri({ workspaceRoot, projectId, phasedTrackId }) {
  return invokeCommand("delete_phased_chr_track", {
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
  return invokeCommand("add_ctg_to_phased_chr_track", {
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
  return invokeCommand("remove_phased_chr_track_item", {
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
  return invokeCommand("reorder_phased_chr_track_items", {
    workspaceRoot,
    projectId,
    phasedTrackId,
    itemIds,
  });
}

async function listDeletedCtgsTauri({ workspaceRoot, projectId, chrName = "", datasetId = null }) {
  const result = await invokeCommand("list_deleted_ctgs", {
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
  return invokeCommand("restore_deleted_ctg", {
    workspaceRoot,
    projectId,
    deletedCtgRecordId,
  });
}

async function getCtgDetailTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  return invokeCommand("get_ctg_detail", {
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });
}

async function listCtgEditCandidatesTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  const result = await invokeCommand("list_ctg_edit_candidates", {
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
  return invokeCommand("run_ctg_editor_action", {
    workspaceRoot,
    projectId,
    action,
    args,
  });
}

function buildMainViewHistoryRequest({ workspaceRoot, projectId, chrName, historyCapacity }) {
  return {
    request: { workspaceRoot, projectId, chrName, historyCapacity },
  };
}

async function getMainViewHistoryStatusTauri({ workspaceRoot, projectId, chrName, historyCapacity }) {
  return invokeCommand(
    "get_main_view_history_status",
    buildMainViewHistoryRequest({ workspaceRoot, projectId, chrName, historyCapacity }),
  );
}

async function inspectMainViewDeleteTauri({
  historyCapacity,
  workspaceRoot,
  projectId,
  chrName,
  assemblyCtgIds,
}) {
  return invokeCommand("inspect_main_view_delete", {
    request: { historyCapacity, workspaceRoot, projectId, chrName, assemblyCtgIds },
  });
}

async function runMainViewEditorActionTauri({
  historyCapacity,
  workspaceRoot,
  projectId,
  chrName,
  action,
  args,
}) {
  return invokeCommand("run_main_view_editor_action", {
    request: { historyCapacity, workspaceRoot, projectId, chrName, action, args },
  });
}

async function runMainViewLayoutActionTauri({
  historyCapacity,
  workspaceRoot,
  projectId,
  chrName,
  action,
  args,
}) {
  return invokeCommand("run_main_view_layout_action", {
    request: { historyCapacity, workspaceRoot, projectId, chrName, action, args },
  });
}

async function runMainViewBatchDeleteTauri({
  historyCapacity,
  workspaceRoot,
  projectId,
  chrName,
  assemblyCtgIds,
}) {
  return invokeCommand("run_main_view_batch_delete", {
    request: { historyCapacity, workspaceRoot, projectId, chrName, assemblyCtgIds },
  });
}

async function executeMainViewHistoryActionTauri({
  historyCapacity,
  workspaceRoot,
  projectId,
  chrName,
  action,
}) {
  const commands = {
    undo: "undo_main_view_history",
    redo: "redo_main_view_history",
    reset: "reset_main_view_history",
  };
  const command = commands[String(action || "").trim().toLowerCase()];
  if (!command) {
    throw new Error(`unsupported main-view history action: ${action || "<empty>"}`);
  }
  return invokeCommand(
    command,
    buildMainViewHistoryRequest({ workspaceRoot, projectId, chrName, historyCapacity }),
  );
}

async function getJunctionInspectionTauri({
  workspaceRoot,
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
  minAlignmentLength = null,
  minIdentityPct = null,
}) {
  return invokeCommand("get_junction_inspection", {
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minIdentityPct,
  });
}

async function getTrackPairwiseEvidenceTauri({
  workspaceRoot,
  projectId,
  topAssemblyCtgIds,
  bottomAssemblyCtgIds,
  minAlignmentLength = null,
  minIdentityPct = null,
}) {
  return invokeCommand("get_track_pairwise_evidence", {
    workspaceRoot,
    projectId,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    minAlignmentLength,
    minIdentityPct,
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
    getMainViewHistoryStatus: getMainViewHistoryStatusTauri,
    inspectMainViewDelete: inspectMainViewDeleteTauri,
    runMainViewEditorAction: runMainViewEditorActionTauri,
    runMainViewLayoutAction: runMainViewLayoutActionTauri,
    runMainViewBatchDelete: runMainViewBatchDeleteTauri,
    executeMainViewHistoryAction: executeMainViewHistoryActionTauri,
    getJunctionInspection: getJunctionInspectionTauri,
    getTrackPairwiseEvidence: getTrackPairwiseEvidenceTauri,
    appendEditAuditLog: appendEditAuditLogTauri,
  };
}
