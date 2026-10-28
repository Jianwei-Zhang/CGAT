import { previewSemanticSignature, previewMutationStamp } from "../../services/preview-content-events.js";
import { normalizeFinalPathByChr } from "./assembly/final-path-state.js";
import { previewProjectKey, previewSourceRange } from "./project-preview-state.js";

export const PREVIEW_MODEL_VERSION = 6;
const sessions = new WeakMap();
const domEntries = new Map();
const DOM = Symbol("previewDom");

export function previewSession(store) {
  if (!sessions.has(store)) sessions.set(store, { entries: new Map(), pending: new Map() });
  return sessions.get(store);
}

export function rememberPreviewEntry(store, key, entry) {
  const map = previewSession(store).entries;
  map.delete(key); map.set(key, entry);
  while (map.size > 3) map.delete(map.keys().next().value);
}

export function previewLocalSignatures(state) {
  return pathSignatures(normalizeFinalPathByChr(state.assembly?.finalPathByChr));
}

export function pathSignatures(paths) {
  return Object.fromEntries(Object.entries(paths || {}).map(([name, entry]) => [name, previewSemanticSignature(entry)]));
}

export function previewOverrideSignature(local, saved) {
  return previewSemanticSignature(Object.fromEntries(Object.entries(local || {})
    .filter(([name, value]) => value !== saved?.[name])));
}

export function previewStateIsApplicable(state) {
  const preview = state.projectPreview;
  return preview?.loaded && preview.modelVersion === PREVIEW_MODEL_VERSION && preview.key === previewProjectKey(state)
    && preview.localSignature === previewOverrideSignature(previewLocalSignatures(state), preview.savedPathSignatures)
    && preview.mutationStamp === previewMutationStamp({ workspaceRoot: state.session?.workspacePath, projectId: state.session?.projectId });
}

export function compactPreviewInputs({ chromosomes, ctgs, datasets, project, ...rest }) {
  const fields = ["assemblyCtgId", "name", "originId", "totalLength", "datasetId", "datasetName",
    "assignedChrName", "coAssignedChrNames", "anchorStart", "orient", "refOrient", "sourceFragment", "memberCount"];
  return { ...rest, chromosomes, project: { primaryDatasetId: project.primaryDatasetId,
    supportDatasetIds: project.supportDatasetIds, phasedAssemblyEnabled: project.phasedAssemblyEnabled },
    datasets: (datasets || []).map(ds => ({ datasetId: ds.datasetId, name: ds.name, label: ds.label })),
    ctgs: (ctgs || []).map(ctg => Object.fromEntries(fields.filter(key => ctg[key] !== undefined).map(key => [key, ctg[key]]))) };
}

export function previewPaletteKey(inputs, paths) {
  const projectIds = new Set([inputs.project?.primaryDatasetId, ...(inputs.project?.supportDatasetIds || [])].map(Number));
  const datasets = (inputs.datasets || []).filter(ds => projectIds.has(Number(ds.datasetId))).slice()
    .sort((a, b) => Number(b.datasetId === inputs.project?.primaryDatasetId) - Number(a.datasetId === inputs.project?.primaryDatasetId));
  const names = new Set();
  const add = (name, id = 0) => names.add(String(name || "").trim() || `ds:${Number(id) || "unknown"}`);
  datasets.forEach(ds => add(ds.name || ds.label, ds.datasetId));
  inputs.ctgs.forEach(ctg => add(ctg.datasetName, ctg.datasetId));
  Object.values(paths || {}).forEach(entry => (entry.segments || []).forEach(part => {
    if (part.type === "ctg") add(previewSourceRange(part).datasetName);
  }));
  return previewSemanticSignature([...names]);
}

export function previewPathParents(inputs) {
  const parents = Object.fromEntries(inputs.chromosomes.map(chr => [chr.chrName, chr.chrName]));
  for (const [chr, tracks] of Object.entries(inputs.phasedChrTracksByChr || {})) {
    tracks.forEach(track => { parents[track.label] = chr; });
  }
  return parents;
}

export function affectedPreviewChromosomes(names, cards, parents) {
  if (!Array.isArray(names) || names.includes("*")) return null;
  const known = new Set(cards.map(card => card.chrName)), affected = new Set();
  for (const name of names) {
    const parent = parents?.[name] || name;
    if (!known.has(parent)) return null;
    affected.add(parent);
  }
  return affected;
}

export function changedLocalNames(before, after) {
  return [...new Set([...Object.keys(before || {}), ...Object.keys(after || {})])]
    .filter(name => before?.[name] !== after?.[name]);
}

export function persistentPreviewPayload(inputs, savedPaths, cards, retainedDependencies = {}) {
  const dependencies = cards.map(card => ({ chrName: card.chrName,
    sourceNames: [...new Map(card.paths.flatMap(path => path.parts).filter(part => part.source?.original)
      .map(part => [JSON.stringify([part.source.datasetName, part.source.contigName]),
        { datasetName: part.source.datasetName, contigName: part.source.contigName }])).values()],
    ctgIds: [...new Set([...(retainedDependencies[card.chrName] || []), ...card.tracks.flatMap(track => [...track.positioned, ...(track.unpositioned || [])].map(item => Number(item.ctg?.assemblyCtgId || 0)))
      .concat(card.paths.flatMap(path => path.parts.map(part => Number(part.source?.assemblyCtgId || 0)))).filter(id => id > 0)])] }));
  // Remove raw ctg records and duplicate/unrendered item collections; retained
  // source/path descriptors are semantic material, never stored screen widths.
  const compact = JSON.parse(JSON.stringify(cards, (key, value) =>
    ["ctg", "items"].includes(key) ? undefined : value));
  return { modelVersion: PREVIEW_MODEL_VERSION, chromosomes: inputs.chromosomes,
    savedPathSignatures: pathSignatures(savedPaths), pathParents: previewPathParents(inputs),
    paletteKey: previewPaletteKey(inputs, savedPaths), cards: compact, dependencies };
}

