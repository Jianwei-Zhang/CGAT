import {
  FINAL_PATH_GAP_BP,
  buildFinalPathCtgSegment,
  buildFinalPathEntry,
  buildFinalPathGapSegment,
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  normalizeFinalPathByChr,
  normalizeFinalPathViewMode,
  resolveCurrentFinalPathChrName,
  resolveFinalPathSegmentDisplayName,
} from "./final-path-state.js";
import { tAssembly } from "./i18n.js";
import {
  buildFinalPathTrackViewportKey,
  normalizeViewportScrollState,
} from "./scroll-position-state.js";

function normalizeTrackContigId(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function normalizePositiveInteger(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeRefOrient(value) {
  return normalizeString(value) === "-" ? "-" : "+";
}

function resolveOriginId(value) {
  return normalizeString(value);
}

function resolveTrackContigOriginId(assembly, ctgContext, ctg) {
  const directOriginId = resolveOriginId(ctg?.originId ?? ctg?.origin_id);
  if (directOriginId) {
    return directOriginId;
  }
  const targetId = normalizeTrackContigId(ctgContext?.assemblyCtgId ?? ctg?.assemblyCtgId);
  if (!targetId) {
    return "";
  }
  const targetDatasetId = normalizeTrackContigId(ctgContext?.datasetId ?? ctg?.datasetId);
  const pools = [
    Array.isArray(assembly?.supportChrCtgs) ? assembly.supportChrCtgs : [],
    Array.isArray(assembly?.supportMirroredCtgs) ? assembly.supportMirroredCtgs : [],
    Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [],
  ];
  for (const pool of pools) {
    const match = pool.find((candidate) => {
      const candidateId = normalizeTrackContigId(candidate?.assemblyCtgId);
      if (candidateId !== targetId) {
        return false;
      }
      if (!targetDatasetId) {
        return true;
      }
      const candidateDatasetId = normalizeTrackContigId(candidate?.datasetId);
      return candidateDatasetId === null || candidateDatasetId === targetDatasetId;
    });
    const candidateOriginId = resolveOriginId(match?.originId ?? match?.origin_id);
    if (candidateOriginId) {
      return candidateOriginId;
    }
  }
  return "";
}

function normalizeMovePlacement(value) {
  return normalizeString(value).toLowerCase() === "after" ? "after" : "before";
}

function resolveTrackContigFromAssembly(assembly, ctgContext) {
  const targetId = normalizeTrackContigId(ctgContext?.assemblyCtgId);
  if (!targetId) {
    return null;
  }
  const pools = [
    Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [],
    Array.isArray(assembly?.supportMirroredCtgs) ? assembly.supportMirroredCtgs : [],
    Array.isArray(assembly?.supportChrCtgs) ? assembly.supportChrCtgs : [],
    Array.isArray(assembly?.refTrackMembers) ? assembly.refTrackMembers : [],
  ];
  for (const pool of pools) {
    const match = pool.find((ctg) => normalizeTrackContigId(ctg?.assemblyCtgId) === targetId);
    if (match) {
      return match;
    }
  }
  return null;
}

function findDatasetNameById(initializer, datasetId) {
  const normalizedDatasetId = normalizeTrackContigId(datasetId);
  if (!normalizedDatasetId) {
    return "";
  }
  const datasets = Array.isArray(initializer?.datasets) ? initializer.datasets : [];
  const matched = datasets.find((item) => normalizeTrackContigId(item?.datasetId) === normalizedDatasetId);
  return normalizeString(matched?.label || matched?.name);
}

function resolveCurrentProjectPrimaryDatasetId(state) {
  const normalizedProjectId = normalizeTrackContigId(state?.session?.projectId);
  if (!normalizedProjectId) {
    return null;
  }
  const projects = Array.isArray(state?.initializer?.existingProjects)
    ? state.initializer.existingProjects
    : [];
  const matchedProject = projects.find((item) => normalizeTrackContigId(item?.projectId) === normalizedProjectId);
  return normalizeTrackContigId(matchedProject?.primaryDatasetId);
}

function resolveTrackContigDatasetName(state, ctgContext, ctg) {
  const ctgDatasetName = normalizeString(ctg?.datasetName);
  if (ctgDatasetName) {
    return ctgDatasetName;
  }
  const trackRole = normalizeString(ctgContext?.trackRole);
  const contextDatasetId = normalizeTrackContigId(ctgContext?.datasetId);
  const ctgDatasetId = normalizeTrackContigId(ctg?.datasetId);
  const fallbackPrimaryDatasetId = resolveCurrentProjectPrimaryDatasetId(state);
  const resolvedDatasetId = trackRole === "primary"
    ? (fallbackPrimaryDatasetId || contextDatasetId || ctgDatasetId)
    : (contextDatasetId || ctgDatasetId);
  return findDatasetNameById(state?.initializer, resolvedDatasetId);
}

function resolveDatasetNameForCandidate(state, ctg, poolType = "primary") {
  const existingDatasetName = normalizeString(ctg?.datasetName);
  if (existingDatasetName) {
    return existingDatasetName;
  }
  const datasetId = normalizeTrackContigId(ctg?.datasetId);
  if (datasetId) {
    return findDatasetNameById(state?.initializer, datasetId);
  }
  if (poolType === "primary") {
    return findDatasetNameById(state?.initializer, resolveCurrentProjectPrimaryDatasetId(state));
  }
  return "";
}

function resolveDisplayCtgName(datasetName, ctgName) {
  const normalizedDatasetName = normalizeString(datasetName);
  const normalizedCtgName = normalizeString(ctgName);
  if (!normalizedCtgName) {
    return "";
  }
  if (!normalizedDatasetName) {
    return normalizedCtgName;
  }
  const prefix = `${normalizedDatasetName}_`;
  if (normalizedCtgName.toLowerCase().startsWith(prefix.toLowerCase())) {
    return normalizedCtgName;
  }
  return `${prefix}${normalizedCtgName}`;
}

function resolveCtgNumericAlias(ctgName) {
  const matched = normalizeString(ctgName).match(/^ctg0*([1-9]\d*)$/i);
  if (!matched) {
    return "";
  }
  return String(Number(matched[1]));
}

function buildCandidateAliasSet(candidate) {
  const aliases = new Set();
  const displayName = normalizeString(candidate?.displayName).toLowerCase();
  const ctgName = normalizeString(candidate?.ctgName).toLowerCase();
  if (displayName) {
    aliases.add(displayName);
  }
  if (ctgName) {
    aliases.add(ctgName);
  }
  const numericAlias = resolveCtgNumericAlias(candidate?.ctgName);
  if (numericAlias) {
    aliases.add(numericAlias);
    aliases.add(`ctg${numericAlias}`);
  }
  return aliases;
}

function collectCurrentChrCtgCandidates(state) {
  const pools = [
    { items: Array.isArray(state?.assembly?.chrCtgs) ? state.assembly.chrCtgs : [], poolType: "primary" },
    { items: Array.isArray(state?.assembly?.supportChrCtgs) ? state.assembly.supportChrCtgs : [], poolType: "support" },
    { items: Array.isArray(state?.assembly?.supportMirroredCtgs) ? state.assembly.supportMirroredCtgs : [], poolType: "support" },
    { items: Array.isArray(state?.assembly?.refTrackMembers) ? state.assembly.refTrackMembers : [], poolType: "ref" },
  ];
  const result = [];
  const seen = new Set();
  pools.forEach(({ items, poolType }) => {
    items.forEach((ctg) => {
      const assemblyCtgId = normalizeTrackContigId(ctg?.assemblyCtgId);
      const overallLen = normalizePositiveInteger(ctg?.totalLength);
      if (!assemblyCtgId || !overallLen) {
        return;
      }
      const sourceKind = normalizeString(ctg?.sourceKind);
      const isRefSegment = poolType === "ref" || sourceKind === "ref_segment";
      const datasetName = isRefSegment ? "" : resolveDatasetNameForCandidate(state, ctg, poolType);
      const ctgName = isRefSegment
        ? resolveFinalPathSegmentDisplayName({
          type: "ctg",
          sourceKind: "ref_segment",
          referenceChrId: ctg?.referenceChrId,
          referenceChrName: ctg?.referenceChrName || state?.assembly?.selectedChrName,
          memberStartBp: ctg?.segmentStartBp,
          memberEndBp: ctg?.segmentEndBp,
          start: 1,
          end: overallLen,
        })
        : (normalizeString(ctg?.name) || `Ctg${assemblyCtgId}`);
      const key = `${assemblyCtgId}:${datasetName.toLowerCase()}:${ctgName.toLowerCase()}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      const candidate = {
        assemblyCtgId,
        sourceKind: isRefSegment ? "ref_segment" : "assembly_ctg",
        datasetName,
        ctgName,
        originId: isRefSegment
          ? (normalizeString(ctg?.referenceChrName || state?.assembly?.selectedChrName) || "")
          : resolveOriginId(ctg?.originId ?? ctg?.origin_id),
        overallLen,
        displayName: resolveDisplayCtgName(datasetName, ctgName),
      };
      if (isRefSegment) {
        candidate.referenceChrId = normalizeTrackContigId(ctg?.referenceChrId);
        candidate.referenceChrName = normalizeString(ctg?.referenceChrName || state?.assembly?.selectedChrName);
        candidate.memberStartBp = normalizePositiveInteger(ctg?.segmentStartBp);
        candidate.memberEndBp = normalizePositiveInteger(ctg?.segmentEndBp);
      }
      result.push(candidate);
    });
  });
  return result;
}

function resolveCandidateByInput(state, rawValue) {
  const normalizedValue = normalizeString(rawValue);
  if (!normalizedValue) {
    return { kind: "invalid", message: "Ctg 不能为空。" };
  }
  if (normalizedValue.toLowerCase() === "gap") {
    return { kind: "gap" };
  }
  const tokenLower = normalizedValue.toLowerCase();
  const candidates = collectCurrentChrCtgCandidates(state);
  const matches = candidates.filter((item) => buildCandidateAliasSet(item).has(tokenLower));
  if (matches.length === 1) {
    return { kind: "ctg", candidate: matches[0] };
  }
  if (matches.length > 1) {
    return { kind: "invalid", message: "Ctg 名称不唯一，请使用 dsName_CtgName。" };
  }
  return { kind: "invalid", message: `未找到 Ctg：${normalizedValue}` };
}

function getPrompt(overrides = {}) {
  if (typeof overrides.prompt === "function") {
    return overrides.prompt;
  }
  return (message, defaultValue = "") => globalThis.window?.prompt?.(message, defaultValue) ?? null;
}

function getAlert(overrides = {}) {
  if (typeof overrides.alert === "function") {
    return overrides.alert;
  }
  return (message) => {
    globalThis.window?.alert?.(message);
  };
}

function getPersistProjectAssemblyViewState(overrides = {}) {
  if (typeof overrides.persistProjectAssemblyViewState === "function") {
    return overrides.persistProjectAssemblyViewState;
  }
  throw new TypeError("Missing final path runtime dep: persistProjectAssemblyViewState");
}

function getRerender(overrides = {}) {
  if (typeof overrides.rerender === "function") {
    return overrides.rerender;
  }
  return () => {};
}

function getCurrentFinalPathContext(store, options = {}) {
  const state = store.getState();
  const chrName = normalizeString(options.targetChrName) || resolveCurrentFinalPathChrName(state?.assembly);
  if (!state?.session?.workspacePath || !state?.session?.projectId || !chrName) {
    return null;
  }
  const finalPathByChr = normalizeFinalPathByChr(state.assembly?.finalPathByChr);
  const currentEntry = finalPathByChr[chrName]
    || buildFinalPathEntry({
      chrName,
      segments: [],
      updatedAt: String(Math.floor(Date.now() / 1000)),
    });
  return {
    state,
    chrName,
    finalPathByChr,
    currentEntry,
  };
}

function captureCurrentFinalPathTrackScrollState(host, state) {
  const finalPathScrollEl =
    host?.querySelector?.("[data-final-path-graph-viewport]")
    || host?.querySelector?.(".assembly-final-path-svg-wrap");
  if (!finalPathScrollEl) {
    return normalizeViewportScrollState(state?.assembly?.finalPathTrackScrollState);
  }
  return normalizeViewportScrollState({
    viewportKey: buildFinalPathTrackViewportKey(state),
    scrollLeft: Number(finalPathScrollEl.scrollLeft || 0),
  });
}

function resolveNextSegmentId(segments) {
  const used = new Set(
    (Array.isArray(segments) ? segments : [])
      .map((segment) => normalizeString(segment?.segmentId))
      .filter((segmentId) => segmentId),
  );
  let index = 1;
  while (used.has(`seg-${index}`)) {
    index += 1;
  }
  return `seg-${index}`;
}

function findSegmentIndexById(segments, segmentId) {
  return (Array.isArray(segments) ? segments : []).findIndex(
    (segment) => normalizeString(segment?.segmentId) === normalizeString(segmentId),
  );
}

async function persistCurrentFinalPathByChr(host, store, nextFinalPathByChr, deps = {}, statusPatch = {}) {
  const state = store.getState();
  const nextFinalPathTrackScrollState = captureCurrentFinalPathTrackScrollState(host, state);
  store.setState({
    assembly: {
      ...state.assembly,
      finalPathTrackScrollState: nextFinalPathTrackScrollState,
    },
  });
  const currentState = store.getState();
  const persisted = await getPersistProjectAssemblyViewState(deps)({
    workspaceRoot: currentState.session.workspacePath,
    projectId: currentState.session.projectId,
    supportDatasetId: currentState.assembly.supportDatasetId,
    trackView: currentState.assembly.trackView,
    supportMirroredCtgs: currentState.assembly.supportMirroredCtgs,
    hiddenPrimaryCtgIds: currentState.assembly.hiddenPrimaryCtgIds,
    hiddenPrimaryCtgIdsByChr: currentState.assembly.hiddenPrimaryCtgIdsByChr,
    trackDragOffsets: currentState.assembly.trackDragOffsets,
    subviewTrackDragOffsets: currentState.assembly.subviewTrackDragOffsets,
    trackScrollState: currentState.assembly.trackScrollState,
    subviewTrackScrollState: currentState.assembly.subviewTrackScrollState,
    finalPathTrackScrollState: currentState.assembly.finalPathTrackScrollState,
    finalPathViewMode: normalizeFinalPathViewMode(currentState.assembly.finalPathViewMode),
    finalPathByChr: nextFinalPathByChr,
  });
  const normalizedPersistedFinalPathByChr = normalizeFinalPathByChr(
    persisted?.finalPathByChr ?? nextFinalPathByChr,
  );
  store.setState({
    assembly: {
      ...store.getState().assembly,
      finalPathByChr: normalizedPersistedFinalPathByChr,
      actionStatus: normalizeString(statusPatch.actionStatus),
      actionError: normalizeString(statusPatch.actionError),
    },
  });
  getRerender(deps)(host, store);
  return normalizedPersistedFinalPathByChr;
}

function setRuntimeError(host, store, deps, message) {
  const state = store.getState();
  store.setState({
    assembly: {
      ...state.assembly,
      actionStatus: "",
      actionError: normalizeString(message),
    },
  });
  getRerender(deps)(host, store);
}

function updateEntryBySegments(entry, chrName, segments, hiddenPrimaryCtgIds = []) {
  return buildFinalPathEntry({
    chrName,
    segments,
    updatedAt: String(Math.floor(Date.now() / 1000)),
    hiddenPrimaryCtgIds,
  });
}

async function persistCurrentEntrySegments(host, store, context, nextSegments, deps = {}, statusPatch = {}) {
  const { chrName, finalPathByChr, currentEntry } = context;
  const nextEntry = updateEntryBySegments(
    currentEntry,
    chrName,
    nextSegments,
    context?.state?.assembly?.hiddenPrimaryCtgIds || currentEntry?.hiddenPrimaryCtgIds || [],
  );
  const nextFinalPathByChr = {
    ...finalPathByChr,
    [chrName]: nextEntry,
  };
  const normalizedPersistedFinalPathByChr = await persistCurrentFinalPathByChr(
    host,
    store,
    nextFinalPathByChr,
    deps,
    statusPatch,
  );
  return normalizedPersistedFinalPathByChr[chrName] || null;
}

function buildTrackContigFinalPathSegment(state, ctgContext, ctg, segmentId) {
  const sourceKind = normalizeString(ctgContext?.sourceKind || ctg?.sourceKind);
  const overallLen = normalizePositiveInteger(ctg?.totalLength);
  if (!overallLen) {
    return null;
  }
  if (sourceKind === "ref_segment") {
    const referenceChrName = normalizeString(
      ctgContext?.referenceChrName
      || ctg?.referenceChrName
      || state?.assembly?.selectedChrName,
    );
    const memberStartBp = normalizePositiveInteger(
      ctgContext?.segmentStart
      ?? ctg?.segmentStartBp
      ?? ctg?.anchorStart,
    );
    const memberEndBp = normalizePositiveInteger(
      ctgContext?.segmentEnd
      ?? ctg?.segmentEndBp
      ?? (memberStartBp ? memberStartBp + overallLen - 1 : null),
    );
    if (!referenceChrName || !memberStartBp || !memberEndBp || memberEndBp < memberStartBp) {
      return null;
    }
    const orient = normalizeRefOrient(ctgContext?.refOrient ?? ctg?.refOrient ?? ctg?.ref_orient);
    const hasExplicitRange = ctgContext?.start != null || ctgContext?.end != null;
    const rangeStart = normalizePositiveInteger(ctgContext?.start);
    const rangeEnd = normalizePositiveInteger(ctgContext?.end);
    if (
      hasExplicitRange
      && (
        !rangeStart
        || !rangeEnd
        || rangeStart > overallLen
        || rangeEnd > overallLen
      )
    ) {
      return null;
    }
    const resolvedStart = rangeStart || 1;
    const resolvedEnd = rangeEnd || overallLen;
    return buildFinalPathCtgSegment({
      segmentId,
      sourceKind: "ref_segment",
      assemblyCtgId: ctg.assemblyCtgId,
      referenceChrId: normalizeTrackContigId(ctg?.referenceChrId),
      referenceChrName,
      memberStartBp,
      memberEndBp,
      datasetName: "",
      originId: referenceChrName,
      overallLen,
      start: orient === "-" ? resolvedEnd : resolvedStart,
      end: orient === "-" ? resolvedStart : resolvedEnd,
    });
  }
  const datasetName = resolveTrackContigDatasetName(state, ctgContext, ctg);
  const orient = normalizeRefOrient(
    ctgContext?.orient
      ?? ctgContext?.refOrient
      ?? ctg?.orient
      ?? ctg?.refOrient
      ?? ctg?.ref_orient,
  );
  const hasExplicitRange = ctgContext?.start != null || ctgContext?.end != null;
  const rangeStart = normalizePositiveInteger(ctgContext?.start);
  const rangeEnd = normalizePositiveInteger(ctgContext?.end);
  if (
    hasExplicitRange
    && (
      !rangeStart
      || !rangeEnd
      || rangeStart > overallLen
      || rangeEnd > overallLen
    )
  ) {
    return null;
  }
  const resolvedStart = rangeStart || 1;
  const resolvedEnd = rangeEnd || overallLen;
  return buildFinalPathCtgSegment({
    segmentId,
    sourceKind: "assembly_ctg",
    assemblyCtgId: ctg.assemblyCtgId,
    datasetName,
    ctgName: ctg.name || `Ctg${ctg.assemblyCtgId}`,
    originId: resolveTrackContigOriginId(state?.assembly, ctgContext, ctg),
    overallLen,
    start: orient === "-" ? resolvedEnd : resolvedStart,
    end: orient === "-" ? resolvedStart : resolvedEnd,
  });
}

export async function appendTrackContigToFinalPath(host, store, ctgContext, deps = {}, options = {}) {
  const context = getCurrentFinalPathContext(store, options);
  if (!context) {
    return null;
  }
  const { state, chrName, currentEntry } = context;
  const ctg = resolveTrackContigFromAssembly(state.assembly, ctgContext);
  if (!ctg) {
    return null;
  }
  const nextSegment = buildTrackContigFinalPathSegment(
    state,
    ctgContext,
    ctg,
    resolveNextSegmentId(currentEntry.segments),
  );
  if (!nextSegment) {
    return null;
  }
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    [...currentEntry.segments, nextSegment],
    deps,
    {
      actionStatus: tAssembly(state, "runtime.appendToPathDone", {
        chrName,
        ctgName: resolveFinalPathSegmentDisplayName(nextSegment),
      }),
      actionError: "",
    },
  );
}

export async function appendFinalPathRow(host, store, payload = {}, deps = {}) {
  if (payload && typeof payload === "object" && typeof payload.persistProjectAssemblyViewState === "function") {
    deps = payload;
    payload = {};
  }
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { currentEntry } = context;
  const nextSegmentId = resolveNextSegmentId(currentEntry.segments);
  const nextSegments = [
    ...currentEntry.segments,
    buildFinalPathGapSegment({
      segmentId: nextSegmentId,
      gapSizeBp: FINAL_PATH_GAP_BP,
    }),
  ];
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function createEmptyFinalPathRow(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { state, currentEntry } = context;
  if (Array.isArray(currentEntry.segments) && currentEntry.segments.length > 0) {
    return null;
  }
  const field = normalizeString(payload?.field).toLowerCase();
  const rawValue = normalizeString(payload?.value);
  if (field !== "ctg" || !rawValue) {
    return null;
  }
  const nextSegmentId = resolveNextSegmentId(currentEntry.segments);
  const updateResult = applyCtgCellUpdate(state, { segmentId: nextSegmentId }, rawValue);
  if (!updateResult.ok || !updateResult.segment) {
    setRuntimeError(host, store, deps, updateResult.error || "创建 final path 首行失败。");
    return null;
  }
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    [updateResult.segment],
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

function applyCtgCellUpdate(state, segment, value) {
  const resolved = resolveCandidateByInput(state, value);
  if (resolved.kind === "invalid") {
    return { ok: false, error: resolved.message };
  }
  if (resolved.kind === "gap") {
    return {
      ok: true,
      segment: buildFinalPathGapSegment({
        segmentId: segment.segmentId,
        gapSizeBp: FINAL_PATH_GAP_BP,
      }),
    };
  }
  const candidate = resolved.candidate;
  return {
    ok: true,
    segment: buildFinalPathCtgSegment({
      segmentId: segment.segmentId,
      type: "ctg",
      sourceKind: candidate.sourceKind || "assembly_ctg",
      assemblyCtgId: candidate.assemblyCtgId,
      referenceChrId: candidate.referenceChrId,
      referenceChrName: candidate.referenceChrName,
      memberStartBp: candidate.memberStartBp,
      memberEndBp: candidate.memberEndBp,
      datasetName: candidate.datasetName,
      ctgName: candidate.ctgName,
      originId: candidate.originId,
      overallLen: candidate.overallLen,
      start: 1,
      end: candidate.overallLen,
    }),
  };
}

function applyRangeCellUpdate(segment, field, value) {
  if (!isFinalPathCtgSegment(segment)) {
    return { ok: false, error: "Gap 行不支持修改 Start/End。" };
  }
  const overallLen = normalizePositiveInteger(segment.overallLen);
  if (!overallLen) {
    return { ok: false, error: "请先填写有效 Ctg。" };
  }
  const numericValue = normalizePositiveInteger(value);
  if (!numericValue) {
    return { ok: false, error: `${field === "start" ? "Start" : "End"} 必须是正整数。` };
  }
  const nextStart = field === "start" ? numericValue : normalizePositiveInteger(segment.start);
  const nextEnd = field === "end" ? numericValue : normalizePositiveInteger(segment.end);
  if (!nextStart || !nextEnd || nextStart > overallLen || nextEnd > overallLen) {
    return { ok: false, error: "Start/End 超出 Ctg 区间。" };
  }
  return {
    ok: true,
    segment: buildFinalPathCtgSegment({
      ...segment,
      start: nextStart,
      end: nextEnd,
      overallLen,
    }),
  };
}

function resolveFinalPathSegmentOrient(segment) {
  if (!isFinalPathCtgSegment(segment)) {
    return "";
  }
  const start = normalizePositiveInteger(segment.start);
  const end = normalizePositiveInteger(segment.end);
  if (!start || !end) {
    return "";
  }
  return start > end ? "-" : "+";
}

function applyOrientCellUpdate(segment, value) {
  if (!isFinalPathCtgSegment(segment)) {
    return { ok: false, error: "Gap 行不支持修改 orient。" };
  }
  const nextOrient = normalizeString(value);
  if (nextOrient !== "+" && nextOrient !== "-") {
    return { ok: false, error: "orient 只允许 + 或 -。" };
  }
  const currentOrient = resolveFinalPathSegmentOrient(segment);
  if (!currentOrient || currentOrient === nextOrient) {
    return { ok: true, segment };
  }
  return {
    ok: true,
    segment: buildFinalPathCtgSegment({
      ...segment,
      start: segment.end,
      end: segment.start,
    }),
  };
}

export async function updateFinalPathRow(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { state, currentEntry } = context;
  const segmentId = normalizeString(payload?.segmentId);
  const field = normalizeString(payload?.field).toLowerCase();
  if (!segmentId || !field) {
    return null;
  }
  const sourceIndex = findSegmentIndexById(currentEntry.segments, segmentId);
  if (sourceIndex < 0) {
    return null;
  }
  const sourceSegment = currentEntry.segments[sourceIndex];
  let updateResult = { ok: false, error: "不支持的更新字段。" };
  if (field === "ctg") {
    if (isFinalPathRefSegment(sourceSegment)) {
      updateResult = { ok: false, error: "Ref 片段名称不可修改。" };
    } else {
      updateResult = applyCtgCellUpdate(state, sourceSegment, payload?.value);
    }
  } else if (field === "start" || field === "end") {
    updateResult = applyRangeCellUpdate(sourceSegment, field, payload?.value);
  } else if (field === "orient") {
    updateResult = applyOrientCellUpdate(sourceSegment, payload?.value);
  }
  if (!updateResult.ok || !updateResult.segment) {
    setRuntimeError(host, store, deps, updateResult.error || "更新 final path 失败。");
    return null;
  }
  const nextSegments = [...currentEntry.segments];
  nextSegments[sourceIndex] = updateResult.segment;
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function removeFinalPathRow(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { currentEntry } = context;
  const segmentId = normalizeString(payload?.segmentId);
  if (!segmentId) {
    return null;
  }
  const nextSegments = currentEntry.segments.filter(
    (segment) => normalizeString(segment?.segmentId) !== segmentId,
  );
  if (nextSegments.length === currentEntry.segments.length) {
    return null;
  }
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function moveFinalPathRow(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { currentEntry } = context;
  const sourceSegmentId = normalizeString(payload?.sourceSegmentId);
  const targetSegmentId = normalizeString(payload?.targetSegmentId);
  if (!sourceSegmentId || !targetSegmentId || sourceSegmentId === targetSegmentId) {
    return null;
  }
  const sourceIndex = findSegmentIndexById(currentEntry.segments, sourceSegmentId);
  const targetIndex = findSegmentIndexById(currentEntry.segments, targetSegmentId);
  if (sourceIndex < 0 || targetIndex < 0) {
    return null;
  }
  const placement = normalizeMovePlacement(payload?.placement);
  const nextSegments = [...currentEntry.segments];
  const [moved] = nextSegments.splice(sourceIndex, 1);
  const insertIndex = placement === "after"
    ? (sourceIndex < targetIndex ? targetIndex : targetIndex + 1)
    : (sourceIndex < targetIndex ? Math.max(0, targetIndex - 1) : targetIndex);
  nextSegments.splice(insertIndex, 0, moved);
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function addFinalPathGapRelativeToSegment(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { currentEntry } = context;
  const segmentId = normalizeString(payload?.segmentId);
  const placement = normalizeMovePlacement(payload?.placement);
  if (!segmentId) {
    return null;
  }
  const sourceIndex = findSegmentIndexById(currentEntry.segments, segmentId);
  if (sourceIndex < 0) {
    return null;
  }
  const nextSegments = [...currentEntry.segments];
  nextSegments.splice(
    placement === "before" ? sourceIndex : sourceIndex + 1,
    0,
    buildFinalPathGapSegment({
      segmentId: resolveNextSegmentId(currentEntry.segments),
      gapSizeBp: FINAL_PATH_GAP_BP,
    }),
  );
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function addFinalPathContigRelativeToSegment(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { state, currentEntry } = context;
  const segmentId = normalizeString(payload?.segmentId);
  const placement = normalizeMovePlacement(payload?.placement);
  if (!segmentId) {
    return null;
  }
  const sourceIndex = findSegmentIndexById(currentEntry.segments, segmentId);
  if (sourceIndex < 0) {
    return null;
  }
  const rawValue = getPrompt(deps)(tAssembly(state, "runtime.finalPathAddCtgPrompt"), "");
  if (rawValue === null) {
    return null;
  }
  const resolved = resolveCandidateByInput(state, rawValue);
  if (resolved.kind !== "ctg" || !resolved.candidate) {
    setRuntimeError(host, store, deps, resolved.message || "添加 final path ctg 失败。");
    return null;
  }
  const candidate = resolved.candidate;
  const nextSegments = [...currentEntry.segments];
  nextSegments.splice(
    placement === "before" ? sourceIndex : sourceIndex + 1,
    0,
    buildFinalPathCtgSegment({
      segmentId: resolveNextSegmentId(currentEntry.segments),
      sourceKind: candidate.sourceKind || "assembly_ctg",
      assemblyCtgId: candidate.assemblyCtgId,
      referenceChrId: candidate.referenceChrId,
      referenceChrName: candidate.referenceChrName,
      memberStartBp: candidate.memberStartBp,
      memberEndBp: candidate.memberEndBp,
      datasetName: candidate.datasetName,
      ctgName: candidate.ctgName,
      originId: candidate.originId,
      overallLen: candidate.overallLen,
      start: 1,
      end: candidate.overallLen,
    }),
  );
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}

export async function flipFinalPathSegment(host, store, payload, deps = {}) {
  const context = getCurrentFinalPathContext(store, payload);
  if (!context) {
    return null;
  }
  const { currentEntry } = context;
  const segmentId = normalizeString(payload?.segmentId);
  if (!segmentId) {
    return null;
  }
  const sourceIndex = findSegmentIndexById(currentEntry.segments, segmentId);
  if (sourceIndex < 0) {
    return null;
  }
  const sourceSegment = currentEntry.segments[sourceIndex];
  if (!isFinalPathCtgSegment(sourceSegment)) {
    return null;
  }
  const nextSegments = [...currentEntry.segments];
  nextSegments[sourceIndex] = buildFinalPathCtgSegment({
    ...sourceSegment,
    start: sourceSegment.end,
    end: sourceSegment.start,
  });
  return persistCurrentEntrySegments(
    host,
    store,
    context,
    nextSegments,
    deps,
    {
      actionStatus: "",
      actionError: "",
    },
  );
}
