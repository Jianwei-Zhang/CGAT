import { areFinalPathEntriesSemanticallyEqual } from "./final-path-state.js";

const DISPLAY_SCOPES = new Set(["main", "subview"]);

function normalizeString(value) {
  return String(value ?? "").trim();
}

function normalizePositiveInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function resolveSourceRange(segment) {
  const source = segment?.source && typeof segment.source === "object" ? segment.source : {};
  const first = normalizePositiveInteger(source.start ?? segment?.start);
  const second = normalizePositiveInteger(source.end ?? segment?.end);
  if (!first || !second) {
    return null;
  }
  return {
    start: Math.min(first, second),
    end: Math.max(first, second),
  };
}

function resolveSegmentOrientation(segment) {
  return normalizeString(segment?.source?.orientation || segment?.orient) === "-" ? "-" : "+";
}

function buildSourceInterval(segment, pathOrder) {
  if (!segment || segment.type === "gap" || normalizeString(segment.kind) === "gap") {
    return null;
  }
  const sourceRange = resolveSourceRange(segment);
  const assemblyCtgId = normalizePositiveInteger(
    segment.assemblyCtgId ?? segment.assembly_ctg_id,
  );
  const assemblySourceStart = normalizePositiveInteger(
    segment.assemblySourceStart ?? segment.assembly_source_start,
  );
  const assemblySourceEnd = normalizePositiveInteger(
    segment.assemblySourceEnd ?? segment.assembly_source_end,
  );
  if (
    !sourceRange
    || !assemblyCtgId
    || !assemblySourceStart
    || !assemblySourceEnd
    || assemblySourceStart > sourceRange.start
    || assemblySourceEnd < sourceRange.end
  ) {
    return null;
  }
  const orientation = resolveSegmentOrientation(segment);
  return {
    segmentId: normalizeString(segment.segmentId || segment.segment_id) || `segment-${pathOrder + 1}`,
    pathOrder,
    datasetName: normalizeString(segment?.source?.dataset || segment.datasetName),
    contigName: normalizeString(segment?.source?.contig || segment.originId || segment.ctgName),
    assemblyCtgId,
    assemblySourceStart,
    assemblySourceEnd,
    sourceStart: sourceRange.start,
    sourceEnd: sourceRange.end,
    orientation,
    entrySourcePosition: orientation === "-" ? sourceRange.end : sourceRange.start,
    exitSourcePosition: orientation === "-" ? sourceRange.start : sourceRange.end,
  };
}

function isContinuousSourceInterval(left, right, gapSizeBp) {
  if (!left || !right || gapSizeBp > 0) {
    return false;
  }
  if (
    left.datasetName !== right.datasetName
    || left.contigName !== right.contigName
    || left.assemblyCtgId !== right.assemblyCtgId
    || left.orientation !== right.orientation
  ) {
    return false;
  }
  if (left.orientation === "-") {
    return left.sourceStart - 1 === right.sourceEnd;
  }
  return left.sourceEnd + 1 === right.sourceStart;
}

function mergeContinuousIntervals(intervals, junctions) {
  const continuousRightOrders = new Set(
    junctions.filter((junction) => junction.kind === "continuous").map((junction) => junction.right.pathOrder),
  );
  const merged = [];
  intervals.forEach((interval) => {
    const previous = merged[merged.length - 1];
    if (previous && continuousRightOrders.has(interval.pathOrder)) {
      previous.sourceStart = Math.min(previous.sourceStart, interval.sourceStart);
      previous.sourceEnd = Math.max(previous.sourceEnd, interval.sourceEnd);
      previous.exitSourcePosition = interval.exitSourcePosition;
      previous.segmentIds.push(interval.segmentId);
      return;
    }
    merged.push({
      ...interval,
      segmentIds: [interval.segmentId],
    });
  });
  return merged;
}

function clusterOverlappingIntervals(intervals) {
  const byCtg = new Map();
  intervals.forEach((interval) => {
    const key = `${interval.assemblyCtgId}:${interval.orientation}`;
    const values = byCtg.get(key) || [];
    values.push(interval);
    byCtg.set(key, values);
  });
  return [...byCtg.values()].flatMap((values) => {
    values.sort((left, right) => left.sourceStart - right.sourceStart || left.pathOrder - right.pathOrder);
    const clusters = [];
    values.forEach((interval) => {
      const previous = clusters[clusters.length - 1];
      if (previous && interval.sourceStart <= previous.sourceEnd) {
        previous.sourceEnd = Math.max(previous.sourceEnd, interval.sourceEnd);
        previous.occurrences.push(interval);
        return;
      }
      clusters.push({
        assemblyCtgId: interval.assemblyCtgId,
        assemblySourceStart: interval.assemblySourceStart,
        assemblySourceEnd: interval.assemblySourceEnd,
        sourceStart: interval.sourceStart,
        sourceEnd: interval.sourceEnd,
        orientation: interval.orientation,
        datasetName: interval.datasetName,
        contigName: interval.contigName,
        occurrences: [interval],
      });
    });
    return clusters;
  });
}

