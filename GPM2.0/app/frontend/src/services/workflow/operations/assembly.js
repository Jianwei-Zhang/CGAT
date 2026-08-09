import { normalizeSupportedCtgEditorAction } from "../contracts.js";
import { workflowRuntime } from "../runtime.js";

const { isTauriRuntime, callDevBridge, mock, tauri } = workflowRuntime;
const {
  listChrViewCtgs: listChrViewCtgsMock,
  listReferenceTrackMembers: listReferenceTrackMembersMock,
  listPhasedChrTracks: listPhasedChrTracksMock,
  createPhasedChrTrack: createPhasedChrTrackMock,
  deletePhasedChrTrack: deletePhasedChrTrackMock,
  addCtgToPhasedChrTrack: addCtgToPhasedChrTrackMock,
  removePhasedChrTrackItem: removePhasedChrTrackItemMock,
  reorderPhasedChrTrackItems: reorderPhasedChrTrackItemsMock,
  listDeletedCtgs: listDeletedCtgsMock,
  restoreDeletedCtg: restoreDeletedCtgMock,
  getCtgDetail: getCtgDetailMock,
  listCtgEditCandidates: listCtgEditCandidatesMock,
  runCtgEditorAction: runCtgEditorActionMock,
  getJunctionInspection: getJunctionInspectionMock,
  getTrackPairwiseEvidence: getTrackPairwiseEvidenceMock,
  appendEditAuditLog: appendEditAuditLogMock,
} = mock;
const {
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
} = tauri;

export async function listChrViewCtgs({ workspaceRoot, projectId, chrName, datasetId = null }) {
  if (isTauriRuntime()) {
    return listChrViewCtgsTauri({ workspaceRoot, projectId, chrName, datasetId });
  }
  try {
    return await callDevBridge("/api/list-chr-view-ctgs", {
      workspaceRoot,
      projectId,
      chrName,
      datasetId,
    });
  } catch {
    // fallback to mock flow
  }
  return listChrViewCtgsMock({ workspaceRoot, projectId, chrName, datasetId });
}

export async function listReferenceTrackMembers({ workspaceRoot, projectId, chrName }) {
  if (isTauriRuntime()) {
    return listReferenceTrackMembersTauri({ workspaceRoot, projectId, chrName });
  }
  try {
    return await callDevBridge("/api/list-reference-track-members", {
      workspaceRoot,
      projectId,
      chrName,
    });
  } catch {
    // fallback to mock flow
  }
  return listReferenceTrackMembersMock({ workspaceRoot, projectId, chrName });
}

export async function listPhasedChrTracks({ workspaceRoot, projectId, parentChrName }) {
  if (isTauriRuntime()) {
    return listPhasedChrTracksTauri({ workspaceRoot, projectId, parentChrName });
  }
  try {
    return await callDevBridge("/api/list-phased-chr-tracks", {
      workspaceRoot,
      projectId,
      parentChrName,
    });
  } catch {
    // fallback to mock flow
  }
  return listPhasedChrTracksMock({ projectId, parentChrName });
}

export async function createPhasedChrTrack({ workspaceRoot, projectId, parentChrName }) {
  if (isTauriRuntime()) {
    return createPhasedChrTrackTauri({ workspaceRoot, projectId, parentChrName });
  }
  try {
    return await callDevBridge("/api/create-phased-chr-track", {
      workspaceRoot,
      projectId,
      parentChrName,
    });
  } catch {
    // fallback to mock flow
  }
  return createPhasedChrTrackMock({ projectId, parentChrName });
}

export async function deletePhasedChrTrack({ workspaceRoot, projectId, phasedTrackId }) {
  if (isTauriRuntime()) {
    return deletePhasedChrTrackTauri({ workspaceRoot, projectId, phasedTrackId });
  }
  try {
    return await callDevBridge("/api/delete-phased-chr-track", {
      workspaceRoot,
      projectId,
      phasedTrackId,
    });
  } catch {
    // fallback to mock flow
  }
  return deletePhasedChrTrackMock({ projectId, phasedTrackId });
}

