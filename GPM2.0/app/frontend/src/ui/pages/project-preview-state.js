import {
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  resolveFinalPathRefSegmentAbsoluteRange,
  resolveFinalPathSegmentLengthBp,
} from "./assembly/final-path-state.js";

import { DEFAULT_CONTIG_PALETTE, createContigColorResolver } from "./assembly/contig-colors.js";
const text = value => String(value ?? "").trim();
const positive = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : 0;

export function previewProjectKey(state) {
  const path = text(state?.session?.workspacePath), id = positive(state?.session?.projectId);
  return path && id ? JSON.stringify([path, id]) : "";
}

export function previewSourceRange(segment) {
  const source = segment?.source || {};
  const sourceLocated = Boolean(text(source.dataset) && text(source.contig));
  const original = sourceLocated || !positive(segment?.assemblyCtgId);
  const start = positive(sourceLocated ? source.start ?? segment.start : segment?.start);
  const end = positive(sourceLocated ? source.end ?? segment.end : segment?.end);
  return {
    datasetName: text(sourceLocated ? source.dataset : segment?.datasetName),
    contigName: text(sourceLocated ? source.contig : segment?.originId || segment?.ctgName),
    assemblyCtgId: positive(segment?.assemblyCtgId),
    original,
    start: Math.min(start, end), end: Math.max(start, end),
    valid: start > 0 && end > 0,
    orient: source.orientation || segment?.orient || (start > end ? "-" : "+"),
  };
}

function sourceItem(ctg, chrName) {
  const length = positive(ctg.totalLength);
  if (!length) return null;
  const anchor = ctg.anchorStart;
  const positioned = text(ctg.assignedChrName) === chrName
    && anchor !== null && anchor !== undefined && Number.isFinite(Number(anchor));
  return {
    ctg, name: text(ctg.name || ctg.originId), length,
    datasetName: text(ctg.datasetName),
    start: positioned ? Number(anchor) : null,
    reverse: ctg.refOrient === "-", highlights: [],
  };
}

// Original-source coordinates and contig-local coordinates are different.
// Convert through the fragment and its orientation before painting the used area.
function localInterval(item, source) {
  if (!source.valid) return null;
  let low = source.start, high = source.end;
  let coveredStart = low, coveredEnd = high;
  if (source.original) {
    const fragment = item.ctg.sourceFragment;
    // A composite contig cannot be projected from an original source using
    // a length alone. Leave that provenance explicitly unpositioned instead.
    if (!fragment && positive(item.ctg.memberCount) > 1) return null;
    const sourceStart = positive(fragment?.sourceStart) || 1;
    const sourceEnd = positive(fragment?.sourceEnd) || item.length;
    low = Math.max(low, sourceStart); high = Math.min(high, sourceEnd);
    if (high < low) return null;
    coveredStart = low; coveredEnd = high;
    if (item.ctg.orient === "-") {
      [low, high] = [sourceEnd - high + 1, sourceEnd - low + 1];
    } else {
      [low, high] = [low - sourceStart + 1, high - sourceStart + 1];
    }
  }
  low = Math.max(1, low); high = Math.min(item.length, high);
  if (high < low) return null;
  const interval = item.reverse
    ? { start: item.length - high, end: item.length - low + 1 }
    : { start: low - 1, end: high };
  return { ...interval, coveredStart: source.original ? coveredStart : low,
    coveredEnd: source.original ? coveredEnd : high };
}

function assignLanes(items) {
  const ends = [];
  for (const item of items.sort((a, b) => a.start - b.start || a.length - b.length)) {
    let lane = ends.findIndex(end => end <= item.start);
    if (lane < 0) lane = ends.length;
    ends[lane] = item.start + item.length;
    item.lane = lane;
  }
  return Math.max(1, ends.length);
}