export function normalizeGrtResultDisplayByChr(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const result = {};
  Object.entries(source).forEach(([rawChrName, rawState]) => {
    const chrName = normalizeString(rawChrName);
    if (!chrName) {
      return;
    }
    const state = rawState && typeof rawState === "object" && !Array.isArray(rawState)
      ? rawState
      : {};
    result[chrName] = {
      main: state.main === true,
      subview: state.subview === true,
    };
  });
  return result;
}

export function setGrtResultDisplayEnabled(value, chrName, scope, enabled) {
  const normalizedChrName = normalizeString(chrName);
  const normalizedScope = normalizeString(scope);
  const current = normalizeGrtResultDisplayByChr(value);
  if (!normalizedChrName || !DISPLAY_SCOPES.has(normalizedScope)) {
    return current;
  }
  return {
    ...current,
    [normalizedChrName]: {
      main: current[normalizedChrName]?.main === true,
      subview: current[normalizedChrName]?.subview === true,
      [normalizedScope]: enabled === true,
    },
  };
}

export function resolveGrtResultContext(assembly) {
  const chrName = normalizeString(assembly?.selectedChrName);
  const baselineEntry = assembly?.grtProjectView?.baselineFinalPathByChr?.[chrName] || null;
  const currentEntry = assembly?.finalPathByChr?.[chrName] || null;
  const displayState = normalizeGrtResultDisplayByChr(assembly?.grtResultDisplayByChr)[chrName]
    || { main: false, subview: false };
  const available = Boolean(
    chrName
    && ["2", "3"].includes(
      normalizeString(assembly?.grtProjectView?.recipe?.finalPathSchemaVersion),
    )
    && baselineEntry?.grtDisplayAvailable === true
    && assembly?.isChrPhased !== true
    && areFinalPathEntriesSemanticallyEqual(currentEntry, baselineEntry),
  );
  return {
    chrName,
    baselineEntry,
    currentEntry,
    available,
    mainEnabled: available && displayState.main,
    subviewEnabled: available && displayState.subview,
  };
}

export function buildGrtResultPlan(entry) {
  const segments = Array.isArray(entry?.segments) ? entry.segments : [];
  const intervals = [];
  const junctions = [];
  let previous = null;
  let pendingGapSizeBp = 0;
  segments.forEach((segment, pathOrder) => {
    if (segment?.type === "gap" || normalizeString(segment?.kind) === "gap") {
      pendingGapSizeBp += normalizePositiveInteger(segment.gapSizeBp ?? segment.length) || 0;
      return;
    }
    const interval = buildSourceInterval(segment, pathOrder);
    if (!interval) {
      return;
    }
    intervals.push(interval);
    if (previous) {
      junctions.push({
        kind: pendingGapSizeBp > 0
          ? "gap"
          : isContinuousSourceInterval(previous, interval, pendingGapSizeBp)
            ? "continuous"
            : "link",
        gapSizeBp: pendingGapSizeBp,
        left: previous,
        right: interval,
      });
    }
    previous = interval;
    pendingGapSizeBp = 0;
  });
  const visualIntervals = clusterOverlappingIntervals(
    mergeContinuousIntervals(intervals, junctions),
  );
  return {
    intervals,
    visualIntervals,
    junctions: junctions.filter((junction) => junction.kind !== "continuous"),
    displayEvidence: Array.isArray(entry?.displayEvidence) ? entry.displayEvidence : [],
  };
}

export function projectGrtSourcePositionToCtg(position, interval, ctgOrientation = "+") {
  const sourcePosition = normalizePositiveInteger(position);
  const sourceStart = normalizePositiveInteger(interval?.assemblySourceStart);
  const sourceEnd = normalizePositiveInteger(interval?.assemblySourceEnd);
  if (!sourcePosition || !sourceStart || !sourceEnd || sourcePosition < sourceStart || sourcePosition > sourceEnd) {
    return null;
  }
  return normalizeString(ctgOrientation) === "-"
    ? sourceEnd - sourcePosition + 1
    : sourcePosition - sourceStart + 1;
}

export function projectGrtSourcePositionToRect(position, interval, ctg, rect) {
  const ctgLength = normalizePositiveInteger(ctg?.lengthBp ?? ctg?.totalLength);
  const width = Number(rect?.width);
  const x = Number(rect?.x);
  if (!ctgLength || !Number.isFinite(width) || !Number.isFinite(x)) {
    return null;
  }
  const ctgPosition = projectGrtSourcePositionToCtg(position, interval, ctg?.orient);
  if (!ctgPosition) {
    return null;
  }
  return x + ((ctgPosition - 1) / Math.max(1, ctgLength)) * width;
}
