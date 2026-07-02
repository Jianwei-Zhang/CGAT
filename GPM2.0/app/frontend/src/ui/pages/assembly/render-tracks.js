import { buildDualTrackModel } from "./track-layout.js";
import {
  ALIGNMENT_LENGTH_OPTIONS,
  MAPQ_OPTIONS,
  MAX_TICK_COUNT_OPTIONS,
  MIN_TICK_UNIT_KB_OPTIONS,
  SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackInnerWidthFromScale,
  resolveTickBpFromScale,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackDragOffsets,
  normalizeTrackRole,
  normalizeTrackSelectionCtgIds,
  normalizeSubviewTrackDragOffsets,
} from "./selection-state.js";
import {
  buildRefSubviewCtgPool,
  buildSubviewFlippedCtgKey,
  buildSubviewTrackSelectionKey,
  buildSupportSubviewCtgPool,
  buildPhasedSubviewCtgPool,
  buildSubviewTrackPairHiddenCtgKey,
  buildSubviewCandidateSelectionKey,
  buildPhasedSubviewCtgHits,
  flipSubviewHitRange,
  getSubviewSelections,
  getSubviewState as getSubviewStateImpl,
  getSubviewTrackSelections,
  resolveSubviewCtgOrientValue,
  normalizeSubviewRole,
  normalizeSubviewSummarySelection,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackPairSelectionCtgs,
  normalizeSubviewTrackSelectionItem,
  normalizeSubviewTrackSource,
  normalizeSubviewTrackSummary,
  resolveSubviewSelectionCtg,
  resolveSubviewTrackSummaryCtgs,
} from "./subview-state.js";
import {
  buildSubviewAnchorEndpointKey,
  deriveSubviewContigFragments,
} from "./subview-anchor-state.js";
import {
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
  hasAdvancedSupportDsCtgLenRules,
} from "./support-ds-ctg-len-rules.js";
import { renderFinalPathCard } from "./final-path-card.js";
import { renderDegapPanel } from "./degap-card.js";
import {
  FINAL_PATH_ALL_KEY,
  buildFinalPathEntry,
  getCurrentChrFinalPath,
  resolveCurrentFinalPathChrName,
  resolveFinalPathSelectionKey,
} from "./final-path-state.js";
import { buildFinalPathLogModel } from "./final-path-log-state.js";
import { getFinalPathGraphPreviewState } from "./final-path-graph-drag-runtime.js";

function escapeSourceTagHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export const SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS = 500;
const DEFAULT_TRACK_VIEWPORT_PX = 1200;
const filteredRefSubviewCtgCache = new WeakMap();
const refSubviewSegmentPairCache = new Map();

function resolveTrackCtgOrientValue(ctg) {
  return resolveSubviewCtgOrientValue(ctg);
}

function resolveDerivedSourceLabel(ctg) {
  const source = String(ctg?.derivedSource || "").trim();
  return source || (ctg?.derivedTargetDatasetId ? "derived" : "");
}

function resolveDerivedSourceClass(sourceLabel) {
  const normalized = String(sourceLabel || "").trim().toLowerCase();
  if (normalized === "gapfiller") return " is-source-gapfiller";
  if (normalized === "telseeker") return " is-source-telseeker";
  return " is-source-derived";
}

function resolveDerivedSourceColor(sourceLabel) {
  const normalized = String(sourceLabel || "").trim().toLowerCase();
  if (normalized === "gapfiller" || normalized === "telseeker" || normalized === "derived") {
    return "";
  }
  if (!normalized) {
    return "";
  }
  let hash = 0;
  for (let index = 0; index < normalized.length; index += 1) {
    hash = (hash * 31 + normalized.charCodeAt(index)) >>> 0;
  }
  const hue = hash % 360;
  return `hsl(${hue}, 72%, 32%)`;
}

function renderDerivedSourceSvgTag(ctg) {
  const sourceLabel = resolveDerivedSourceLabel(ctg);
  if (!sourceLabel) {
    return "";
  }
  const color = resolveDerivedSourceColor(sourceLabel);
  const styleAttr = color ? ` style="fill:${escapeSourceTagHtml(color)}"` : "";
  return `<tspan class="track-ctg-source-tag${resolveDerivedSourceClass(sourceLabel)}"${styleAttr}> [${escapeSourceTagHtml(sourceLabel)}]</tspan>`;
}

function renderDerivedSourceHtmlTag(ctg) {
  const sourceLabel = resolveDerivedSourceLabel(ctg);
  if (!sourceLabel) {
    return "";
  }
  const color = resolveDerivedSourceColor(sourceLabel);
  const styleAttr = color ? ` style="color:${escapeSourceTagHtml(color)}"` : "";
  return `<span class="ctg-chip-source-tag${resolveDerivedSourceClass(sourceLabel)}"${styleAttr}>[${escapeSourceTagHtml(sourceLabel)}]</span>`;
}

function buildPhasedFinalPathOptions(assembly) {
  if (!assembly?.isChrPhased) {
    return [];
  }
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!tracks.length) {
    return [];
  }
  const activeKey = resolveFinalPathSelectionKey(assembly) || FINAL_PATH_ALL_KEY;
  const allOption = {
    key: FINAL_PATH_ALL_KEY,
    label: "All",
    chrName: String(assembly?.selectedChrName || "").trim(),
    active: activeKey === FINAL_PATH_ALL_KEY,
  };
  return [allOption, ...tracks
    .map((track) => {
      const key = String(track?.haplotypeKey || "").trim();
      const chrName = String(track?.label || "").trim();
      if (!key || !chrName) {
        return null;
      }
      return {
        key,
        chrName,
        active: key === activeKey,
      };
    })
    .filter(Boolean)];
}

function buildFinalPathDisplayEntries(assembly) {
  const selectedChrName = String(assembly?.selectedChrName || "").trim();
  const finalPathByChr = assembly?.finalPathByChr || {};
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!assembly?.isChrPhased || !tracks.length) {
    const chrName = resolveCurrentFinalPathChrName(assembly) || selectedChrName;
    const entry = getCurrentChrFinalPath(assembly)
      || (chrName ? buildFinalPathEntry({ chrName, segments: [], updatedAt: "" }) : null);
    return entry ? [{ key: "", label: chrName, chrName, finalPathEntry: entry }] : [];
  }
  const selectedKey = resolveFinalPathSelectionKey(assembly);
  const selectedTracks = selectedKey === FINAL_PATH_ALL_KEY
    ? tracks
    : tracks.filter((track) => String(track?.haplotypeKey || "").trim() === selectedKey);
  return selectedTracks
    .map((track) => {
      const key = String(track?.haplotypeKey || "").trim();
      const chrName = String(track?.label || "").trim();
      if (!key || !chrName) {
        return null;
      }
      return {
        key,
        label: chrName,
        chrName,
        finalPathEntry: finalPathByChr[chrName]
          || buildFinalPathEntry({ chrName, segments: [], updatedAt: "" }),
      };
    })
    .filter(Boolean);
}

function resolveRefOverlapBpCached(leftSegment, rightSegment) {
  const leftStart = Math.min(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const leftEnd = Math.max(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const rightStart = Math.min(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const rightEnd = Math.max(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const start = Math.max(leftStart, rightStart);
  const end = Math.min(leftEnd, rightEnd);
  return Math.max(0, end - start);
}

function pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? [...topSegments] : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? [...bottomSegments] : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  safeTopSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });
  safeBottomSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });

  const pairs = [];
  let bottomWindowStart = 0;
  for (const topSegment of safeTopSegments) {
    while (
      bottomWindowStart < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomWindowStart]?.refEnd || 0) <= Number(topSegment.refStart || 0)
    ) {
      bottomWindowStart += 1;
    }
    for (
      let bottomIndex = bottomWindowStart;
      bottomIndex < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomIndex]?.refStart || 0) < Number(topSegment.refEnd || 0);
      bottomIndex += 1
    ) {
      const bottomSegment = safeBottomSegments[bottomIndex];
      if (resolveRefOverlapBpCached(topSegment, bottomSegment) <= 0) {
        continue;
      }
      pairs.push({ topSegment, bottomSegment });
    }
  }
  return pairs;
}

function pairSubviewTrackSegmentsByReferenceCached(topSegments, bottomSegments) {
  return pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments).filter(
    ({ topSegment, bottomSegment }) => {
      const overlapBp = resolveRefOverlapBpCached(topSegment, bottomSegment);
      const topSpanBp = Math.max(
        1,
        Math.abs((Number(topSegment?.refEnd) || 0) - (Number(topSegment?.refStart) || 0)),
      );
      const bottomSpanBp = Math.max(
        1,
        Math.abs((Number(bottomSegment?.refEnd) || 0) - (Number(bottomSegment?.refStart) || 0)),
      );
      const minSpanBp = Math.min(topSpanBp, bottomSpanBp);
      return overlapBp / minSpanBp >= 0.5;
    },
  );
}

function pairSubviewSegmentsByProjectionKey(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? topSegments : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? bottomSegments : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  const bottomByKey = new Map();
  safeBottomSegments.forEach((segment) => {
    const pairKey = String(segment?.pairKey || segment?.hitKey || "").trim();
    if (!pairKey) {
      return;
    }
    const current = bottomByKey.get(pairKey) || [];
    current.push(segment);
    bottomByKey.set(pairKey, current);
  });
  return safeTopSegments.flatMap((topSegment) => {
    const pairKey = String(topSegment?.pairKey || topSegment?.hitKey || "").trim();
    if (!pairKey) {
      return [];
    }
    const matches = bottomByKey.get(pairKey) || [];
    const bottomSegment = matches.shift();
    if (!bottomSegment) {
      return [];
    }
    return [{ topSegment, bottomSegment }];
  });
}

function resolveRefTrackSegmentBounds(ctg) {
  const segmentStartBp = Math.max(
    1,
    normalizePositiveInt(ctg?.segmentStartBp ?? ctg?.startBp ?? ctg?.anchorStart ?? 1) ?? 1,
  );
  const totalLength = Math.max(
    1,
    normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
  );
  const segmentEndBp = Math.max(
    segmentStartBp,
    normalizePositiveInt(ctg?.segmentEndBp ?? ctg?.endBp ?? (segmentStartBp + totalLength - 1)) ?? (segmentStartBp + totalLength - 1),
  );
  return {
    segmentStartBp,
    segmentEndBp,
    totalLength,
  };
}

function projectRefIntervalToLocalRange(ctg, refStart, refEnd) {
  const { segmentStartBp, segmentEndBp, totalLength } = resolveRefTrackSegmentBounds(ctg);
  const normalizedRefStart = Math.min(Number(refStart) || 0, Number(refEnd) || 0);
  const normalizedRefEnd = Math.max(Number(refStart) || 0, Number(refEnd) || 0);
  if (
    !Number.isFinite(normalizedRefStart)
    || !Number.isFinite(normalizedRefEnd)
    || normalizedRefEnd < segmentStartBp
    || normalizedRefStart > segmentEndBp
  ) {
    return null;
  }
  const clampedStart = Math.max(segmentStartBp, normalizedRefStart);
  const clampedEnd = Math.min(segmentEndBp, normalizedRefEnd);
  const localStart = Math.max(1, Math.min(totalLength, clampedStart - segmentStartBp + 1));
  const localEnd = Math.max(localStart, Math.min(totalLength, clampedEnd - segmentStartBp + 1));
  return {
    ctgStart: localStart,
    ctgEnd: localEnd,
  };
}

function buildProjectedRefSubviewHits(refCtg, sourceHits) {
  return (Array.isArray(sourceHits) ? sourceHits : [])
    .map((hit, index) => {
      const projectedRange = projectRefIntervalToLocalRange(
        refCtg,
        hit?.refStart,
        hit?.refEnd,
      );
      if (!projectedRange) {
        return null;
      }
      const hitKey = String(hit?.hitKey || `hit-${index + 1}`);
      const pairKey = String(hit?.pairKey || hitKey);
      return {
        ...hit,
        hitKey,
        pairKey,
        ctgStart: projectedRange.ctgStart,
        ctgEnd: projectedRange.ctgEnd,
      };
    })
    .filter(Boolean);
}

function buildSubviewPairwiseEvidenceKey(summary, scope = {}) {
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    const topIds = (Array.isArray(scope?.topAssemblyCtgIds) ? scope.topAssemblyCtgIds : [])
      .map((value) => normalizeSupportDatasetId(value))
      .filter((value) => value)
      .sort((left, right) => left - right);
    const bottomIds = (Array.isArray(scope?.bottomAssemblyCtgIds) ? scope.bottomAssemblyCtgIds : [])
      .map((value) => normalizeSupportDatasetId(value))
      .filter((value) => value)
      .sort((left, right) => left - right);
    if (!topTrack || !bottomTrack || topTrack.role === "ref" || bottomTrack.role === "ref" || !topIds.length || !bottomIds.length) {
      return "";
    }
    const topTrackKey = `${buildSubviewTrackSelectionKey(topTrack)}:${topIds.join(",")}`;
    const bottomTrackKey = `${buildSubviewTrackSelectionKey(bottomTrack)}:${bottomIds.join(",")}`;
    return `track-pair:${topTrackKey}|${bottomTrackKey}`;
  }
  if (mode !== "2-contig") {
    return "";
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  if (!top || !bottom) {
    return "";
  }
  return `2-contig:${buildSubviewCandidateSelectionKey(top)}:${buildSubviewCandidateSelectionKey(bottom)}`;
}

function isDsDsSubviewSummary(summary) {
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    return Boolean(topTrack && bottomTrack && topTrack.role !== "ref" && bottomTrack.role !== "ref");
  }
  if (mode !== "2-contig") {
    return false;
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  return Boolean(top && bottom && top.role !== "ref" && bottom.role !== "ref");
}

function resolveSubviewPairwiseEvidence(subview, summary, scope = {}) {
  if (!isDsDsSubviewSummary(summary)) {
    return {
      enabled: false,
      key: "",
      evidence: null,
    };
  }
  const key = buildSubviewPairwiseEvidenceKey(summary, scope);
  const evidence = subview?.pairwiseEvidence || null;
  if (!evidence || String(evidence.key || "") !== key) {
    return {
      enabled: false,
      key,
      evidence: null,
    };
  }
  return {
    enabled: true,
    key,
    evidence,
  };
}

function resolvePairwiseHitTrackRanges(hit, topSelection, bottomSelection) {
  const topContigId = normalizeSupportDatasetId(topSelection?.contigId);
  const bottomContigId = normalizeSupportDatasetId(bottomSelection?.contigId);
  const queryAssemblyCtgId = normalizeSupportDatasetId(
    hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id,
  );
  const subjectAssemblyCtgId = normalizeSupportDatasetId(
    hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id,
  );
  const queryStart = Number(hit?.queryStart ?? hit?.query_start);
  const queryEnd = Number(hit?.queryEnd ?? hit?.query_end);
  const subjectStart = Number(hit?.subjectStart ?? hit?.subject_start);
  const subjectEnd = Number(hit?.subjectEnd ?? hit?.subject_end);
  if (
    !topContigId
    || !bottomContigId
    || !queryAssemblyCtgId
    || !subjectAssemblyCtgId
    || !Number.isFinite(queryStart)
    || !Number.isFinite(queryEnd)
    || !Number.isFinite(subjectStart)
    || !Number.isFinite(subjectEnd)
  ) {
    return null;
  }
  if (queryAssemblyCtgId === topContigId && subjectAssemblyCtgId === bottomContigId) {
    return {
      topStart: queryStart,
      topEnd: queryEnd,
      bottomStart: subjectStart,
      bottomEnd: subjectEnd,
    };
  }
  if (queryAssemblyCtgId === bottomContigId && subjectAssemblyCtgId === topContigId) {
    return {
      topStart: subjectStart,
      topEnd: subjectEnd,
      bottomStart: queryStart,
      bottomEnd: queryEnd,
    };
  }
  return null;
}

function resolvePairwiseHitDisplayReversed(hit) {
  const strand = String(hit?.strand || "").trim();
  return strand === "-";
}

function resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topFlipped, bottomFlipped) {
  let reversed = resolvePairwiseHitDisplayReversed(hit);
  if (topFlipped === true) {
    reversed = !reversed;
  }
  if (bottomFlipped === true) {
    reversed = !reversed;
  }
  return reversed;
}

function isSubviewRenderableContigLocallyFlipped(ctg) {
  return ctg?.subviewLocallyFlipped === true;
}

function isSubviewPairwiseRangeMirrored(ctg) {
  return Boolean(ctg?.subviewPhasedOrientFlipped) !== isSubviewRenderableContigLocallyFlipped(ctg);
}

function resolveSubviewPairwiseCtgLengthBp(ctg) {
  const candidates = [
    ctg?.lengthBp,
    ctg?.totalLength,
    ctg?.length,
  ];
  for (const candidate of candidates) {
    const parsed = normalizePositiveInt(candidate);
    if (parsed && parsed > 0) {
      return parsed;
    }
  }
  return 1;
}

function resolveSubviewPairwiseDisplayRange(start, end, ctg, flipped) {
  const numericStart = Number(start);
  const numericEnd = Number(end);
  if (!Number.isFinite(numericStart) || !Number.isFinite(numericEnd)) {
    return null;
  }
  if (flipped !== true) {
    return { start: numericStart, end: numericEnd };
  }
  const totalLength = Math.max(1, resolveSubviewPairwiseCtgLengthBp(ctg));
  return {
    start: totalLength - numericEnd + 1,
    end: totalLength - numericStart + 1,
  };
}

function buildSubviewPairwiseRenderableHits({
  evidence,
  topSelection,
  bottomSelection,
  topCtg,
  bottomCtg,
  blockLength,
  minMapq,
}) {
  if (normalizeSupportDatasetId(topSelection?.contigId) === normalizeSupportDatasetId(bottomSelection?.contigId)) {
    return { topHits: [], bottomHits: [] };
  }
  const topHits = [];
  const bottomHits = [];
  const topMirrored = isSubviewPairwiseRangeMirrored(topCtg);
  const bottomMirrored = isSubviewPairwiseRangeMirrored(bottomCtg);
  const hits = Array.isArray(evidence?.hits) ? evidence.hits : [];
  hits.forEach((hit, index) => {
    const alignLength = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
    const mapq = Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
    if (alignLength < blockLength || mapq < minMapq) {
      return;
    }
    const ranges = resolvePairwiseHitTrackRanges(hit, topSelection, bottomSelection);
    if (!ranges) {
      return;
    }
    const topRange = resolveSubviewPairwiseDisplayRange(
      ranges.topStart,
      ranges.topEnd,
      topCtg,
      topMirrored,
    );
    const bottomRange = resolveSubviewPairwiseDisplayRange(
      ranges.bottomStart,
      ranges.bottomEnd,
      bottomCtg,
      bottomMirrored,
    );
    if (!topRange || !bottomRange) {
      return;
    }
    const pairOrdinal = index + 1;
    const pairKey = `pairwise-${pairOrdinal}`;
    const hitKey = String(hit?.hitKey || pairKey);
    const reversed = resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topMirrored, bottomMirrored);
    const refStart = pairOrdinal;
    const refEnd = pairOrdinal + 1;
    topHits.push({
      hitKey,
      pairKey,
      reversed,
      ctgStart: Math.min(topRange.start, topRange.end),
      ctgEnd: Math.max(topRange.start, topRange.end),
      refStart,
      refEnd,
      refMid: (refStart + refEnd) / 2,
    });
    bottomHits.push({
      hitKey,
      pairKey,
      reversed,
      ctgStart: Math.min(bottomRange.start, bottomRange.end),
      ctgEnd: Math.max(bottomRange.start, bottomRange.end),
      refStart,
      refEnd,
      refMid: (refStart + refEnd) / 2,
    });
  });
  return { topHits, bottomHits };
}

function resolveSubviewRefDatasetId(subview, supportContext = {}) {
  const summary = subview?.summary || null;
  if (!summary) {
    return null;
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const tracks = [summary?.topTrack, summary?.bottomTrack]
      .map((track) => normalizeSubviewTrackSummary(track))
      .filter(Boolean);
    const nonRefTrack = tracks.find((track) => track.role !== "ref");
    if (!nonRefTrack) {
      return null;
    }
    if (nonRefTrack.role === "primary") {
      return normalizeSupportDatasetId(supportContext?.primaryDatasetId);
    }
    return normalizeSupportDatasetId(nonRefTrack.datasetId);
  }
  const selections = [summary?.top, summary?.bottom]
    .map((selection) => normalizeSubviewSummarySelection(selection))
    .filter(Boolean);
  const nonRefSelection = selections.find((selection) => selection.role !== "ref");
  if (!nonRefSelection) {
    return null;
  }
  if (nonRefSelection.role === "primary") {
    return normalizeSupportDatasetId(supportContext?.primaryDatasetId);
  }
  const matchedSupportCtg = resolveSubviewSelectionCtg(nonRefSelection, supportContext);
  return normalizeSupportDatasetId(
    matchedSupportCtg?.datasetId ?? supportContext?.supportDatasetId ?? null,
  );
}

function buildSubviewRefCacheSelectionKey(summary) {
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    return [
      "track-pair",
      topTrack
        ? [topTrack.role, topTrack.source, normalizeSupportDatasetId(topTrack.datasetId) || 0, topTrack.isMirror ? 1 : 0].join(":")
        : "",
      bottomTrack
        ? [bottomTrack.role, bottomTrack.source, normalizeSupportDatasetId(bottomTrack.datasetId) || 0, bottomTrack.isMirror ? 1 : 0].join(":")
        : "",
    ].join("|");
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  return [
    "2-contig",
    top ? `${top.role}:${top.contigId}` : "",
    bottom ? `${bottom.role}:${bottom.contigId}` : "",
  ].join("|");
}

function getCachedFilteredRefSubviewCtgs({
  refTrackMembers,
  subview,
  supportContext = {},
}) {
  const list = Array.isArray(refTrackMembers) ? refTrackMembers : [];
  const datasetId = resolveSubviewRefDatasetId(subview, supportContext);
  const selectionKey = buildSubviewRefCacheSelectionKey(subview?.summary || null);
  const cacheKey = `${String(supportContext?.refTrackLabel || supportContext?.selectedChrName || "")}|${selectionKey}|${normalizeSupportDatasetId(datasetId) || 0}`;
  let cacheBySelection = filteredRefSubviewCtgCache.get(list);
  if (!cacheBySelection) {
    cacheBySelection = new Map();
    filteredRefSubviewCtgCache.set(list, cacheBySelection);
  }
  if (cacheBySelection.has(cacheKey)) {
    return cacheBySelection.get(cacheKey);
  }
  const value = buildRefSubviewCtgPool(list, { datasetId });
  cacheBySelection.set(cacheKey, value);
  return value;
}

function buildSubviewSegmentSignature(segments) {
  return (Array.isArray(segments) ? segments : [])
    .map((segment) => [
      normalizeSupportDatasetId(segment?.ctgId) || 0,
      String(segment?.hitKey || ""),
      Number(segment?.refStart || 0),
      Number(segment?.refEnd || 0),
      Number(segment?.ctgStart || 0),
      Number(segment?.ctgEnd || 0),
      Number(segment?.x || 0),
      Number(segment?.width || 0),
    ].join(":"))
    .join("|");
}

function pairRefSubviewSegmentsWithCache({
  cacheKey,
  topSegments,
  bottomSegments,
  trackMode = "2-contig",
  pairingMode = "reference-overlap",
}) {
  if (pairingMode === "projection-key") {
    return pairSubviewSegmentsByProjectionKey(topSegments, bottomSegments);
  }
  const pairCacheKey = [
    trackMode,
    String(cacheKey || ""),
    buildSubviewSegmentSignature(topSegments),
    buildSubviewSegmentSignature(bottomSegments),
  ].join("::");
  if (refSubviewSegmentPairCache.has(pairCacheKey)) {
    return refSubviewSegmentPairCache.get(pairCacheKey);
  }
  const value = trackMode === "track-pair"
    ? pairSubviewTrackSegmentsByReferenceCached(topSegments, bottomSegments)
    : pairSubviewSegmentsByReferenceCached(topSegments, bottomSegments);
  refSubviewSegmentPairCache.set(pairCacheKey, value);
  return value;
}

export function __testBuildFilteredRefSubviewCtgs(args) {
  return getCachedFilteredRefSubviewCtgs(args);
}

export function __testPairRefSubviewSegmentsWithCache(args) {
  return pairRefSubviewSegmentsWithCache(args);
}