export function isPreviewSnapshot(snapshot) {
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const color = value => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
  const part = value => object(value) && finite(value.start) && value.start >= 0
    && finite(value.length) && value.length > 0 && color(value.color)
    && ["primary", "companion", "ref"].includes(value.role)
    && typeof value.gap === "boolean" && typeof value.pathName === "string"
    && Number.isInteger(value.index) && value.index >= 0 && object(value.segment)
    && ["ctg", "gap"].includes(value.segment.type)
    && (!value.source || (object(value.source) && typeof value.source.datasetName === "string"
      && typeof value.source.contigName === "string" && finite(value.source.start) && finite(value.source.end)));
  const patch = value => object(value) && finite(value.start) && finite(value.end) && part(value.part);
  const sourceItem = (item, positioned) => object(item) && typeof item.name === "string"
    && (positioned ? finite(item.start) : item.start === null)
    && finite(item.length) && item.length > 0 && typeof item.reverse === "boolean"
    && (!item.alignment || (object(item.alignment) && typeof item.alignment.pathName === "string"
      && Number.isInteger(item.alignment.index) && finite(item.alignment.offset)
      && finite(item.alignment.usedStart) && finite(item.alignment.usedEnd)))
    && Array.isArray(item.highlights) && item.highlights.every(patch);
  return object(snapshot) && snapshot.modelVersion === PREVIEW_MODEL_VERSION
    && Array.isArray(snapshot.chromosomes) && snapshot.chromosomes.every(chr => object(chr) && typeof chr.chrName === "string")
    && object(snapshot.savedPathSignatures) && Object.values(snapshot.savedPathSignatures).every(value => typeof value === "string")
    && object(snapshot.pathParents) && Object.values(snapshot.pathParents).every(value => typeof value === "string")
    && Array.isArray(snapshot.dependencies) && snapshot.dependencies.every(dependency => object(dependency) && typeof dependency.chrName === "string"
      && Array.isArray(dependency.ctgIds) && Array.isArray(dependency.sourceNames)
      && dependency.sourceNames.every(source => object(source) && typeof source.datasetName === "string" && typeof source.contigName === "string"))
    && typeof snapshot.paletteKey === "string"
    && Array.isArray(snapshot.cards) && snapshot.cards.every(card => object(card) && typeof card.chrName === "string"
      && finite(card.domain?.start) && card.domain.start <= 0 && finite(card.domain.end) && card.domain.end > card.domain.start
      && finite(card.refLength) && typeof card.hasReference === "boolean"
      && object(card.reference) && finite(card.reference.start) && typeof card.reference.reverse === "boolean"
      && (card.reference.alignment === null || (object(card.reference.alignment)
        && typeof card.reference.alignment.pathName === "string" && Number.isInteger(card.reference.alignment.index)
        && finite(card.reference.alignment.offset)))
      && Array.isArray(card.refHighlights) && card.refHighlights.every(patch)
      && Array.isArray(card.paths) && card.paths.every(path => object(path) && typeof path.name === "string"
        && finite(path.length) && path.length >= 0 && Array.isArray(path.parts) && path.parts.every(part))
      && Array.isArray(card.tracks) && card.tracks.every(track => object(track) && typeof track.name === "string"
        && color(track.color) && ["primary", "companion"].includes(track.role) && Number.isInteger(track.laneCount) && track.laneCount >= 1
        && Array.isArray(track.unpositioned) && track.unpositioned.every(item => sourceItem(item, false))
        && Array.isArray(track.positioned) && track.positioned.every(item => sourceItem(item, true))))
    && new Set(snapshot.cards.map(card => card.chrName)).size === snapshot.cards.length
    && snapshot.cards.length === snapshot.chromosomes.length
    && snapshot.chromosomes.every(chr => snapshot.cards.some(card => card.chrName === chr.chrName));
}

export function markPreviewDom(host, state) {
  if (!state.projectPreview?.loaded || state.projectPreview.key !== previewProjectKey(state)) return;
  host[DOM] = { key: previewProjectKey(state), locale: state.locale,
    identity: state.projectPreview.identity, cards: state.projectPreview.cards, localSignature: state.projectPreview.localSignature,
    mutationStamp: state.projectPreview.mutationStamp };
}

export function rememberProjectPreviewDom(host) {
  const entry = host[DOM], nodes = [...(host?.childNodes || [])];
  if (!entry || !nodes.length || !host.querySelector?.(".project-preview-cards")) return;
  domEntries.delete(entry.key); domEntries.set(entry.key, { ...entry, nodes });
  while (domEntries.size > 3) domEntries.delete(domEntries.keys().next().value);
}

export function restoreProjectPreviewDom(host, state, options = {}) {
  const key = previewProjectKey(state), entry = domEntries.get(key);
  if (!entry || entry.locale !== state.locale || !previewStateIsApplicable(state)
    || entry.identity !== state.projectPreview.identity
    || (!options.allowModelMismatch && entry.cards !== state.projectPreview.cards) || !host?.replaceChildren) return false;
  host.replaceChildren(...entry.nodes); host[DOM] = entry;
  return true;
}