// Final Path has its own origin. Anchor the reference to the longest adopted
// interval with known reference placement, not to Final Path coordinate zero.
// One intact reference cannot follow every rearrangement/reuse independently.
function referencePlacement(rows, highlights, chrName, refLength, primaryDatasetId) {
  const candidates = highlights.map(patch => {
    const reverse = patch.part.segment.orient === "-";
    const start = reverse ? patch.part.start + patch.end - refLength : patch.part.start - patch.start;
    return { start, reverse, length: patch.end - patch.start, primary: true, part: patch.part };
  });
  for (const row of rows) {
    for (const item of row.positioned) {
      const anchor = item.ctg.anchorStart;
      if (!item.alignment || text(item.ctg.assignedChrName) !== chrName
        || anchor === null || anchor === undefined || !Number.isFinite(Number(anchor))) continue;
      const start = item.reverse
        ? item.start + item.length + Number(anchor) - refLength
        : item.start - Number(anchor);
      candidates.push({ start, reverse: item.reverse,
        length: item.alignment.usedEnd - item.alignment.usedStart,
        primary: positive(item.ctg.datasetId) === positive(primaryDatasetId),
        part: item.highlights[0].part });
    }
  }
  const best = candidates.sort((a, b) => b.length - a.length || Number(b.primary) - Number(a.primary))[0];
  return best ? { start: best.start, reverse: best.reverse,
    alignment: { pathName: best.part.pathName, index: best.part.index, offset: best.start - best.part.start } }
    : { start: 0, reverse: false, alignment: null };
}