function createRenderTracksRenderer(deps = {}) {
  const {
    escapeAttr,
    escapeHtml,
    formatBp,
    getAssemblyI18n,
    getCurrentProject,
    getDatasetNameById,
    getMeasuredTrackViewportPx: getMeasuredTrackViewportPxImpl,
    getSupportDatasetOptions,
  } = deps;
  if (
    typeof escapeAttr !== "function"
    || typeof escapeHtml !== "function"
    || typeof formatBp !== "function"
    || typeof getAssemblyI18n !== "function"
    || typeof getCurrentProject !== "function"
    || typeof getDatasetNameById !== "function"
    || typeof getSupportDatasetOptions !== "function"
  ) {
    throw new Error("render-tracks.js missing required render dependencies");
  }

  function getMeasuredTrackViewportPx(role = "primary") {
    const value = Number(getMeasuredTrackViewportPxImpl?.(role));
    return Number.isFinite(value) && value > 0 ? value : DEFAULT_TRACK_VIEWPORT_PX;
  }

  function getSelectedChromosome(assembly) {
    const selectedChrName = String(assembly?.selectedChrName || "").trim();
    if (!selectedChrName || !Array.isArray(assembly?.chromosomes)) {
      return null;
    }
    return (
      assembly.chromosomes.find((chromosome) => String(chromosome?.chrName || "").trim() === selectedChrName) ||
      null
    );
  }

  function resolveTelomereRuleClass(ruleId) {
    const text = String(ruleId || "");
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash * 31) + text.charCodeAt(index)) % 9973;
    }
    return `is-rule-${(Math.abs(hash) % 6) + 1}`;
  }

  function resolveVisibleTelomereMarkerRect(markerRect, ctgRect) {
    const minimumMarkerWidth = 6;
    const ctgLeft = Number(ctgRect?.x);
    const ctgWidth = Number(ctgRect?.width);
    if (!Number.isFinite(ctgLeft) || !Number.isFinite(ctgWidth) || ctgWidth <= 0) {
      return null;
    }
    const markerCenterX = Number.isFinite(markerRect?.centerX)
      ? markerRect.centerX
      : Number(markerRect?.x || 0) + Number(markerRect?.width || 0) / 2;
    const markerWidth = Math.min(
      ctgWidth,
      Math.max(minimumMarkerWidth, Number(markerRect?.width || 0)),
    );
    const minX = ctgLeft;
    const maxX = ctgLeft + ctgWidth - markerWidth;
    const x = Math.max(minX, Math.min(maxX, markerCenterX - markerWidth / 2));
    return {
      x,
      width: markerWidth,
      centerX: x + markerWidth / 2,
    };
  }

  function renderTelomereMarkersForTrackCtg({ ctg, rect, y, barHeight, role, isMirror }) {
    if (role !== "primary" || isMirror || !Array.isArray(ctg?.telomereMarks) || ctg.telomereMarks.length === 0) {
      return "";
    }
    return ctg.telomereMarks
      .map((mark) => {
        const ctgStart = normalizePositiveInt(mark?.ctgStart ?? mark?.ctg_start ?? mark?.startBp ?? mark?.start_bp);
        const ctgEnd = normalizePositiveInt(mark?.ctgEnd ?? mark?.ctg_end ?? mark?.endBp ?? mark?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const ruleId = String(mark?.ruleId ?? mark?.rule_id ?? "");
        const motif = String(mark?.motif ?? "");
        const strand = String(mark?.strand ?? "");
        const repeatCount = normalizePositiveInt(mark?.repeatCount ?? mark?.repeat_count) ?? "";
        const tooltip = [
          motif || ruleId || "tel",
          repeatCount ? `repeat=${repeatCount}` : "",
          ctgStart && ctgEnd ? `range=${ctgStart}-${ctgEnd}` : "",
          strand ? `strand=${strand}` : "",
        ].filter(Boolean).join("|");
        return `<rect
              class="track-telomere-marker ${resolveTelomereRuleClass(ruleId)}"
              data-telomere-marker="1"
              data-telomere-rule-id="${escapeAttr(ruleId)}"
              data-telomere-motif="${escapeAttr(motif)}"
              data-telomere-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-telomere-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-telomere-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-telomere-strand="${escapeAttr(strand)}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function renderCentromereMarkersForTrackCtg({ ctg, rect, y, barHeight, role, isMirror }) {
    if (
      role !== "primary"
      || isMirror
      || !Array.isArray(ctg?.centromereMarks)
      || ctg.centromereMarks.length === 0
    ) {
      return "";
    }
    return ctg.centromereMarks
      .map((mark) => {
        const ctgStart = normalizePositiveInt(mark?.ctgStart ?? mark?.ctg_start ?? mark?.startBp ?? mark?.start_bp);
        const ctgEnd = normalizePositiveInt(mark?.ctgEnd ?? mark?.ctg_end ?? mark?.endBp ?? mark?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const cenId = String(mark?.cenId ?? mark?.cen_id ?? "cen");
        const queryName = String(mark?.queryName ?? mark?.query_name ?? "");
        const strand = String(mark?.strand ?? "");
        const identityValue = Number(mark?.identity);
        const identity = Number.isFinite(identityValue) ? String(identityValue) : String(mark?.identity ?? "");
        const tooltip = [
          cenId || "cen",
          ctgStart && ctgEnd ? `range=${ctgStart}-${ctgEnd}` : "",
          identity ? `identity=${identity}` : "",
          strand ? `strand=${strand}` : "",
        ].filter(Boolean).join("|");
        return `<rect
              class="track-centromere-marker"
              data-centromere-marker="1"
              data-centromere-cen-id="${escapeAttr(cenId)}"
              data-centromere-query-name="${escapeAttr(queryName)}"
              data-centromere-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-centromere-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-centromere-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-centromere-strand="${escapeAttr(strand)}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function renderNRegionMarkersForTrackCtg({ ctg, rect, y, barHeight, isMirror }) {
    if (isMirror || !Array.isArray(ctg?.nRegions) || ctg.nRegions.length === 0) {
      return "";
    }
    return ctg.nRegions
      .map((region) => {
        const ctgStart = normalizePositiveInt(region?.ctgStart ?? region?.ctg_start ?? region?.startBp ?? region?.start_bp);
        const ctgEnd = normalizePositiveInt(region?.ctgEnd ?? region?.ctg_end ?? region?.endBp ?? region?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const lengthValue = normalizePositiveInt(region?.lengthBp ?? region?.length_bp)
          ?? (ctgStart && ctgEnd ? Math.abs(ctgEnd - ctgStart) + 1 : null);
        const tooltip = [
          "N",
          ctgStart && ctgEnd ? `${ctgStart}-${ctgEnd}` : "",
          lengthValue ? String(lengthValue) : "",
        ].filter(Boolean).join("\t");
        return `<rect
              class="track-n-region-marker"
              data-n-region-marker="1"
              data-n-region-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-n-region-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-n-region-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-n-region-length="${escapeAttr(String(lengthValue ?? ""))}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function resolveReferenceTrackLabel(selectedChrName) {
    if (!selectedChrName) {
      return "ref_chr1";
    }
    const lowered = String(selectedChrName).trim().toLowerCase();
    let suffix = lowered.startsWith("chr") ? lowered.slice(3) : lowered;
    suffix = suffix.replace(/^[_\-\s]+/, "");
    if (/^\d+$/.test(suffix)) {
      suffix = String(Number(suffix));
    }
    return suffix ? `ref_chr${suffix}` : "ref_chr1";
  }

  function isDatasetFastaAvailable(datasets, datasetId) {
    const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
    if (normalizedDatasetId === null || !Array.isArray(datasets)) {
      return false;
    }
    const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
    if (!matched) {
      return true;
    }
    return matched.fastaAvailable !== false;
  }

  function canProjectExportFinalPathFasta(state, currentProject) {
    if (!currentProject) {
      return true;
    }
    const datasetIds = [
      normalizeSupportDatasetId(currentProject.primaryDatasetId),
      ...(Array.isArray(currentProject.supportDatasetIds) ? currentProject.supportDatasetIds : [])
        .map((datasetId) => normalizeSupportDatasetId(datasetId)),
    ].filter((datasetId) => datasetId !== null);
    if (!datasetIds.length) {
      return false;
    }
    return datasetIds.every((datasetId) =>
      isDatasetFastaAvailable(state.initializer?.datasets || [], datasetId),
    );
  }

  function buildDeletedCtgChips(items, selectedRecordIds = new Set(), i18n) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      return "";
    }
    const selectedSet = selectedRecordIds instanceof Set
      ? selectedRecordIds
      : new Set(normalizeDeletedCtgRecordIds(Array.from(selectedRecordIds || [])));
    const chips = list
      .map((item) => {
        const deletedCtgRecordId = normalizeSupportDatasetId(item?.deletedCtgRecordId);
        if (!deletedCtgRecordId) {
          return "";
        }
        const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId) || "-";
        const totalLength = normalizePositiveInt(item?.totalLength) ?? 0;
        const fullName = resolveTrackCtgDisplayName(item, assemblyCtgId);
        const visibleName = resolveTrackCtgVisibleName(item, assemblyCtgId);
        const selectedClass = selectedSet.has(deletedCtgRecordId) ? "is-multi-selected" : "";
        return `
        <button
          type="button"
          class="ctg-chip ${selectedClass}"
          data-deleted-ctg-record-id="${deletedCtgRecordId}"
          data-deleted-assembly-ctg-id="${escapeAttr(String(assemblyCtgId))}"
          title="${escapeAttr(fullName)}"
        >
          <strong>${escapeHtml(visibleName)}</strong>
          <span class="ctg-chip-meta">${formatBp(totalLength)}</span>
        </button>
      `;
      })
      .filter((item) => item)
      .join("");
    if (!chips) {
      return "";
    }
    return `<div class="assembly-members-panel-head chip-group-separator">
      <span class="assembly-members-panel-title-inline">
        <strong>${escapeHtml(i18n.page.deletedMembersTitle)}</strong>
        <button
          type="button"
          class="assembly-members-icon-action"
          data-restore-all-deleted-ctgs="1"
          aria-label="${escapeAttr(i18n.page.restoreAllDeletedMembers)}"
          title="${escapeAttr(i18n.page.restoreAllDeletedMembers)}"
        >
          ↶
        </button>
      </span>
    </div>${chips}`;
  }

  function renderAssemblyStatusToast(assembly) {
    const parts = [];
    if (assembly?.actionStatus) {
      parts.push(`<p class="muted">${escapeHtml(assembly.actionStatus)}</p>`);
    }
    if (assembly?.actionError) {
      parts.push(`<p class="error-text">${escapeHtml(assembly.actionError)}</p>`);
    }
    if (!parts.length) {
      return "";
    }
    return `
    <div class="assembly-status-toast-wrap" aria-live="polite">
      ${parts.join("")}
    </div>
  `;
  }

  function formatBpInterval(start, end) {
    const resolvedStart = Number(start || 0).toLocaleString("en-US");
    const resolvedEnd = Number(end || 0).toLocaleString("en-US");
    return `${resolvedStart}-${resolvedEnd} bp`;
  }

  function formatRulerTickLabel(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) {
      return "0";
    }
    if (numeric >= 1_000_000 && numeric % 1_000_000 === 0) {
      return `${(numeric / 1_000_000).toLocaleString("en-US")}M`;
    }
    if (numeric >= 1_000) {
      const kbValue = Math.round((numeric / 1_000) * 10) / 10;
      return `${kbValue.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 1 })}k`;
    }
    return numeric.toLocaleString("en-US");
  }

  function resolveSupportDatasetLabelById(supportContext, datasetId) {
    const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
    const selectedSupportDatasetId = normalizeSupportDatasetId(supportContext?.supportDatasetId);
    const selectedSupportName = String(supportContext?.supportDatasetName || "").trim();
    if (
      normalizedDatasetId !== null
      && selectedSupportDatasetId !== null
      && normalizedDatasetId === selectedSupportDatasetId
      && selectedSupportName
    ) {
      return selectedSupportName;
    }
    const optionLabel = (Array.isArray(supportContext?.supportDatasetOptions) ? supportContext.supportDatasetOptions : [])
      .find((item) => normalizeSupportDatasetId(item?.datasetId) === normalizedDatasetId)?.label || "";
    if (optionLabel) {
      return String(optionLabel);
    }
    const mirrorDatasetName = (Array.isArray(supportContext?.supportMirrorCtgs) ? supportContext.supportMirrorCtgs : [])
      .find((entry) => normalizeSupportDatasetId(entry?.datasetId) === normalizedDatasetId)?.datasetName || "";
    if (mirrorDatasetName) {
      return String(mirrorDatasetName);
    }
    if (normalizedDatasetId !== null) {
      return `ds-${normalizedDatasetId}`;
    }
    return selectedSupportName;
  }

  function resolveSubviewTrackSelectionLabel(trackSelection, supportContext, i18n) {
    const normalizedSelection = normalizeSubviewTrackSelectionItem(trackSelection);
    if (!normalizedSelection) {
      return "";
    }
    if (normalizedSelection.role === "ref") {
      return String(supportContext?.refTrackLabel || "ref");
    }
    if (normalizedSelection.role === "phased") {
      const track = (Array.isArray(supportContext?.phasedChrTracks) ? supportContext.phasedChrTracks : [])
        .find((item) =>
          normalizeSupportDatasetId(item?.phasedTrackId) === normalizeSupportDatasetId(normalizedSelection.phasedTrackId),
        );
      const key = String(track?.label || normalizedSelection.haplotypeKey || normalizedSelection.phasedTrackId || "phased");
      return i18n.trackControls.phasedTrackLabel.replace("{key}", key);
    }
    if (normalizedSelection.role !== "support") {
      const primaryName = String(supportContext?.primaryDatasetName || "").trim();
      return primaryName
        ? i18n.trackControls.primaryTrackLabelWithName.replace("{name}", primaryName)
        : i18n.trackControls.primaryTrackLabel;
    }
    const supportName = resolveSupportDatasetLabelById(supportContext, normalizedSelection.datasetId);
    if (normalizedSelection.source === "mirror" || normalizedSelection.isMirror) {
      return supportName
        ? i18n.trackControls.mirrorTrackLabelWithName.replace("{name}", supportName)
        : i18n.trackControls.mirrorTrackLabel;
    }
    return supportName
      ? i18n.trackControls.supportTrackLabelWithName.replace("{name}", supportName)
      : i18n.trackControls.supportTrackLabel;
  }

  function resolveTrackToneClass(role) {
    const normalizedRole = normalizeTrackRole(role);
    if (normalizedRole === "support") {
      return " is-companion";
    }
    if (normalizedRole === "ref") {
      return " is-ref";
    }
    return "";
  }

  function getSubviewState(assembly) {
    return getSubviewStateImpl(assembly);
  }

  function renderAssemblyLoadingCurtain(assembly, i18n) {
    const loadingText = String(assembly?.summary || i18n.status?.loadingChromosomes || "Loading...");
    return `
      <div class="assembly-loading-curtain" data-assembly-loading-curtain="1" aria-busy="true" aria-live="polite">
        <div class="assembly-loading-panel">
          <div class="assembly-loading-spinner" aria-hidden="true"></div>
          <p class="assembly-loading-text">${escapeHtml(loadingText)}</p>
        </div>
      </div>
    `;
  }

  function renderAssemblyMainTab(state) {
  const assembly = state.assembly;
  const session = state.session || {};
  const i18n = getAssemblyI18n(state);
  if (assembly.loading) {
    const projectLabel = String(session.projectName || session.projectId || "Project");
    const currentChrLabel = String(assembly.selectedChrName || "current-chr");
    const membersCardTitle = i18n.page.membersCardTitle
      .replace("{projectLabel}", projectLabel)
      .replace("{currentChrLabel}", currentChrLabel);
    const membersCardCollapsed = assembly?.membersCardCollapsed !== false;
    const membersCardToggleLabel = membersCardCollapsed
      ? i18n.page.expandMembersCard
      : i18n.page.collapseMembersCard;
    return `
      <div class="chr-strip has-members-panel">
        <div class="chr-title-wrap">
          <div class="chr-title-and-picker">
            <div class="chr-title">${
              assembly.selectedChrName
                ? `${i18n.chrTitle} ${escapeHtml(assembly.selectedChrName)}`
                : i18n.mainViewTitle
            }</div>
            <div class="chr-picker-inline">
              <button
                id="assembly-chr-picker-toggle"
                class="button ghost tiny"
                title="${escapeAttr(i18n.page.selectChromosomeTitle)}"
                aria-expanded="false"
                disabled
              >
                ▾
              </button>
            </div>
          </div>
        </div>
        <article class="card assembly-members-panel assembly-members-panel-inline is-collapsed">
          <div class="assembly-members-panel-head">
            <strong>${escapeHtml(membersCardTitle)}</strong>
            <button
              type="button"
              class="button ghost tiny"
              data-members-card-toggle="1"
              aria-expanded="${membersCardCollapsed ? "false" : "true"}"
              aria-label="${escapeAttr(membersCardToggleLabel)}"
              title="${escapeAttr(membersCardToggleLabel)}"
              disabled
            >
              ${membersCardCollapsed ? "▾" : "▴"}
            </button>
          </div>
        </article>
      </div>
      <section class="assembly-track-content-stack is-loading">
        <section class="assembly-main-view">
          ${renderAssemblyStatusToast(assembly)}
          <div class="assembly-track-unified assembly-track-panel assembly-track-loading-shell" aria-hidden="true"></div>
        </section>
        ${renderAssemblyLoadingCurtain(assembly, i18n)}
      </section>
    `;
  }
  const currentProject = getCurrentProject(state);
  const selectedChromosome = getSelectedChromosome(assembly);
  const supportDatasetOptions = getSupportDatasetOptions(state, currentProject);
  const supportDatasetId = normalizeSupportDatasetId(assembly.supportDatasetId);
  const primaryDatasetName = getDatasetNameById(
    state.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  const selectedSupportDataset =
    supportDatasetOptions.find((item) => item.datasetId === supportDatasetId) || null;
  const trackPrefs = resolveTrackPrefs(assembly.trackView);
  const subviewTrackPrefs = resolveTrackPrefs(assembly.subviewTrackView || assembly.trackView);
  const subview = getSubviewStateImpl(assembly);
  const supportDsCtgLenBp = Math.max(0, normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0);
  const selectedChrName = String(assembly.selectedChrName || "").trim();
  const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
    assembly.supportDsCtgLenRulesByChr,
    selectedChrName,
    { chrLength: selectedChromosome?.chrLength },
  );
  const supportTrackCtgs = supportDatasetId
    ? filterSupportCtgsBySupportDsCtgLenRules(assembly.supportChrCtgs || [], {
        rules: supportDsCtgLenRules,
        defaultSupportDsCtgLen: supportDsCtgLenBp,
        chrLength: selectedChromosome?.chrLength,
      })
    : [];
  const trackModel = buildDualTrackModel({
    primaryCtgs: assembly.chrCtgs,
    companionCtgs: supportTrackCtgs,
    selectedPrimaryCtgId: assembly.selectedCtgId,
    selectedCompanionCtgId: assembly.selectedCtgId,
    prefs: trackPrefs,
  });
  const supportMirroredCtgs = buildSupportMirroredCtgsForRender({
    supportMirroredCtgs: assembly.supportMirroredCtgs,
    selectedChrName,
    supportDatasetId,
    supportDatasetName: selectedSupportDataset?.label || "",
    supportModelCtgs: trackModel.companion?.ctgs || [],
    supportDatasetOptions,
  });
  const supportSubviewCtgs = buildSupportSubviewCtgPool({
    supportChrCtgs: supportTrackCtgs,
    supportMirroredCtgs,
    selectedChrName,
    deletedCtgs: assembly.deletedCtgs,
    minSupportLengthBp: supportDsCtgLenBp,
    supportDsCtgLenRules,
  });
  const phasedSubviewCtgs = buildPhasedSubviewCtgPool({
    phasedChrTracks: assembly.phasedChrTracks || [],
    primaryCtgs: assembly.chrCtgs || [],
    deletedCtgs: assembly.deletedCtgs,
  });
  const refSubviewCtgs = getCachedFilteredRefSubviewCtgs({
    refTrackMembers: assembly.refTrackMembers || [],
    subview,
    supportContext: {
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      supportDatasetId,
      selectedChrName,
      refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
      primaryCtgs: assembly.chrCtgs,
      supportCtgs: supportSubviewCtgs,
      supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
      phasedCtgs: phasedSubviewCtgs,
    },
  });
  const subviewPanel = renderSubviewSelectionPanel(
    assembly,
    {
      supportDatasetId,
      supportDatasetOptions,
      supportDatasetName: selectedSupportDataset?.label || "",
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      primaryDatasetName,
      primaryCtgs: assembly.chrCtgs,
      supportCtgs: supportSubviewCtgs,
      supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
      phasedCtgs: phasedSubviewCtgs,
      phasedChrTracks: assembly.phasedChrTracks || [],
      refCtgs: refSubviewCtgs,
      refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
    },
    subviewTrackPrefs,
    i18n,
  );
  const chromosomeOptions = assembly.chromosomes.length
    ? assembly.chromosomes
        .map((chr) => {
          const active = chr.chrName === assembly.selectedChrName ? "is-active" : "";
          return `<button class="chr-picker-option ${active}" data-chr-name="${escapeAttr(chr.chrName)}">
            <strong>${escapeHtml(chr.chrName)}</strong>
            <span>${chr.ctgCount} Contigs · ${formatBp(chr.placedBp)}</span>
          </button>`;
        })
        .join("")
    : `<div class="muted">${escapeHtml(i18n.page.noChromosomeData)}</div>`;
  const selectedDeletedRecordIds = new Set(
    normalizeDeletedCtgRecordIds(assembly.selectedDeletedCtgRecordIds),
  );
  const hiddenPrimaryCtgIdSet = new Set(
    filterPrimaryTrackSelectionCtgIds(assembly.hiddenPrimaryCtgIds, assembly),
  );
  const selectedPrimaryTrackCtgIdSet = new Set(
    filterPrimaryTrackSelectionCtgIds(assembly.trackSelectedCtgIds, assembly),
  );
  const ctgChips = assembly.chrCtgs.length
    ? assembly.chrCtgs
        .map((ctg) => {
          const active = ctg.assemblyCtgId === assembly.selectedCtgId ? "is-active" : "";
          const selectedClass = selectedPrimaryTrackCtgIdSet.has(Number(ctg.assemblyCtgId)) ? " is-multi-selected" : "";
          const hiddenClass = hiddenPrimaryCtgIdSet.has(Number(ctg.assemblyCtgId)) ? " is-hidden-contig" : "";
          const hiddenTag = hiddenClass
            ? ` <span class="ctg-chip-hidden-tag">${escapeHtml(i18n.page.deletedHiddenTag)}</span>`
            : "";
          const fullName = resolveTrackCtgDisplayName(ctg, ctg.assemblyCtgId);
          const visibleName = resolveTrackCtgVisibleName(ctg, ctg.assemblyCtgId);
          const sourceTagMarkup = renderDerivedSourceHtmlTag(ctg);
          const coAssignedChrNames = Array.isArray(ctg.coAssignedChrNames)
            ? ctg.coAssignedChrNames
                .map((chrName) => String(chrName || "").trim())
                .filter(Boolean)
            : [];
          const coAssignedTooltip = coAssignedChrNames.length
            ? i18n.page.coAssignedChrTooltip.replace("{chrNames}", coAssignedChrNames.join(", "))
            : "";
          if (coAssignedTooltip) {
            const nameTitle = `${escapeAttr(fullName)}&#10;${escapeAttr(coAssignedTooltip)}`;
            return `<button class="ctg-chip ${active}${selectedClass}${hiddenClass}" data-assembly-ctg-id="${ctg.assemblyCtgId}" data-track-focus-mode="start">
              <strong><span class="ctg-chip-name is-coassigned" title="${nameTitle}">${escapeHtml(visibleName)}</span>${sourceTagMarkup}${hiddenTag}</strong>
              <span class="ctg-chip-meta">${formatBp(ctg.totalLength)}</span>
            </button>`;
          }
          const nameTitle = escapeAttr(fullName);
          return `<button class="ctg-chip ${active}${selectedClass}${hiddenClass}" data-assembly-ctg-id="${ctg.assemblyCtgId}" data-track-focus-mode="start" title="${nameTitle}">
            <strong>${escapeHtml(visibleName)}${sourceTagMarkup}${hiddenTag}</strong>
            <span class="ctg-chip-meta">${formatBp(ctg.totalLength)}</span>
          </button>`;
        })
        .join("")
    : `<div class="muted">${escapeHtml(i18n.noContigsInChr)}</div>`;
  const deletedCtgChips = buildDeletedCtgChips(assembly.deletedCtgs, selectedDeletedRecordIds, i18n);
  const combinedMemberChips = `${ctgChips}${deletedCtgChips}`;
  const projectLabel = String(session.projectName || session.projectId || "Project");
  const currentChrLabel = String(assembly.selectedChrName || "current-chr");
  const membersCardTitle = i18n.page.membersCardTitle
    .replace("{projectLabel}", projectLabel)
    .replace("{currentChrLabel}", currentChrLabel);
  const membersCardCollapsed = assembly?.membersCardCollapsed !== false;
  const membersCardToggleLabel = membersCardCollapsed
    ? i18n.page.expandMembersCard
    : i18n.page.collapseMembersCard;
  const membersPanelClassName = membersCardCollapsed
    ? "card assembly-members-panel assembly-members-panel-inline is-collapsed"
    : "card assembly-members-panel assembly-members-panel-inline";
  const currentFinalPathChrName = resolveCurrentFinalPathChrName(assembly) || currentChrLabel;
  const finalPathDisplayEntries = buildFinalPathDisplayEntries(assembly);
  const currentFinalPath = finalPathDisplayEntries[0]?.finalPathEntry
    || getCurrentChrFinalPath(assembly)
    || (currentFinalPathChrName
      ? buildFinalPathEntry({
        chrName: currentFinalPathChrName,
        segments: [],
        updatedAt: "",
      })
      : null);
  const phasedFinalPathOptions = buildPhasedFinalPathOptions(assembly);
  const graphPreviewState = getFinalPathGraphPreviewState();
  const graphPreviewSegmentOrder =
    String(assembly.finalPathViewMode || "").trim() === "graph"
    && String(graphPreviewState?.selectedChrName || "").trim() === currentFinalPathChrName
      ? graphPreviewState.previewSegmentOrder
      : null;
  const finalPathLogModel = buildFinalPathLogModel({
    chrName: currentFinalPathChrName,
    finalPathEntry: currentFinalPath,
    finalPathByChr: assembly.finalPathByChr,
    primaryCtgs: assembly.chrCtgs,
    hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
    primaryDatasetName,
  });
  const finalPathEntriesWithLog = finalPathDisplayEntries.map((entry) => ({
    ...entry,
    graphPreviewSegmentOrder:
      String(assembly.finalPathViewMode || "").trim() === "graph"
      && String(graphPreviewState?.selectedChrName || "").trim() === entry.chrName
        ? graphPreviewState.previewSegmentOrder
        : null,
    finalPathLogModel: buildFinalPathLogModel({
      chrName: entry.chrName,
      finalPathEntry: entry.finalPathEntry,
      finalPathByChr: assembly.finalPathByChr,
      primaryCtgs: assembly.chrCtgs,
      hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
      primaryDatasetName,
    }),
  }));
  const finalPathCard = renderFinalPathCard(
    {
      projectName: String(session.projectName || session.projectId || "project"),
      chrName: currentFinalPathChrName,
      finalPathEntry: currentFinalPath,
      viewMode: assembly.finalPathViewMode,
      trackView: assembly.finalPathTrackView,
      trackViewportPx: getMeasuredTrackViewportPx("final-path"),
      primaryDatasetName,
      graphPreviewSegmentOrder,
      degapTrackView: assembly.degap?.trackView || assembly.finalPathTrackView,
      degapBody: renderDegapPanel(
        {
          finalPathEntry: currentFinalPath,
          finalPathEntries: finalPathEntriesWithLog,
          trackView: assembly.degap?.trackView || assembly.finalPathTrackView,
          trackViewportPx: getMeasuredTrackViewportPx("final-path"),
          primaryDatasetName,
          degap: assembly.degap,
        },
        {
          escapeAttr,
          escapeHtml,
          i18n,
        },
      ),
      canExportFasta: canProjectExportFinalPathFasta(state, currentProject),
      canExportDegapJobs: Array.isArray(assembly.degap?.jobs) && assembly.degap.jobs.length > 0,
      finalPathLogModel,
      phasedFinalPathOptions,
      finalPathEntries: finalPathEntriesWithLog,
    },
    {
      escapeAttr,
      escapeHtml,
      i18n,
    },
  );

  return `
      <div class="chr-strip has-members-panel">
        <div class="chr-title-wrap">
          <div class="chr-title-and-picker">
            <div class="chr-title">${
              assembly.selectedChrName
                ? `${i18n.chrTitle} ${escapeHtml(assembly.selectedChrName)}`
                : i18n.mainViewTitle
            }</div>
            <div class="chr-picker-inline">
              <button
                id="assembly-chr-picker-toggle"
                class="button ghost tiny"
                title="${escapeAttr(i18n.page.selectChromosomeTitle)}"
                aria-expanded="${assembly.chrPickerOpen ? "true" : "false"}"
                ${assembly.chromosomes.length ? "" : "disabled"}
              >
                ${assembly.chrPickerOpen ? "▴" : "▾"}
              </button>
              ${
                assembly.chrPickerOpen
                  ? `<div class="chr-picker-menu ${assembly.chromosomes.length ? "" : "muted"}">
                      ${chromosomeOptions}
                    </div>`
                  : ""
              }
            </div>
          </div>
        </div>
        <article class="${membersPanelClassName}">
          <div class="assembly-members-panel-head">
            <span class="assembly-members-panel-title-inline">
              <strong>${escapeHtml(membersCardTitle)}</strong>
              <button
                type="button"
                class="assembly-members-icon-action"
                data-reset-members-state="1"
                aria-label="${escapeAttr(i18n.page.resetMembersState)}"
                title="${escapeAttr(i18n.page.resetMembersState)}"
              >
                ↺
              </button>
            </span>
            <button
              type="button"
              class="button ghost tiny"
              data-members-card-toggle="1"
              aria-expanded="${membersCardCollapsed ? "false" : "true"}"
              aria-label="${escapeAttr(membersCardToggleLabel)}"
              title="${escapeAttr(membersCardToggleLabel)}"
            >
              ${membersCardCollapsed ? "▾" : "▴"}
            </button>
          </div>
          ${
            membersCardCollapsed
              ? ""
              : `<div class="ctg-chip-grid assembly-member-chip-region">${combinedMemberChips}</div>`
          }
        </article>
      </div>
      <section class="assembly-track-content-stack">
        <section class="assembly-main-view">
          ${renderAssemblyStatusToast(assembly)}
          ${renderAssemblyTracks({
            model: trackModel,
            hasPrimaryData: assembly.chrCtgs.length > 0,
            hasSupportTrack: supportDatasetId !== null,
            primaryDatasetName,
            supportDatasetName: selectedSupportDataset?.label || "",
            supportDatasetOptions,
            supportDatasetId,
            hasSupportDatasetOptions: supportDatasetOptions.length > 0,
            selectedChrName: assembly.selectedChrName,
            chrLength: normalizePositiveInt(selectedChromosome?.chrLength),
            supportDsCtgLenRules,
            supportDsCtgLenRulesDialogOpen: assembly.supportDsCtgLenRulesDialogOpen === true,
            refTrackMembers: assembly.refTrackMembers,
            trackPrefs,
            subview,
            selectionCtgIds: assembly.trackSelectedCtgIds,
            hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
            dragOffsets: assembly.trackDragOffsets,
            supportMirroredCtgs,
            activeHitsTrackKey: assembly.activeHitsTrackKey,
            phasedAssemblyEnabled: Boolean(currentProject?.phasedAssemblyEnabled),
            phasedChrTracks: assembly.phasedChrTracks,
            i18n,
          })}
          ${subviewPanel}
        </section>
        ${finalPathCard}
      </section>
  `;
}

  function renderAssemblySubviewPanel(state) {
    const assembly = state.assembly;
    const i18n = getAssemblyI18n(state);
    const currentProject = getCurrentProject(state);
    const supportDatasetOptions = getSupportDatasetOptions(state, currentProject);
    const supportDatasetId = normalizeSupportDatasetId(assembly.supportDatasetId);
    const primaryDatasetName = getDatasetNameById(
      state.initializer?.datasets || [],
      currentProject?.primaryDatasetId,
    );
    const selectedSupportDataset =
      supportDatasetOptions.find((item) => item.datasetId === supportDatasetId) || null;
    const selectedChromosome = getSelectedChromosome(assembly);
    const trackPrefs = resolveTrackPrefs(assembly.trackView);
    const subviewTrackPrefs = resolveTrackPrefs(assembly.subviewTrackView || assembly.trackView);
    const subview = getSubviewStateImpl(assembly);
    const supportDsCtgLenBp = Math.max(0, normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0);
    const selectedChrName = String(assembly.selectedChrName || "").trim();
    const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
      assembly.supportDsCtgLenRulesByChr,
      selectedChrName,
      { chrLength: selectedChromosome?.chrLength },
    );
    const supportTrackCtgs = supportDatasetId
      ? filterSupportCtgsBySupportDsCtgLenRules(assembly.supportChrCtgs || [], {
          rules: supportDsCtgLenRules,
          defaultSupportDsCtgLen: supportDsCtgLenBp,
          chrLength: selectedChromosome?.chrLength,
        })
      : [];
    const trackModel = buildDualTrackModel({
      primaryCtgs: assembly.chrCtgs,
      companionCtgs: supportTrackCtgs,
      selectedPrimaryCtgId: assembly.selectedCtgId,
      selectedCompanionCtgId: assembly.selectedCtgId,
      prefs: trackPrefs,
    });
    const supportMirroredCtgs = buildSupportMirroredCtgsForRender({
      supportMirroredCtgs: assembly.supportMirroredCtgs,
      selectedChrName,
      supportDatasetId,
      supportDatasetName: selectedSupportDataset?.label || "",
      supportModelCtgs: trackModel.companion?.ctgs || [],
      supportDatasetOptions,
    });
    const supportSubviewCtgs = buildSupportSubviewCtgPool({
      supportChrCtgs: supportTrackCtgs,
      supportMirroredCtgs,
      selectedChrName,
      deletedCtgs: assembly.deletedCtgs,
      minSupportLengthBp: supportDsCtgLenBp,
      supportDsCtgLenRules,
    });
    const phasedSubviewCtgs = buildPhasedSubviewCtgPool({
      phasedChrTracks: assembly.phasedChrTracks || [],
      primaryCtgs: assembly.chrCtgs || [],
      deletedCtgs: assembly.deletedCtgs,
    });
    const supportContext = {
      supportDatasetId,
      supportDatasetOptions,
      supportDatasetName: selectedSupportDataset?.label || "",
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      primaryDatasetName,
      primaryCtgs: assembly.chrCtgs,
      supportCtgs: supportSubviewCtgs,
      supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
      phasedCtgs: phasedSubviewCtgs,
      phasedChrTracks: assembly.phasedChrTracks || [],
      refCtgs: getCachedFilteredRefSubviewCtgs({
        refTrackMembers: assembly.refTrackMembers || [],
        subview,
        supportContext: {
          primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
          supportDatasetId,
          selectedChrName,
          refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
          primaryCtgs: assembly.chrCtgs,
          supportCtgs: supportSubviewCtgs,
          supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
          phasedCtgs: phasedSubviewCtgs,
        },
      }),
      refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
    };
    return renderSubviewSelectionPanel(assembly, supportContext, subviewTrackPrefs, i18n);
  }

