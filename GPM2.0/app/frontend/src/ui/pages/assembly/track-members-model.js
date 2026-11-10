import { filterPrimaryTrackSelectionCtgIds, normalizeTrackSelectionCtgIds } from "./selection-state.js";
import { getSupportDsCtgLenRulesForChr, resolveEffectiveSupportDsCtgLenForCtg } from "./support-ds-ctg-len-rules.js";
import { hiddenSupportCtgIds } from "./support-visibility-state.js";
import { resolveTrackCtgDisplayName } from "./track-label-geometry.js";

export function resolveTrackMembersScope(state, context) {
  if (context?.isMirror || !["primary", "support"].includes(context?.trackRole)) return null;
  const project = state.initializer?.existingProjects?.find(item => Number(item.projectId) === Number(state.session?.projectId));
  const datasetId = Number(context.datasetId || (context.trackRole === "primary" ? project?.primaryDatasetId : state.assembly?.supportDatasetId));
  if (!Number.isSafeInteger(datasetId) || datasetId <= 0 || !state.assembly?.selectedChrName) return null;
  if (context.trackRole === "support" && datasetId !== Number(state.assembly.supportDatasetId)) return null;
  if (context.trackRole === "primary" && datasetId !== Number(project?.primaryDatasetId)) return null;
  return { workspacePath: state.session?.workspacePath, projectId: state.session?.projectId,
    chrName: state.assembly.selectedChrName, datasetId, trackRole: context.trackRole,
    name: state.initializer?.datasets?.find(item => Number(item.datasetId) === datasetId)?.name || `ds-${datasetId}` };
}

export function matchesTrackMembersScope(state, scope) {
  return state.session?.workspacePath === scope.workspacePath && state.session?.projectId === scope.projectId
    && state.assembly?.selectedChrName === scope.chrName
    && (scope.trackRole !== "support" || Number(state.assembly.supportDatasetId) === scope.datasetId);
}

export function trackMemberRows(state, scope, deleted = []) {
  const assembly = state.assembly;
  const support = scope.trackRole === "support";
  const hidden = support ? hiddenSupportCtgIds(assembly, scope.datasetId) : new Set(assembly.hiddenPrimaryCtgIds || []);
  const chrLength = assembly.chromosomes?.find(chr => chr.chrName === scope.chrName)?.chrLength;
  const rules = getSupportDsCtgLenRulesForChr(assembly.supportDsCtgLenRulesByChr, scope.chrName, { chrLength });
  return [...(support ? assembly.supportChrCtgs || [] : assembly.chrCtgs || []).map(ctg => {
    const threshold = support ? resolveEffectiveSupportDsCtgLenForCtg(ctg, {
      rules, defaultSupportDsCtgLen: assembly.trackView?.supportDsCtgLen ?? assembly.trackView?.supportDsCtgLenBp ?? 0, chrLength,
    }) : 0;
    const length = Math.max(0, Number(ctg.totalLength ?? ctg.lengthBp) || 0);
    const filtered = length < threshold;
    const isHidden = hidden.has(Number(ctg.assemblyCtgId));
    return { key: `ctg:${ctg.assemblyCtgId}`, ctg, name: resolveTrackCtgDisplayName(ctg, ctg.assemblyCtgId),
      length, threshold, filtered, hidden: isHidden, deleted: false, displayed: !filtered && !isHidden,
      // Co-assigned display instances are not independent editable entities.
      editable: !ctg.assignedChrName || ctg.assignedChrName === scope.chrName };
  }), ...deleted.map(ctg => ({ key: `deleted:${ctg.deletedCtgRecordId}`, ctg,
    name: resolveTrackCtgDisplayName(ctg, ctg.assemblyCtgId), length: Number(ctg.totalLength) || 0,
    deleted: true, filtered: false, hidden: false, displayed: false, editable: true }))];
}

export function filterTrackMemberRows(rows, filter = "all", query = "") {
  const needle = query.trim().toLocaleLowerCase();
  return rows.filter(row => (filter === "deleted" ? row.deleted : !row.deleted && (filter === "all" || row[filter]))
    && (!needle || row.name.toLocaleLowerCase().includes(needle)));
}

// Ordinary callers retain their primary-only contract; auxiliary editing must explicitly name its dataset.
export function filterEditableTrackCtgIds(ids, assembly, scope = {}) {
  if (scope.trackRole !== "support") return filterPrimaryTrackSelectionCtgIds(ids, assembly);
  if (Number(scope.datasetId) !== Number(assembly.supportDatasetId)) return [];
  const eligible = new Set((assembly.supportChrCtgs || [])
    .filter(ctg => !ctg.assignedChrName || ctg.assignedChrName === assembly.selectedChrName)
    .map(ctg => Number(ctg.assemblyCtgId)));
  return normalizeTrackSelectionCtgIds(ids).filter(id => eligible.has(id));
}