export function buildProjectPreviewModel({ chromosomes = [], referenceGenomeId = 0, ctgs = [],
  datasets = [], project = {}, finalPathByChr = {}, phasedChrTracksByChr = {} } = {}) {
  const byId = new Map(), bySource = new Map(), byChr = new Map();
  const sourceKey = (dataset, contig) => JSON.stringify([text(dataset), text(contig)]);
  ctgs.forEach(ctg => {
    for (const name of new Set([text(ctg.assignedChrName), ...(ctg.coAssignedChrNames || []).map(text)].filter(Boolean))) {
      if (!byChr.has(name)) byChr.set(name, []);
      byChr.get(name).push(ctg);
    }
    if (positive(ctg.assemblyCtgId)) byId.set(positive(ctg.assemblyCtgId), ctg);
    for (const name of new Set([text(ctg.originId), text(ctg.name)].filter(Boolean))) {
      const key = sourceKey(ctg.datasetName, name), items = bySource.get(key) || [];
      items.push(ctg); bySource.set(key, items);
    }
  });
  const findSource = source => source.original
    ? bySource.get(sourceKey(source.datasetName, source.contigName)) || []
    : [byId.get(source.assemblyCtgId)].filter(Boolean);
  const primaryDataset = datasets.find(ds => positive(ds.datasetId) === positive(project.primaryDatasetId));
  const primaryName = text(primaryDataset?.name || primaryDataset?.label
    || ctgs.find(ctg => positive(ctg.datasetId) === positive(project.primaryDatasetId))?.datasetName);
  const resolveRole = createContigColorResolver({ primaryDatasetName: primaryName,
    primaryCtgs: ctgs.filter(ctg => positive(ctg.datasetId) === positive(project.primaryDatasetId)),
    supportCtgs: ctgs.filter(ctg => positive(ctg.datasetId) !== positive(project.primaryDatasetId)) });
  const catalog = new Map();
  const registerDataset = (name, id = 0) => {
    const key = text(name) || `ds:${positive(id) || "unknown"}`;
    const role = positive(id) && positive(id) === positive(project.primaryDatasetId)
      || primaryName && text(name).toLowerCase() === primaryName.toLowerCase() ? "primary" : "companion";
    if (!catalog.has(key)) catalog.set(key, { key, name: text(name) || (id ? `ds ${id}` : ""),
      role, color: DEFAULT_CONTIG_PALETTE[role].fill });
    return catalog.get(key);
  };
  const projectIds = new Set([project.primaryDatasetId, ...(project.supportDatasetIds || [])].map(positive).filter(Boolean));
  const projectDatasets = datasets.filter(ds => projectIds.has(positive(ds.datasetId)));
  projectDatasets.sort((a, b) => Number(b.datasetId === project.primaryDatasetId) - Number(a.datasetId === project.primaryDatasetId));
  projectDatasets.forEach(ds => registerDataset(ds.name || ds.label, ds.datasetId));
  ctgs.forEach(ctg => registerDataset(ctg.datasetName, ctg.datasetId));
  Object.values(finalPathByChr).forEach(entry => (entry?.segments || []).forEach(segment => {
    if (!isFinalPathGapSegment(segment) && !isFinalPathRefSegment(segment)) registerDataset(previewSourceRange(segment).datasetName);
  }));
  const ordered = chromosomes.slice().sort((a, b) => Number(a.chrOrder || 0) - Number(b.chrOrder || 0)
    || text(a.chrName).localeCompare(text(b.chrName), undefined, { numeric: true }));
  return ordered.map(chr => {
    const chrName = text(chr.chrName), refLength = positive(chr.chrLength);
    const hasReference = positive(referenceGenomeId) > 0 && refLength > 0;
    const tracks = new Map();
    const trackFor = ds => {
      if (!tracks.has(ds.key)) tracks.set(ds.key, { ...ds, items: [] });
      return tracks.get(ds.key);
    };
    projectDatasets.forEach(ds => trackFor(registerDataset(ds.name || ds.label, ds.datasetId)));
    const included = new Map();
    const includeCtg = ctg => {
      if (included.has(ctg)) return included.get(ctg);
      const item = sourceItem(ctg, chrName);
      if (item) {
        trackFor(registerDataset(item.datasetName, ctg.datasetId)).items.push(item);
        included.set(ctg, item);
      }
      return item;
    };
    (byChr.get(chrName) || []).forEach(includeCtg);
    const phasedNames = (phasedChrTracksByChr[chrName] || []).map(track => text(track.label));
    const pathNames = phasedNames.some(name => finalPathByChr[name]) ? phasedNames : [chrName];
    const refHighlights = [], paths = [];
    let unresolvedCount = 0;
    for (const name of pathNames) {
      const entry = finalPathByChr[name];
      if (!entry) continue;
      let cursor = 0;
      const parts = [];
      for (const segment of entry.segments || []) {
        const length = resolveFinalPathSegmentLengthBp(segment);
        if (!(length > 0)) { unresolvedCount++; continue; }
        const part = { segment, pathName: name, index: parts.length, start: cursor, length, gap: isFinalPathGapSegment(segment), role: "ref", color: DEFAULT_CONTIG_PALETTE.ref.fill };
        cursor += length;
        if (!part.gap && isFinalPathRefSegment(segment)) {
          const range = resolveFinalPathRefSegmentAbsoluteRange(segment);
          if (hasReference && text(segment.referenceChrName) === chrName && range) {
            refHighlights.push({ start: range.startBp - 1, end: range.endBp, part });
          } else {
            unresolvedCount++;
          }
        } else if (!part.gap) {
          const source = previewSourceRange(segment);
          const ds = registerDataset(source.datasetName);
          part.role = resolveRole(segment);
          // Unknown dataset names are support, not an accidental extra primary track.
          if (!primaryName && !positive(segment.assemblyCtgId)) part.role = ds.role;
          part.color = DEFAULT_CONTIG_PALETTE[part.role].fill; part.source = source;
          const covered = [];
          if (source.valid) {
            for (const ctg of findSource(source)) {
              const item = includeCtg(ctg);
              if (!item) continue;
              const interval = localInterval(item, source);
              if (interval) {
                item.highlights.push({ ...interval, part });
                covered.push([interval.coveredStart, interval.coveredEnd]);
                part.color = trackFor(registerDataset(item.datasetName, ctg.datasetId)).color;
              }
            }
          }
          let coveredLength = 0, coveredEnd = 0;
          for (const [start, end] of covered.sort((a, b) => a[0] - b[0])) {
            coveredLength += Math.max(0, end - Math.max(start, coveredEnd + 1) + 1);
            coveredEnd = Math.max(coveredEnd, end);
          }
          if (coveredLength < source.end - source.start + 1 && source.valid) {
            // The source may be hidden/cut out of the editable main view. Keep
            // it visible in a clearly unpositioned original-source strip.
            const ghostKey = JSON.stringify([source.datasetName, source.contigName, source.original ? 0 : source.assemblyCtgId]);
            const track = trackFor(ds);
            let ghost = track.items.find(item => item.ghostKey === ghostKey);
            if (!ghost) {
              ghost = { ghostKey, name: source.contigName, datasetName: source.datasetName,
                length: Math.max(positive(segment.overallLen), source.end), start: null, reverse: false,
                highlights: [], ctg: {} };
              track.items.push(ghost);
            }
            ghost.length = Math.max(ghost.length, source.end);
            ghost.highlights.push({ start: source.start - 1, end: source.end, part });
          } else if (!source.valid) {
            unresolvedCount++;
          }
        }
        parts.push(part);
      }
      paths.push({ name, length: cursor, parts });
    }
    const rows = [...tracks.values()].map(track => {
      const items = track.items.flatMap(item => {
        if (!item.highlights.length) return [item];
        // Split reused/reordered sources by the actual adopted fragment. A
        // single whole-contig translation cannot align all of its uses.
        return item.highlights.map(patch => {
          const source = patch.part.source;
          const localStart = item.reverse ? item.length - patch.end : patch.start;
          const localEnd = item.reverse ? item.length - patch.start : patch.end;
          const reverse = source.original ? (source.orient === "-") !== (item.ctg.orient === "-") : source.orient === "-";
          const usedStart = reverse ? item.length - localEnd : localStart;
          const usedEnd = reverse ? item.length - localStart : localEnd;
          const offset = source.orient === "-"
            ? source.end - (patch.coveredEnd ?? source.end)
            : (patch.coveredStart ?? source.start) - source.start;
          return { ...item, reverse, displayOrient: source.orient, start: patch.part.start + offset - usedStart,
            alignment: { pathName: patch.part.pathName, index: patch.part.index, offset, usedStart, usedEnd },
            highlights: [{ ...patch, start: usedStart, end: usedEnd }] };
        });
      });
      const positioned = items.filter(item => item.start !== null);
      const adopted = positioned.filter(item => item.alignment).map(item => ({
        item, start: item.start + item.alignment.usedStart,
        length: item.alignment.usedEnd - item.alignment.usedStart,
      }));
      const laneCount = assignLanes(adopted);
      adopted.forEach(({ item, lane }) => { item.lane = lane; });
      // Unused context is subdued on the same lane; only overlapping adopted
      // fragments (e.g. alternative haplotypes) need additional rows.
      positioned.filter(item => !item.alignment).forEach(item => { item.lane = 0; });
      return { ...track, items, positioned, unpositioned: items.filter(item => item.start === null), laneCount };
    });
    const reference = referencePlacement(rows, refHighlights, chrName, refLength, project.primaryDatasetId);
    // Context-only contigs still use reference coordinates; translate them too.
    if (hasReference) rows.forEach(row => row.positioned.filter(item => !item.alignment).forEach(item => {
      item.start = reference.start + (reference.reverse ? refLength - item.start - item.length : item.start);
    }));
    const start = 0;
    const end = paths.reduce((max, path) => Math.max(max, path.length), Math.max(1, hasReference ? reference.start + refLength : 0));
    return { chrName, refLength, hasReference, reference, refHighlights, tracks: rows, paths,
      domain: { start, end }, unresolvedCount,
      unpositionedCount: rows.reduce((sum, row) => sum + row.unpositioned.length, 0) };
  });
}

export function requestPreviewChromosome(store, chrName) {
  const state = store.getState(), name = text(chrName);
  const key = previewProjectKey(state);
  if (!key || state.projectPreview?.key !== key || !name
    || !state.projectPreview?.chromosomes?.some(chr => text(chr.chrName) === name)) return false;
  store.setState({ activeRoute: "assembly", assembly: { ...state.assembly,
    activeTab: "assembly", previewRequestedChrName: name, projectExportScrollToBottom: false } });
  return true;
}