function renderAssemblyTrackControls({
  trackPrefs,
  supportDsCtgLenRules = [],
  chrLength = null,
  supportDatasetOptions,
  supportDatasetId,
  i18n,
}) {
  const supportOptions = supportDatasetOptions.length
    ? supportDatasetOptions
        .map((dataset) => {
          const active = dataset.datasetId === supportDatasetId ? "selected" : "";
          return `<option value="${dataset.datasetId}" ${active}>${escapeHtml(dataset.label)}</option>`;
        })
        .join("")
    : "";
  const supportDatasetSelect = supportDatasetOptions.length
    ? renderFixedTrackSelect({
        id: "assembly-support-dataset-id",
        shellClassName: "assembly-track-select-shell is-support",
        optionsHtml: supportOptions,
      })
    : "";
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "assembly-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const supportDsCtgLenInput = renderSupportDsCtgLenControl({
    field: "supportDsCtgLen",
    id: "assembly-track-support-ds-ctg-len",
    label: i18n.trackControls.supportDatasetLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.supportDatasetLengthBp),
    value: trackPrefs.supportDsCtgLen,
    options: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
    supportDsCtgLenRules,
    chrLength,
    i18n,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "assembly-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "assembly-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "assembly-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  return `
    <div class="assembly-v1-control-grid">
      <div class="assembly-v1-control-item assembly-v1-control-item-wide">
        <label>${escapeHtml(i18n.trackControls.supportDataset)}</label>
        ${
          supportDatasetOptions.length
            ? supportDatasetSelect
            : `<div class="muted assembly-v1-control-note">${escapeHtml(i18n.trackControls.noSupportDatasetConfigured)}</div>`
        }
      </div>
      <div class="assembly-v1-control-item">
        <label>${renderSupportDsCtgLenLabel(i18n)}</label>
        ${supportDsCtgLenInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.minTickUnitKb)}</label>
        ${minTickUnitInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.maxTickCount)}</label>
        ${maxTickCountInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</label>
        ${alignmentInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.mapq)}</label>
        ${mapqInput}
      </div>
    </div>
  `;
}

function renderAssemblyTrackInlineControls({
  trackPrefs,
  supportDsCtgLenRules = [],
  chrLength = null,
  supportDatasetOptions,
  supportDatasetId,
  i18n,
}) {
  const supportOptions = supportDatasetOptions.length
    ? supportDatasetOptions
        .map((dataset) => {
          const active = dataset.datasetId === supportDatasetId ? "selected" : "";
          return `<option value="${dataset.datasetId}" ${active}>${escapeHtml(dataset.label)}</option>`;
        })
        .join("")
    : "";
  const supportDatasetSelect = supportDatasetOptions.length
    ? renderFixedTrackSelect({
        id: "assembly-support-dataset-id",
        shellClassName: "assembly-track-select-shell is-support",
        optionsHtml: supportOptions,
      })
    : "";
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "assembly-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const supportDsCtgLenInput = renderSupportDsCtgLenControl({
    field: "supportDsCtgLen",
    id: "assembly-track-support-ds-ctg-len",
    label: i18n.trackControls.supportDatasetLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.supportDatasetLengthBp),
    value: trackPrefs.supportDsCtgLen,
    options: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
    supportDsCtgLenRules,
    chrLength,
    i18n,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "assembly-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "assembly-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "assembly-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  return `
    <div class="assembly-track-inline-controls" role="group" aria-label="${escapeAttr(i18n.page.primaryAlignmentViewControlsAria)}">
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.supportDataset)}</span>
        ${
          supportDatasetOptions.length
            ? supportDatasetSelect
            : `<span class="muted">${escapeHtml(i18n.trackControls.unconfigured)}</span>`
        }
      </label>
      <label class="assembly-track-inline-field">
        ${renderSupportDsCtgLenLabel(i18n)}
        ${supportDsCtgLenInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.minTickUnitKb)}</span>
        ${minTickUnitInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.maxTickCount)}</span>
        ${maxTickCountInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</span>
        ${alignmentInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.mapq)}</span>
        ${mapqInput}
      </label>
    </div>
  `;
}

function renderCreatePhasedTrackButton({ phasedAssemblyEnabled, phasedTrackCount = 0, i18n }) {
  if (!phasedAssemblyEnabled) {
    return "";
  }
  const disabled = Number(phasedTrackCount) >= 26 ? "disabled" : "";
  const label = i18n.trackControls.createPhasedTrack;
  return `<button type="button" class="button ghost tiny" data-create-phased-track="1" ${disabled}>${escapeHtml(label)}</button>`;
}

function renderFixedTrackSelect({ id, shellClassName = "assembly-track-select-shell", optionsHtml }) {
  return `
    <div class="${shellClassName}">
      <select id="${id}" class="assembly-track-fixed-select">${optionsHtml}</select>
      <span class="assembly-track-control-marker" aria-hidden="true">▾</span>
    </div>
  `;
}

function renderSupportDsCtgLenControl({
  field,
  id,
  label,
  openOptionLabel = "",
  value,
  options,
  supportDsCtgLenRules = [],
  chrLength = null,
  i18n,
}) {
  const advancedActive = hasAdvancedSupportDsCtgLenRules(supportDsCtgLenRules, { chrLength });
  const inputHtml = advancedActive
    ? `
      <div class="assembly-track-combo is-readonly-summary" data-track-combo-field="${escapeAttr(field)}">
        <input
          id="${id}"
          class="assembly-track-combo-input"
          type="text"
          value="${escapeAttr((i18n.trackControls.supportDatasetLengthAdvancedSummary || "Advanced({count})").replace("{count}", String(supportDsCtgLenRules.length)))}"
          readonly
          aria-readonly="true"
          title="${escapeAttr((i18n.trackControls.supportDatasetLengthAdvancedTitle || "Current chromosome uses {count} region rules").replace("{count}", String(supportDsCtgLenRules.length)))}"
        >
      </div>
    `
    : renderTrackNumberInput({
      field,
      id,
      label,
      openOptionLabel,
      value,
      options,
      allowZero: true,
    });
  return inputHtml;
}

function renderSupportDsCtgLenLabel(i18n) {
  const label = i18n.trackControls.supportDatasetLengthBp;
  const settingsLabel = i18n.trackControls.supportDatasetLengthRulesSettings || "Advanced rules";
  return `
    <span class="assembly-support-ds-len-label">
      ${escapeHtml(label)}
      <button
        type="button"
        class="assembly-support-ds-len-settings-button"
        data-support-ds-ctg-len-settings="1"
        aria-label="${escapeAttr(settingsLabel)}"
        title="${escapeAttr(settingsLabel)}"
      >⚙</button>
    </span>
  `;
}

function renderTrackNumberInput({ field, id, label, openOptionLabel = "", value, options, allowZero = false }) {
  const normalizedRaw = allowZero ? normalizeNonNegativeInt(value) : normalizePositiveInt(value);
  const normalized = normalizedRaw ?? (allowZero ? 0 : 1);
  const menuId = `${id}-menu`;
  const optionButtons = options
    .map((optionValue) => {
      const active = Number(optionValue) === Number(normalized) ? " is-active" : "";
      const selected = Number(optionValue) === Number(normalized) ? "true" : "false";
      return `<button type="button" class="assembly-track-combo-option${active}" data-track-combo-option data-track-combo-value="${optionValue}" role="option" aria-selected="${selected}">${escapeHtml(String(optionValue))}</button>`;
    })
    .join("");
  return `
    <div class="assembly-track-combo" data-track-combo-field="${escapeAttr(field)}">
      <input
        id="${id}"
        class="assembly-track-combo-input"
        type="text"
        inputmode="numeric"
        pattern="[0-9]*"
        value="${escapeAttr(String(normalized))}"
        autocomplete="off"
        aria-controls="${escapeAttr(menuId)}"
        aria-expanded="false"
      >
      <button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="${escapeAttr(openOptionLabel || label)}" aria-expanded="false" aria-controls="${escapeAttr(menuId)}">
        <span class="assembly-track-control-marker" aria-hidden="true">▾</span>
      </button>
      <div id="${menuId}" class="assembly-track-combo-menu is-hidden" role="listbox">
        ${optionButtons}
      </div>
    </div>
  `;
}

function renderAssemblyTracks({
  model,
  hasPrimaryData,
  hasSupportTrack,
  primaryDatasetName,
  supportDatasetName,
  supportDatasetOptions,
  supportDatasetId,
  hasSupportDatasetOptions,
  selectedChrName,
  chrLength,
  supportDsCtgLenRules = [],
  supportDsCtgLenRulesDialogOpen = false,
  refTrackMembers = [],
  trackPrefs,
  subview,
  selectionCtgIds = [],
  hiddenPrimaryCtgIds = [],
  dragOffsets = [],
  supportMirroredCtgs = [],
  activeHitsTrackKey = "primary",
  phasedAssemblyEnabled = false,
  phasedChrTracks = [],
  i18n,
}) {
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_MIRROR_ROW_GAP = 10;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const REF_ROW_HEIGHT = 34 * TRACK_HEIGHT_SCALE;
  const TRACK_TAIL_PADDING = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_EMPTY_TEXT_OFFSET_Y = 12 * TRACK_HEIGHT_SCALE;
  const TRACK_MIN_ADJACENT_GAP_PX = 20;
  const TRACK_LABEL_ROW_HEIGHT = 18;
  const TRACK_LABEL_ALIGN_OFFSET = Math.max(
    0,
    Math.round((TRACK_LABEL_ROW_HEIGHT - TRACK_BAR_HEIGHT) / 2),
  );
  const LABEL_COLUMN_WIDTH_PX = 136;
  const blockLength = Math.max(1, normalizePositiveInt(trackPrefs?.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(trackPrefs?.mapq) ?? 0);
  const resolvedChrLength = normalizePositiveInt(chrLength);
  const hasResolvedChrLength = resolvedChrLength !== null;
  const maxPrimaryEndBp = resolveMaxTrackEndBp(model?.primary?.ctgs || []);
  const maxCompanionEndBp = resolveMaxTrackEndBp(model?.companion?.ctgs || []);
  const mirrorRows = buildSupportMirrorTrackRows(supportMirroredCtgs, i18n);
  const maxMirrorEndBp = resolveMaxTrackEndBp(
    mirrorRows.flatMap((row) => (Array.isArray(row.trackModel?.ctgs) ? row.trackModel.ctgs : [])),
  );
  const maxTrackEndBp = Math.max(maxPrimaryEndBp, maxCompanionEndBp, maxMirrorEndBp);
  const visualWindowStart = hasResolvedChrLength
    ? Math.min(0, model.primary.windowStart)
    : model.primary.windowStart;
  const visualDomainSpanBp = hasResolvedChrLength
    ? Math.max(
        1,
        resolvedChrLength - visualWindowStart,
        maxTrackEndBp - visualWindowStart + 1,
      )
    : Math.max(1, model.primary.domainSpanBp);
  const innerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: visualDomainSpanBp,
    minTickUnitKb: trackPrefs?.minTickUnitKb,
    maxTickCount: trackPrefs?.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("primary"),
    fallbackInnerWidth: model.primary.innerWidth,
  });
  const tickBp = resolveTickBpFromScale({
    domainSpanBp: visualDomainSpanBp,
    minTickUnitKb: trackPrefs?.minTickUnitKb,
    maxTickCount: trackPrefs?.maxTickCount,
    fallbackTickBp: trackPrefs?.tickBp,
  });
  const visualWindowEnd = visualWindowStart + visualDomainSpanBp;
  const trackRows = [];
  if (hasSupportTrack) {
    trackRows.push({
      id: "support",
      role: "support",
      interactiveRole: "support",
      dragRole: "support",
      label: supportDatasetName
        ? i18n.trackControls.supportTrackLabelWithName.replace("{name}", supportDatasetName)
        : i18n.trackControls.supportTrackLabel,
      trackModel: model.companion,
      selectable: true,
      emptyMessage: i18n.trackControls.supportTrackEmpty,
      className: "is-companion",
      connectorDirection: "down",
      includeBands: true,
      datasetId: supportDatasetId,
    });
  } else if (hasSupportDatasetOptions) {
    trackRows.push({
      id: "support",
      role: "support",
      interactiveRole: "support",
      dragRole: "support",
      label: i18n.trackControls.supportTrackLabelUnselected,
      trackModel: { ...model.companion, ctgs: [], laneCount: 1 },
      selectable: false,
      emptyMessage: i18n.trackControls.supportTrackSelectFirst,
      className: "is-companion",
      connectorDirection: "down",
      includeBands: true,
      datasetId: null,
    });
  }
  trackRows.push({
    id: "primary",
    role: "primary",
    interactiveRole: "primary",
    dragRole: "primary",
    label: primaryDatasetName
      ? i18n.trackControls.primaryTrackLabelWithName.replace("{name}", primaryDatasetName)
      : i18n.trackControls.primaryTrackLabel,
    trackModel: model.primary,
    selectable: true,
    emptyMessage: hasPrimaryData ? i18n.trackControls.primaryTrackEmpty : i18n.noContigsInChr,
    className: "",
    connectorDirection: "up",
    includeBands: String(activeHitsTrackKey) === "primary",
    datasetId: null,
  });
  const phasedRows = buildPhasedTrackRows({
    phasedChrTracks,
    primaryModel: model.primary,
    activeHitsTrackKey,
    i18n,
  });
  trackRows.push(...phasedRows);
  const normalizedSupportDatasetId = normalizeSupportDatasetId(supportDatasetId);
  trackRows.push(
    ...mirrorRows.map((row) => ({
      ...row,
      alignWithSupport:
        hasSupportTrack
        && normalizedSupportDatasetId !== null
        && normalizeSupportDatasetId(row.datasetId) === normalizedSupportDatasetId,
    })),
  );

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  const rowLayouts = [];
  const refLabel = resolveReferenceTrackLabel(selectedChrName);
  const refRowLayout = {
    id: "ref",
    role: "ref",
    interactiveRole: "ref",
    label: refLabel,
    selectable: true,
    barY: 0,
    labelY: 0,
    labelTop: 0,
    rowTop: 0,
    rowBottom: 0,
  };
  const appendRowLayout = (row, gapAfter = TRACK_ROW_GAP) => {
    const laneCount = Math.max(1, row.trackModel?.laneCount || 1);
    const rowHeight = laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
    const layout = {
      ...row,
      laneCount,
      rowTop: cursorY,
      laneTop: cursorY + TRACK_ROW_PADDING_TOP,
      labelY: cursorY - TRACK_LABEL_OFFSET_Y,
      labelTop: cursorY + TRACK_ROW_PADDING_TOP - TRACK_LABEL_ALIGN_OFFSET,
      rowBottom: cursorY + rowHeight,
    };
    rowLayouts.push(layout);
    cursorY += rowHeight + Math.max(0, Number(gapAfter) || 0);
    return layout;
  };
  const supportRow = trackRows.find((row) => row.id === "support");
  const supportLayout = supportRow ? appendRowLayout(supportRow) : null;
  refRowLayout.rowTop = cursorY;
  refRowLayout.barY = cursorY + TRACK_ROW_PADDING_TOP;
  refRowLayout.labelY = cursorY - TRACK_LABEL_OFFSET_Y;
  refRowLayout.labelTop = refRowLayout.barY - TRACK_LABEL_ALIGN_OFFSET;
  refRowLayout.rowBottom = cursorY + REF_ROW_HEIGHT;
  cursorY += REF_ROW_HEIGHT + TRACK_ROW_GAP;

  const rowsAfterRef = trackRows.filter((row) => row.id !== "support");
  const hasMirrorRows = rowsAfterRef.some((row) => row.isMirror);
  const hasPhasedRows = rowsAfterRef.some((row) => row.role === "phased");
  if (!hasMirrorRows && !hasPhasedRows) {
    rowsAfterRef.forEach((row, index) => {
      const isLast = index === rowsAfterRef.length - 1;
      appendRowLayout(row, isLast ? 0 : TRACK_ROW_GAP);
    });
  } else {
    rowsAfterRef.forEach((row, index) => {
      const laneCount = Math.max(1, row.trackModel?.laneCount || 1);
      const barInsetPx = row.isMirror ? 0 : TRACK_ROW_PADDING_TOP;
      const rowHeight = laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
      const layout = {
        ...row,
        laneCount,
        rowTop: cursorY,
        laneTop: cursorY + barInsetPx,
        labelY: cursorY - TRACK_LABEL_OFFSET_Y,
        labelTop: cursorY + barInsetPx - TRACK_LABEL_ALIGN_OFFSET,
        rowBottom: cursorY + rowHeight,
      };
      rowLayouts.push(layout);
      const lastLaneBottom = layout.laneTop + (laneCount - 1) * TRACK_LANE_HEIGHT + TRACK_BAR_HEIGHT;
      const nextRow = rowsAfterRef[index + 1] || null;
      if (!nextRow) {
        cursorY = lastLaneBottom;
        return;
      }
      const nextInset = nextRow.isMirror ? 0 : TRACK_ROW_PADDING_TOP;
      const usesCompactPhasedGap = row.role === "phased" || nextRow.role === "phased";
      const gapBetweenBars = nextRow.isMirror || row.isMirror || usesCompactPhasedGap
        ? TRACK_MIRROR_ROW_GAP
        : TRACK_ROW_GAP;
      cursorY = lastLaneBottom + gapBetweenBars - nextInset;
    });
  }
  const firstTrackLayout = supportLayout || rowLayouts.find((layout) => layout.id !== "ref") || null;
  const topTrackGapToRuler = firstTrackLayout
    ? Math.max(0, roundTrackMetric(firstTrackLayout.laneTop - rulerTop))
    : TRACK_TAIL_PADDING;
  const tailPadding = hasMirrorRows ? topTrackGapToRuler : TRACK_TAIL_PADDING;
  cursorY += tailPadding;

  const contentBottom = cursorY;
  const buildTrackRectsByLayoutId = (resolvedInnerWidth) =>
    new Map(
      rowLayouts.map((layout) => [
        layout.id,
        buildTrackRectsWithMinGap(layout.trackModel.ctgs, {
          windowStart: visualWindowStart,
          domainSpanBp: visualDomainSpanBp,
          innerWidth: resolvedInnerWidth,
          minGapPx: TRACK_MIN_ADJACENT_GAP_PX,
        }),
      ]),
    );

  const trackRectsByLayoutId = buildTrackRectsByLayoutId(innerWidth);
  const buildBaseRectByCtgId = (layout) => {
    if (!layout) {
      return new Map();
    }
    const rects = trackRectsByLayoutId.get(layout.id) || [];
    return new Map(
      (Array.isArray(layout.trackModel?.ctgs) ? layout.trackModel.ctgs : [])
        .map((ctg, index) => {
          const ctgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (ctgId === null) {
            return null;
          }
          const baseRect = rects[index] ?? buildTrackRect(ctg, {
            windowStart: visualWindowStart,
            domainSpanBp: visualDomainSpanBp,
            innerWidth,
          });
          return [ctgId, baseRect];
        })
        .filter((item) => item !== null),
    );
  };
  const primaryLayout = rowLayouts.find((layout) => layout.role === "primary") || null;
  const primaryRectByCtgId = buildBaseRectByCtgId(primaryLayout);
  const trackDragOffsetMap = new Map(
    normalizeTrackDragOffsets(dragOffsets).map((item) => [
      buildTrackDragOffsetKey(item.trackRole, item.assemblyCtgId, item),
      item,
    ]),
  );
  const resolveTrackCtgHorizontalOffset = (layoutRole, assemblyCtgId, scope = {}) => {
    const item = trackDragOffsetMap.get(buildTrackDragOffsetKey(layoutRole, assemblyCtgId, scope))
      || trackDragOffsetMap.get(buildTrackDragOffsetKey(layoutRole, assemblyCtgId));
    if (!item) {
      return 0;
    }
    if (isFiniteTrackMetric(item.offsetBp)) {
      return convertTrackOffsetBpToPx(item.offsetBp, {
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      });
    }
    return isFiniteTrackMetric(item.offsetPx) ? roundTrackMetric(item.offsetPx) : 0;
  };
  const applyTrackRectHorizontalOffset = (rect, offsetPx) => {
    if (!Number.isFinite(offsetPx) || Math.abs(offsetPx) < 0.01) {
      return rect;
    }
    const x = roundTrackMetric(rect.x + offsetPx);
    const centerX = roundTrackMetric((Number.isFinite(rect.centerX) ? rect.centerX : rect.x + rect.width / 2) + offsetPx);
    return {
      ...rect,
      x,
      centerX,
    };
  };
  const rawRefTrackMembers = Array.isArray(refTrackMembers)
    ? refTrackMembers
    : [];
  const resolvedRefTrackMembers = (rawRefTrackMembers.length
    ? rawRefTrackMembers
    : (() => {
        const fallbackLength = Math.max(1, resolvedChrLength ?? model.primary.domainSpanBp);
        return [{
          sourceKind: "ref_segment",
          name: `${refLabel}:1-${fallbackLength}`,
          segmentStartBp: 1,
          segmentEndBp: fallbackLength,
          anchorStart: 1,
          totalLength: fallbackLength,
          refOrient: "+",
          hits: [],
        }];
      })())
    .map((item, index) => {
      const segmentStartBp = Math.max(1, normalizePositiveInt(item?.segmentStartBp ?? item?.anchorStart) ?? 1);
      const segmentEndBp = Math.max(
        segmentStartBp,
        normalizePositiveInt(item?.segmentEndBp)
          ?? (segmentStartBp + Math.max(1, normalizePositiveInt(item?.totalLength) ?? 1) - 1),
      );
      return {
        ...item,
        assemblyCtgId: normalizeSupportDatasetId(item?.assemblyCtgId) ?? (2_100_000_000 + index + 1),
        segmentOrder: Number.isFinite(Number(item?.segmentOrder)) ? Number(item.segmentOrder) : index + 1,
        segmentStartBp,
        segmentEndBp,
        totalLength: Math.max(1, normalizePositiveInt(item?.totalLength) ?? (segmentEndBp - segmentStartBp + 1)),
        name: String(item?.name || "").trim() || `${refLabel}:${segmentStartBp}-${segmentEndBp}`,
        referenceChrName: String(item?.referenceChrName || selectedChrName || "").trim(),
        refOrient: resolveTrackCtgOrient(item),
      };
    })
    .sort((left, right) => {
      if (left.segmentStartBp !== right.segmentStartBp) {
        return left.segmentStartBp - right.segmentStartBp;
      }
      return left.segmentEndBp - right.segmentEndBp;
    });
  const refMemberLayoutCtgs = resolvedRefTrackMembers.map((member) => ({
    ...member,
    startBp: member.segmentStartBp,
    lengthBp: Math.max(1, member.segmentEndBp - member.segmentStartBp + 1),
    laneIndex: 0,
  }));
  const refMemberRects = buildTrackRectsWithMinGap(refMemberLayoutCtgs, {
    windowStart: visualWindowStart,
    domainSpanBp: visualDomainSpanBp,
    innerWidth,
    minGapPx: 15,
  });
  const refMemberRectByCtgId = new Map(
    refMemberLayoutCtgs.map((member, index) => [member.assemblyCtgId, refMemberRects[index]]),
  );
  const refMemberBlocks = resolvedRefTrackMembers
    .map((member) => {
      const rect = refMemberRectByCtgId.get(member.assemblyCtgId) || buildTrackHitRect({
        ctgStartBp: member.segmentStartBp,
        ctgEndBp: member.segmentEndBp,
        windowStart: visualWindowStart,
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      });
      const refLabelX = rect.x + 4;
      const refLabelY = refRowLayout.barY + TRACK_TEXT_OFFSET_Y;
      const slotToken = getSubviewSlotToken(subview, "ref", member.assemblyCtgId);
      const slotClass = slotToken ? " is-subview-selected" : "";
      return `
        <g
          class="track-ctg-group${slotClass}"
          data-track-contig-id="${member.assemblyCtgId}"
          data-track-role="ref"
          data-track-is-mirror="0"
          data-track-dataset-id="0"
          data-track-source-kind="${escapeAttr(String(member.sourceKind || "ref_segment"))}"
          data-track-reference-chr-name="${escapeAttr(String(member.referenceChrName || selectedChrName || ""))}"
          data-track-segment-start="${member.segmentStartBp}"
          data-track-segment-end="${member.segmentEndBp}"
          data-track-contig-name="${escapeAttr(member.name)}"
        >
          <rect
            class="track-reference-member${slotClass}"
            x="${rect.x.toFixed(2)}"
            y="${refRowLayout.barY.toFixed(2)}"
            width="${rect.width.toFixed(2)}"
            height="${TRACK_BAR_HEIGHT}"
            rx="${TRACK_HEIGHT_SCALE * 2}"
            ry="${TRACK_HEIGHT_SCALE * 2}"
            data-ref-member-name="${escapeAttr(member.name)}"
            data-ref-member-start-bp="${member.segmentStartBp}"
            data-ref-member-end-bp="${member.segmentEndBp}"
          >
            <title>${escapeHtml(member.name)} | start=${member.segmentStartBp} | end=${member.segmentEndBp}</title>
          </rect>
          <text
            class="track-ctg-label track-reference-member-label is-ref"
            x="${refLabelX.toFixed(2)}"
            y="${refLabelY.toFixed(2)}"
            text-anchor="start"
            data-track-label-for-contig-id="${member.assemblyCtgId}"
            data-track-label-role="ref"
            data-track-label-is-mirror="0"
          >${escapeHtml(
            `${member.name} (${member.refOrient})`,
          )}</text>
          ${
            slotToken
              ? `<text class="track-slot-badge" x="${(rect.x + rect.width - 8).toFixed(2)}" y="${(refRowLayout.barY + TRACK_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(slotToken)}</text>`
              : ""
          }
        </g>
      `;
    })
    .join("");
  const resolveReferenceTrackHitRect = (refStartBp, refEndBp) => {
    const hitStartBp = Math.min(refStartBp, refEndBp);
    const hitEndBp = Math.max(refStartBp, refEndBp);
    const containingMember = resolvedRefTrackMembers.find((member) =>
      hitStartBp >= member.segmentStartBp && hitEndBp <= member.segmentEndBp,
    );
    if (containingMember) {
      const containingRect = refMemberRectByCtgId.get(containingMember.assemblyCtgId);
      if (containingRect) {
        return buildTrackHitRectWithinCtgDisplay({
          ctgRect: containingRect,
          ctgLengthBp: containingMember.totalLength,
          ctgStartOffset: hitStartBp - containingMember.segmentStartBp + 1,
          ctgEndOffset: hitEndBp - containingMember.segmentStartBp + 1,
        });
      }
    }
    return buildTrackHitRect({
      ctgStartBp: refStartBp,
      ctgEndBp: refEndBp,
      windowStart: visualWindowStart,
      domainSpanBp: visualDomainSpanBp,
      innerWidth,
    });
  };
  const supportRectByCtgId = buildBaseRectByCtgId(supportLayout);
  const resolveTrackCtgBaseRect = (layout, ctg, index) => {
    if (layout?.alignWithPrimary) {
      const primaryRect = primaryRectByCtgId.get(normalizeSupportDatasetId(ctg?.assemblyCtgId));
      if (primaryRect) {
        return primaryRect;
      }
    }
    if (layout?.isMirror && layout?.alignWithSupport) {
      const supportRect = supportRectByCtgId.get(normalizeSupportDatasetId(ctg?.assemblyCtgId));
      if (supportRect) {
        return supportRect;
      }
    }
    const rects = trackRectsByLayoutId.get(layout.id) || [];
    return rects[index] ?? buildTrackRect(ctg, {
      windowStart: visualWindowStart,
      domainSpanBp: visualDomainSpanBp,
      innerWidth,
    });
  };
  const resolveTrackCtgDisplayRect = (layout, ctg, index) =>
    applyTrackRectHorizontalOffset(
      resolveTrackCtgBaseRect(layout, ctg, index),
      resolveTrackCtgHorizontalOffset(layout.dragRole || layout.role, ctg.assemblyCtgId, {
        datasetId: layout.datasetId || ctg.datasetId,
        phasedTrackId: layout.phasedTrackId || ctg.phasedTrackId,
        phasedTrackItemId: ctg.phasedTrackItemId,
      }),
    );
  const maxRectRight = Math.max(
    innerWidth,
    ...rowLayouts
      .flatMap((layout) => layout.trackModel.ctgs.map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
        return Number(rect.x) + Number(rect.width);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const minRectLeft = Math.min(
    0,
    ...rowLayouts
      .flatMap((layout) => layout.trackModel.ctgs.map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
        return Number(rect.x);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const labelVisibleMinX = Math.floor(Math.min(0, minRectLeft));
  const labelVisibleMaxX = Math.ceil(Math.max(innerWidth, maxRectRight));
  const maxLabelRight = rowLayouts.reduce((layoutMax, layout) => {
    return layout.trackModel.ctgs.reduce((ctgMax, ctg, index) => {
      const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        outsideLabelAnchor: "bar-middle",
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMax;
      }
      const labelRight = resolveTrackCtgLabelRightBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.max(ctgMax, labelRight);
    }, layoutMax);
  }, innerWidth);
  const minLabelLeft = rowLayouts.reduce((layoutMin, layout) => {
    return layout.trackModel.ctgs.reduce((ctgMin, ctg, index) => {
      const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        outsideLabelAnchor: "bar-middle",
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMin;
      }
      const labelLeft = resolveTrackCtgLabelLeftBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.min(ctgMin, labelLeft);
    }, layoutMin);
  }, 0);
  const renderMinX = Math.floor(Math.min(0, minRectLeft, minLabelLeft));
  const renderMaxX = Math.ceil(Math.max(innerWidth, maxRectRight, maxLabelRight));
  const renderInnerWidth = Math.max(innerWidth, renderMaxX - renderMinX);
  const renderViewBoxMinX = renderMinX;
  const focusCtg = model.primary.ctgs.find((ctg) => ctg.isSelected) || model.primary.ctgs[0] || null;
  const primaryRects = trackRectsByLayoutId.get("primary") || [];
  const focusCtgIndex = focusCtg
    ? model.primary.ctgs.findIndex((ctg) => Number(ctg.assemblyCtgId) === Number(focusCtg.assemblyCtgId))
    : -1;
  const focusOffsetPx = focusCtg
    ? resolveTrackCtgHorizontalOffset("primary", focusCtg.assemblyCtgId)
    : 0;
  const focusRect = focusCtgIndex >= 0 && primaryRects[focusCtgIndex]
    ? applyTrackRectHorizontalOffset(primaryRects[focusCtgIndex], focusOffsetPx)
    : null;
  const fallbackFocusRect = focusCtg
    ? buildTrackRect(focusCtg, {
        windowStart: visualWindowStart,
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      })
    : null;
  const shiftedFallbackFocusRect = fallbackFocusRect
    ? applyTrackRectHorizontalOffset(fallbackFocusRect, focusOffsetPx)
    : null;
  const focusCenterX = focusCtg
    ? (focusRect
      ? focusRect.centerX
      : shiftedFallbackFocusRect?.centerX ?? 0)
    : 0;
  const focusStartX = focusCtg
    ? (focusRect
      ? focusRect.x
      : shiftedFallbackFocusRect?.x ?? 0)
    : 0;
  const focusCenterContentX = focusCenterX - renderViewBoxMinX;
  const focusStartContentX = focusStartX - renderViewBoxMinX;
  const refTrackX = buildTrackBpX({
    bp: 0,
    windowStart: visualWindowStart,
    domainSpanBp: visualDomainSpanBp,
    innerWidth,
  });
  const refTrackWidth = buildTrackReferenceWidth(resolvedChrLength, visualDomainSpanBp, innerWidth);
  const refWindowEnd = hasResolvedChrLength
    ? resolvedChrLength
    : visualWindowEnd;
  const rulerWindowEnd = Math.max(0, Math.min(visualWindowEnd, refWindowEnd));
  const tickItems = buildTrackTickItems({
    windowStart: visualWindowStart,
    windowEnd: rulerWindowEnd,
    tickBp,
    innerWidth,
    domainSpanBp: visualDomainSpanBp,
  });
  const tickRenderItems = tickItems.map((tick, index) => {
      const isFirst = index === 0;
      const isLast = index === tickItems.length - 1;
      const isSingle = isFirst && isLast;
      const labelAnchor = isSingle ? "middle" : isFirst ? "start" : isLast ? "end" : "middle";
      const labelX = isSingle
        ? tick.x
        : isFirst
          ? Math.min(innerWidth, tick.x + TRACK_EDGE_LABEL_PADDING)
          : isLast
            ? Math.max(0, tick.x - TRACK_EDGE_LABEL_PADDING)
            : tick.x;
      return {
        ...tick,
        labelAnchor,
        labelX,
        bp: tick.bp,
        labelText: isLast ? formatBp(tick.bp) : formatRulerTickLabel(tick.bp),
        hideLabel: false,
      };
    });

  if (tickRenderItems.length >= 2) {
    const endTick = tickRenderItems[tickRenderItems.length - 1];
    const previousTick = tickRenderItems[tickRenderItems.length - 2];
    if (isTrackTickLabelOverlap(previousTick, endTick)) {
      previousTick.hideLabel = true;
    }
  }

  const tickLines = tickRenderItems
    .map((tick) => `<g class="track-tick">
        <line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${rulerTop + TRACK_LABEL_OFFSET_Y}" x2="${tick.x.toFixed(2)}" y2="${(contentBottom - 3 * TRACK_HEIGHT_SCALE).toFixed(2)}" />
        ${
          tick.hideLabel
            ? ""
            : `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${rulerTop - TRACK_LABEL_OFFSET_Y}" text-anchor="${tick.labelAnchor}">${escapeHtml(
                tick.labelText,
              )}</text>`
        }
      </g>`)
    .join("");

  const hiddenPrimaryCtgIdSet = new Set(normalizeTrackSelectionCtgIds(hiddenPrimaryCtgIds));
  const resolveTrackCtgVerticalOffset = (layoutRole, assemblyCtgId) =>
    layoutRole === "primary" && hiddenPrimaryCtgIdSet.has(Number(assemblyCtgId)) ? -30 : 0;

  const subviewTrackSelections = getSubviewTrackSelections(subview);
  const isSubviewTrackLabelSelected = (layout, trackLabelRole) => {
    if (!trackLabelRole) {
      return false;
    }
    const labelSource = layout?.isMirror ? "mirror" : "mother";
    const labelDatasetId = normalizeSupportDatasetId(layout?.datasetId);
    return subviewTrackSelections.some((selection) => {
      if (selection?.role !== trackLabelRole) {
        return false;
      }
      if (trackLabelRole === "phased") {
        const selectionPhasedTrackId = normalizeSupportDatasetId(selection?.phasedTrackId);
        const labelPhasedTrackId = normalizeSupportDatasetId(layout?.phasedTrackId);
        return selectionPhasedTrackId !== null && selectionPhasedTrackId === labelPhasedTrackId;
      }
      if (trackLabelRole !== "support") {
        return true;
      }
      const selectionDatasetId = normalizeSupportDatasetId(selection?.datasetId);
      if (selectionDatasetId !== null && selectionDatasetId !== labelDatasetId) {
        return false;
      }
      const selectionSource = selection?.isMirror === true
        ? "mirror"
        : normalizeSubviewTrackSource(selection?.source);
      return selectionSource === labelSource;
    });
  };
  const labelRows = [supportLayout, refRowLayout, ...rowLayouts.filter((layout) => layout.id !== "support")]
    .filter((layout) => Boolean(layout))
    .map((layout) => {
      const trackLabelRole = normalizeTrackRole(layout.interactiveRole || layout.role);
      const selectableTrackLabel = trackLabelRole && layout.selectable !== false;
      const isSelectedTrackLabel = selectableTrackLabel && isSubviewTrackLabelSelected(layout, trackLabelRole);
      const roleClass =
        `${layout.id === "ref" ? " is-ref" : layout.className ? ` ${layout.className}` : ""}`
        + `${selectableTrackLabel ? " is-track-selectable" : ""}`
        + `${isSelectedTrackLabel ? " is-subview-track-selected" : ""}`;
      const labelTop = Number.isFinite(layout.labelTop) ? layout.labelTop : layout.rowTop;
      const trackLabelDatasetId = normalizeSupportDatasetId(layout.datasetId);
      const trackLabelIsMirror = layout.isMirror ? "1" : "0";
      const trackLabelSource = layout.isMirror ? "mirror" : "mother";
      const phasedTrackId = normalizeSupportDatasetId(layout.phasedTrackId);
      const phasedHaplotypeKey = String(layout.phasedHaplotypeKey || "").trim();
      const phasedTrackAttrs = trackLabelRole === "phased"
        ? ` data-track-label-phased-track-id="${phasedTrackId || 0}" data-track-label-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
        : "";
      const trackLabelAttrs = selectableTrackLabel
        ? ` data-track-label-role="${trackLabelRole}" data-track-label-selectable="1" data-track-label-source="${trackLabelSource}" data-track-label-is-mirror="${trackLabelIsMirror}" data-track-label-dataset-id="${trackLabelDatasetId || 0}"${phasedTrackAttrs}`
        : "";
      return `<div class="assembly-track-label-row${roleClass}" style="top:${labelTop}px"${trackLabelAttrs} title="${escapeAttr(layout.label)}">
        <span>${escapeHtml(layout.label)}</span>
      </div>`;
    })
    .join("");

  const collinearityBandItems = rowLayouts
    .flatMap((layout) => {
      if (!layout.includeBands) {
        return [];
      }
      if (!layout.trackModel.ctgs.length) {
        return [];
      }
      return layout.trackModel.ctgs.flatMap((ctg, ctgIndex) => {
        const isHiddenPrimaryCtg =
          layout.role === "primary" && hiddenPrimaryCtgIdSet.has(Number(ctg.assemblyCtgId));
        if (isHiddenPrimaryCtg) {
          return [];
        }
        const hits = resolveTrackRenderableHits(ctg);
        if (!hits.length) {
          return [];
        }
        const ctgDisplayRect = resolveTrackCtgDisplayRect(layout, ctg, ctgIndex);
        return hits.flatMap((hit) => {
          const hitBlockLength = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
          if (hitBlockLength < blockLength) {
            return [];
          }
          const hitMapq = resolveHitMapq(hit);
          if (hitMapq < minMapq) {
            return [];
          }
          const hitStartOffset = Number(hit?.ctgStart ?? hit?.ctg_start);
          const hitEndOffset = Number(hit?.ctgEnd ?? hit?.ctg_end);
          const refStartBp = Number(hit?.refStart ?? hit?.ref_start);
          const refEndBp = Number(hit?.refEnd ?? hit?.ref_end);
          if (
            !Number.isFinite(hitStartOffset) ||
            !Number.isFinite(hitEndOffset) ||
            !Number.isFinite(refStartBp) ||
            !Number.isFinite(refEndBp)
          ) {
            return [];
          }
          const ctgRect = buildTrackHitRectWithinCtgDisplay({
            ctgRect: ctgDisplayRect,
            ctgLengthBp: ctg.lengthBp,
            ctgStartOffset: hitStartOffset,
            ctgEndOffset: hitEndOffset,
          });
          const refRect = resolveReferenceTrackHitRect(refStartBp, refEndBp);
          const ctgVerticalOffset = resolveTrackCtgVerticalOffset(layout.role, ctg.assemblyCtgId);
          const ctgLaneTop = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT + ctgVerticalOffset;
          const bandPoints = buildCollinearityBandPoints({
            ctgRect,
            refRect,
            refLeftClamp: refTrackX,
            refRightClamp: refTrackX + refTrackWidth,
            refTop: refRowLayout.barY,
            refBottom: refRowLayout.barY + TRACK_BAR_HEIGHT,
            ctgTop: ctgLaneTop,
            ctgBottom: ctgLaneTop + TRACK_BAR_HEIGHT,
            direction: layout.connectorDirection,
            reversed: resolveTrackHitDisplayReversed(ctg, hit),
          });
          const trackRole = layout.interactiveRole || layout.role;
          const phasedTrackId = trackRole === "phased"
            ? normalizeSupportDatasetId(layout.phasedTrackId ?? ctg.phasedTrackId)
            : null;
          const phasedTrackItemId = trackRole === "phased"
            ? normalizeSupportDatasetId(ctg.phasedTrackItemId)
            : null;
          return {
            className: layout.className ? ` ${layout.className}` : "",
            tone: trackRole === "support" ? "companion" : "primary",
            trackRole,
            contigId: ctg.assemblyCtgId,
            phasedTrackId,
            phasedTrackItemId,
            phasedHaplotypeKey: trackRole === "phased"
              ? String(layout.phasedHaplotypeKey || ctg.phasedHaplotypeKey || "").trim()
              : "",
            points: bandPoints,
          };
        });
      });
    })
    .filter(Boolean);
  const collinearityBands = collinearityBandItems
    .map((band) => {
      const phasedBandAttrs = band.trackRole === "phased"
        ? ` data-band-phased-track-id="${band.phasedTrackId || 0}" data-band-phased-track-item-id="${band.phasedTrackItemId || 0}" data-band-phased-haplotype-key="${escapeAttr(band.phasedHaplotypeKey || "")}"`
        : "";
      return `<polygon class="track-collinearity-band${band.className}" data-band-track-role="${escapeAttr(
          band.trackRole,
        )}" data-band-contig-id="${band.contigId}"${phasedBandAttrs} data-track-band-proxy="1" points="${band.points}" />`;
    })
    .join("");

  const rowBlocks = rowLayouts
    .map((layout) => {
      const rowBgClass = layout.className ? ` ${layout.className}` : "";
      if (!layout.trackModel.ctgs.length) {
        return `<text class="track-row-empty-label" x="12" y="${(layout.laneTop + TRACK_EMPTY_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(
            layout.emptyMessage,
          )}</text>`;
      }
      const selectedTrackCtgIds = new Set(normalizeTrackSelectionCtgIds(selectionCtgIds));
      const renderEntries = layout.trackModel.ctgs
        .map((ctg, index) => {
          const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
          const ctgVerticalOffset = resolveTrackCtgVerticalOffset(layout.role, ctg.assemblyCtgId);
          const y = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT + ctgVerticalOffset;
          const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
          const labelPlacement = resolveBoundedTrackCtgLabelPlacement({
            ctgName: labelText,
            role: layout.interactiveRole || layout.role,
            rect,
            barY: y,
            barHeight: TRACK_BAR_HEIGHT,
            inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
            outsideLabelAnchor: "bar-middle",
            hideOutsideLabel: true,
            minVisibleX: labelVisibleMinX,
            maxVisibleX: labelVisibleMaxX,
          });
          const slotToken = getSubviewSlotToken(
            subview,
            layout.interactiveRole || layout.role,
            ctg.assemblyCtgId,
          );
          const activeClass = ctg.isSelected ? " is-active" : "";
          const slotClass = slotToken ? " is-subview-selected" : "";
          const multiSelectedClass = selectedTrackCtgIds.has(Number(ctg.assemblyCtgId)) ? " is-multi-selected" : "";
          const hiddenClass = ctgVerticalOffset < 0 ? " is-hidden-contig" : "";
          const mirrorClass = layout.isMirror ? " is-mirror" : "";
          const groupClass = `track-ctg-group${activeClass}${slotClass}${multiSelectedClass}${hiddenClass}${mirrorClass}${rowBgClass}`;
          const rectMetricsAttrs = `data-track-rect-x="${rect.x.toFixed(2)}" data-track-rect-y="${y.toFixed(2)}" data-track-rect-width="${rect.width.toFixed(2)}" data-track-rect-height="${TRACK_BAR_HEIGHT}"`;
          const phasedTrackId = normalizeSupportDatasetId(layout.phasedTrackId);
          const phasedTrackItemId = normalizeSupportDatasetId(ctg.phasedTrackItemId);
          const phasedHaplotypeKey = String(layout.phasedHaplotypeKey || ctg.phasedHaplotypeKey || "").trim();
          const phasedAttrs = (layout.interactiveRole || layout.role) === "phased"
            ? ` data-track-phased-track-id="${phasedTrackId || 0}" data-track-phased-track-item-id="${phasedTrackItemId || 0}" data-track-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
            : "";
          const phasedLabelAttrs = (layout.interactiveRole || layout.role) === "phased"
            ? ` data-track-label-phased-track-id="${phasedTrackId || 0}" data-track-label-phased-track-item-id="${phasedTrackItemId || 0}" data-track-label-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
            : "";
          const groupAttrs = layout.selectable
            ? `data-track-contig-id="${ctg.assemblyCtgId}" data-track-role="${layout.interactiveRole || layout.role}" data-track-contig-name="${escapeAttr(ctg.name)}" data-track-is-mirror="${layout.isMirror ? "1" : "0"}" data-track-dataset-id="${Number(layout.datasetId || 0)}" data-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(ctg))}"${phasedAttrs} ${rectMetricsAttrs}`
            : "";
          const labelAttrs = layout.selectable
            ? ` data-track-label-for-contig-id="${ctg.assemblyCtgId}" data-track-label-role="${escapeAttr(layout.interactiveRole || layout.role)}" data-track-label-is-mirror="${layout.isMirror ? "1" : "0"}"${phasedLabelAttrs}`
            : "";
          const sourceTagMarkup = renderDerivedSourceSvgTag(ctg);
          const labelMarkup = labelPlacement.hidden
            ? ""
            : `<text class="track-ctg-label${mirrorClass}${rowBgClass}${labelPlacement.classSuffix}" x="${labelPlacement.x.toFixed(2)}" y="${labelPlacement.y.toFixed(2)}"${labelPlacement.transformAttr} text-anchor="${labelPlacement.textAnchor}"${labelAttrs}>${escapeHtml(
              labelText,
            )}${sourceTagMarkup}</text>`;
          const telomereMarkerMarkup = renderTelomereMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          const centromereMarkerMarkup = renderCentromereMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          const nRegionMarkerMarkup = renderNRegionMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          return {
            ctg,
            rect,
            markup: `<g class="${groupClass}" ${groupAttrs}>
            <rect
              class="track-ctg${activeClass}${slotClass}${multiSelectedClass}${hiddenClass}${mirrorClass}${rowBgClass}"
              data-track-focus="${ctg.isSelected ? "true" : "false"}"
              x="${rect.x.toFixed(2)}"
              y="${y.toFixed(2)}"
              width="${rect.width.toFixed(2)}"
              height="${TRACK_BAR_HEIGHT}"
              rx="${TRACK_HEIGHT_SCALE * 2}"
              ry="${TRACK_HEIGHT_SCALE * 2}"
            >
              <title>${escapeHtml(ctg.name)} | start=${ctg.startBp} | len=${ctg.lengthBp}</title>
            </rect>
            ${telomereMarkerMarkup}
            ${centromereMarkerMarkup}
            ${nRegionMarkerMarkup}
            ${labelMarkup}
            ${
              slotToken
                ? `<text class="track-slot-badge" x="${(rect.x + rect.width - 8).toFixed(2)}" y="${(y + TRACK_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(slotToken)}</text>`
                : ""
            }
          </g>`,
          };
        })
        .filter((entry) => entry && entry.markup);
      const blocks = sortTrackEntriesForRender(renderEntries)
        .map((entry) => entry.markup)
        .join("");
      return blocks;
    })
    .join("");

  const refBaseBar = resolvedRefTrackMembers.length <= 1
    ? `
    <rect
      class="track-reference-bar"
      x="${refTrackX.toFixed(2)}"
      y="${refRowLayout.barY.toFixed(2)}"
      width="${refTrackWidth.toFixed(2)}"
      height="${TRACK_BAR_HEIGHT}"
      rx="0"
      ry="0"
      data-ref-span-bp="${resolvedChrLength ?? model.primary.domainSpanBp}"
    ></rect>`
    : "";
  const refRow = `
    ${refBaseBar}
    ${refMemberBlocks}
  `;

  const inlineControls = renderAssemblyTrackInlineControls({
    trackPrefs,
    supportDsCtgLenRules,
    chrLength,
    supportDatasetOptions,
    supportDatasetId,
    i18n,
  });
  const createPhasedTrackButton = renderCreatePhasedTrackButton({
    phasedAssemblyEnabled,
    phasedTrackCount: phasedChrTracks.length,
    i18n,
  });
  const supportDsCtgLenRulesDialog = supportDsCtgLenRulesDialogOpen
    ? renderSupportDsCtgLenRulesDialog({
      rules: supportDsCtgLenRules,
      chrLength: resolvedChrLength,
      supportDsCtgLen: trackPrefs.supportDsCtgLen,
      i18n,
    })
    : "";
  return `
    <div class="assembly-track-unified assembly-track-panel">
      <div class="assembly-track-panel-head">
        <strong>${escapeHtml(i18n.page.primaryAlignmentViewSingleCardTitle)}</strong>
        <div class="assembly-track-panel-actions">
          ${createPhasedTrackButton}
          ${inlineControls}
        </div>
      </div>
      <div class="assembly-track-layout">
        <div class="assembly-track-label-column" style="width:${LABEL_COLUMN_WIDTH_PX}px;height:${contentBottom}px">
          ${labelRows}
        </div>
        <div
          class="assembly-track-scroll"
          data-track-role="primary"
          data-focus-center="${focusCenterContentX}"
          data-focus-start="${focusStartContentX}"
          data-track-window-start-bp="${visualWindowStart}"
          data-track-domain-span-bp="${visualDomainSpanBp}"
          data-track-inner-width="${innerWidth}"
          data-track-viewbox-min-x="${renderViewBoxMinX}"
        >
          ${renderTrackBandCanvasLayer({
            sceneKind: "main-track",
            width: renderInnerWidth,
            height: contentBottom,
            viewBoxMinX: renderViewBoxMinX,
            bands: collinearityBandItems,
          })}
          <svg class="assembly-track-svg" data-track-band-svg-overlay="1" width="${renderInnerWidth}" height="${contentBottom}" viewBox="${renderViewBoxMinX} 0 ${renderInnerWidth} ${contentBottom}" preserveAspectRatio="xMinYMin meet">
            <line class="track-ruler-line" x1="${refTrackX.toFixed(2)}" y1="${rulerTop}" x2="${(refTrackX + refTrackWidth).toFixed(2)}" y2="${rulerTop}" />
            ${tickLines}
            ${collinearityBands}
            ${rowBlocks}
            ${refRow}
          </svg>
        </div>
      </div>
      ${supportDsCtgLenRulesDialog}
    </div>
  `;
}

function renderSupportDsCtgLenRulesDialog({ rules = [], chrLength = null, supportDsCtgLen = 0, i18n }) {
  const resolvedChrLength = normalizePositiveInt(chrLength) ?? 1;
  const rows = normalizeSupportRulesForDialog(rules, {
    chrLength: resolvedChrLength,
    supportDsCtgLen,
  });
  const labels = i18n.trackControls;
  const rowHtml = rows.map((rule, index) => renderSupportDsCtgLenRulesDialogRow(rule, index, labels)).join("");
  const baseline = JSON.stringify(rows.map((rule) => ({
    startMb: formatRuleMbValue(rule.startBp <= 1 ? 0 : rule.startBp / 1_000_000),
    endMb: formatRuleMbValue(rule.endBp / 1_000_000),
    supportDsCtgLen: String(rule.supportDsCtgLen),
  })));
  return `
    <div class="modal-overlay assembly-support-ds-len-rules-overlay" data-support-ds-ctg-len-rules-overlay="1">
      <article
        class="card modal-dialog assembly-support-ds-len-rules-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(labels.supportDatasetLengthRulesTitle)}"
        data-support-ds-ctg-len-rules-dialog="1"
        data-support-ds-ctg-len-rules-chr-length="${resolvedChrLength}"
        data-support-ds-ctg-len-rules-delete-label="${escapeAttr(labels.supportDatasetLengthRulesDelete)}"
        data-support-ds-ctg-len-rules-baseline="${escapeAttr(baseline)}"
        data-support-ds-ctg-len-rules-unsaved-message="${escapeAttr(labels.supportDatasetLengthRulesUnsavedClose)}"
      >
        <div class="assembly-support-ds-len-rules-head">
          <h4>${escapeHtml(labels.supportDatasetLengthRulesTitle)}</h4>
          <button
            type="button"
            class="button ghost tiny assembly-support-ds-len-rules-close"
            data-support-ds-ctg-len-rules-close="1"
            aria-label="${escapeAttr(labels.supportDatasetLengthRulesClose)}"
            title="${escapeAttr(labels.supportDatasetLengthRulesClose)}"
          >X</button>
        </div>
        <div class="assembly-support-ds-len-rules-body">
          <table class="records-table assembly-support-ds-len-rules-table">
            <thead>
              <tr>
                <th>${escapeHtml(labels.supportDatasetLengthRulesStartMb)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesEndMb)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesLenBp)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesDelete)}</th>
              </tr>
            </thead>
            <tbody data-support-ds-ctg-len-rules-body="1">${rowHtml}</tbody>
          </table>
        </div>
        <div class="assembly-support-ds-len-rules-foot">
          <button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-add="1">${escapeHtml(labels.supportDatasetLengthRulesAdd)}</button>
          <div class="assembly-support-ds-len-rules-actions">
            <button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-reset="1">${escapeHtml(labels.supportDatasetLengthRulesReset)}</button>
            <button type="button" class="button primary tiny" data-support-ds-ctg-len-rules-save="1">${escapeHtml(labels.supportDatasetLengthRulesSave)}</button>
          </div>
        </div>
      </article>
    </div>
  `;
}

function renderSupportDsCtgLenRulesDialogRow(rule, index, labels) {
  return `
    <tr data-support-ds-ctg-len-rules-row="1">
      <td><input type="number" step="0.001" min="0" value="${escapeAttr(formatRuleMbValue(rule.startBp <= 1 ? 0 : rule.startBp / 1_000_000))}" data-support-ds-rule-field="startMb" aria-label="${escapeAttr(labels.supportDatasetLengthRulesStartMb)}"></td>
      <td><input type="number" step="0.001" min="0" value="${escapeAttr(formatRuleMbValue(rule.endBp / 1_000_000))}" data-support-ds-rule-field="endMb" aria-label="${escapeAttr(labels.supportDatasetLengthRulesEndMb)}"></td>
      <td><input type="text" inputmode="numeric" pattern="[0-9]*" value="${escapeAttr(String(rule.supportDsCtgLen))}" data-support-ds-rule-field="supportDsCtgLen" aria-label="${escapeAttr(labels.supportDatasetLengthRulesLenBp)}"></td>
      <td><button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-delete="1" aria-label="${escapeAttr(labels.supportDatasetLengthRulesDelete)} ${index + 1}">${escapeHtml(labels.supportDatasetLengthRulesDelete)}</button></td>
    </tr>
  `;
}

function normalizeSupportRulesForDialog(rules, { chrLength, supportDsCtgLen }) {
  const normalized = getSupportDsCtgLenRulesForChr({ current: rules }, "current", { chrLength });
  if (normalized.length) {
    return normalized;
  }
  return [{
    startBp: 1,
    endBp: normalizePositiveInt(chrLength) ?? 1,
    supportDsCtgLen: normalizeNonNegativeInt(supportDsCtgLen) ?? 0,
  }];
}

function formatRuleMbValue(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) {
    return "0";
  }
  return normalized.toFixed(6).replace(/\.?0+$/, "");
}

function renderSubviewSelectionPanel(assembly, supportContext, trackPrefs, i18n) {
  const subview = getSubviewState(assembly);
  const candidates = getSubviewSelections(subview);
  const trackSelections = getSubviewTrackSelections(subview);
  const candidateBadges = candidates
    .map((selection, index) => {
      const slot = index === 0 ? "A" : "B";
      const resolvedCtg = resolveSubviewSelectionCtg(selection, supportContext);
      const ctgName = resolveTrackCtgDisplayName(resolvedCtg, selection.contigId);
      const visibleCtgName = resolveTrackCtgVisibleName(resolvedCtg, selection.contigId);
      const roleLabel = selection.role === "support"
        ? i18n.trackControls.supportDataset
        : selection.role === "ref"
          ? String(supportContext?.refTrackLabel || "ref")
          : selection.role === "phased"
            ? i18n.trackControls.phasedTrackLabel.replace(
              "{key}",
              String(selection.phasedHaplotypeKey || resolvedCtg?.phasedHaplotypeKey || "").trim() || "phased",
            )
            : i18n.trackControls.primaryTrackLabel;
      const phasedRemoveAttrs = selection.role === "phased"
        ? ` data-subview-remove-phased-track-id="${Number(selection.phasedTrackId || 0)}" data-subview-remove-phased-track-item-id="${Number(selection.phasedTrackItemId || 0)}" data-subview-remove-phased-haplotype-key="${escapeAttr(selection.phasedHaplotypeKey || "")}"`
        : "";
      return `<span class="subview-candidate-badge" title="${escapeAttr(ctgName)}"><strong>${slot}</strong>${escapeHtml(visibleCtgName)} · ${escapeHtml(roleLabel)}<button type="button" class="subview-candidate-remove" data-subview-remove-type="candidate" data-subview-remove-role="${escapeAttr(selection.role)}" data-subview-remove-contig-id="${selection.contigId}"${phasedRemoveAttrs} aria-label="${escapeAttr(i18n.subview.removeCandidateAria)}" title="${escapeAttr(i18n.subview.removeCandidateAria)}">&times;</button></span>`;
    })
    .join("");
  const trackBadges = trackSelections
    .map((selection, index) => {
      const slot = index === 0 ? "T1" : "T2";
      return `<span class="subview-candidate-badge"><strong>${slot}</strong>${escapeHtml(
        resolveSubviewTrackSelectionLabel(selection, supportContext, i18n),
      )}<button type="button" class="subview-candidate-remove" data-subview-remove-type="track" data-subview-remove-role="${escapeAttr(selection.role)}" data-subview-remove-source="${escapeAttr(selection.source || "mother")}" data-subview-remove-dataset-id="${Number(selection.datasetId || 0)}" data-subview-remove-is-mirror="${selection.isMirror ? "1" : "0"}" aria-label="${escapeAttr(i18n.subview.removeTrackCandidateAria)}" title="${escapeAttr(i18n.subview.removeTrackCandidateAria)}">&times;</button></span>`;
    })
    .join("");
  const allBadges = `${candidateBadges}${trackBadges}`;
  const sameContigWarning = resolveSubviewPanelSameContigWarningText(subview, supportContext, i18n);
  return `
    <article class="card subview-selection-panel" data-subview-panel="1">
      <div class="subview-panel-head">
        <h4>${escapeHtml(i18n.subview.panelTitle)}${sameContigWarning ? ` <span class="subview-same-contig-warning">${escapeHtml(sameContigWarning)}</span>` : ""}</h4>
        <div class="subview-panel-guide-inline">
          <p class="muted">${escapeHtml(i18n.subview.guide)}</p>
          ${
            allBadges
              ? `<div class="subview-candidate-row">${allBadges}</div>`
              : ""
          }
        </div>
      </div>
      ${subview.error ? `<p class="error-text">${escapeHtml(subview.error)}</p>` : ""}
      ${renderSubviewAlignmentCard(subview, supportContext, trackPrefs, assembly?.subviewTrackDragOffsets, i18n)}
    </article>
  `;
}

function renderSubviewTrackInlineControls(trackPrefs, i18n) {
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "subview-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs?.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "subview-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs?.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "subview-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs?.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "subview-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs?.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  return `
    <div class="assembly-track-inline-controls subview-track-inline-controls" role="group" aria-label="${escapeAttr(i18n.subview.trackControlsAria)}">
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.minTickUnitKb)}</span>
        ${minTickUnitInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.maxTickCount)}</span>
        ${maxTickCountInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</span>
        ${alignmentInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.mapq)}</span>
        ${mapqInput}
      </label>
    </div>
  `;
}

function renderSubviewTrackOrderToggleButton({ className = "", style = "", swapTrackOrderLabel = "" } = {}) {
  const resolvedClassName = String(className || "").trim();
  const resolvedStyle = String(style || "").trim();
  return `
    <button
      type="button"
      class="button ghost tiny subview-track-order-toggle${resolvedClassName ? ` ${resolvedClassName}` : ""}"
      data-subview-action="swap-track-order"
      aria-label="${escapeAttr(swapTrackOrderLabel)}"
      title="${escapeAttr(swapTrackOrderLabel)}"
      ${resolvedStyle ? `style="${escapeAttr(resolvedStyle)}"` : ""}
    >⇅</button>
  `;
}

function buildSubviewActiveAnchorKeySet(activeAnchors) {
  const keys = new Set();
  (Array.isArray(activeAnchors) ? activeAnchors : []).forEach((anchor) => {
    const hitKey = String(anchor?.hitKey || "").trim();
    const edge = String(anchor?.edge || "").trim();
    if (!hitKey || !edge) {
      return;
    }
    keys.add(`${hitKey}:${edge}`);
    const match = hitKey.match(/^pair:([^:]*):([^:]*):([^:]*):([^:]*)$/);
    if (match) {
      keys.add(`pair:${match[3]}:${match[4]}:${match[1]}:${match[2]}:${edge}`);
    }
  });
  return keys;
}

function buildSubviewFlippedCtgKeySet(flippedCtgs) {
  return new Set(
    (Array.isArray(flippedCtgs) ? flippedCtgs : []).map((entry) =>
      buildSubviewFlippedCtgKey(entry?.slot, entry?.contigId),
    ).filter(Boolean),
  );
}

function buildSubviewLocallyFlippedContig(ctg) {
  const totalLength = Math.max(
    1,
    normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
  );
  const flippedHits = (Array.isArray(ctg?.hits) ? ctg.hits : []).map((hit) => ({
    ...hit,
    ...flipSubviewHitRange(hit, totalLength, "ctgStart", "ctgEnd"),
    ...flipSubviewHitRange(hit, totalLength, "ctg_start", "ctg_end"),
    ...flipSubviewHitRange(hit, totalLength, "queryStart", "queryEnd"),
    ...flipSubviewHitRange(hit, totalLength, "query_start", "query_end"),
    ...flipSubviewHitRange(hit, totalLength, "hitStart", "hitEnd"),
    ...flipSubviewHitRange(hit, totalLength, "hit_start", "hit_end"),
  }));
  const nextOrient = resolveTrackCtgOrient(ctg) === "-" ? "+" : "-";
  return {
    ...ctg,
    subviewLocallyFlipped: true,
    orient: nextOrient,
    refOrient: nextOrient,
    ref_orient: nextOrient,
    hits: flippedHits,
  };
}

function resolveTrackRenderableHits(ctg) {
  // Main-track hits from list_chr_view_ctgs are already projected into ctg display coordinates.
  return Array.isArray(ctg?.hits) ? ctg.hits : [];
}

function resolveTrackHitStrand(hit) {
  const strand = String(hit?.strand || "").trim();
  return strand === "-" || strand === "+" ? strand : "";
}

function resolveTrackHitDisplayReversed(ctg, hit) {
  const hitStrand = resolveTrackHitStrand(hit);
  if (!hitStrand) {
    return false;
  }
  return resolveTrackCtgOrient(ctg) !== hitStrand;
}

function resolveSubviewRenderableContig(ctg, flippedKeySet, slot) {
  const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
  if (!contigId || !(flippedKeySet instanceof Set)) {
    return ctg;
  }
  return flippedKeySet.has(buildSubviewFlippedCtgKey(slot, contigId))
    ? buildSubviewLocallyFlippedContig(ctg)
    : ctg;
}

function resolveSubviewSameContigWarningText(topContigIds, bottomContigIds, i18n) {
  const topIds = new Set(
    (Array.isArray(topContigIds) ? topContigIds : [])
      .map((contigId) => normalizeSupportDatasetId(contigId))
      .filter(Boolean),
  );
  if (!topIds.size) {
    return "";
  }
  for (const contigId of (Array.isArray(bottomContigIds) ? bottomContigIds : [])
    .map((value) => normalizeSupportDatasetId(value))
    .filter(Boolean)) {
    if (topIds.has(contigId)) {
      return i18n?.subview?.sameContigSkippedHint || "";
    }
  }
  return "";
}

function resolveSubviewPanelSameContigWarningText(subview, supportContext, i18n) {
  const summary = subview?.summary || null;
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "").trim() === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    if (!topTrack || !bottomTrack) {
      return "";
    }
    return resolveSubviewSameContigWarningText(
      (resolveSubviewTrackSummaryCtgs(topTrack, supportContext) || []).map((ctg) => ctg?.assemblyCtgId),
      (resolveSubviewTrackSummaryCtgs(bottomTrack, supportContext) || []).map((ctg) => ctg?.assemblyCtgId),
      i18n,
    );
  }
  const topSelection = normalizeSubviewSummarySelection(summary?.top);
  const bottomSelection = normalizeSubviewSummarySelection(summary?.bottom);
  if (!topSelection || !bottomSelection) {
    return "";
  }
  return resolveSubviewSameContigWarningText(
    [topSelection.contigId],
    [bottomSelection.contigId],
    i18n,
  );
}

function buildSubviewActiveAnchorCutsByContig(anchorEdges) {
  const cutsByContig = new Map();
  (Array.isArray(anchorEdges) ? anchorEdges : [])
    .filter((edge) => edge?.active)
    .forEach((edge) => {
      const topContigId = normalizeSupportDatasetId(edge?.topContigId);
      const bottomContigId = normalizeSupportDatasetId(edge?.bottomContigId);
      const topCutBp = normalizePositiveInt(edge?.topCutBp);
      const bottomCutBp = normalizePositiveInt(edge?.bottomCutBp);
      if (topContigId && topCutBp) {
        const current = cutsByContig.get(topContigId) || [];
        cutsByContig.set(topContigId, [...current, topCutBp]);
      }
      if (bottomContigId && bottomCutBp) {
        const current = cutsByContig.get(bottomContigId) || [];
        cutsByContig.set(bottomContigId, [...current, bottomCutBp]);
      }
    });
  return cutsByContig;
}

function resolveSubviewAnchorEndpointX({ barX, barWidth, lengthBp, cutBp }) {
  const safeLengthBp = Math.max(1, normalizePositiveInt(lengthBp) ?? 1);
  const normalizedCutBp = Math.max(1, Math.min(safeLengthBp, Number(cutBp || 1)));
  return Number(barX || 0) + Number(barWidth || 0) * ((normalizedCutBp - 1) / safeLengthBp);
}

function buildSubviewManualAnchorEdges(manualAnchors, { topEndpoint, bottomEndpoint }) {
  if (!topEndpoint?.endpointKey || !bottomEndpoint?.endpointKey) {
    return [];
  }
  return (Array.isArray(manualAnchors) ? manualAnchors : []).flatMap((anchor) => {
    const endpointA = anchor?.endpointA || null;
    const endpointB = anchor?.endpointB || null;
    const topManualEndpoint = endpointA?.endpointKey === topEndpoint.endpointKey
      ? endpointA
      : endpointB?.endpointKey === topEndpoint.endpointKey
        ? endpointB
        : null;
    const bottomManualEndpoint = endpointA?.endpointKey === bottomEndpoint.endpointKey
      ? endpointA
      : endpointB?.endpointKey === bottomEndpoint.endpointKey
        ? endpointB
        : null;
    const topCutBp = normalizePositiveInt(topManualEndpoint?.cutBp);
    const bottomCutBp = normalizePositiveInt(bottomManualEndpoint?.cutBp);
    if (!topManualEndpoint || !bottomManualEndpoint || !topCutBp || !bottomCutBp) {
      return [];
    }
    return [{
      manualAnchorId: String(anchor?.manualAnchorId || "").trim(),
      hitKey: String(anchor?.manualAnchorId || "").trim(),
      edge: "manual",
      active: true,
      topX: topEndpoint.xForCut(topCutBp),
      bottomX: bottomEndpoint.xForCut(bottomCutBp),
      topY: topEndpoint.topY,
      bottomY: bottomEndpoint.bottomY,
      hitTopY: topEndpoint.hitY,
      hitBottomY: bottomEndpoint.hitY,
      topContigId: topEndpoint.contigId,
      bottomContigId: bottomEndpoint.contigId,
      topEndpointKey: topEndpoint.endpointKey,
      bottomEndpointKey: bottomEndpoint.endpointKey,
      topCutBp,
      bottomCutBp,
      topLengthBp: topEndpoint.lengthBp,
      bottomLengthBp: bottomEndpoint.lengthBp,
    }];
  }).filter((edge) => edge.manualAnchorId);
}

function buildSubviewManualAnchorEdgesFromEndpointMaps(manualAnchors, { topEndpointsByKey, bottomEndpointsByKey }) {
  const topMap = topEndpointsByKey instanceof Map ? topEndpointsByKey : new Map();
  const bottomMap = bottomEndpointsByKey instanceof Map ? bottomEndpointsByKey : new Map();
  return (Array.isArray(manualAnchors) ? manualAnchors : []).flatMap((anchor) => {
    const endpointA = anchor?.endpointA || null;
    const endpointB = anchor?.endpointB || null;
    const topManualEndpoint = topMap.has(endpointA?.endpointKey)
      ? endpointA
      : topMap.has(endpointB?.endpointKey)
        ? endpointB
        : null;
    const bottomManualEndpoint = bottomMap.has(endpointA?.endpointKey)
      ? endpointA
      : bottomMap.has(endpointB?.endpointKey)
        ? endpointB
        : null;
    if (!topManualEndpoint || !bottomManualEndpoint) {
      return [];
    }
    const topEndpoint = topMap.get(topManualEndpoint.endpointKey);
    const bottomEndpoint = bottomMap.get(bottomManualEndpoint.endpointKey);
    return buildSubviewManualAnchorEdges([anchor], { topEndpoint, bottomEndpoint });
  });
}

function buildSubviewFragmentRects({
  fragments,
  slot,
  role,
  barX,
  barY,
  barWidth,
  barHeight,
  ctgLengthBp,
  ctgName,
  contigId,
  datasetId,
  isMirror,
  refOrient,
  sourceKind,
  referenceChrId,
  referenceChrName,
  segmentStartBp,
  segmentEndBp,
  ctgTitle,
  phasedTrackId,
  phasedTrackItemId,
  phasedHaplotypeKey,
}) {
  const hoverTitle = String(ctgTitle || "").trim()
    || buildTrackCtgHoverTitle(ctgName, { startBp: 0, lengthBp: ctgLengthBp });
  return fragments.map((fragment) => {
    const safeLengthBp = Math.max(1, Number(ctgLengthBp || 0));
    const startRatio = Math.max(0, (Number(fragment.start || 1) - 1) / safeLengthBp);
    const endRatio = Math.max(startRatio, Number(fragment.end || 0) / safeLengthBp);
    const x = Number(barX || 0) + Number(barWidth || 0) * startRatio;
    const right = Number(barX || 0) + Number(barWidth || 0) * endRatio;
    const width = Math.max(1, right - x);
    return `
              <rect
                class="subview-fragment-hit-zone"
                x="${x.toFixed(2)}"
                y="${Number(barY || 0).toFixed(2)}"
                width="${width.toFixed(2)}"
                height="${Number(barHeight || 0).toFixed(2)}"
                fill="transparent"
                data-subview-fragment-key="${escapeAttr(fragment.fragmentKey)}"
                data-subview-fragment-slot="${escapeAttr(slot)}"
                data-subview-fragment-role="${escapeAttr(role)}"
                data-subview-fragment-contig-id="${contigId}"
                data-subview-fragment-start="${fragment.start}"
                data-subview-fragment-end="${fragment.end}"
                data-subview-fragment-ctg-name="${escapeAttr(ctgName)}"
                data-subview-fragment-dataset-id="${Number(datasetId || 0)}"
                data-subview-fragment-is-mirror="${isMirror ? "1" : "0"}"
                data-subview-fragment-ref-orient="${escapeAttr(refOrient || "+")}"
                data-subview-fragment-source-kind="${escapeAttr(sourceKind || "assembly_ctg")}"
                data-subview-fragment-reference-chr-id="${Number(referenceChrId || 0)}"
                data-subview-fragment-reference-chr-name="${escapeAttr(referenceChrName || "")}"
                data-subview-fragment-segment-start-bp="${Number(segmentStartBp || 0)}"
                data-subview-fragment-segment-end-bp="${Number(segmentEndBp || 0)}"
                data-subview-fragment-phased-track-id="${Number(phasedTrackId || 0)}"
                data-subview-fragment-phased-track-item-id="${Number(phasedTrackItemId || 0)}"
                data-subview-fragment-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey || "")}"
              >
                <title>${escapeHtml(hoverTitle)}</title>
              </rect>
              <rect
                class="subview-fragment-outline"
                x="${x.toFixed(2)}"
                y="${Number(barY || 0).toFixed(2)}"
                width="${width.toFixed(2)}"
                height="${Number(barHeight || 0).toFixed(2)}"
                rx="4"
                ry="4"
                fill="none"
                stroke="transparent"
                stroke-width="2.5"
                pointer-events="none"
              />`;
  }).join("");
}

function renderSubviewAnchorLines(anchorEdges, { topY, bottomY, hitTopY, hitBottomY }) {
  return (Array.isArray(anchorEdges) ? anchorEdges : [])
    .map(
      (edge) => {
        const anchorKind = edge.manualAnchorId ? "manual" : "evidence";
        const anchorEdge = edge.manualAnchorId ? "manual" : String(edge.edge || "");
        return `<line
                  class="subview-anchor-line${edge.active ? " is-active" : ""}"
                  x1="${Number(edge.topX || 0).toFixed(2)}"
                  y1="${Number(hitTopY ?? edge.hitTopY ?? edge.topY ?? topY ?? 0).toFixed(2)}"
                  x2="${Number(edge.bottomX || 0).toFixed(2)}"
                  y2="${Number(hitBottomY ?? edge.hitBottomY ?? edge.bottomY ?? bottomY ?? 0).toFixed(2)}"
                  stroke="${edge.active ? "red" : "transparent"}"
                  stroke-width="3"
                  pointer-events="none"
                />
                <line
                  class="subview-anchor-hit-zone${edge.active ? " is-active" : ""}"
                  x1="${Number(edge.topX || 0).toFixed(2)}"
                  y1="${Number(hitTopY ?? edge.hitTopY ?? edge.topY ?? topY ?? 0).toFixed(2)}"
                  x2="${Number(edge.bottomX || 0).toFixed(2)}"
                  y2="${Number(hitBottomY ?? edge.hitBottomY ?? edge.bottomY ?? bottomY ?? 0).toFixed(2)}"
                  stroke="transparent"
                  stroke-width="3"
                  pointer-events="stroke"
                  data-subview-anchor-kind="${anchorKind}"
                  data-subview-anchor-hit-key="${escapeAttr(edge.hitKey)}"
                  data-subview-anchor-edge="${escapeAttr(anchorEdge)}"
                  data-subview-anchor-active="${edge.active ? "1" : "0"}"
                  data-subview-manual-anchor-id="${escapeAttr(edge.manualAnchorId || "")}"
                  data-subview-anchor-top-endpoint-key="${escapeAttr(edge.topEndpointKey || "")}"
                  data-subview-anchor-bottom-endpoint-key="${escapeAttr(edge.bottomEndpointKey || "")}"
                  data-subview-anchor-top-contig-id="${Number(edge.topContigId || 0)}"
                  data-subview-anchor-bottom-contig-id="${Number(edge.bottomContigId || 0)}"
                  data-subview-anchor-top-cut-bp="${Number(edge.topCutBp || 0)}"
                  data-subview-anchor-bottom-cut-bp="${Number(edge.bottomCutBp || 0)}"
                  data-subview-anchor-top-length-bp="${Number(edge.topLengthBp || 0)}"
                  data-subview-anchor-bottom-length-bp="${Number(edge.bottomLengthBp || 0)}"
                />`;
      },
    )
    .join("");
}

function parseTrackBandPoints(pointsText) {
  return String(pointsText || "")
    .trim()
    .split(/\s+/)
    .map((point) => {
      const [rawX = "", rawY = ""] = String(point || "").split(",");
      const x = Number(rawX);
      const y = Number(rawY);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        return null;
      }
      return [roundTrackMetric(x), roundTrackMetric(y)];
    })
    .filter(Boolean);
}

function stringifyTrackBandCanvasScene(scene) {
  return JSON.stringify(scene).replaceAll("</", "<\\/");
}

function renderTrackBandCanvasLayer({
  sceneKind,
  width,
  height,
  viewBoxMinX = 0,
  clipRect = null,
  bands = [],
}) {
  const scene = {
    version: 1,
    kind: String(sceneKind || "").trim() || "track",
    width: roundTrackMetric(width),
    height: roundTrackMetric(height),
    viewBoxMinX: roundTrackMetric(viewBoxMinX),
    clipRect: clipRect
      ? {
          x: roundTrackMetric(clipRect.x),
          y: roundTrackMetric(clipRect.y),
          width: roundTrackMetric(clipRect.width),
          height: roundTrackMetric(clipRect.height),
        }
      : null,
    bands: (Array.isArray(bands) ? bands : [])
      .map((band) => {
        const points = parseTrackBandPoints(band?.points);
        if (points.length < 4) {
          return null;
        }
        return {
          hitKey: String(band?.hitKey || ""),
          tone: String(band?.tone || "").trim() || "primary",
          points,
        };
      })
      .filter(Boolean),
  };
  return `
    <div
      class="track-band-canvas-layer"
      data-track-band-canvas-layer="1"
      data-track-band-canvas-scene-kind="${escapeAttr(scene.kind)}"
      style="width:${scene.width.toFixed(2)}px;height:${scene.height.toFixed(2)}px"
      aria-hidden="true"
    >
      <canvas class="track-band-canvas" data-track-band-canvas="1"></canvas>
      <script type="application/json" data-track-band-canvas-scene>${escapeHtml(stringifyTrackBandCanvasScene(scene))}</script>
    </div>
  `;
}

function resolveSubviewSegmentCtgBpByRef(segment, refBp) {
  const refStart = Number(segment?.refStart || 0);
  const refEnd = Number(segment?.refEnd || 0);
  const ctgStart = Number(segment?.ctgStart || 0);
  const ctgEnd = Number(segment?.ctgEnd || 0);
  if (!Number.isFinite(refStart) || !Number.isFinite(refEnd) || !Number.isFinite(ctgStart) || !Number.isFinite(ctgEnd)) {
    return null;
  }
  const safeRefSpan = Math.max(1, refEnd - refStart);
  const clampedRefBp = Math.max(refStart, Math.min(refEnd, Number(refBp || 0)));
  const ratio = (clampedRefBp - refStart) / safeRefSpan;
  const ctgValue = ctgStart + ratio * (ctgEnd - ctgStart);
  const normalized = Math.round(ctgValue);
  return normalized > 0 ? normalized : null;
}

function renderSubviewAlignmentCard(subview, supportContext, trackPrefs, subviewTrackDragOffsets = [], i18n) {
  const summary = subview?.summary || null;
  if (!summary) {
    return "";
  }
  if (String(summary.mode || "") === "track-pair") {
    return renderSubviewTrackPairAlignmentCard(
      subview,
      supportContext,
      trackPrefs,
      subviewTrackDragOffsets,
      i18n,
    );
  }
  const topSelection = normalizeSubviewSummarySelection(summary.top);
  const bottomSelection = normalizeSubviewSummarySelection(summary.bottom);
  if (!topSelection || !bottomSelection) {
    return "";
  }
  const flippedKeySet = buildSubviewFlippedCtgKeySet(subview?.flippedCtgs);
  const topCtg = resolveSubviewRenderableContig(
    resolveSubviewSelectionCtg(topSelection, supportContext),
    flippedKeySet,
    "top",
  );
  const bottomCtg = resolveSubviewRenderableContig(
    resolveSubviewSelectionCtg(bottomSelection, supportContext),
    flippedKeySet,
    "bottom",
  );
  if (!topCtg || !bottomCtg) {
    return `<article class="assembly-track-panel subview-alignment-card"><p class="muted">${escapeHtml(i18n.subview.invalidCandidate)}</p></article>`;
  }
  const resolvedTrackPrefs = resolveTrackPrefs(trackPrefs || {});
  const blockLength = Math.max(1, normalizePositiveInt(resolvedTrackPrefs.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(resolvedTrackPrefs.mapq) ?? 0);
  const activeAnchorHitKeys = new Set(
    (Array.isArray(subview?.activeAnchors) ? subview.activeAnchors : [])
      .map((entry) => String(entry?.hitKey || "").trim())
      .filter(Boolean),
  );
  const topHits = collectSubviewRenderableHits(topCtg, {
    blockLength,
    minMapq,
    preserveHitKeys: activeAnchorHitKeys,
  });
  const bottomHits = collectSubviewRenderableHits(bottomCtg, {
    blockLength,
    minMapq,
    preserveHitKeys: activeAnchorHitKeys,
  });
  const usesRefProjection =
    (topSelection.role === "ref" && bottomSelection.role !== "ref")
    || (bottomSelection.role === "ref" && topSelection.role !== "ref");
  const pairwiseEvidenceState = resolveSubviewPairwiseEvidence(subview, summary);
  const isPairwiseEvidenceLoading =
    pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loading";
  const pairwiseHits = pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loaded"
    ? buildSubviewPairwiseRenderableHits({
      evidence: pairwiseEvidenceState.evidence,
      topSelection,
      bottomSelection,
      topCtg,
      bottomCtg,
      blockLength,
      minMapq,
    })
    : null;
  const resolvedTopHits = pairwiseEvidenceState.enabled
    ? pairwiseHits?.topHits || []
    : usesRefProjection
      ? topSelection.role === "ref"
        ? buildProjectedRefSubviewHits(topCtg, bottomHits)
        : topHits
      : topHits;
  const resolvedBottomHits = pairwiseEvidenceState.enabled
    ? pairwiseHits?.bottomHits || []
    : usesRefProjection
      ? bottomSelection.role === "ref"
        ? buildProjectedRefSubviewHits(bottomCtg, topHits)
        : bottomHits
      : bottomHits;
  const topCtgName = resolveTrackCtgDisplayName(topCtg, topSelection.contigId);
  const bottomCtgName = resolveTrackCtgDisplayName(bottomCtg, bottomSelection.contigId);
  const topVisibleCtgName = resolveTrackCtgVisibleName(topCtg, topSelection.contigId);
  const bottomVisibleCtgName = resolveTrackCtgVisibleName(bottomCtg, bottomSelection.contigId);
  const subviewDomainSpanBp = Math.max(
    1,
    resolveSubviewCtgLengthBp(topCtg, resolvedTopHits),
    resolveSubviewCtgLengthBp(bottomCtg, resolvedBottomHits),
  );
  const subviewRenderInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: subviewDomainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: getMeasuredTrackViewportPx("subview"),
  });
  const refPairCacheKey = [
    buildSubviewRefCacheSelectionKey(summary),
    normalizeSupportDatasetId(resolveSubviewRefDatasetId(subview, supportContext)) || 0,
    normalizePositiveInt(resolvedTrackPrefs.alignmentLength) || 0,
    normalizeNonNegativeInt(resolvedTrackPrefs.mapq) || 0,
  ].join("|");
  const svgModel = buildSubviewAlignmentSvgModel({
    topCtg,
    bottomCtg,
    topHits: resolvedTopHits,
    bottomHits: resolvedBottomHits,
    pairCacheKey: refPairCacheKey,
    pairingMode: (usesRefProjection || pairwiseEvidenceState.enabled)
      ? "projection-key"
      : "reference-overlap",
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    topManualOffsetPx: resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      "top",
      topSelection.contigId,
      {
        domainSpanBp: subviewDomainSpanBp,
        innerWidth: subviewRenderInnerWidth,
      },
    ),
    bottomManualOffsetPx: resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      "bottom",
      bottomSelection.contigId,
      {
        domainSpanBp: subviewDomainSpanBp,
        innerWidth: subviewRenderInnerWidth,
      },
    ),
  });
  const topRowClass = resolveTrackToneClass(topSelection.role);
  const bottomRowClass = resolveTrackToneClass(bottomSelection.role);
  const connectorClass = topSelection.role === "support" ? " is-companion" : "";
  const bandTone = topSelection.role === "support" ? "companion" : "primary";
  const topLabelText = resolveTrackCtgLabelText(topCtg, topSelection.contigId);
  const bottomLabelText = resolveTrackCtgLabelText(bottomCtg, bottomSelection.contigId);
  const topLabelPlacement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: topLabelText,
    role: topSelection.role,
    rect: {
      x: svgModel.topBarX,
      width: svgModel.topBarWidth,
      centerX: svgModel.topBarX + (svgModel.topBarWidth / 2),
    },
    barY: svgModel.topBarY,
    barHeight: svgModel.barHeight,
    inlineTextOffsetY: svgModel.textOffsetY,
    hideOutsideLabel: true,
    minVisibleX: 0,
    maxVisibleX: svgModel.renderInnerWidth,
  });
  const bottomLabelPlacement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: bottomLabelText,
    role: bottomSelection.role,
    rect: {
      x: svgModel.bottomBarX,
      width: svgModel.bottomBarWidth,
      centerX: svgModel.bottomBarX + (svgModel.bottomBarWidth / 2),
    },
    barY: svgModel.bottomBarY,
    barHeight: svgModel.barHeight,
    inlineTextOffsetY: svgModel.textOffsetY,
    hideOutsideLabel: true,
    minVisibleX: 0,
    maxVisibleX: svgModel.renderInnerWidth,
  });
  const trackOrderButtonTopPx = ((Number(svgModel.topLabelTop) + Number(svgModel.bottomLabelTop)) / 2).toFixed(2);
  const activeAnchorKeys = buildSubviewActiveAnchorKeySet(subview?.activeAnchors);
  const topEndpointKey = buildSubviewAnchorEndpointKey({
    ...topSelection,
    role: topSelection.role,
    contigId: topSelection.contigId,
    datasetId: topCtg?.datasetId,
    isMirror: String(topCtg?.subviewSource || "") === "mirror",
    sourceKind: topCtg?.sourceKind,
  });
  const bottomEndpointKey = buildSubviewAnchorEndpointKey({
    ...bottomSelection,
    role: bottomSelection.role,
    contigId: bottomSelection.contigId,
    datasetId: bottomCtg?.datasetId,
    isMirror: String(bottomCtg?.subviewSource || "") === "mirror",
    sourceKind: bottomCtg?.sourceKind,
  });
  const evidenceAnchorEdges = (Array.isArray(svgModel.anchorEdges) ? svgModel.anchorEdges : []).map((edge) => ({
    ...edge,
    topEndpointKey,
    bottomEndpointKey,
    topLengthBp: svgModel.topLengthBp,
    bottomLengthBp: svgModel.bottomLengthBp,
    active: activeAnchorKeys.has(`${String(edge.hitKey || "").trim()}:${String(edge.edge || "").trim()}`),
  }));
  const manualAnchorEdges = buildSubviewManualAnchorEdges(subview?.manualAnchors, {
    topEndpoint: {
      endpointKey: topEndpointKey,
      contigId: topSelection.contigId,
      lengthBp: svgModel.topLengthBp,
      topY: svgModel.topBarY,
      bottomY: svgModel.topBarY + svgModel.barHeight,
      hitY: svgModel.topBarY + svgModel.barHeight,
      xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
        barX: svgModel.topBarX,
        barWidth: svgModel.topBarWidth,
        lengthBp: svgModel.topLengthBp,
        cutBp,
      }),
    },
    bottomEndpoint: {
      endpointKey: bottomEndpointKey,
      contigId: bottomSelection.contigId,
      lengthBp: svgModel.bottomLengthBp,
      topY: svgModel.bottomBarY,
      bottomY: svgModel.bottomBarY + svgModel.barHeight,
      hitY: svgModel.bottomBarY,
      xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
        barX: svgModel.bottomBarX,
        barWidth: svgModel.bottomBarWidth,
        lengthBp: svgModel.bottomLengthBp,
        cutBp,
      }),
    },
  });
  const anchorEdges = [...evidenceAnchorEdges, ...manualAnchorEdges];
  const activeAnchorCutsByContig = buildSubviewActiveAnchorCutsByContig(anchorEdges);
  const topFragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: topSelection.contigId,
      role: topSelection.role,
      lengthBp: svgModel.topLengthBp,
    },
    anchorCuts: activeAnchorCutsByContig.get(topSelection.contigId) || [],
  });
  const bottomFragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: bottomSelection.contigId,
      role: bottomSelection.role,
      lengthBp: svgModel.bottomLengthBp,
    },
    anchorCuts: activeAnchorCutsByContig.get(bottomSelection.contigId) || [],
  });
  const loadingOverlay = isPairwiseEvidenceLoading
    ? `<div class="subview-pairwise-loading-overlay" data-subview-pairwise-loading="1">
        <div class="subview-pairwise-loading-panel">
          <button type="button" class="subview-pairwise-loading-close" data-subview-pairwise-cancel="1" aria-label="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}" title="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}">&times;</button>
          <div class="subview-pairwise-loading-spinner" aria-hidden="true"></div>
          <p class="subview-pairwise-loading-text">${escapeHtml(i18n.subview.loadingPairwiseEvidence)}</p>
        </div>
      </div>`
    : "";
  const topCtgTitle = buildTrackCtgHoverTitle(topCtgName, {
    startBp: 0,
    lengthBp: svgModel.topLengthBp,
  });
  const bottomCtgTitle = buildTrackCtgHoverTitle(bottomCtgName, {
    startBp: 0,
    lengthBp: svgModel.bottomLengthBp,
  });
  return `
    <article class="assembly-track-panel subview-alignment-card">
      <div class="assembly-track-panel-head">
        <strong>${escapeHtml(`${topVisibleCtgName} vs ${bottomVisibleCtgName}`)}</strong>
        ${renderSubviewTrackInlineControls(resolvedTrackPrefs, i18n)}
      </div>
      <div class="assembly-track-layout subview-track-layout">
        <div class="assembly-track-label-column subview-track-label-column" style="width:${svgModel.labelColumnWidth}px;height:${svgModel.contentBottom}px">
          <div class="assembly-track-label-row${topRowClass}" style="top:${svgModel.topLabelTop}px" title="${escapeAttr(topCtgName)}">${escapeHtml(topVisibleCtgName)}</div>
          ${renderSubviewTrackOrderToggleButton({
            className: "is-in-label-column",
            style: `top:${trackOrderButtonTopPx}px`,
            swapTrackOrderLabel: i18n.subview.swapTrackOrderAria,
          })}
          <div class="assembly-track-label-row${bottomRowClass}" style="top:${svgModel.bottomLabelTop}px" title="${escapeAttr(bottomCtgName)}">${escapeHtml(bottomVisibleCtgName)}</div>
        </div>
        <div
          class="assembly-track-scroll subview-track-scroll"
          data-track-role="subview"
          data-subview-domain-span-bp="${svgModel.domainSpanBp}"
          data-subview-inner-width="${svgModel.renderInnerWidth}"
        >
          ${renderTrackBandCanvasLayer({
            sceneKind: "subview-ctg",
            width: svgModel.renderInnerWidth,
            height: svgModel.contentBottom,
            bands: svgModel.collinearityBands.map((band) => ({
              ...band,
              tone: bandTone,
            })),
          })}
          <div
            class="subview-band-tooltip is-hidden"
            data-subview-band-tooltip-delay-ms="${SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS}"
            aria-hidden="true"
          ></div>
          <svg class="assembly-track-svg subview-track-svg" width="${svgModel.renderInnerWidth}" height="${svgModel.contentBottom}" viewBox="0 0 ${svgModel.renderInnerWidth} ${svgModel.contentBottom}" preserveAspectRatio="xMinYMin meet">
            <line class="track-ruler-line" x1="0" y1="${svgModel.rulerTop}" x2="${svgModel.renderInnerWidth}" y2="${svgModel.rulerTop}" />
            ${svgModel.tickItems
              .map(
                (tick) => `<line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${svgModel.tickY1.toFixed(2)}" x2="${tick.x.toFixed(2)}" y2="${svgModel.tickY2.toFixed(2)}" />
                ${
                  tick.showLabel
                    ? `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${svgModel.tickLabelY.toFixed(2)}" text-anchor="${tick.labelAnchor}">${escapeHtml(tick.labelText)}</text>`
                    : ""
                }`,
              )
              .join("")}
            ${svgModel.collinearityBands
              .map(
                (band) => {
                  const hitKey = String(band.hitKey || "");
                  return `<polygon class="track-collinearity-band${connectorClass}" points="${band.points}" pointer-events="visibleFill" data-track-band-proxy="1" data-subview-top-contig-id="${topSelection.contigId}" data-subview-bottom-contig-id="${bottomSelection.contigId}" data-subview-band-tooltip="${escapeAttr(band.tooltipText)}" data-subview-hit-key="${escapeAttr(hitKey)}" data-subview-hit-left-active="${activeAnchorKeys.has(`${hitKey}:left`) ? "1" : "0"}" data-subview-hit-right-active="${activeAnchorKeys.has(`${hitKey}:right`) ? "1" : "0"}" />`;
                },
              )
              .join("")}
            <g
              class="subview-track-ctg-group${topRowClass}"
              data-subview-track-pair-role="${escapeAttr(topSelection.role)}"
              data-subview-track-pair-contig-id="${topSelection.contigId}"
              data-subview-track-pair-dataset-id="${Number(topCtg?.datasetId || 0)}"
              data-subview-track-pair-is-mirror="${String(topCtg?.subviewSource || "") === "mirror" ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${Number(topCtg?.phasedTrackId || 0)}"
              data-subview-track-pair-phased-track-item-id="${Number(topCtg?.phasedTrackItemId || 0)}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(topCtg?.phasedHaplotypeKey || "")}"
              data-subview-track-slot="top"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(topCtg))}"
              data-subview-track-role="${escapeAttr(topSelection.role)}"
              data-subview-contig-id="${topSelection.contigId}"
              data-subview-rect-x="${svgModel.topBarX.toFixed(2)}"
              data-subview-rect-y="${svgModel.topBarY.toFixed(2)}"
              data-subview-rect-width="${svgModel.topBarWidth.toFixed(2)}"
              data-subview-rect-height="${svgModel.barHeight}"
            >
              <title>${escapeHtml(topCtgTitle)}</title>
              <rect class="track-ctg subview-track-ctg${topRowClass}" x="${svgModel.topBarX.toFixed(2)}" y="${svgModel.topBarY.toFixed(2)}" width="${svgModel.topBarWidth.toFixed(2)}" height="${svgModel.barHeight}" rx="4" ry="4" pointer-events="all">
                <title>${escapeHtml(topCtgTitle)}</title>
              </rect>
              ${topFragments.length
                ? buildSubviewFragmentRects({
                    fragments: topFragments,
                    slot: "top",
                    role: topSelection.role,
                    barX: svgModel.topBarX,
                    barY: svgModel.topBarY,
                    barWidth: svgModel.topBarWidth,
                    barHeight: svgModel.barHeight,
                    ctgLengthBp: svgModel.topLengthBp,
                    ctgName: topCtgName,
                    contigId: topSelection.contigId,
                    datasetId: topCtg?.datasetId,
                    isMirror: String(topCtg?.subviewSource || "") === "mirror",
                    refOrient: resolveTrackCtgOrient(topCtg),
                    sourceKind: topCtg?.sourceKind,
                    referenceChrId: topCtg?.referenceChrId,
                    referenceChrName: topCtg?.referenceChrName,
                    segmentStartBp: topCtg?.segmentStartBp,
                    segmentEndBp: topCtg?.segmentEndBp,
                    ctgTitle: topCtgTitle,
                    phasedTrackId: topCtg?.phasedTrackId,
                    phasedTrackItemId: topCtg?.phasedTrackItemId,
                    phasedHaplotypeKey: topCtg?.phasedHaplotypeKey,
                  })
                : ""}
            </g>
            <g
              class="subview-track-ctg-group${bottomRowClass}"
              data-subview-track-pair-role="${escapeAttr(bottomSelection.role)}"
              data-subview-track-pair-contig-id="${bottomSelection.contigId}"
              data-subview-track-pair-dataset-id="${Number(bottomCtg?.datasetId || 0)}"
              data-subview-track-pair-is-mirror="${String(bottomCtg?.subviewSource || "") === "mirror" ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${Number(bottomCtg?.phasedTrackId || 0)}"
              data-subview-track-pair-phased-track-item-id="${Number(bottomCtg?.phasedTrackItemId || 0)}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(bottomCtg?.phasedHaplotypeKey || "")}"
              data-subview-track-slot="bottom"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(bottomCtg))}"
              data-subview-track-role="${escapeAttr(bottomSelection.role)}"
              data-subview-contig-id="${bottomSelection.contigId}"
              data-subview-rect-x="${svgModel.bottomBarX.toFixed(2)}"
              data-subview-rect-y="${svgModel.bottomBarY.toFixed(2)}"
              data-subview-rect-width="${svgModel.bottomBarWidth.toFixed(2)}"
              data-subview-rect-height="${svgModel.barHeight}"
            >
              <title>${escapeHtml(bottomCtgTitle)}</title>
              <rect class="track-ctg subview-track-ctg${bottomRowClass}" x="${svgModel.bottomBarX.toFixed(2)}" y="${svgModel.bottomBarY.toFixed(2)}" width="${svgModel.bottomBarWidth.toFixed(2)}" height="${svgModel.barHeight}" rx="4" ry="4" pointer-events="all">
                <title>${escapeHtml(bottomCtgTitle)}</title>
              </rect>
              ${bottomFragments.length
                ? buildSubviewFragmentRects({
                    fragments: bottomFragments,
                    slot: "bottom",
                    role: bottomSelection.role,
                    barX: svgModel.bottomBarX,
                    barY: svgModel.bottomBarY,
                    barWidth: svgModel.bottomBarWidth,
                    barHeight: svgModel.barHeight,
                    ctgLengthBp: svgModel.bottomLengthBp,
                    ctgName: bottomCtgName,
                    contigId: bottomSelection.contigId,
                    datasetId: bottomCtg?.datasetId,
                    isMirror: String(bottomCtg?.subviewSource || "") === "mirror",
                    refOrient: resolveTrackCtgOrient(bottomCtg),
                    sourceKind: bottomCtg?.sourceKind,
                    referenceChrId: bottomCtg?.referenceChrId,
                    referenceChrName: bottomCtg?.referenceChrName,
                    segmentStartBp: bottomCtg?.segmentStartBp,
                    segmentEndBp: bottomCtg?.segmentEndBp,
                    ctgTitle: bottomCtgTitle,
                    phasedTrackId: bottomCtg?.phasedTrackId,
                    phasedTrackItemId: bottomCtg?.phasedTrackItemId,
                    phasedHaplotypeKey: bottomCtg?.phasedHaplotypeKey,
                  })
                : ""}
            </g>
            ${renderSubviewAnchorLines(anchorEdges, {
              topY: svgModel.topBarY,
              bottomY: svgModel.bottomBarY + svgModel.barHeight,
            })}
            ${topLabelPlacement?.hidden
              ? ""
              : `<text class="track-ctg-label${topRowClass}${topLabelPlacement.classSuffix}" x="${topLabelPlacement.x.toFixed(2)}" y="${topLabelPlacement.y.toFixed(2)}"${topLabelPlacement.transformAttr} text-anchor="${topLabelPlacement.textAnchor}" data-subview-label-slot="top" data-subview-label-role="${escapeAttr(topSelection.role)}" data-subview-label-contig-id="${topSelection.contigId}">${escapeHtml(topLabelText)}</text>`}
            ${bottomLabelPlacement?.hidden
              ? ""
              : `<text class="track-ctg-label${bottomRowClass}${bottomLabelPlacement.classSuffix}" x="${bottomLabelPlacement.x.toFixed(2)}" y="${bottomLabelPlacement.y.toFixed(2)}"${bottomLabelPlacement.transformAttr} text-anchor="${bottomLabelPlacement.textAnchor}" data-subview-label-slot="bottom" data-subview-label-role="${escapeAttr(bottomSelection.role)}" data-subview-label-contig-id="${bottomSelection.contigId}">${escapeHtml(bottomLabelText)}</text>`}
          </svg>
        </div>
      </div>
      ${loadingOverlay}
    </article>
  `;
}

