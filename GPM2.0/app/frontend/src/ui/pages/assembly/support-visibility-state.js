// Main-view display preference. Source membership, Local View and Final Path are unchanged.
export function normalizeHiddenSupportCtgs(value) {
  const entries = new Map();
  for (const item of Array.isArray(value) ? value : []) {
    const chrName = String(item?.chrName || "").trim();
    const datasetId = Number(item?.datasetId), assemblyCtgId = Number(item?.assemblyCtgId);
    if (!chrName || !Number.isSafeInteger(datasetId) || datasetId <= 0
      || !Number.isSafeInteger(assemblyCtgId) || assemblyCtgId <= 0) continue;
    entries.set(JSON.stringify([chrName, datasetId, assemblyCtgId]), { chrName, datasetId, assemblyCtgId });
  }
  return [...entries.values()];
}

export function hiddenSupportCtgIds(assembly, datasetId = assembly?.supportDatasetId) {
  return new Set(normalizeHiddenSupportCtgs(assembly?.trackView?.hiddenSupportCtgs)
    .filter(item => item.chrName === assembly?.selectedChrName && item.datasetId === Number(datasetId))
    .map(item => item.assemblyCtgId));
}

export function setSupportCtgsHidden(assembly, datasetId, ids, hidden) {
  const allowed = new Set((assembly.supportChrCtgs || []).map(ctg => Number(ctg.assemblyCtgId)));
  const selected = new Set(ids.map(Number).filter(id => allowed.has(id)));
  if (Number(datasetId) !== Number(assembly.supportDatasetId)) return assembly;
  const entries = normalizeHiddenSupportCtgs(assembly.trackView?.hiddenSupportCtgs).filter(item => !(
    item.chrName === assembly.selectedChrName && item.datasetId === Number(datasetId) && selected.has(item.assemblyCtgId)
  ));
  if (hidden) for (const assemblyCtgId of selected) entries.push({ chrName: assembly.selectedChrName, datasetId: Number(datasetId), assemblyCtgId });
  return { ...assembly, trackView: { ...assembly.trackView, hiddenSupportCtgs: entries } };
}