export async function addCtgToPhasedChrTrack({
  workspaceRoot,
  projectId,
  phasedTrackId,
  assemblyCtgId,
}) {
  if (isTauriRuntime()) {
    return addCtgToPhasedChrTrackTauri({
      workspaceRoot,
      projectId,
      phasedTrackId,
      assemblyCtgId,
    });
  }
  try {
    return await callDevBridge("/api/add-ctg-to-phased-chr-track", {
      workspaceRoot,
      projectId,
      phasedTrackId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return addCtgToPhasedChrTrackMock({ projectId, phasedTrackId, assemblyCtgId });
}

export async function removePhasedChrTrackItem({ workspaceRoot, projectId, phasedTrackItemId }) {
  if (isTauriRuntime()) {
    return removePhasedChrTrackItemTauri({ workspaceRoot, projectId, phasedTrackItemId });
  }
  try {
    return await callDevBridge("/api/remove-phased-chr-track-item", {
      workspaceRoot,
      projectId,
      phasedTrackItemId,
    });
  } catch {
    // fallback to mock flow
  }
  return removePhasedChrTrackItemMock({ projectId, phasedTrackItemId });
}

export async function reorderPhasedChrTrackItems({
  workspaceRoot,
  projectId,
  phasedTrackId,
  itemIds,
}) {
  if (isTauriRuntime()) {
    return reorderPhasedChrTrackItemsTauri({ workspaceRoot, projectId, phasedTrackId, itemIds });
  }
  try {
    return await callDevBridge("/api/reorder-phased-chr-track-items", {
      workspaceRoot,
      projectId,
      phasedTrackId,
      itemIds,
    });
  } catch {
    // fallback to mock flow
  }
  return reorderPhasedChrTrackItemsMock({ projectId, phasedTrackId, itemIds });
}

export async function listDeletedCtgs({ workspaceRoot, projectId, chrName = "", datasetId = null }) {
  if (isTauriRuntime()) {
    return listDeletedCtgsTauri({ workspaceRoot, projectId, chrName, datasetId });
  }
  try {
    return await callDevBridge("/api/list-deleted-ctgs", {
      workspaceRoot,
      projectId,
      chrName,
      datasetId,
    });
  } catch {
    // fallback to mock flow
  }
  return listDeletedCtgsMock({ workspaceRoot, projectId, chrName, datasetId });
}

export async function restoreDeletedCtg({ workspaceRoot, projectId, deletedCtgRecordId }) {
  if (isTauriRuntime()) {
    return restoreDeletedCtgTauri({ workspaceRoot, projectId, deletedCtgRecordId });
  }
  try {
    return await callDevBridge("/api/restore-deleted-ctg", {
      workspaceRoot,
      projectId,
      deletedCtgRecordId,
    });
  } catch {
    // fallback to mock flow
  }
  return restoreDeletedCtgMock({ workspaceRoot, projectId, deletedCtgRecordId });
}

export async function getCtgDetail({ workspaceRoot, projectId, assemblyCtgId }) {
  if (isTauriRuntime()) {
    return getCtgDetailTauri({ workspaceRoot, projectId, assemblyCtgId });
  }
  try {
    return await callDevBridge("/api/get-ctg-detail", {
      workspaceRoot,
      projectId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return getCtgDetailMock({ workspaceRoot, projectId, assemblyCtgId });
}

export async function listCtgEditCandidates({ workspaceRoot, projectId, assemblyCtgId }) {
  if (isTauriRuntime()) {
    return listCtgEditCandidatesTauri({ workspaceRoot, projectId, assemblyCtgId });
  }
  try {
    return await callDevBridge("/api/list-ctg-edit-candidates", {
      workspaceRoot,
      projectId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return listCtgEditCandidatesMock({ workspaceRoot, projectId, assemblyCtgId });
}

export async function runCtgEditorAction({ workspaceRoot, projectId, action, args }) {
  const normalizedAction = normalizeSupportedCtgEditorAction(action);
  if (isTauriRuntime()) {
    return runCtgEditorActionTauri({ workspaceRoot, projectId, action: normalizedAction, args });
  }
  try {
    return await callDevBridge("/api/ctg-editor-action", {
      workspaceRoot,
      projectId,
      action: normalizedAction,
      args,
    });
  } catch {
    // fallback to mock flow
  }
  return runCtgEditorActionMock({ workspaceRoot, projectId, action: normalizedAction, args });
}

export async function getJunctionInspection({
  workspaceRoot,
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
  minAlignmentLength = null,
  minMapq = null,
}) {
  if (isTauriRuntime()) {
    return getJunctionInspectionTauri({
      workspaceRoot,
      projectId,
      leftAssemblyCtgId,
      rightAssemblyCtgId,
      minAlignmentLength,
      minMapq,
    });
  }
  try {
    return await callDevBridge("/api/get-junction-inspection", {
      workspaceRoot,
      projectId,
      leftAssemblyCtgId,
      rightAssemblyCtgId,
      minAlignmentLength,
      minMapq,
    });
  } catch {
    // fallback to mock flow
  }
  return getJunctionInspectionMock({
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  });
}

export async function getTrackPairwiseEvidence({
  workspaceRoot,
  projectId,
  topAssemblyCtgIds,
  bottomAssemblyCtgIds,
  minAlignmentLength = null,
  minMapq = null,
}) {
  if (isTauriRuntime()) {
    return getTrackPairwiseEvidenceTauri({
      workspaceRoot,
      projectId,
      topAssemblyCtgIds,
      bottomAssemblyCtgIds,
      minAlignmentLength,
      minMapq,
    });
  }
  try {
    return await callDevBridge("/api/get-track-pairwise-evidence", {
      workspaceRoot,
      projectId,
      topAssemblyCtgIds,
      bottomAssemblyCtgIds,
      minAlignmentLength,
      minMapq,
    });
  } catch {
    // fallback to mock flow
  }
  return getTrackPairwiseEvidenceMock({
    workspaceRoot,
    projectId,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    minAlignmentLength,
    minMapq,
  });
}

export async function appendEditAuditLog({ workspaceRoot, projectId, category, action, detail }) {
  if (isTauriRuntime()) {
    return appendEditAuditLogTauri({ workspaceRoot, projectId, category, action, detail });
  }
  try {
    return await callDevBridge("/api/append-edit-audit-log", {
      workspaceRoot,
      projectId,
      category,
      action,
      detail,
    });
  } catch {
    // fallback to mock flow
  }
  return appendEditAuditLogMock({ workspaceRoot, projectId, category, action, detail });
}