function renderSubviewTrackPairAlignmentCard(
  subview,
  supportContext,
  trackPrefs,
  subviewTrackDragOffsets = [],
  i18n,
) {
  const summary = subview?.summary || null;
  const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
  const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
  if (!topTrack || !bottomTrack) {
    return "";
  }
  const rawTopCtgs = resolveSubviewTrackSummaryCtgs(topTrack, supportContext) || [];
  const rawBottomCtgs = resolveSubviewTrackSummaryCtgs(bottomTrack, supportContext) || [];
  const pairwiseEvidenceState = resolveSubviewPairwiseEvidence(subview, summary, {
    topAssemblyCtgIds: rawTopCtgs.map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId)).filter(Boolean),
    bottomAssemblyCtgIds: rawBottomCtgs.map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId)).filter(Boolean),
  });
  const isPairwiseEvidenceLoading =
    pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loading";
  const flippedKeySet = buildSubviewFlippedCtgKeySet(subview?.flippedCtgs);
  const hiddenKeySet = new Set(
    normalizeSubviewTrackPairHiddenCtgs(subview?.trackPairHiddenCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const topCtgs = rawTopCtgs
    .filter((ctg) =>
      !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(topTrack.role, ctg?.assemblyCtgId)),
    )
    .map((ctg) => resolveSubviewRenderableContig(ctg, flippedKeySet, "top"));
  const bottomCtgs = rawBottomCtgs
    .filter((ctg) =>
      !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(bottomTrack.role, ctg?.assemblyCtgId)),
    )
    .map((ctg) => resolveSubviewRenderableContig(ctg, flippedKeySet, "bottom"));
  const resolvedTrackPrefs = resolveTrackPrefs(trackPrefs || {});
  const pairModel = buildDualTrackModel({
    primaryCtgs: bottomCtgs,
    companionCtgs: topCtgs,
    selectedPrimaryCtgId: null,
    selectedCompanionCtgId: null,
    prefs: resolvedTrackPrefs,
    preserveInputOrder: true,
  });
  const domainStart = Number(pairModel.windowStart || 0);
  const domainEnd = Math.max(domainStart, Number(pairModel.windowEnd || 0));
  const domainSpanBp = Math.max(1, domainEnd - domainStart + 1);
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_EMPTY_TEXT_OFFSET_Y = 12 * TRACK_HEIGHT_SCALE;
  const TRACK_MIN_ADJACENT_GAP_PX = 20;
  const LABEL_COLUMN_WIDTH_PX = 136;
  const baseInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: Math.max(1, Number(pairModel.innerWidth || getMeasuredTrackViewportPx("subview"))),
  });
  const topLayout = {
    id: "top",
    role: topTrack.role,
    source: topTrack.source,
    datasetId: topTrack.datasetId,
    isMirror: topTrack.isMirror === true,
    phasedTrackId: topTrack.phasedTrackId,
    haplotypeKey: topTrack.haplotypeKey,
    trackModel: pairModel.companion || buildEmptyTrackModelLike(),
    className: resolveTrackToneClass(topTrack.role).trim(),
    emptyMessage: i18n.trackControls.topTrackEmpty,
  };
  const bottomLayout = {
    id: "bottom",
    role: bottomTrack.role,
    source: bottomTrack.source,
    datasetId: bottomTrack.datasetId,
    isMirror: bottomTrack.isMirror === true,
    phasedTrackId: bottomTrack.phasedTrackId,
    haplotypeKey: bottomTrack.haplotypeKey,
    trackModel: pairModel.primary || buildEmptyTrackModelLike(),
    className: resolveTrackToneClass(bottomTrack.role).trim(),
    emptyMessage: i18n.trackControls.bottomTrackEmpty,
  };
  const rowLayouts = [topLayout, bottomLayout].map((layout) => ({
    ...layout,
    laneCount: Math.max(1, Number(layout.trackModel?.laneCount || 1)),
  }));

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  rowLayouts.forEach((layout, index) => {
    const rowHeight = layout.laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
    layout.rowTop = cursorY;
    layout.laneTop = cursorY + TRACK_ROW_PADDING_TOP;
    layout.labelTop = layout.laneTop - TRACK_LABEL_OFFSET_Y;
    layout.rowBottom = cursorY + rowHeight;
    cursorY += rowHeight + (index === rowLayouts.length - 1 ? 0 : TRACK_ROW_GAP);
  });
  const [resolvedTopLayout, resolvedBottomLayout] = rowLayouts;
  const contentBottom = cursorY;

  const tickBp = resolveTickBpFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    fallbackTickBp: resolvedTrackPrefs.tickBp,
  });
  const tickItems = buildTrackTickItems({
    windowStart: domainStart,
    windowEnd: domainEnd,
    tickBp,
    innerWidth: baseInnerWidth,
    domainSpanBp,
  }).map((tick, index, all) => {
    const isFirst = index === 0;
    const isLast = index === all.length - 1;
    const isSingle = isFirst && isLast;
    const labelAnchor = isSingle ? "middle" : isFirst ? "start" : isLast ? "end" : "middle";
    const labelX = isSingle
      ? tick.x
      : isFirst
        ? Math.min(baseInnerWidth, tick.x + TRACK_EDGE_LABEL_PADDING)
        : isLast
          ? Math.max(0, tick.x - TRACK_EDGE_LABEL_PADDING)
          : tick.x;
    return {
      ...tick,
      labelAnchor,
      labelX,
      labelText: isLast ? formatBp(tick.bp) : formatRulerTickLabel(tick.bp),
    };
  });
  if (tickItems.length >= 2) {
    const endTick = tickItems[tickItems.length - 1];
    const previousTick = tickItems[tickItems.length - 2];
    if (isTrackTickLabelOverlap(previousTick, endTick)) {
      previousTick.showLabel = false;
    }
  }
  const buildRectsForLayout = (layout) =>
    buildTrackRectsWithMinGap(layout.trackModel?.ctgs || [], {
      windowStart: domainStart,
      domainSpanBp,
      innerWidth: baseInnerWidth,
      minGapPx: TRACK_MIN_ADJACENT_GAP_PX,
    });
  const baseRectsByLayoutId = new Map(
    rowLayouts.map((layout) => [layout.id, buildRectsForLayout(layout)]),
  );
  const resolveLayoutSlot = (layoutId) => (layoutId === "top" ? "top" : "bottom");
  const resolveTrackPairDisplayRect = (layout, ctg, index) => {
    const baseRect = (baseRectsByLayoutId.get(layout.id) || [])[index] || buildTrackRect(ctg, {
      windowStart: domainStart,
      domainSpanBp,
      innerWidth: baseInnerWidth,
    });
    const offsetPx = resolveSubviewTrackDragOffsetPx(
      subviewTrackDragOffsets,
      resolveLayoutSlot(layout.id),
      ctg?.assemblyCtgId,
      {
        domainSpanBp,
        innerWidth: baseInnerWidth,
      },
    );
    if (!Number.isFinite(offsetPx) || Math.abs(offsetPx) < 0.01) {
      return baseRect;
    }
    return {
      ...baseRect,
      x: roundTrackMetric(baseRect.x + offsetPx),
      centerX: roundTrackMetric(baseRect.centerX + offsetPx),
    };
  };
  const maxRectRight = Math.max(
    baseInnerWidth,
    ...rowLayouts
      .flatMap((layout) => (layout.trackModel?.ctgs || []).map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackPairDisplayRect(layout, ctg, index);
        return Number(rect.x) + Number(rect.width);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const minRectLeft = Math.min(
    0,
    ...rowLayouts
      .flatMap((layout) => (layout.trackModel?.ctgs || []).map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => Number(resolveTrackPairDisplayRect(layout, ctg, index).x))
      .filter((value) => Number.isFinite(value)),
  );
  const labelVisibleMinX = Math.floor(Math.min(0, minRectLeft));
  const labelVisibleMaxX = Math.ceil(Math.max(baseInnerWidth, maxRectRight));
  const maxLabelRight = rowLayouts.reduce((layoutMax, layout) => {
    return (layout.trackModel?.ctgs || []).reduce((ctgMax, ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMax;
      }
      const labelRight = resolveTrackCtgLabelRightBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.max(ctgMax, labelRight);
    }, layoutMax);
  }, baseInnerWidth);
  const minLabelLeft = rowLayouts.reduce((layoutMin, layout) => {
    return (layout.trackModel?.ctgs || []).reduce((ctgMin, ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMin;
      }
      const labelLeft = resolveTrackCtgLabelLeftBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.min(ctgMin, labelLeft);
    }, layoutMin);
  }, 0);
  const renderViewBoxMinX = Math.floor(Math.min(0, minRectLeft, minLabelLeft));
  const renderMaxX = Math.ceil(Math.max(baseInnerWidth, maxRectRight, maxLabelRight));
  const renderInnerWidth = Math.max(baseInnerWidth, renderMaxX - renderViewBoxMinX);
  const blockLength = Math.max(1, normalizePositiveInt(resolvedTrackPrefs.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(resolvedTrackPrefs.mapq) ?? 0);
  const refPairCacheKey = [
    buildSubviewRefCacheSelectionKey(summary),
    normalizeSupportDatasetId(resolveSubviewRefDatasetId(subview, supportContext)) || 0,
    normalizePositiveInt(resolvedTrackPrefs.alignmentLength) || 0,
    normalizeNonNegativeInt(resolvedTrackPrefs.mapq) || 0,
  ].join("|");
  const buildSegmentsForLayout = (layout) =>
    (layout.trackModel?.ctgs || []).flatMap((ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
      const barBottom = barTop + TRACK_BAR_HEIGHT;
      const endpointKey = buildSubviewAnchorEndpointKey({
        role: layout.role,
        contigId: ctg?.assemblyCtgId,
        datasetId: layout.datasetId,
        source: layout.source,
        isMirror: layout.isMirror === true,
        phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
        phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
        phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
      });
      return collectSubviewRenderableHits(ctg, { blockLength, minMapq }).map((hit) => {
        const hitRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: hit.ctgStart,
          ctgEndOffset: hit.ctgEnd,
        });
        return {
          ctgId: normalizeSupportDatasetId(ctg?.assemblyCtgId),
          ctgName: String(ctg?.name || ""),
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
          ),
          hitKey: String(hit?.hitKey || ""),
          pairKey: String(hit?.pairKey || hit?.hitKey || ""),
          ctgStart: hit.ctgStart,
          ctgEnd: hit.ctgEnd,
          refStart: hit.refStart,
          refEnd: hit.refEnd,
          refMid: hit.refMid,
          role: layout.role,
          datasetId: normalizeSupportDatasetId(layout.datasetId),
          isMirror: layout.isMirror === true,
          endpointKey,
          x: hitRect.x,
          width: hitRect.width,
          midX: hitRect.centerX,
          barTop,
          barBottom,
        };
      });
    });
  const buildLayoutEntryByCtgId = (layout) =>
    new Map(
      (layout.trackModel?.ctgs || [])
        .map((ctg, index) => {
          const ctgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (!ctgId) {
            return null;
          }
          const rect = resolveTrackPairDisplayRect(layout, ctg, index);
          const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
          const barBottom = barTop + TRACK_BAR_HEIGHT;
          const endpointKey = buildSubviewAnchorEndpointKey({
            role: layout.role,
            contigId: ctg?.assemblyCtgId,
            datasetId: layout.datasetId,
            source: layout.source,
            isMirror: layout.isMirror === true,
            phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
            phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
            phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
          });
          return [ctgId, { ctg, rect, barTop, barBottom, endpointKey }];
        })
        .filter(Boolean),
    );
  const buildPairwiseSegmentsForTrackPair = (evidence) => {
    const topEntriesByCtgId = buildLayoutEntryByCtgId(resolvedTopLayout);
    const bottomEntriesByCtgId = buildLayoutEntryByCtgId(resolvedBottomLayout);
    const topSegments = [];
    const bottomSegments = [];
    const hits = Array.isArray(evidence?.hits) ? evidence.hits : [];
    const renderedPairs = [];
    const pushRenderablePair = (pairRecord) => {
      const {
        topEntry,
        bottomEntry,
        topRange,
        bottomRange,
        hitKey,
        pairKey,
        reversed,
        ordinal,
      } = pairRecord;
      const refStart = ordinal + 1;
      const refEnd = ordinal + 2;
      const topRect = buildTrackHitRectWithinCtgDisplay({
        ctgRect: topEntry.rect,
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(topEntry.ctg?.lengthBp ?? topEntry.ctg?.totalLength) ?? 1,
        ),
        ctgStartOffset: Math.min(topRange.start, topRange.end),
        ctgEndOffset: Math.max(topRange.start, topRange.end),
      });
      const bottomRect = buildTrackHitRectWithinCtgDisplay({
        ctgRect: bottomEntry.rect,
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(bottomEntry.ctg?.lengthBp ?? bottomEntry.ctg?.totalLength) ?? 1,
        ),
        ctgStartOffset: Math.min(bottomRange.start, bottomRange.end),
        ctgEndOffset: Math.max(bottomRange.start, bottomRange.end),
      });
      topSegments.push({
        ctgId: normalizeSupportDatasetId(topEntry.ctg?.assemblyCtgId),
        ctgName: String(topEntry.ctg?.name || ""),
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(topEntry.ctg?.lengthBp ?? topEntry.ctg?.totalLength) ?? 1,
        ),
        hitKey,
        pairKey,
        reversed,
        ctgStart: Math.min(topRange.start, topRange.end),
        ctgEnd: Math.max(topRange.start, topRange.end),
        refStart,
        refEnd,
        refMid: (refStart + refEnd) / 2,
        role: resolvedTopLayout.role,
        datasetId: normalizeSupportDatasetId(resolvedTopLayout.datasetId),
        isMirror: resolvedTopLayout.isMirror === true,
        endpointKey: topEntry.endpointKey,
        x: topRect.x,
        width: topRect.width,
        midX: topRect.centerX,
        barTop: topEntry.barTop,
        barBottom: topEntry.barBottom,
      });
      bottomSegments.push({
        ctgId: normalizeSupportDatasetId(bottomEntry.ctg?.assemblyCtgId),
        ctgName: String(bottomEntry.ctg?.name || ""),
        ctgLengthBp: Math.max(
          1,
          normalizePositiveInt(bottomEntry.ctg?.lengthBp ?? bottomEntry.ctg?.totalLength) ?? 1,
        ),
        hitKey,
        pairKey,
        reversed,
        ctgStart: Math.min(bottomRange.start, bottomRange.end),
        ctgEnd: Math.max(bottomRange.start, bottomRange.end),
        refStart,
        refEnd,
        refMid: (refStart + refEnd) / 2,
        role: resolvedBottomLayout.role,
        datasetId: normalizeSupportDatasetId(resolvedBottomLayout.datasetId),
        isMirror: resolvedBottomLayout.isMirror === true,
        endpointKey: bottomEntry.endpointKey,
        x: bottomRect.x,
        width: bottomRect.width,
        midX: bottomRect.centerX,
        barTop: bottomEntry.barTop,
        barBottom: bottomEntry.barBottom,
      });
    };
    hits.forEach((hit, index) => {
      const alignLength = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
      const mapq = Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
      if (alignLength < blockLength || mapq < minMapq) {
        return;
      }
      const queryAssemblyCtgId = normalizeSupportDatasetId(
        hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id,
      );
      const subjectAssemblyCtgId = normalizeSupportDatasetId(
        hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id,
      );
      const queryStart = Number(hit?.queryStart ?? hit?.query_start);
      const queryEnd = Number(hit?.queryEnd ?? hit?.query_end);
      const subjectStart = Number(hit?.subjectStart ?? hit?.subject_start);
      const subjectEnd = Number(hit?.subjectEnd ?? hit?.subject_end);
      if (
        !queryAssemblyCtgId
        || !subjectAssemblyCtgId
        || !Number.isFinite(queryStart)
        || !Number.isFinite(queryEnd)
        || !Number.isFinite(subjectStart)
        || !Number.isFinite(subjectEnd)
      ) {
        return;
      }
      let topEntry = topEntriesByCtgId.get(queryAssemblyCtgId) || null;
      let bottomEntry = bottomEntriesByCtgId.get(subjectAssemblyCtgId) || null;
      let topStart = queryStart;
      let topEnd = queryEnd;
      let bottomStart = subjectStart;
      let bottomEnd = subjectEnd;
      if (!topEntry || !bottomEntry) {
        topEntry = topEntriesByCtgId.get(subjectAssemblyCtgId) || null;
        bottomEntry = bottomEntriesByCtgId.get(queryAssemblyCtgId) || null;
        topStart = subjectStart;
        topEnd = subjectEnd;
        bottomStart = queryStart;
        bottomEnd = queryEnd;
      }
      if (!topEntry || !bottomEntry) {
        return;
      }
      const topMirrored = isSubviewPairwiseRangeMirrored(topEntry.ctg);
      const bottomMirrored = isSubviewPairwiseRangeMirrored(bottomEntry.ctg);
      const topRange = resolveSubviewPairwiseDisplayRange(topStart, topEnd, topEntry.ctg, topMirrored);
      const bottomRange = resolveSubviewPairwiseDisplayRange(
        bottomStart,
        bottomEnd,
        bottomEntry.ctg,
        bottomMirrored,
      );
      if (!topRange || !bottomRange) {
        return;
      }
      const hitKey = String(hit?.hitKey || `pairwise-track-${index + 1}`);
      const pairKey = String(hit?.pairKey || hitKey);
      const reversed = resolvePairwiseHitDisplayReversedWithLocalFlip(hit, topMirrored, bottomMirrored);
      const sameContigHit = normalizeSupportDatasetId(topEntry.ctg?.assemblyCtgId)
        === normalizeSupportDatasetId(bottomEntry.ctg?.assemblyCtgId);
      if (sameContigHit) {
        return;
      }
      renderedPairs.push({
        topEntry,
        bottomEntry,
        topRange,
        bottomRange,
        hitKey,
        pairKey,
        reversed,
        index,
      });
    });
    renderedPairs.forEach((pairRecord) => {
      pushRenderablePair({
        ...pairRecord,
        ordinal: pairRecord.index,
      });
    });
    return { topSegments, bottomSegments };
  };
  const buildProjectedRefSegmentsForLayout = (layout, sourceSegments) => {
    const refEntries = (layout.trackModel?.ctgs || []).map((ctg, index) => {
      const rect = resolveTrackPairDisplayRect(layout, ctg, index);
      const barTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
      const barBottom = barTop + TRACK_BAR_HEIGHT;
      const bounds = resolveRefTrackSegmentBounds(ctg);
      const endpointKey = buildSubviewAnchorEndpointKey({
        role: layout.role,
        contigId: ctg?.assemblyCtgId,
        datasetId: layout.datasetId,
        source: layout.source,
        isMirror: layout.isMirror === true,
        phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
        phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
        phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
      });
      return {
        ctg,
        rect,
        barTop,
        barBottom,
        endpointKey,
        segmentStartBp: bounds.segmentStartBp,
        segmentEndBp: bounds.segmentEndBp,
      };
    });
    return (Array.isArray(sourceSegments) ? sourceSegments : [])
      .map((segment) => {
        const refEntry = refEntries.find(
          (entry) =>
            Number(segment?.refStart || 0) >= entry.segmentStartBp
            && Number(segment?.refEnd || 0) <= entry.segmentEndBp,
        );
        if (!refEntry) {
          return null;
        }
        const projectedRange = projectRefIntervalToLocalRange(
          refEntry.ctg,
          segment?.refStart,
          segment?.refEnd,
        );
        if (!projectedRange) {
          return null;
        }
        const hitRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: refEntry.rect,
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(refEntry.ctg?.lengthBp ?? refEntry.ctg?.totalLength) ?? 1,
          ),
          ctgStartOffset: projectedRange.ctgStart,
          ctgEndOffset: projectedRange.ctgEnd,
        });
        return {
          ctgId: normalizeSupportDatasetId(refEntry.ctg?.assemblyCtgId),
          ctgName: String(refEntry.ctg?.name || ""),
          ctgLengthBp: Math.max(
            1,
            normalizePositiveInt(refEntry.ctg?.lengthBp ?? refEntry.ctg?.totalLength) ?? 1,
          ),
          hitKey: String(segment?.hitKey || ""),
          pairKey: String(segment?.pairKey || segment?.hitKey || ""),
          ctgStart: projectedRange.ctgStart,
          ctgEnd: projectedRange.ctgEnd,
          refStart: segment.refStart,
          refEnd: segment.refEnd,
          refMid: segment.refMid,
          role: layout.role,
          datasetId: normalizeSupportDatasetId(segment?.datasetId ?? null),
          isMirror: false,
          endpointKey: refEntry.endpointKey,
          x: hitRect.x,
          width: hitRect.width,
          midX: hitRect.centerX,
          barTop: refEntry.barTop,
          barBottom: refEntry.barBottom,
        };
      })
      .filter(Boolean);
  };
  const usesRefProjection =
    (resolvedTopLayout.role === "ref" && resolvedBottomLayout.role !== "ref")
    || (resolvedBottomLayout.role === "ref" && resolvedTopLayout.role !== "ref");
  const pairwiseTrackSegments = pairwiseEvidenceState.enabled
    && String(pairwiseEvidenceState.evidence?.status || "") === "loaded"
    ? buildPairwiseSegmentsForTrackPair(pairwiseEvidenceState.evidence)
    : null;
  const sourceTopSegments = pairwiseEvidenceState.enabled
    ? (pairwiseTrackSegments?.topSegments || [])
    : resolvedTopLayout.role === "ref"
      ? []
      : buildSegmentsForLayout(resolvedTopLayout);
  const sourceBottomSegments = pairwiseEvidenceState.enabled
    ? (pairwiseTrackSegments?.bottomSegments || [])
    : resolvedBottomLayout.role === "ref"
      ? []
      : buildSegmentsForLayout(resolvedBottomLayout);
  const topSegments = usesRefProjection
    ? resolvedTopLayout.role === "ref"
      ? buildProjectedRefSegmentsForLayout(resolvedTopLayout, sourceBottomSegments)
      : sourceTopSegments
    : sourceTopSegments;
  const bottomSegments = usesRefProjection
    ? resolvedBottomLayout.role === "ref"
      ? buildProjectedRefSegmentsForLayout(resolvedBottomLayout, sourceTopSegments)
      : sourceBottomSegments
    : sourceBottomSegments;
  const buildOverlapRectWithinSegment = (segment, overlapStart, overlapEnd) => {
    const segmentRefStart = Number(segment?.refStart || 0);
    const segmentRefEnd = Number(segment?.refEnd || 0);
    const segmentX = Number(segment?.x || 0);
    const segmentWidth = Math.max(1, Number(segment?.width || 1));
    const segmentRight = segmentX + segmentWidth;
    const refSpan = Math.max(1, segmentRefEnd - segmentRefStart);
    const clampedStart = Math.max(segmentRefStart, Math.min(segmentRefEnd, Number(overlapStart || 0)));
    const clampedEnd = Math.max(segmentRefStart, Math.min(segmentRefEnd, Number(overlapEnd || 0)));
    const startRatio = Math.max(0, Math.min(1, (clampedStart - segmentRefStart) / refSpan));
    const endRatio = Math.max(startRatio, Math.min(1, (clampedEnd - segmentRefStart) / refSpan));
    const projectedLeft = segmentX + startRatio * segmentWidth;
    const projectedRight = segmentX + endRatio * segmentWidth;
    const x = Math.min(segmentRight, Math.max(segmentX, projectedLeft));
    const right = Math.min(segmentRight, Math.max(x, projectedRight));
    const width = Math.max(0, right - x);
    return {
      x,
      width,
      midX: x + width / 2,
    };
  };
  const activeAnchorKeys = buildSubviewActiveAnchorKeySet(subview?.activeAnchors);
  const pairedTrackSegments = pairRefSubviewSegmentsWithCache({
    cacheKey: refPairCacheKey,
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
    pairingMode: (usesRefProjection || pairwiseTrackSegments) ? "projection-key" : "reference-overlap",
  });
  const collinearityBands = pairedTrackSegments
    .map(({ topSegment, bottomSegment }, index) => {
      const overlapStart = Math.max(Number(topSegment.refStart || 0), Number(bottomSegment.refStart || 0));
      const overlapEnd = Math.min(Number(topSegment.refEnd || 0), Number(bottomSegment.refEnd || 0));
      if (!Number.isFinite(overlapStart) || !Number.isFinite(overlapEnd) || overlapEnd <= overlapStart) {
        return null;
      }
      const topOverlapRect = buildOverlapRectWithinSegment(topSegment, overlapStart, overlapEnd);
      const bottomOverlapRect = buildOverlapRectWithinSegment(bottomSegment, overlapStart, overlapEnd);
      const hitKey = buildSubviewTrackPairHitKey(topSegment, bottomSegment);
      const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
      const topLeftX = topOverlapRect.x;
      const topRightX = topOverlapRect.x + topOverlapRect.width;
      const bottomLeftX = bottomOverlapRect.x;
      const bottomRightX = bottomOverlapRect.x + bottomOverlapRect.width;
      return {
        hitKey,
        topContigId: topSegment.ctgId,
        bottomContigId: bottomSegment.ctgId,
        leftActive: activeAnchorKeys.has(`${hitKey}:left`),
        rightActive: activeAnchorKeys.has(`${hitKey}:right`),
        tooltipText: buildSubviewBandTooltipText({
          topName: topSegment.ctgName,
          bottomName: bottomSegment.ctgName,
          topSegment,
          bottomSegment,
        }),
        points: (reversed
          ? [
              `${topLeftX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${topRightX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${bottomLeftX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
              `${bottomRightX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
            ]
          : [
              `${topLeftX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${topRightX.toFixed(2)},${Number(topSegment.barBottom ?? (resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT)).toFixed(2)}`,
              `${bottomRightX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
              `${bottomLeftX.toFixed(2)},${Number(bottomSegment.barTop ?? resolvedBottomLayout.laneTop).toFixed(2)}`,
            ]).join(" "),
      };
    })
    .filter(Boolean);
  const anchorEdges = pairedTrackSegments
    .flatMap(({ topSegment, bottomSegment }, index) => {
      const overlapStart = Math.max(Number(topSegment.refStart || 0), Number(bottomSegment.refStart || 0));
      const overlapEnd = Math.min(Number(topSegment.refEnd || 0), Number(bottomSegment.refEnd || 0));
      if (!Number.isFinite(overlapStart) || !Number.isFinite(overlapEnd) || overlapEnd <= overlapStart) {
        return [];
      }
      const topOverlapRect = buildOverlapRectWithinSegment(topSegment, overlapStart, overlapEnd);
      const bottomOverlapRect = buildOverlapRectWithinSegment(bottomSegment, overlapStart, overlapEnd);
      const hitKey = buildSubviewTrackPairHitKey(topSegment, bottomSegment);
      const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
      const topLeftX = topOverlapRect.x;
      const topRightX = topOverlapRect.x + topOverlapRect.width;
      const bottomLeftX = bottomOverlapRect.x;
      const bottomRightX = bottomOverlapRect.x + bottomOverlapRect.width;
      const topLeftCutBp = resolveSubviewSegmentCtgBpByRef(topSegment, overlapStart);
      const topRightCutBp = resolveSubviewSegmentCtgBpByRef(topSegment, overlapEnd);
      const bottomLeftCutBp = resolveSubviewSegmentCtgBpByRef(bottomSegment, overlapStart);
      const bottomRightCutBp = resolveSubviewSegmentCtgBpByRef(bottomSegment, overlapEnd);
      return [
        {
          hitKey,
          edge: "left",
          topX: topLeftX,
          bottomX: reversed ? bottomRightX : bottomLeftX,
          topY: topSegment.barTop,
          bottomY: bottomSegment.barBottom,
          hitTopY: topSegment.barBottom,
          hitBottomY: bottomSegment.barTop,
          topContigId: topSegment.ctgId,
          bottomContigId: bottomSegment.ctgId,
          topEndpointKey: topSegment.endpointKey,
          bottomEndpointKey: bottomSegment.endpointKey,
          topCutBp: topLeftCutBp,
          bottomCutBp: reversed ? bottomRightCutBp : bottomLeftCutBp,
          topLengthBp: topSegment.ctgLengthBp,
          bottomLengthBp: bottomSegment.ctgLengthBp,
        },
        {
          hitKey,
          edge: "right",
          topX: topRightX,
          bottomX: reversed ? bottomLeftX : bottomRightX,
          topY: topSegment.barTop,
          bottomY: bottomSegment.barBottom,
          hitTopY: topSegment.barBottom,
          hitBottomY: bottomSegment.barTop,
          topContigId: topSegment.ctgId,
          bottomContigId: bottomSegment.ctgId,
          topEndpointKey: topSegment.endpointKey,
          bottomEndpointKey: bottomSegment.endpointKey,
          topCutBp: topRightCutBp,
          bottomCutBp: reversed ? bottomLeftCutBp : bottomRightCutBp,
          topLengthBp: topSegment.ctgLengthBp,
          bottomLengthBp: bottomSegment.ctgLengthBp,
        },
      ];
    })
    .map((edge) => ({
      ...edge,
      active: activeAnchorKeys.has(`${String(edge.hitKey || "").trim()}:${String(edge.edge || "").trim()}`),
    }));
  const buildManualEndpointMapForLayout = (layout) =>
    new Map(
      (layout.trackModel?.ctgs || [])
        .map((ctg, index) => {
          const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (!contigId) {
            return null;
          }
          const rect = resolveTrackPairDisplayRect(layout, ctg, index);
          const lengthBp = Math.max(1, normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1);
          const laneTop = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
          const endpointKey = buildSubviewAnchorEndpointKey({
            role: layout.role,
            contigId,
            datasetId: layout.datasetId,
            source: layout.source,
            isMirror: layout.isMirror === true,
            phasedTrackId: ctg?.phasedTrackId ?? layout.phasedTrackId,
            phasedTrackItemId: ctg?.phasedTrackItemId ?? ctg?.itemId,
            phasedHaplotypeKey: ctg?.phasedHaplotypeKey ?? layout.haplotypeKey,
          });
          if (!endpointKey) {
            return null;
          }
          return [endpointKey, {
            endpointKey,
            contigId,
            lengthBp,
            topY: laneTop,
            bottomY: laneTop + TRACK_BAR_HEIGHT,
            hitY: layout.id === "top" ? laneTop + TRACK_BAR_HEIGHT : laneTop,
            xForCut: (cutBp) => resolveSubviewAnchorEndpointX({
              barX: rect.x,
              barWidth: rect.width,
              lengthBp,
              cutBp,
            }),
          }];
        })
        .filter(Boolean),
    );
  const manualAnchorEdges = buildSubviewManualAnchorEdgesFromEndpointMaps(subview?.manualAnchors, {
    topEndpointsByKey: buildManualEndpointMapForLayout(resolvedTopLayout),
    bottomEndpointsByKey: buildManualEndpointMapForLayout(resolvedBottomLayout),
  });
  const allAnchorEdges = [...anchorEdges, ...manualAnchorEdges];
  const activeAnchorCutsByContig = buildSubviewActiveAnchorCutsByContig(allAnchorEdges);
  const selectedTrackPairKeySet = new Set(
    normalizeSubviewTrackPairSelectionCtgs(subview?.trackPairSelectedCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const topTrackLabel = resolveSubviewTrackSelectionLabel(topTrack, supportContext, i18n);
  const bottomTrackLabel = resolveSubviewTrackSelectionLabel(bottomTrack, supportContext, i18n);
  const topRoleClass = resolveTrackToneClass(topTrack.role);
  const bottomRoleClass = resolveTrackToneClass(bottomTrack.role);
  const trackOrderButtonTopPx = (
    (Number(resolvedTopLayout.labelTop) + Number(resolvedBottomLayout.labelTop)) / 2
  ).toFixed(2);
  const bandClipId = "subview-track-band-clip";
  const bandClipInsetPx = 0.75;
  const bandClipTop = roundTrackMetric(
    resolvedTopLayout.laneTop + TRACK_BAR_HEIGHT + bandClipInsetPx,
  );
  const bandClipBottom = roundTrackMetric(resolvedBottomLayout.laneTop - bandClipInsetPx);
  const bandClipHeight = Math.max(0, roundTrackMetric(bandClipBottom - bandClipTop));
  const loadingOverlay = isPairwiseEvidenceLoading
    ? `<div class="subview-pairwise-loading-overlay" data-subview-pairwise-loading="1">
        <div class="subview-pairwise-loading-panel">
          <button type="button" class="subview-pairwise-loading-close" data-subview-pairwise-cancel="1" aria-label="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}" title="${escapeAttr(i18n.subview.cancelPairwiseLoadingAria)}">&times;</button>
          <div class="subview-pairwise-loading-spinner" aria-hidden="true"></div>
          <p class="subview-pairwise-loading-text">${escapeHtml(i18n.subview.loadingPairwiseEvidence)}</p>
        </div>
      </div>`
    : "";
  const renderTrackCtgs = (layout, roleClass) => {
    const ctgs = Array.isArray(layout.trackModel?.ctgs) ? layout.trackModel.ctgs : [];
    if (!ctgs.length) {
      return `<text class="track-row-empty-label" x="12" y="${(layout.laneTop + TRACK_EMPTY_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(layout.emptyMessage)}</text>`;
    }
    const renderEntries = ctgs
      .map((ctg, index) => {
        const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
        if (!contigId) {
          return null;
        }
        const rect = resolveTrackPairDisplayRect(layout, ctg, index);
        const y = layout.laneTop + Math.max(0, Number(ctg?.laneIndex || 0)) * TRACK_LANE_HEIGHT;
        const displayName = resolveTrackCtgDisplayName(ctg, contigId);
        const labelText = resolveTrackCtgLabelText(ctg, contigId);
        const placement = resolveBoundedTrackCtgLabelPlacement({
          ctgName: labelText,
          role: layout.role,
          rect,
          barY: y,
          barHeight: TRACK_BAR_HEIGHT,
          inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
          hideOutsideLabel: true,
          minVisibleX: labelVisibleMinX,
          maxVisibleX: labelVisibleMaxX,
        });
        const selectedClass = selectedTrackPairKeySet.has(
          buildSubviewTrackPairHiddenCtgKey(layout.role, contigId),
        )
          ? " is-multi-selected"
          : "";
        const ctgLengthBp = Math.max(
          1,
          normalizePositiveInt(ctg?.lengthBp ?? ctg?.totalLength) ?? 1,
        );
        const ctgTitle = buildTrackCtgHoverTitle(displayName, {
          startBp: ctg?.startBp,
          lengthBp: ctg?.lengthBp ?? ctg?.totalLength,
        });
        const fragments = deriveSubviewContigFragments({
          contig: {
            assemblyCtgId: contigId,
            role: layout.role,
            lengthBp: ctgLengthBp,
          },
          anchorCuts: activeAnchorCutsByContig.get(contigId) || [],
        });
        const trackPairDatasetId = layout.role === "support"
          ? (normalizeSupportDatasetId(layout.datasetId)
            || normalizeSupportDatasetId(supportContext?.supportDatasetId)
            || 0)
          : 0;
        const phasedTrackId = normalizeSupportDatasetId(ctg?.phasedTrackId);
        const phasedTrackItemId = normalizeSupportDatasetId(ctg?.phasedTrackItemId);
        const phasedHaplotypeKey = String(ctg?.phasedHaplotypeKey || "").trim();
        const labelMarkup = placement.hidden
          ? ""
          : `<text class="track-ctg-label${roleClass}${placement.classSuffix}" x="${placement.x.toFixed(2)}" y="${placement.y.toFixed(2)}"${placement.transformAttr} text-anchor="${placement.textAnchor}" data-subview-label-slot="${escapeAttr(resolveLayoutSlot(layout.id))}" data-subview-label-role="${escapeAttr(layout.role)}" data-subview-label-contig-id="${contigId}">${escapeHtml(labelText)}</text>`;
        return {
          ctg,
          rect,
          markup: `<g
              class="track-ctg-group${roleClass}${selectedClass}"
              data-subview-track-pair-role="${escapeAttr(layout.role)}"
              data-subview-track-pair-contig-id="${contigId}"
              data-subview-track-pair-dataset-id="${trackPairDatasetId}"
              data-subview-track-pair-is-mirror="${layout.isMirror ? "1" : "0"}"
              data-subview-track-pair-phased-track-id="${phasedTrackId || 0}"
              data-subview-track-pair-phased-track-item-id="${phasedTrackItemId || 0}"
              data-subview-track-pair-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"
              data-subview-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(ctg))}"
              data-subview-track-slot="${escapeAttr(resolveLayoutSlot(layout.id))}"
              data-subview-track-role="${escapeAttr(layout.role)}"
              data-subview-contig-id="${contigId}"
              data-subview-rect-x="${rect.x.toFixed(2)}"
              data-subview-rect-y="${y.toFixed(2)}"
              data-subview-rect-width="${rect.width.toFixed(2)}"
              data-subview-rect-height="${TRACK_BAR_HEIGHT}"
            >
              <title>${escapeHtml(ctgTitle)}</title>
              <rect
                class="track-ctg subview-track-ctg${roleClass}${selectedClass}"
                x="${rect.x.toFixed(2)}"
                y="${y.toFixed(2)}"
                width="${rect.width.toFixed(2)}"
                height="${TRACK_BAR_HEIGHT}"
                rx="4"
                ry="4"
                pointer-events="all"
              >
                <title>${escapeHtml(ctgTitle)}</title>
              </rect>
              ${fragments.length
                ? buildSubviewFragmentRects({
                    fragments,
                    slot: resolveLayoutSlot(layout.id),
                    role: layout.role,
                    barX: rect.x,
                    barY: y,
                    barWidth: rect.width,
                    barHeight: TRACK_BAR_HEIGHT,
                    ctgLengthBp,
                    ctgName: displayName,
                    contigId,
                    datasetId: trackPairDatasetId,
                    isMirror: layout.isMirror,
                    refOrient: resolveTrackCtgOrient(ctg),
                    sourceKind: ctg?.sourceKind,
                    referenceChrId: ctg?.referenceChrId,
                    referenceChrName: ctg?.referenceChrName,
                    segmentStartBp: ctg?.segmentStartBp,
                    segmentEndBp: ctg?.segmentEndBp,
                    ctgTitle,
                    phasedTrackId,
                    phasedTrackItemId,
                    phasedHaplotypeKey,
                  })
                : ""}
              ${labelMarkup}
            </g>`,
        };
      })
      .filter((entry) => entry && entry.markup);
    return sortTrackEntriesForRender(renderEntries)
      .map((entry) => entry.markup)
      .join("");
  };
  return `
    <article class="assembly-track-panel subview-alignment-card">
      <div class="assembly-track-panel-head">
        <strong>${escapeHtml(`${topTrackLabel} vs ${bottomTrackLabel}`)}</strong>
        ${renderSubviewTrackInlineControls(resolvedTrackPrefs, i18n)}
      </div>
      <div class="assembly-track-layout subview-track-layout">
        <div class="assembly-track-label-column subview-track-label-column" style="width:${LABEL_COLUMN_WIDTH_PX}px;height:${contentBottom}px">
          <div class="assembly-track-label-row${topRoleClass}" style="top:${resolvedTopLayout.labelTop}px">${escapeHtml(topTrackLabel)}</div>
          ${renderSubviewTrackOrderToggleButton({
            className: "is-in-label-column",
            style: `top:${trackOrderButtonTopPx}px`,
            swapTrackOrderLabel: i18n.subview.swapTrackOrderAria,
          })}
          <div class="assembly-track-label-row${bottomRoleClass}" style="top:${resolvedBottomLayout.labelTop}px">${escapeHtml(bottomTrackLabel)}</div>
        </div>
        <div class="assembly-track-scroll subview-track-scroll" data-track-role="subview" data-subview-domain-span-bp="${domainSpanBp}" data-subview-inner-width="${baseInnerWidth}" data-subview-viewbox-min-x="${renderViewBoxMinX}">
          ${renderTrackBandCanvasLayer({
            sceneKind: "subview-track-pair",
            width: renderInnerWidth,
            height: contentBottom,
            viewBoxMinX: renderViewBoxMinX,
            clipRect: {
              x: renderViewBoxMinX,
              y: bandClipTop,
              width: renderInnerWidth,
              height: bandClipHeight,
            },
            bands: collinearityBands.map((band) => ({
              ...band,
              tone: topTrack.role === "support" ? "companion" : "primary",
            })),
          })}
          <div class="subview-band-tooltip is-hidden" data-subview-band-tooltip-delay-ms="${SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS}" aria-hidden="true"></div>
          <svg class="assembly-track-svg subview-track-svg" width="${renderInnerWidth}" height="${contentBottom}" viewBox="${renderViewBoxMinX} 0 ${renderInnerWidth} ${contentBottom}" preserveAspectRatio="xMinYMin meet">
            <defs>
              <clipPath id="${bandClipId}" clipPathUnits="userSpaceOnUse">
                <rect x="${renderViewBoxMinX.toFixed(2)}" y="${bandClipTop.toFixed(2)}" width="${renderInnerWidth.toFixed(2)}" height="${bandClipHeight.toFixed(2)}" />
              </clipPath>
            </defs>
            <line class="track-ruler-line" x1="0" y1="${rulerTop}" x2="${baseInnerWidth}" y2="${rulerTop}" />
            ${tickItems
              .map(
                (tick) => `<line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${(rulerTop + TRACK_LABEL_OFFSET_Y).toFixed(2)}" x2="${tick.x.toFixed(2)}" y2="${(contentBottom - 3 * TRACK_HEIGHT_SCALE).toFixed(2)}" />
                ${
                  tick.showLabel === false
                    ? ""
                    : `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${(rulerTop - TRACK_LABEL_OFFSET_Y).toFixed(2)}" text-anchor="${tick.labelAnchor}">${escapeHtml(tick.labelText)}</text>`
                }`,
              )
              .join("")}
            <g clip-path="url(#${bandClipId})">
              ${collinearityBands
                .map(
                  (band) =>
                  `<polygon class="track-collinearity-band${topRoleClass}" points="${band.points}" pointer-events="visibleFill" data-track-band-proxy="1" data-subview-top-contig-id="${band.topContigId}" data-subview-bottom-contig-id="${band.bottomContigId}" data-subview-band-tooltip="${escapeAttr(band.tooltipText)}" data-subview-hit-key="${escapeAttr(band.hitKey)}" data-subview-hit-left-active="${band.leftActive ? "1" : "0"}" data-subview-hit-right-active="${band.rightActive ? "1" : "0"}" />`,
                )
                .join("")}
            </g>
            ${renderTrackCtgs(resolvedTopLayout, topRoleClass)}
            ${renderTrackCtgs(resolvedBottomLayout, bottomRoleClass)}
            ${renderSubviewAnchorLines(allAnchorEdges, {
              topY: resolvedTopLayout.laneTop,
              bottomY: resolvedBottomLayout.laneTop + TRACK_BAR_HEIGHT,
            })}
          </svg>
        </div>
      </div>
      ${loadingOverlay}
    </article>
  `;
}

function collectSubviewRenderableHits(ctg, { blockLength, minMapq, preserveHitKeys = null }) {
  const hits = Array.isArray(ctg?.hits) ? ctg.hits : [];
  const preserved = preserveHitKeys instanceof Set ? preserveHitKeys : new Set(preserveHitKeys || []);
  return hits
    .map((hit, index) => {
      const hitBlockLength = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
      const hitMapq = resolveHitMapq(hit);
      const refStart = Number(hit?.refStart ?? hit?.ref_start);
      const refEnd = Number(hit?.refEnd ?? hit?.ref_end);
      const ctgStart = Number(
        hit?.ctgStart
        ?? hit?.ctg_start
        ?? hit?.queryStart
        ?? hit?.query_start
        ?? hit?.hitStart
        ?? hit?.hit_start,
      );
      const ctgEnd = Number(
        hit?.ctgEnd
        ?? hit?.ctg_end
        ?? hit?.queryEnd
        ?? hit?.query_end
        ?? hit?.hitEnd
        ?? hit?.hit_end,
      );
      if (
        (!preserved.has(`hit-${index + 1}`) && hitBlockLength < blockLength) ||
        (!preserved.has(`hit-${index + 1}`) && hitMapq < minMapq)
      ) {
        return null;
      }
      if (
        !Number.isFinite(ctgStart)
        || !Number.isFinite(ctgEnd)
        || !Number.isFinite(refStart)
        || !Number.isFinite(refEnd)
      ) {
        return null;
      }
      const normalizedRefStart = Math.min(refStart, refEnd);
      const normalizedRefEnd = Math.max(refStart, refEnd);
      return {
        hitKey: `hit-${index + 1}`,
        pairKey: String(hit?.pairKey || `hit-${index + 1}`),
        ctgStart: Math.min(ctgStart, ctgEnd),
        ctgEnd: Math.max(ctgStart, ctgEnd),
        refStart: normalizedRefStart,
        refEnd: normalizedRefEnd,
        refMid: (normalizedRefStart + normalizedRefEnd) / 2,
      };
    })
    .filter(Boolean);
}

function buildSubviewAlignmentSvgModel({
  topCtg,
  bottomCtg,
  topHits,
  bottomHits,
  pairCacheKey = "",
  pairingMode = "reference-overlap",
  minTickUnitKb,
  maxTickCount,
  topManualOffsetPx = 0,
  bottomManualOffsetPx = 0,
}) {
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const TRACK_TAIL_PADDING = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_MIN_DRAG_VISIBLE_PX = 24;
  const LABEL_COLUMN_WIDTH_PX = 136;

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  const rowHeight = TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
  const topBarY = cursorY + TRACK_ROW_PADDING_TOP;
  const topLabelTop = topBarY;
  cursorY += rowHeight + TRACK_ROW_GAP;
  const bottomBarY = cursorY + TRACK_ROW_PADDING_TOP;
  const bottomLabelTop = bottomBarY;
  cursorY += rowHeight + TRACK_TAIL_PADDING;
  const contentBottom = cursorY;

  const safeMinTickUnitKb = Math.max(1, normalizePositiveInt(minTickUnitKb) ?? 1);
  const safeMaxTickCount = Math.max(1, normalizePositiveInt(maxTickCount) ?? 10);
  const topLengthBp = resolveSubviewCtgLengthBp(topCtg, topHits);
  const bottomLengthBp = resolveSubviewCtgLengthBp(bottomCtg, bottomHits);
  const domainStart = 0;
  const domainEnd = Math.max(topLengthBp, bottomLengthBp);
  const domainSpan = Math.max(1, domainEnd - domainStart);
  const renderInnerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: domainSpan,
    minTickUnitKb: safeMinTickUnitKb,
    maxTickCount: safeMaxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("subview"),
    fallbackInnerWidth: getMeasuredTrackViewportPx("subview"),
  });
  const tickBp = resolveTickBpFromScale({
    domainSpanBp: domainSpan,
    minTickUnitKb: safeMinTickUnitKb,
    maxTickCount: safeMaxTickCount,
    fallbackTickBp: safeMinTickUnitKb * 1000,
  });
  const tickItems = buildTrackTickItems({
    windowStart: domainStart,
    windowEnd: domainEnd,
    tickBp,
    innerWidth: renderInnerWidth,
    domainSpanBp: domainSpan,
  }).map((tick, index, items) => {
    const isFirst = index === 0;
    const isLast = index === items.length - 1;
    const labelText = isLast ? formatBp(tick.bp) : formatRulerTickLabel(tick.bp);
    const labelX = isFirst
      ? Math.min(renderInnerWidth, tick.x + TRACK_EDGE_LABEL_PADDING)
      : isLast
        ? Math.max(0, tick.x - TRACK_EDGE_LABEL_PADDING)
        : tick.x;
    const labelAnchor = isFirst ? "start" : isLast ? "end" : "middle";
    return {
      ...tick,
      labelText,
      labelX,
      labelAnchor,
      showLabel: true,
    };
  });
  const endTick = tickItems[tickItems.length - 1];
  const previousTick = tickItems[tickItems.length - 2];
  if (isTrackTickLabelOverlap(previousTick, endTick)) {
    previousTick.showLabel = false;
  }

  const toX = (bpValue) =>
    (Math.max(0, Math.min(domainEnd, Number(bpValue) || 0)) / domainSpan) * Math.max(1, renderInnerWidth);
  const topBarWidth = toX(topLengthBp);
  const bottomBarWidth = toX(bottomLengthBp);
  const toSegments = (hits, trackOffsetBp = 0) =>
    hits.map((hit) => {
      const x1 = toX((Number(hit.ctgStart) || 0) + trackOffsetBp);
      const x2 = toX((Number(hit.ctgEnd) || 0) + trackOffsetBp);
      return {
        hitKey: String(hit?.hitKey || ""),
        pairKey: String(hit?.pairKey || hit?.hitKey || ""),
        reversed: hit?.reversed === true,
        ctgStart: Math.min(Number(hit.ctgStart) || 0, Number(hit.ctgEnd) || 0),
        ctgEnd: Math.max(Number(hit.ctgStart) || 0, Number(hit.ctgEnd) || 0),
        x: Math.min(x1, x2),
        width: Math.max(1, Math.abs(x2 - x1)),
        midX: (x1 + x2) / 2,
        refStart: Math.min(Number(hit.refStart) || 0, Number(hit.refEnd) || 0),
        refEnd: Math.max(Number(hit.refStart) || 0, Number(hit.refEnd) || 0),
        refMid: Number(hit.refMid || 0),
      };
    });
  const baseTopSegments = toSegments(topHits).sort((left, right) => left.refMid - right.refMid);
  const baseBottomSegments = toSegments(bottomHits).sort(
    (left, right) => left.refMid - right.refMid,
  );
  const baseSegmentPairs = pairRefSubviewSegmentsWithCache({
    cacheKey: `${pairCacheKey}:base`,
    topSegments: baseTopSegments,
    bottomSegments: baseBottomSegments,
    trackMode: "2-contig",
    pairingMode,
  });
  const { topOffsetBp, bottomOffsetBp } = resolveSubviewAutoTrackOffsets({
    topLengthBp,
    bottomLengthBp,
    domainEnd,
    segmentPairs: baseSegmentPairs,
  });
  const topBarBaseX = toX(topOffsetBp);
  const bottomBarBaseX = toX(bottomOffsetBp);
  const resolveClampedManualOffsetPx = (requestedOffsetPx, barBaseX, barWidth) => {
    const numeric = Number(requestedOffsetPx || 0);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    const minOffset = -barBaseX;
    const maxOffset = Math.max(0, renderInnerWidth - (barBaseX + barWidth));
    if (maxOffset - minOffset > 0.01) {
      return roundTrackMetric(Math.min(Math.max(numeric, minOffset), maxOffset));
    }
    const minVisiblePx = Math.min(Math.max(3, Number(barWidth) || 0), TRACK_MIN_DRAG_VISIBLE_PX);
    const relaxedMinOffset = minVisiblePx - (barBaseX + barWidth);
    const relaxedMaxOffset = renderInnerWidth - minVisiblePx - barBaseX;
    if (relaxedMaxOffset < relaxedMinOffset) {
      return 0;
    }
    return roundTrackMetric(Math.min(Math.max(numeric, relaxedMinOffset), relaxedMaxOffset));
  };
  const resolvedTopManualOffsetPx = resolveClampedManualOffsetPx(topManualOffsetPx, topBarBaseX, topBarWidth);
  const resolvedBottomManualOffsetPx = resolveClampedManualOffsetPx(bottomManualOffsetPx, bottomBarBaseX, bottomBarWidth);
  const topBarX = roundTrackMetric(topBarBaseX + resolvedTopManualOffsetPx);
  const bottomBarX = roundTrackMetric(bottomBarBaseX + resolvedBottomManualOffsetPx);
  const topSegments = toSegments(topHits, topOffsetBp).sort((left, right) => left.refMid - right.refMid);
  const bottomSegments = toSegments(bottomHits, bottomOffsetBp).sort(
    (left, right) => left.refMid - right.refMid,
  );
  const shiftedTopSegments = topSegments.map((segment) => ({
    ...segment,
    x: roundTrackMetric(segment.x + resolvedTopManualOffsetPx),
    midX: roundTrackMetric(segment.midX + resolvedTopManualOffsetPx),
  }));
  const shiftedBottomSegments = bottomSegments.map((segment) => ({
    ...segment,
    x: roundTrackMetric(segment.x + resolvedBottomManualOffsetPx),
    midX: roundTrackMetric(segment.midX + resolvedBottomManualOffsetPx),
  }));
  const segmentPairs = pairRefSubviewSegmentsWithCache({
    cacheKey: `${pairCacheKey}:shifted`,
    topSegments: shiftedTopSegments,
    bottomSegments: shiftedBottomSegments,
    trackMode: "2-contig",
    pairingMode,
  });
  const collinearityBands = segmentPairs.map(({ topSegment, bottomSegment }) => {
    const topStartX = topSegment.x;
    const topEndX = topSegment.x + topSegment.width;
    const bottomStartX = bottomSegment.x;
    const bottomEndX = bottomSegment.x + bottomSegment.width;
    const hitKey = String(topSegment?.hitKey || bottomSegment?.hitKey || "");
    const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
    return {
      hitKey,
      tooltipText: buildSubviewBandTooltipText({
        topName: String(topCtg?.name || ""),
        bottomName: String(bottomCtg?.name || ""),
        topSegment,
        bottomSegment,
      }),
      points: (reversed
        ? [
            `${topStartX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${topEndX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${bottomStartX.toFixed(2)},${bottomBarY.toFixed(2)}`,
            `${bottomEndX.toFixed(2)},${bottomBarY.toFixed(2)}`,
          ]
        : [
            `${topStartX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${topEndX.toFixed(2)},${(topBarY + TRACK_BAR_HEIGHT).toFixed(2)}`,
            `${bottomEndX.toFixed(2)},${bottomBarY.toFixed(2)}`,
            `${bottomStartX.toFixed(2)},${bottomBarY.toFixed(2)}`,
          ]).join(" "),
    };
  });
  const anchorEdges = segmentPairs.flatMap(({ topSegment, bottomSegment }, index) => {
    const hitKey = String(topSegment?.hitKey || bottomSegment?.hitKey || `hit-${index + 1}`);
    const reversed = topSegment.reversed === true || bottomSegment.reversed === true;
    return [
      {
        hitKey,
        edge: "left",
        topX: topSegment.x,
        bottomX: reversed ? bottomSegment.x + bottomSegment.width : bottomSegment.x,
        topY: topBarY,
        bottomY: bottomBarY + TRACK_BAR_HEIGHT,
        hitTopY: topBarY + TRACK_BAR_HEIGHT,
        hitBottomY: bottomBarY,
        topContigId: normalizeSupportDatasetId(topCtg?.assemblyCtgId),
        bottomContigId: normalizeSupportDatasetId(bottomCtg?.assemblyCtgId),
        topCutBp: topSegment.ctgStart,
        bottomCutBp: reversed ? bottomSegment.ctgEnd : bottomSegment.ctgStart,
      },
      {
        hitKey,
        edge: "right",
        topX: topSegment.x + topSegment.width,
        bottomX: reversed ? bottomSegment.x : bottomSegment.x + bottomSegment.width,
        topY: topBarY,
        bottomY: bottomBarY + TRACK_BAR_HEIGHT,
        hitTopY: topBarY + TRACK_BAR_HEIGHT,
        hitBottomY: bottomBarY,
        topContigId: normalizeSupportDatasetId(topCtg?.assemblyCtgId),
        bottomContigId: normalizeSupportDatasetId(bottomCtg?.assemblyCtgId),
        topCutBp: topSegment.ctgEnd,
        bottomCutBp: reversed ? bottomSegment.ctgStart : bottomSegment.ctgEnd,
      },
    ];
  });
  return {
    labelColumnWidth: LABEL_COLUMN_WIDTH_PX,
    contentBottom,
    domainSpanBp: domainSpan,
    renderInnerWidth,
    rulerTop,
    tickY1: rulerTop + TRACK_LABEL_OFFSET_Y,
    tickY2: contentBottom - 3 * TRACK_HEIGHT_SCALE,
    tickLabelY: rulerTop - TRACK_LABEL_OFFSET_Y,
    tickItems,
    topBarY,
    bottomBarY,
    topBarX,
    bottomBarX,
    topBarWidth,
    bottomBarWidth,
    topLabelTop,
    bottomLabelTop,
    barHeight: TRACK_BAR_HEIGHT,
    textOffsetY: TRACK_TEXT_OFFSET_Y,
    collinearityBands,
    anchorEdges,
    topLengthBp,
    bottomLengthBp,
  };
}

function buildSubviewBandTooltipText({ topName, bottomName, topSegment, bottomSegment }) {
  const resolvedTopName = String(topName || "Top");
  const resolvedBottomName = String(bottomName || "Bottom");
  return [
    `${resolvedTopName}: ${formatBpInterval(topSegment?.ctgStart, topSegment?.ctgEnd)}`,
    `${resolvedBottomName}: ${formatBpInterval(bottomSegment?.ctgStart, bottomSegment?.ctgEnd)}`,
  ].join(" | ");
}

function resolveSubviewAutoTrackOffsets({ topLengthBp, bottomLengthBp, domainEnd, segmentPairs }) {
  if (topLengthBp === bottomLengthBp) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const shorterTrack = topLengthBp < bottomLengthBp ? "top" : "bottom";
  const shorterLengthBp = shorterTrack === "top" ? topLengthBp : bottomLengthBp;
  const maxOffsetBp = Math.max(0, domainEnd - shorterLengthBp);
  if (!Array.isArray(segmentPairs) || !segmentPairs.length || maxOffsetBp <= 0) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const offsetCandidates = segmentPairs
    .map(({ topSegment, bottomSegment }) => {
      const topMid = (Number(topSegment?.ctgStart) + Number(topSegment?.ctgEnd)) / 2;
      const bottomMid = (Number(bottomSegment?.ctgStart) + Number(bottomSegment?.ctgEnd)) / 2;
      if (!Number.isFinite(topMid) || !Number.isFinite(bottomMid)) {
        return null;
      }
      const rawOffsetBp = shorterTrack === "top" ? bottomMid - topMid : topMid - bottomMid;
      return clampSubviewTrackOffsetBp(rawOffsetBp, maxOffsetBp);
    })
    .filter((value) => Number.isFinite(value));
  if (!offsetCandidates.length) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const resolvedOffsetBp = resolveMedianNumber(offsetCandidates);
  return shorterTrack === "top"
    ? { topOffsetBp: resolvedOffsetBp, bottomOffsetBp: 0 }
    : { topOffsetBp: 0, bottomOffsetBp: resolvedOffsetBp };
}

function clampSubviewTrackOffsetBp(value, maxOffsetBp) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(Math.max(0, numeric), Math.max(0, Number(maxOffsetBp) || 0));
}

function resolveMedianNumber(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middleIndex = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middleIndex];
  }
  return (sorted[middleIndex - 1] + sorted[middleIndex]) / 2;
}

function pairSubviewSegmentsByReference(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? [...topSegments] : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? [...bottomSegments] : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  safeTopSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });
  safeBottomSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });

  const pairs = [];
  let bottomWindowStart = 0;
  for (const topSegment of safeTopSegments) {
    while (
      bottomWindowStart < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomWindowStart]?.refEnd || 0) <= Number(topSegment.refStart || 0)
    ) {
      bottomWindowStart += 1;
    }
    for (
      let bottomIndex = bottomWindowStart;
      bottomIndex < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomIndex]?.refStart || 0) < Number(topSegment.refEnd || 0);
      bottomIndex += 1
    ) {
      const bottomSegment = safeBottomSegments[bottomIndex];
      if (resolveRefOverlapBp(topSegment, bottomSegment) <= 0) {
        continue;
      }
      pairs.push({
        topSegment,
        bottomSegment,
      });
    }
  }
  return pairs;
}

function pairSubviewTrackSegmentsByReference(topSegments, bottomSegments) {
  return pairSubviewSegmentsByReference(topSegments, bottomSegments).filter(
    ({ topSegment, bottomSegment }) => {
      const overlapBp = resolveRefOverlapBp(topSegment, bottomSegment);
      const topSpanBp = Math.max(
        1,
        Math.abs((Number(topSegment?.refEnd) || 0) - (Number(topSegment?.refStart) || 0)),
      );
      const bottomSpanBp = Math.max(
        1,
        Math.abs((Number(bottomSegment?.refEnd) || 0) - (Number(bottomSegment?.refStart) || 0)),
      );
      const minSpanBp = Math.min(topSpanBp, bottomSpanBp);
      return overlapBp / minSpanBp >= 0.5;
    },
  );
}

function buildSubviewTrackPairHitKey(topSegment, bottomSegment) {
  const topContigId = normalizeSupportDatasetId(topSegment?.ctgId) || 0;
  const bottomContigId = normalizeSupportDatasetId(bottomSegment?.ctgId) || 0;
  const topHitKey = String(topSegment?.hitKey || "").trim();
  const bottomHitKey = String(bottomSegment?.hitKey || "").trim();
  return `pair:${topContigId}:${topHitKey}:${bottomContigId}:${bottomHitKey}`;
}

function resolveRefOverlapBp(leftSegment, rightSegment) {
  const leftStart = Math.min(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const leftEnd = Math.max(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const rightStart = Math.min(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const rightEnd = Math.max(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const start = Math.max(leftStart, rightStart);
  const end = Math.min(leftEnd, rightEnd);
  return Math.max(0, end - start);
}

function resolveSubviewCtgLengthBp(ctg, hits) {
  const candidates = [
    ctg?.totalLength,
    ctg?.lengthBp,
    ctg?.length,
  ];
  for (const candidate of candidates) {
    const parsed = normalizePositiveInt(candidate);
    if (parsed && parsed > 0) {
      return parsed;
    }
  }
  const fallbackHitEnd = (Array.isArray(hits) ? hits : []).reduce((maxValue, hit) => {
    const hitEnd = Number(hit?.ctgEnd);
    if (!Number.isFinite(hitEnd)) {
      return maxValue;
    }
    return Math.max(maxValue, hitEnd);
  }, 0);
  return Math.max(1, fallbackHitEnd || 1);
}

function buildTrackTickItems({ windowStart, windowEnd, tickBp, innerWidth, domainSpanBp }) {
  const ticks = [];
  const resolvedEnd = Math.max(windowStart, windowEnd);
  const firstTick = Math.max(0, Math.ceil(Math.max(0, windowStart) / tickBp) * tickBp);
  for (let bp = firstTick; bp <= resolvedEnd; bp += tickBp) {
    const x = ((Math.min(bp, resolvedEnd) - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp, x });
  }
  const hasEndTick = ticks.length > 0 && Number(ticks[ticks.length - 1].bp) === Number(resolvedEnd);
  if (!hasEndTick) {
    const endX = ((resolvedEnd - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp: resolvedEnd, x: endX });
  }
  return ticks;
}

function isTrackTickLabelOverlap(previousTick, endTick) {
  if (!previousTick || !endTick) {
    return false;
  }
  const previousBounds = resolveTrackTickLabelBounds(previousTick);
  const endBounds = resolveTrackTickLabelBounds(endTick);
  return previousBounds.right > endBounds.left;
}

function resolveTrackTickLabelBounds(tick) {
  const width = estimateTrackTickLabelWidth(tick?.labelText || "");
  if (tick?.labelAnchor === "start") {
    return { left: tick.labelX, right: tick.labelX + width };
  }
  if (tick?.labelAnchor === "end") {
    return { left: tick.labelX - width, right: tick.labelX };
  }
  return {
    left: tick.labelX - width / 2,
    right: tick.labelX + width / 2,
  };
}

function estimateTrackTickLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(12, text.length * 7);
}

function resolveTrackCtgDisplayName(ctg, fallbackId) {
  const resolvedName = String(ctg?.name || "").trim();
  if (resolvedName) {
    return resolvedName;
  }
  const contigId = normalizeSupportDatasetId(fallbackId ?? ctg?.assemblyCtgId);
  return contigId ? `Ctg${contigId}` : "";
}

function stripTrackCtgAssignmentSuffix(name) {
  const text = String(name || "").trim();
  const atIndex = text.lastIndexOf("@");
  if (atIndex <= 0 || atIndex >= text.length - 1) {
    return text;
  }
  const suffix = text.slice(atIndex + 1);
  if (!suffix || /\s/.test(suffix)) {
    return text;
  }
  return text.slice(0, atIndex);
}

function resolveTrackCtgVisibleName(ctg, fallbackId) {
  return stripTrackCtgAssignmentSuffix(resolveTrackCtgDisplayName(ctg, fallbackId));
}

function resolveTrackCtgOrient(ctg) {
  const orient = String((ctg?.orient ?? ctg?.refOrient ?? ctg?.ref_orient) || "").trim();
  return orient === "-" ? "-" : "+";
}

function resolveTrackCtgLabelText(ctg, fallbackId) {
  const displayName = resolveTrackCtgVisibleName(ctg, fallbackId);
  if (!displayName) {
    return "";
  }
  return `${displayName} (${resolveTrackCtgOrient(ctg)})`;
}

function buildTrackCtgHoverTitle(ctgName, { startBp = 0, lengthBp = 0 } = {}) {
  return `${String(ctgName || "").trim()} | start=${normalizePositiveInt(startBp) || 0} | len=${normalizePositiveInt(lengthBp) || 0}`;
}

function resolveTrackCtgLabelPlacement({
  ctgName,
  role,
  rect,
  barY,
  barHeight,
  inlineTextOffsetY,
  outsideLabelAnchor = "trailing-edge",
  hideOutsideLabel = false,
}) {
  const inlineX = Number(rect?.x || 0) + 4;
  const inlineY = Number(barY || 0) + Number(inlineTextOffsetY || 0);
  const estimatedLabelWidth = estimateTrackCtgLabelWidth(ctgName);
  const fitsInsideBar = Number(rect?.width || 0) >= estimatedLabelWidth + 8;
  if (fitsInsideBar) {
    return {
      x: inlineX,
      y: inlineY,
      classSuffix: "",
      transformAttr: "",
      textAnchor: "start",
      tiltAngleDeg: 0,
    };
  }

  if (hideOutsideLabel) {
    return {
      x: inlineX,
      y: inlineY,
      classSuffix: " is-hidden-label",
      transformAttr: "",
      textAnchor: "start",
      tiltAngleDeg: 0,
      hidden: true,
    };
  }

  const isCompanion = String(role || "") === "support";
  const outsideX = outsideLabelAnchor === "bar-middle"
    ? Number.isFinite(Number(rect?.centerX))
      ? Number(rect.centerX)
      : Number(rect?.x || 0) + Number(rect?.width || 0) / 2
    : Number(rect?.x || 0) + Number(rect?.width || 0) + 2;
  const outsideY = isCompanion
    ? Number(barY || 0) - 2
    : Number(barY || 0) + Number(barHeight || 0) + 10;
  const angle = isCompanion ? -25 : 25;
  return {
    x: outsideX,
    y: outsideY,
    classSuffix: isCompanion ? " is-outside is-tilt-up" : " is-outside is-tilt-down",
    transformAttr: buildTrackCtgLabelTransformAttr({
      tiltAngleDeg: angle,
      x: outsideX,
      y: outsideY,
    }),
    textAnchor: "start",
    tiltAngleDeg: angle,
  };
}

function buildTrackCtgLabelTransformAttr({
  tiltAngleDeg = 0,
  x,
  y,
}) {
  const angle = Number(tiltAngleDeg) || 0;
  if (!angle) {
    return "";
  }
  return ` transform="rotate(${angle} ${Number(x).toFixed(2)} ${Number(y).toFixed(2)})"`;
}

function resolveBoundedTrackCtgLabelPlacement({
  minVisibleX = -Infinity,
  maxVisibleX = Infinity,
  ...args
}) {
  const placement = resolveTrackCtgLabelPlacement(args);
  if (!placement) {
    return placement;
  }
  const resolvedMinX = Number.isFinite(minVisibleX) ? Number(minVisibleX) : -Infinity;
  const resolvedMaxX = Number.isFinite(maxVisibleX) ? Number(maxVisibleX) : Infinity;
  if (!(resolvedMinX < resolvedMaxX)) {
    return placement;
  }
  const bounds = resolveTrackCtgLabelBounds({
    x: placement.x,
    labelText: args.ctgName,
    tiltAngleDeg: placement.tiltAngleDeg,
    textAnchor: placement.textAnchor,
  });
  let shiftX = 0;
  if (bounds.left < resolvedMinX) {
    shiftX += resolvedMinX - bounds.left;
  }
  if (bounds.right + shiftX > resolvedMaxX) {
    shiftX += resolvedMaxX - (bounds.right + shiftX);
  }
  if (Math.abs(shiftX) < 0.01) {
    return placement;
  }
  const nextX = Number(placement.x) + shiftX;
  return {
    ...placement,
    x: nextX,
    transformAttr: buildTrackCtgLabelTransformAttr({
      tiltAngleDeg: placement.tiltAngleDeg,
      x: nextX,
      y: placement.y,
    }),
  };
}

function estimateTrackCtgLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(10, text.length * 6.2);
}

function resolveTrackCtgLabelRightBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX;
  }
  if (textAnchor === "middle") {
    return baseX + projectedWidth / 2;
  }
  return baseX + projectedWidth;
}

function resolveTrackCtgLabelLeftBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX - projectedWidth;
  }
  if (textAnchor === "middle") {
    return baseX - projectedWidth / 2;
  }
  return baseX;
}

function resolveTrackCtgLabelBounds({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  return {
    left: resolveTrackCtgLabelLeftBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
    right: resolveTrackCtgLabelRightBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
  };
}

function buildTrackRect(ctg, { windowStart, domainSpanBp, innerWidth }) {
  const x = buildTrackBpX({
    bp: ctg.startBp,
    windowStart,
    domainSpanBp,
    innerWidth,
  });
  const width = Math.max(3, (ctg.lengthBp / domainSpanBp) * innerWidth);
  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

function sortTrackEntriesForRender(entries) {
  const sourceEntries = Array.isArray(entries) ? entries : [];
  const laneBuckets = new Map();
  sourceEntries.forEach((entry) => {
    const laneIndex = Math.max(0, Number(entry?.ctg?.laneIndex ?? 0));
    const bucket = laneBuckets.get(laneIndex) || [];
    bucket.push(entry);
    laneBuckets.set(laneIndex, bucket);
  });
  const laneIndices = Array.from(laneBuckets.keys()).sort((left, right) => left - right);
  return laneIndices.flatMap((laneIndex) => {
    const laneEntries = laneBuckets.get(laneIndex) || [];
    const sortedByX = laneEntries
      .slice()
      .sort((left, right) => {
        const leftX = Number(left?.rect?.x || 0);
        const rightX = Number(right?.rect?.x || 0);
        if (leftX !== rightX) {
          return leftX - rightX;
        }
        const leftCtgId = normalizeSupportDatasetId(left?.ctg?.assemblyCtgId) || 0;
        const rightCtgId = normalizeSupportDatasetId(right?.ctg?.assemblyCtgId) || 0;
        return leftCtgId - rightCtgId;
      });
    if (sortedByX.length <= 1) {
      return sortedByX;
    }

    const overlapGroups = [];
    let currentGroup = [];
    let currentGroupMaxRight = Number.NEGATIVE_INFINITY;
    const flushCurrentGroup = () => {
      if (!currentGroup.length) {
        return;
      }
      overlapGroups.push(currentGroup);
      currentGroup = [];
      currentGroupMaxRight = Number.NEGATIVE_INFINITY;
    };
    sortedByX.forEach((entry) => {
      const x = Number(entry?.rect?.x || 0);
      const width = Math.max(0, Number(entry?.rect?.width || 0));
      const right = x + width;
      if (!currentGroup.length) {
        currentGroup.push(entry);
        currentGroupMaxRight = right;
        return;
      }
      if (x <= currentGroupMaxRight + 0.01) {
        currentGroup.push(entry);
        currentGroupMaxRight = Math.max(currentGroupMaxRight, right);
        return;
      }
      flushCurrentGroup();
      currentGroup.push(entry);
      currentGroupMaxRight = right;
    });
    flushCurrentGroup();

    return overlapGroups.flatMap((group) => {
      if (group.length <= 1) {
        return group;
      }
      return group.sort((left, right) => {
        const leftLength = Math.max(0, Number(left?.ctg?.lengthBp || 0));
        const rightLength = Math.max(0, Number(right?.ctg?.lengthBp || 0));
        if (leftLength !== rightLength) {
          return rightLength - leftLength;
        }
        const leftWidth = Math.max(0, Number(left?.rect?.width || 0));
        const rightWidth = Math.max(0, Number(right?.rect?.width || 0));
        if (leftWidth !== rightWidth) {
          return rightWidth - leftWidth;
        }
        const leftX = Number(left?.rect?.x || 0);
        const rightX = Number(right?.rect?.x || 0);
        if (leftX !== rightX) {
          return leftX - rightX;
        }
        const leftCtgId = normalizeSupportDatasetId(left?.ctg?.assemblyCtgId) || 0;
        const rightCtgId = normalizeSupportDatasetId(right?.ctg?.assemblyCtgId) || 0;
        return leftCtgId - rightCtgId;
      });
    });
  });
}

function buildTrackRectsWithMinGap(ctgs, { windowStart, domainSpanBp, innerWidth, minGapPx = 0 }) {
  const sourceCtgs = Array.isArray(ctgs) ? ctgs : [];
  const rects = sourceCtgs.map((ctg) => buildTrackRect(ctg, { windowStart, domainSpanBp, innerWidth }));
  const resolvedMinGapPx = Math.max(0, Number(minGapPx) || 0);
  if (rects.length <= 1 || !resolvedMinGapPx) {
    return rects;
  }

  const laneBuckets = new Map();
  sourceCtgs.forEach((ctg, index) => {
    const laneIndex = Number(ctg?.laneIndex ?? 0);
    const bucket = laneBuckets.get(laneIndex) || [];
    bucket.push(index);
    laneBuckets.set(laneIndex, bucket);
  });

  laneBuckets.forEach((indices) => {
    indices.sort((leftIndex, rightIndex) => rects[leftIndex].x - rects[rightIndex].x);
    for (let cursor = 0; cursor < indices.length - 1; cursor += 1) {
      const current = rects[indices[cursor]];
      const next = rects[indices[cursor + 1]];
      const currentGap = next.x - (current.x + current.width);
      if (currentGap >= resolvedMinGapPx) {
        continue;
      }
      let neededPx = resolvedMinGapPx - currentGap;
      const maxReduciblePx = Math.max(0, current.width - 3);
      const reducePx = Math.min(maxReduciblePx, neededPx);
      if (reducePx > 0) {
        current.width -= reducePx;
        current.centerX = current.x + current.width / 2;
        neededPx -= reducePx;
      }
      if (neededPx <= 0) {
        continue;
      }
      for (let shiftIndex = cursor + 1; shiftIndex < indices.length; shiftIndex += 1) {
        const shifted = rects[indices[shiftIndex]];
        shifted.x += neededPx;
        shifted.centerX = shifted.x + shifted.width / 2;
      }
    }
  });

  return rects;
}

function buildTrackHitRect({ ctgStartBp, ctgEndBp, windowStart, domainSpanBp, innerWidth }) {
  const startBp = Math.min(ctgStartBp, ctgEndBp);
  const endBp = Math.max(ctgStartBp, ctgEndBp);
  const x = buildTrackBpX({
    bp: startBp,
    windowStart,
    domainSpanBp,
    innerWidth,
  });
  const width = Math.max(3, ((endBp - startBp + 1) / domainSpanBp) * innerWidth);
  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

function buildTrackHitRectWithinCtgDisplay({
  ctgRect,
  ctgLengthBp,
  ctgStartOffset,
  ctgEndOffset,
}) {
  const baseX = Number(ctgRect?.x);
  const baseWidth = Number(ctgRect?.width);
  if (!Number.isFinite(baseX) || !Number.isFinite(baseWidth) || baseWidth <= 0) {
    return {
      x: 0,
      width: 1,
      centerX: 0.5,
    };
  }

  const resolvedLengthBp = Math.max(1, normalizePositiveInt(ctgLengthBp) ?? 1);
  const normalizedStart = Number.isFinite(ctgStartOffset) ? ctgStartOffset : 1;
  const normalizedEnd = Number.isFinite(ctgEndOffset) ? ctgEndOffset : resolvedLengthBp;
  const hitStartBp = Math.min(normalizedStart, normalizedEnd);
  const hitEndBp = Math.max(normalizedStart, normalizedEnd);
  const clampedStartBp = Math.max(1, Math.min(resolvedLengthBp, hitStartBp));
  const clampedEndBp = Math.max(1, Math.min(resolvedLengthBp, hitEndBp));
  const startRatio = (clampedStartBp - 1) / resolvedLengthBp;
  const hitSpanBp = Math.max(1, clampedEndBp - clampedStartBp + 1);
  const x = baseX + startRatio * baseWidth;
  const maxAvailableWidth = Math.max(1, baseX + baseWidth - x);
  const width = Math.max(1, Math.min(maxAvailableWidth, (hitSpanBp / resolvedLengthBp) * baseWidth));

  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

function resolveHitMapq(hit) {
  return Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
}

function buildTrackBpX({ bp, windowStart, domainSpanBp, innerWidth }) {
  return ((bp - windowStart) / domainSpanBp) * innerWidth;
}

function buildTrackReferenceWidth(chrLength, domainSpanBp, innerWidth) {
  const spanBp = Math.max(1, normalizePositiveInt(chrLength) ?? domainSpanBp);
  return Math.max(3, (spanBp / domainSpanBp) * innerWidth);
}

function resolveMaxTrackEndBp(ctgs) {
  return (Array.isArray(ctgs) ? ctgs : []).reduce((maxEndBp, ctg) => {
    const endBp = normalizePositiveInt(ctg?.endBp);
    if (endBp !== null) {
      return Math.max(maxEndBp, endBp);
    }
    const startBp = normalizePositiveInt(ctg?.startBp);
    const lengthBp = normalizePositiveInt(ctg?.lengthBp);
    if (startBp === null || lengthBp === null) {
      return maxEndBp;
    }
    return Math.max(maxEndBp, startBp + lengthBp - 1);
  }, 0);
}

function buildCollinearityBandPoints({
  ctgRect,
  refRect,
  refLeftClamp = 0,
  refRightClamp = Number.POSITIVE_INFINITY,
  refTop,
  refBottom,
  ctgTop,
  ctgBottom,
  direction,
  reversed = false,
}) {
  const ctgLeft = ctgRect.x;
  const ctgRight = ctgRect.x + ctgRect.width;
  const refLeft = Math.max(refLeftClamp, refRect.x);
  const refRight = Math.min(refRightClamp, refRect.x + refRect.width);
  if (direction === "down") {
    if (reversed) {
      return [
        `${ctgLeft.toFixed(2)},${ctgBottom.toFixed(2)}`,
        `${ctgRight.toFixed(2)},${ctgBottom.toFixed(2)}`,
        `${refLeft.toFixed(2)},${refTop.toFixed(2)}`,
        `${refRight.toFixed(2)},${refTop.toFixed(2)}`,
      ].join(" ");
    }
    return [
      `${ctgLeft.toFixed(2)},${ctgBottom.toFixed(2)}`,
      `${ctgRight.toFixed(2)},${ctgBottom.toFixed(2)}`,
      `${refRight.toFixed(2)},${refTop.toFixed(2)}`,
      `${refLeft.toFixed(2)},${refTop.toFixed(2)}`,
    ].join(" ");
  }
  if (reversed) {
    return [
      `${refLeft.toFixed(2)},${refBottom.toFixed(2)}`,
      `${refRight.toFixed(2)},${refBottom.toFixed(2)}`,
      `${ctgLeft.toFixed(2)},${ctgTop.toFixed(2)}`,
      `${ctgRight.toFixed(2)},${ctgTop.toFixed(2)}`,
    ].join(" ");
  }
  return [
    `${refLeft.toFixed(2)},${refBottom.toFixed(2)}`,
    `${refRight.toFixed(2)},${refBottom.toFixed(2)}`,
    `${ctgRight.toFixed(2)},${ctgTop.toFixed(2)}`,
    `${ctgLeft.toFixed(2)},${ctgTop.toFixed(2)}`,
  ].join(" ");
}

function getSubviewSlotToken(subview, role, contigId) {
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  const normalizedRole = normalizeSubviewRole(role);
  if (!normalizedContigId || !normalizedRole) {
    return "";
  }
  const selections = getSubviewSelections(subview);
  const matchedIndex = selections.findIndex(
    (selection) =>
      Number(selection.contigId) === Number(normalizedContigId) && selection.role === normalizedRole,
  );
  if (matchedIndex < 0) {
    return "";
  }
  return matchedIndex === 0 ? "A" : "B";
}

  return { renderAssemblyMainTab, renderAssemblySubviewPanel };
}

export function renderAssemblyMainTab(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblyMainTab(state);
}

export function renderAssemblySubviewPanel(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblySubviewPanel(state);
}

export function roundTrackMetric(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function isFiniteTrackMetric(value) {
  return Number.isFinite(Number(value));
}

function resolveTrackBpPerPixel({ domainSpanBp, innerWidth } = {}) {
  const domain = Number(domainSpanBp);
  const width = Number(innerWidth);
  if (!Number.isFinite(domain) || !Number.isFinite(width) || domain <= 0 || width <= 0) {
    return 0;
  }
  return domain / width;
}

export function convertTrackOffsetPxToBp(offsetPx, scaleContext) {
  const offset = Number(offsetPx);
  const bpPerPixel = resolveTrackBpPerPixel(scaleContext);
  if (!Number.isFinite(offset) || bpPerPixel <= 0) {
    return 0;
  }
  return roundTrackMetric(offset * bpPerPixel);
}

function convertTrackOffsetBpToPx(offsetBp, scaleContext) {
  const offset = Number(offsetBp);
  const bpPerPixel = resolveTrackBpPerPixel(scaleContext);
  if (!Number.isFinite(offset) || bpPerPixel <= 0) {
    return 0;
  }
  return roundTrackMetric(offset / bpPerPixel);
}

function buildEmptyTrackModelLike() {
  return {
    windowStart: 0,
    windowEnd: 0,
    viewSpanBp: 1,
    innerWidth: 0,
    domainSpanBp: 1,
    laneCount: 1,
    ticks: [],
  };
}

function buildSupportMirroredCtgsForRender({
  supportMirroredCtgs,
  selectedChrName,
  supportDatasetId,
  supportDatasetName,
  supportModelCtgs,
  supportDatasetOptions,
}) {
  const currentDatasetId = normalizeSupportDatasetId(supportDatasetId);
  const currentDatasetName = String(supportDatasetName || "");
  const selectedChr = String(selectedChrName || "").trim();
  const liveSupportById = new Map(
    (Array.isArray(supportModelCtgs) ? supportModelCtgs : []).map((ctg) => [
      normalizeSupportDatasetId(ctg?.assemblyCtgId),
      ctg,
    ]),
  );
  return normalizeSupportMirroredCtgs(supportMirroredCtgs)
    .filter((entry) => !selectedChr || !entry.chrName || entry.chrName === selectedChr)
    .map((entry) => {
      const optionLabel = (Array.isArray(supportDatasetOptions) ? supportDatasetOptions : []).find(
        (item) => normalizeSupportDatasetId(item?.datasetId) === entry.datasetId,
      )?.label || "";
      const fallbackDatasetName = currentDatasetId === entry.datasetId ? currentDatasetName : optionLabel;
      const liveCtg = currentDatasetId === entry.datasetId
        ? liveSupportById.get(entry.assemblyCtgId) || null
        : null;
      if (!liveCtg) {
        return {
          ...entry,
          datasetName: entry.datasetName || fallbackDatasetName || `ds-${entry.datasetId}`,
          hits: Array.isArray(entry?.hits) ? entry.hits.map((hit) => ({ ...hit })) : [],
        };
      }
      const liveLength = Math.max(
        1,
        normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength ?? entry.lengthBp) ?? entry.lengthBp,
      );
      const liveStart = Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp ?? entry.startBp) ?? entry.startBp);
      return {
        ...entry,
        datasetName: entry.datasetName || fallbackDatasetName || `ds-${entry.datasetId}`,
        name: String(liveCtg?.name || entry.name || `Ctg${entry.assemblyCtgId}`),
        totalLength: Math.max(
          1,
          normalizePositiveInt(liveCtg?.totalLength ?? liveCtg?.lengthBp ?? entry.totalLength) ?? entry.totalLength,
        ),
        anchorStart: normalizeNonNegativeInt(liveCtg?.anchorStart ?? entry.anchorStart),
        lengthBp: liveLength,
        startBp: liveStart,
        endBp: Math.max(
          1,
          normalizePositiveInt(liveCtg?.endBp) ?? (liveStart + liveLength - 1),
        ),
        laneIndex: Math.max(0, normalizeNonNegativeInt(liveCtg?.laneIndex ?? entry.laneIndex) ?? entry.laneIndex),
        hits: Array.isArray(liveCtg?.hits)
          ? liveCtg.hits.map((hit) => ({ ...hit }))
        : (Array.isArray(entry?.hits) ? entry.hits.map((hit) => ({ ...hit })) : []),
      };
  });
}

function buildPhasedTrackItemHits(sourceCtg, totalLength, itemOrient) {
  return buildPhasedSubviewCtgHits({ sourceCtg, totalLength, itemOrient });
}

function buildPhasedTrackRows({ phasedChrTracks = [], primaryModel, activeHitsTrackKey = "primary", i18n }) {
  const primaryCtgs = Array.isArray(primaryModel?.ctgs) ? primaryModel.ctgs : [];
  const primaryById = new Map(
    primaryCtgs
      .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
      .filter(([ctgId]) => ctgId !== null),
  );
  return (Array.isArray(phasedChrTracks) ? phasedChrTracks : [])
    .map((track) => {
      const haplotypeKey = String(track?.haplotypeKey || "").trim();
      const label = String(track?.label || "").trim();
      if (!haplotypeKey) {
        return null;
      }
      const ctgs = (Array.isArray(track?.items) ? track.items : [])
        .map((item, index) => {
          const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId);
          const sourceCtg = primaryById.get(assemblyCtgId) || item?.sourceCtg || null;
          if (!sourceCtg || assemblyCtgId === null) {
            return null;
          }
          const totalLength = Math.max(
            1,
            normalizePositiveInt(sourceCtg.totalLength ?? sourceCtg.lengthBp) ?? 1,
          );
          const startBp = Math.max(
            0,
            normalizeNonNegativeInt(sourceCtg.startBp ?? sourceCtg.anchorStart) ?? 0,
          );
          const rawItemOrient = String(item?.orient || "").trim();
          const itemOrient = rawItemOrient === "-" || rawItemOrient === "+"
            ? rawItemOrient
            : resolveTrackCtgOrientValue(sourceCtg);
          return {
            ...sourceCtg,
            assemblyCtgId,
            orient: itemOrient,
            refOrient: itemOrient,
            ref_orient: itemOrient,
            phasedTrackId: Number(track?.phasedTrackId || 0),
            phasedTrackItemId: Number(item?.itemId || item?.phasedTrackItemId || 0),
            phasedHaplotypeKey: haplotypeKey,
            phasedInstanceKey: `${track?.phasedTrackId || haplotypeKey}:${item?.itemId || index}`,
            startBp,
            lengthBp: totalLength,
            totalLength,
            endBp: Math.max(1, startBp + totalLength - 1),
            laneIndex: 0,
            hits: buildPhasedTrackItemHits(sourceCtg, totalLength, itemOrient),
            isSelected: false,
          };
        })
        .filter(Boolean);
      const trackLabel = i18n.trackControls.phasedTrackLabel.replace(
        "{key}",
        label || haplotypeKey,
      );
      return {
        id: `phased-${haplotypeKey}`,
        role: "phased",
        interactiveRole: "phased",
        dragRole: "phased",
        label: trackLabel,
        trackModel: {
          ...(primaryModel || buildEmptyTrackModelLike()),
          ctgs,
          laneCount: 1,
        },
        selectable: true,
        emptyMessage: i18n.trackControls.phasedTrackEmpty,
        className: "is-phased-track",
        connectorDirection: "up",
        includeBands: String(activeHitsTrackKey) === haplotypeKey,
        datasetId: null,
        alignWithPrimary: true,
        phasedTrackId: Number(track?.phasedTrackId || 0),
        phasedHaplotypeKey: haplotypeKey,
      };
    })
    .filter(Boolean);
}

function buildSupportMirrorTrackRows(supportMirroredCtgs, i18n) {
  const grouped = new Map();
  normalizeSupportMirroredCtgs(supportMirroredCtgs).forEach((entry) => {
    const bucket = grouped.get(entry.datasetId) || [];
    bucket.push(entry);
    grouped.set(entry.datasetId, bucket);
  });
  return Array.from(grouped.entries())
    .map(([datasetId, ctgs]) => {
      const normalizedCtgs = ctgs
        .slice()
        .sort((left, right) => {
          if (left.startBp !== right.startBp) {
            return left.startBp - right.startBp;
          }
          if (left.lengthBp !== right.lengthBp) {
            return right.lengthBp - left.lengthBp;
          }
          return left.assemblyCtgId - right.assemblyCtgId;
        })
        .map((ctg) => ({
          ...ctg,
          laneIndex: Math.max(0, normalizeNonNegativeInt(ctg.laneIndex) ?? 0),
          lengthBp: Math.max(1, normalizePositiveInt(ctg.lengthBp ?? ctg.totalLength) ?? 1),
          startBp: Math.max(0, normalizeNonNegativeInt(ctg.startBp) ?? 0),
          endBp: Math.max(
            1,
            normalizePositiveInt(ctg.endBp)
              ?? (Math.max(0, normalizeNonNegativeInt(ctg.startBp) ?? 0)
                + Math.max(1, normalizePositiveInt(ctg.lengthBp ?? ctg.totalLength) ?? 1)
                - 1),
          ),
          hits: Array.isArray(ctg?.hits) ? ctg.hits.map((hit) => ({ ...hit })) : [],
          isSelected: false,
        }));
      const laneCount = normalizedCtgs.length
        ? Math.max(...normalizedCtgs.map((ctg) => Math.max(0, Number(ctg.laneIndex || 0)))) + 1
        : 1;
      const datasetName = String(
        ctgs.find((item) => String(item.datasetName || "").trim())?.datasetName
          || `ds-${datasetId}`,
      );
      return {
        id: `support-mirror-${datasetId}`,
        role: "support",
        interactiveRole: "support",
        dragRole: "support",
        label: i18n.trackControls.mirrorTrackLabelWithName.replace("{name}", datasetName),
        trackModel: {
          ...buildEmptyTrackModelLike(),
          ctgs: normalizedCtgs,
          laneCount,
        },
        selectable: true,
        emptyMessage: i18n.trackControls.mirrorTrackEmpty,
        className: "is-companion is-mirror-track",
        connectorDirection: "down",
        includeBands: false,
        datasetId,
        isMirror: true,
      };
    });
}

function resolveTrackDragOffsetPx(offsets, trackRole, assemblyCtgId, scaleContext = {}) {
  const targetKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId, scaleContext);
  const legacyKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId);
  const item = normalizeTrackDragOffsets(offsets).find(
    (entry) => {
      const entryKey = buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry);
      return entryKey === targetKey || entryKey === legacyKey;
    },
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return convertTrackOffsetBpToPx(item.offsetBp, scaleContext);
  }
  return Number.isFinite(Number(item.offsetPx)) ? Math.round(Number(item.offsetPx) * 100) / 100 : 0;
}

export function resolveTrackDragOffsetBp(offsets, trackRole, assemblyCtgId, scaleContext = {}) {
  const targetKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId, scaleContext);
  const legacyKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId);
  const item = normalizeTrackDragOffsets(offsets).find(
    (entry) => {
      const entryKey = buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry);
      return entryKey === targetKey || entryKey === legacyKey;
    },
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return Math.round(Number(item.offsetBp) * 100) / 100;
  }
  if (Number.isFinite(Number(item.offsetPx))) {
    return convertTrackOffsetPxToBp(item.offsetPx, scaleContext);
  }
  return 0;
}

function resolveSubviewTrackDragOffsetPx(offsets, slot, contigId, scaleContext = {}) {
  const targetKey = buildSubviewTrackDragOffsetKey(slot, contigId);
  const item = normalizeSubviewTrackDragOffsets(offsets).find(
    (entry) => buildSubviewTrackDragOffsetKey(entry.slot, entry.contigId) === targetKey,
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return convertTrackOffsetBpToPx(item.offsetBp, scaleContext);
  }
  return Number.isFinite(Number(item.offsetPx)) ? Math.round(Number(item.offsetPx) * 100) / 100 : 0;
}

export function resolveSubviewTrackDragOffsetBp(offsets, slot, contigId, scaleContext = {}) {
  const targetKey = buildSubviewTrackDragOffsetKey(slot, contigId);
  const item = normalizeSubviewTrackDragOffsets(offsets).find(
    (entry) => buildSubviewTrackDragOffsetKey(entry.slot, entry.contigId) === targetKey,
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return Math.round(Number(item.offsetBp) * 100) / 100;
  }
  if (Number.isFinite(Number(item.offsetPx))) {
    return convertTrackOffsetPxToBp(item.offsetPx, scaleContext);
  }
  return 0;
}
