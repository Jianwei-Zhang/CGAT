import {
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  resolveFinalPathSegmentDisplayName,
} from "./final-path-state.js";

export const MANUAL_REFINEMENT_GAP_TOOLS = Object.freeze([
  "degap",
  "lrgapcloser",
  "tgsgapcloser",
  "quartet",
]);

export const MANUAL_REFINEMENT_TOOL_LABELS = Object.freeze({
  degap: "DEGAP",
  lrgapcloser: "LR_Gapcloser",
  tgsgapcloser: "TGS-GapCloser",
  quartet: "quarTeT",
});

export const MANUAL_REFINEMENT_TEL_TOOLS = Object.freeze(["degap"]);

export const MANUAL_REFINEMENT_SETTINGS_TABS = Object.freeze([
  "degap",
  "lrgapcloser",
  "tgsgapcloser",
  "quartet",
  "reads",
]);

export const TGS_HIFI_MINIMAP_OPTIONS = Object.freeze([
  "-x asm20",
  "-x asm5",
  "-x asm10",
  "-x map-hifi",
  "-x map-pb",
]);

export const TGS_ONT_MINIMAP_OPTIONS = Object.freeze([
  "-x ava-ont",
  "-x map-ont",
  "-x asm20",
  "-x asm10",
]);

export const QUARTET_MINIMAP_OPTIONS = Object.freeze([
  "-x asm5",
  "-x asm10",
  "-x asm20",
  "-x map-hifi",
  "-x map-ont",
]);

export const TGS_CORRECTION_OPTIONS = Object.freeze([
  "none",
  "native_racon",
]);

export const DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS = Object.freeze({
  degap: Object.freeze({
    max_extension_rounds: 10,
    max_extension_bp: 500000,
    kmer_filter: true,
    kmer_size: 41,
    kmer_num: 20,
    edge: 500,
    filter_depth_hifi: null,
    filter_depth_ont: null,
    tel_n: 100,
    tel_r: 0.6,
    tel_mm: 0,
  }),
  lrgapcloser: Object.freeze({
    iterations: 3,
    tag_partitions: 1,
  }),
  tgsgapcloser: Object.freeze({
    hifi_correction: "none",
    hifi_racon_rounds: 1,
    hifi_minimap: "-x asm20",
    ont_correction: "native_racon",
    ont_racon_rounds: 1,
    ont_minimap: "-x ava-ont",
  }),
  quartet: Object.freeze({
    minimap: "-x asm5",
  }),
});

function normalizeString(value) {
  return String(value ?? "").trim();
}

function normalizeBoundedInt(value, min, max, fallback) {
  if (typeof value === "boolean" || value === "" || value === null || value === undefined) {
    return fallback;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  const truncated = Math.trunc(numeric);
  if (truncated < min || truncated > max) {
    return fallback;
  }
  return truncated;
}

function normalizeDegapLimit(value, min, max, fallback) {
  if (normalizeString(value).toLowerCase() === "unlimited") {
    return "unlimited";
  }
  return normalizeBoundedInt(value, min, max, fallback);
}

function normalizeOptionalRatio(value) {
  if (typeof value === "boolean" || value === "" || value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || !(numeric > 0 && numeric < 1)) {
    return null;
  }
  return Math.round(numeric * 10000) / 10000;
}

function normalizeBoundedFloat(value, min, max, fallback) {
  if (typeof value === "boolean" || value === "" || value === null || value === undefined) {
    return fallback;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < min || numeric > max) {
    return fallback;
  }
  return Math.round(numeric * 10000) / 10000;
}

function normalizeAllowedOption(value, options, fallback) {
  const text = normalizeString(value);
  return options.includes(text) ? text : fallback;
}

export function normalizeManualRefinementToolParams(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const dSrc = source.degap && typeof source.degap === "object" ? source.degap : {};
  const lrSrc = source.lrgapcloser && typeof source.lrgapcloser === "object" ? source.lrgapcloser : {};
  const tgsSrc = source.tgsgapcloser && typeof source.tgsgapcloser === "object" ? source.tgsgapcloser : {};
  const qSrc = source.quartet && typeof source.quartet === "object" ? source.quartet : {};

  const dDef = DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS.degap;
  const lrDef = DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS.lrgapcloser;
  const tgsDef = DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS.tgsgapcloser;
  const qDef = DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS.quartet;

  return {
    degap: {
      max_extension_rounds: normalizeDegapLimit(dSrc.max_extension_rounds, 1, 1000, dDef.max_extension_rounds),
      max_extension_bp: normalizeDegapLimit(dSrc.max_extension_bp, 1000, 100000000, dDef.max_extension_bp),
      kmer_filter: dSrc.kmer_filter === false ? false : true,
      kmer_size: normalizeBoundedInt(dSrc.kmer_size, 11, 127, dDef.kmer_size),
      kmer_num: normalizeBoundedInt(dSrc.kmer_num, 1, 1000, dDef.kmer_num),
      edge: normalizeBoundedInt(dSrc.edge, 50, 50000, dDef.edge),
      filter_depth_hifi: normalizeOptionalRatio(dSrc.filter_depth_hifi),
      filter_depth_ont: normalizeOptionalRatio(dSrc.filter_depth_ont),
      tel_n: normalizeBoundedInt(dSrc.tel_n, 10, 10000, dDef.tel_n),
      tel_r: normalizeBoundedFloat(dSrc.tel_r, 0.01, 1.0, dDef.tel_r),
      tel_mm: Number(dSrc.tel_mm) === 1 ? 1 : 0,
    },
    lrgapcloser: {
      iterations: normalizeBoundedInt(lrSrc.iterations, 1, 20, lrDef.iterations),
      tag_partitions: normalizeBoundedInt(lrSrc.tag_partitions, 1, 16, lrDef.tag_partitions),
    },
    tgsgapcloser: {
      hifi_correction: normalizeAllowedOption(tgsSrc.hifi_correction, TGS_CORRECTION_OPTIONS, tgsDef.hifi_correction),
      hifi_racon_rounds: normalizeBoundedInt(tgsSrc.hifi_racon_rounds, 1, 5, tgsDef.hifi_racon_rounds),
      hifi_minimap: normalizeAllowedOption(tgsSrc.hifi_minimap, TGS_HIFI_MINIMAP_OPTIONS, tgsDef.hifi_minimap),
      ont_correction: normalizeAllowedOption(tgsSrc.ont_correction, TGS_CORRECTION_OPTIONS, tgsDef.ont_correction),
      ont_racon_rounds: normalizeBoundedInt(tgsSrc.ont_racon_rounds, 1, 5, tgsDef.ont_racon_rounds),
      ont_minimap: normalizeAllowedOption(tgsSrc.ont_minimap, TGS_ONT_MINIMAP_OPTIONS, tgsDef.ont_minimap),
    },
    quartet: {
      minimap: normalizeAllowedOption(qSrc.minimap, QUARTET_MINIMAP_OPTIONS, qDef.minimap),
    },
  };
}

export function buildManualRefinementToolParametersPayload(toolParams) {
  const normalized = normalizeManualRefinementToolParams(toolParams);
  const payload = {};
  for (const tool of MANUAL_REFINEMENT_GAP_TOOLS) {
    const defaults = DEFAULT_MANUAL_REFINEMENT_TOOL_PARAMS[tool];
    const current = normalized[tool];
    const diff = {};
    for (const [key, defaultValue] of Object.entries(defaults)) {
      if (current[key] !== defaultValue) {
        diff[key] = current[key];
      }
    }
    if (Object.keys(diff).length > 0) {
      payload[tool] = diff;
    }
  }
  return Object.keys(payload).length > 0 ? payload : null;
}

export function isToolParamBlockCustomized(tool, toolParams) {
  if (!MANUAL_REFINEMENT_GAP_TOOLS.includes(tool)) {
    return false;
  }
  const payload = buildManualRefinementToolParametersPayload(toolParams);
  return Boolean(payload?.[tool]);
}

export function hasCustomManualRefinementToolParams(toolParams) {
  return buildManualRefinementToolParametersPayload(toolParams) !== null;
}

export function normalizeManualRefinementKind(value) {
  const normalized = normalizeString(value).toLowerCase();
  if (normalized === "gap" || normalized === "tel_left" || normalized === "tel_right") {
    return normalized;
  }
  return "";
}

export function normalizeManualRefinementMotif(value) {
  const upper = normalizeString(value).toUpperCase();
  return upper && /^[ACGT]+$/.test(upper) ? upper : "";
}

// Older drafts used a scalar tool; the current task keeps the entire selection.
export function normalizeManualRefinementTools(value, kind = "gap") {
  if (kind !== "gap") return ["degap"];
  const values = (Array.isArray(value) ? value : [value]).map((v) => normalizeString(v).toLowerCase());
  const tools = MANUAL_REFINEMENT_GAP_TOOLS.filter((tool) => values.includes(tool));
  return tools.length ? tools : ["degap"];
}

export function normalizeManualRefinementExportScope(scope) {
  const normalized = normalizeString(scope).toLowerCase();
  if (
    normalized === "current-chr"
    || normalized === "refinement-current-chr"
    || normalized === "current_chr"
    || normalized === "refine-jobs"
  ) {
    return "current-chr";
  }
  return "all";
}

export function buildManualRefinementLocusKey({ chr, kind, segmentId, segment_id }) {
  const normalizedChr = normalizeString(chr);
  const normalizedKind = normalizeManualRefinementKind(kind);
  const normalizedSegmentId = normalizeString(segmentId || segment_id);
  if (!normalizedChr || !normalizedKind || !normalizedSegmentId) {
    return "";
  }
  return `${normalizedChr}\t${normalizedKind}\t${normalizedSegmentId}`;
}

export function normalizeManualRefinementLocus(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const chr = normalizeString(value.chr);
  const kind = normalizeManualRefinementKind(value.kind);
  const segmentId = normalizeString(value.segmentId || value.segment_id);
  if (!chr || !kind || !segmentId) {
    return null;
  }
  const motif = kind === "gap" ? "" : normalizeString(value.motif).toUpperCase();
  const tools = normalizeManualRefinementTools(value.tools ?? value.tool, kind);
  return {
    locusKey: buildManualRefinementLocusKey({ chr, kind, segmentId }),
    chr,
    kind,
    segmentId,
    label: normalizeString(value.label),
    tool: tools[0],
    tools,
    motif,
  };
}

export function countManualRefinementJobs(loci) {
  return (Array.isArray(loci) ? loci : []).reduce((total, locus) => {
    const normalized = normalizeManualRefinementLocus(locus);
    if (!normalized) {
      return total;
    }
    return total + (normalized.kind === "gap" ? normalized.tools.length : 1);
  }, 0);
}

export function hasManualRefinementJob(loci, { chr, kind, segmentId, segment_id, tool = "degap" } = {}) {
  const locusKey = buildManualRefinementLocusKey({ chr, kind, segmentId, segment_id });
  if (!locusKey) {
    return false;
  }
  const matched = (Array.isArray(loci) ? loci : [])
    .map(normalizeManualRefinementLocus)
    .find((item) => item && item.locusKey === locusKey);
  if (!matched) {
    return false;
  }
  if (matched.kind !== "gap") {
    return true;
  }
  const normalizedTool = normalizeString(tool).toLowerCase();
  return matched.tools.includes(normalizedTool);
}

export function addManualRefinementGapTool(loci, candidate, tool = "degap") {
  const list = (Array.isArray(loci) ? loci : []).map(normalizeManualRefinementLocus).filter(Boolean);
  const normalizedCandidate = normalizeManualRefinementLocus(candidate);
  const requestedTool = MANUAL_REFINEMENT_GAP_TOOLS.includes(normalizeString(tool).toLowerCase())
    ? normalizeString(tool).toLowerCase()
    : "degap";
  if (!normalizedCandidate || normalizedCandidate.kind !== "gap") {
    return { loci: list, added: false, duplicate: false, tool: requestedTool };
  }
  const existingIndex = list.findIndex((item) => item.locusKey === normalizedCandidate.locusKey);
  if (existingIndex >= 0) {
    const existing = list[existingIndex];
    if (existing.tools.includes(requestedTool)) {
      return { loci: list, added: false, duplicate: true, tool: requestedTool };
    }
    const nextTools = normalizeManualRefinementTools([...existing.tools, requestedTool], "gap");
    const next = list.map((item, idx) => (
      idx === existingIndex
        ? normalizeManualRefinementLocus({ ...item, label: item.label || normalizedCandidate.label, tools: nextTools })
        : item
    ));
    return { loci: next, added: true, duplicate: false, tool: requestedTool };
  }
  const nextLocus = normalizeManualRefinementLocus({
    ...normalizedCandidate,
    tool: requestedTool,
    tools: [requestedTool],
  });
  return { loci: [...list, nextLocus], added: true, duplicate: false, tool: requestedTool };
}

export function removeManualRefinementGapTool(loci, locusKey, tool) {
  const normalizedKey = normalizeString(locusKey);
  const normalizedTool = normalizeString(tool).toLowerCase();
  const list = (Array.isArray(loci) ? loci : []).map(normalizeManualRefinementLocus).filter(Boolean);
  const next = [];
  for (const item of list) {
    if (item.locusKey !== normalizedKey || item.kind !== "gap") {
      next.push(item);
      continue;
    }
    const remaining = item.tools.filter((id) => id !== normalizedTool);
    if (remaining.length > 0) {
      next.push(normalizeManualRefinementLocus({ ...item, tools: remaining }));
    }
  }
  return next;
}

function normalizeExportedBatch(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const batchSha256 = normalizeString(value.batchSha256 || value.batch_sha256);
  if (!batchSha256) {
    return null;
  }
  const loci = (Array.isArray(value.loci) ? value.loci : [])
    .map(normalizeManualRefinementLocus)
    .filter(Boolean);
  const lociCount = Number.isInteger(Number(value.lociCount ?? value.loci))
    ? Number(value.lociCount ?? value.loci)
    : loci.length;
  const tasksCount = Number.isInteger(Number(value.tasksCount ?? value.tasks))
    ? Number(value.tasksCount ?? value.tasks)
    : loci.reduce((count, locus) => count + locus.tools.length, 0);
  return {
    batchSha256,
    exportedAt: normalizeString(value.exportedAt || value.exported_at),
    outputPath: normalizeString(value.outputPath || value.output_path),
    outputFileName: normalizeString(value.outputFileName) || extractFileName(value.outputPath || value.output_path) || "refinement_tasks.zip",
    scope: normalizeManualRefinementExportScope(value.scope),
    chrName: normalizeString(value.chrName),
    lociCount: Math.max(0, lociCount),
    tasksCount: Math.max(0, tasksCount),
    readsMode: value.readsMode === "override" ? "override" : "inherit",
    loci,
    status: "exported_awaiting_server",
  };
}

export function normalizeManualRefinementState(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const seenLoci = new Set();
  const loci = (Array.isArray(source.loci) ? source.loci : [])
    .map(normalizeManualRefinementLocus)
    .filter((item) => {
      if (!item || seenLoci.has(item.locusKey)) {
        return false;
      }
      seenLoci.add(item.locusKey);
      return true;
    })
    .sort(compareManualRefinementLoci);
  const seenBatches = new Set();
  const exportedBatches = (Array.isArray(source.exportedBatches) ? source.exportedBatches : [])
    .map(normalizeExportedBatch)
    .filter((item) => {
      if (!item || seenBatches.has(item.batchSha256)) {
        return false;
      }
      seenBatches.add(item.batchSha256);
      return true;
    })
    .slice(0, 20);
  const toolParams = normalizeManualRefinementToolParams(source.toolParams ?? source.tool_parameters);
  return {
    loci,
    readsMode: source.readsMode === "override" ? "override" : "inherit",
    hifiReadsInput: normalizeString(source.hifiReadsInput),
    ontReadsInput: normalizeString(source.ontReadsInput),
    toolParams,
    panelOpen: typeof source.panelOpen === "boolean" ? source.panelOpen : (loci.length > 0 || Boolean(source.lastExport)),
    settingsOpen: source.settingsOpen === true,
    settingsTab: MANUAL_REFINEMENT_SETTINGS_TABS.includes(source.settingsTab) ? source.settingsTab : "degap",
    viewScope: source.viewScope === "all" ? "all" : "current-chr",
    receiptDismissed: source.receiptDismissed === true,
    exporting: source.exporting === true,
    feedback: normalizeString(source.feedback),
    error: normalizeString(source.error),
    lastExport: normalizeExportedBatch(source.lastExport),
    exportedBatches,
  };
}

export function buildManualRefinementStateForPersistence(value) {
  const normalized = normalizeManualRefinementState(value);
  const customToolParams = buildManualRefinementToolParametersPayload(normalized.toolParams);
  if (
    !normalized.loci.length
    && !normalized.exportedBatches.length
    && normalized.readsMode === "inherit"
    && !customToolParams
  ) {
    return null;
  }
  return {
    loci: normalized.loci,
    readsMode: normalized.readsMode,
    hifiReadsInput: normalized.readsMode === "override" ? normalized.hifiReadsInput : "",
    ontReadsInput: normalized.readsMode === "override" ? normalized.ontReadsInput : "",
    ...(customToolParams ? { toolParams: normalized.toolParams } : {}),
    exportedBatches: normalized.exportedBatches,
  };
}

function compareManualRefinementLoci(left, right) {
  const chrDelta = left.chr.localeCompare(right.chr, undefined, { numeric: true });
  if (chrDelta) {
    return chrDelta;
  }
  const kindOrder = { tel_left: 0, gap: 1, tel_right: 2 };
  const kindDelta = (kindOrder[left.kind] ?? 9) - (kindOrder[right.kind] ?? 9);
  if (kindDelta) {
    return kindDelta;
  }
  return left.segmentId.localeCompare(right.segmentId);
}

export function extractFileName(filePath) {
  const text = normalizeString(filePath);
  if (!text) {
    return "";
  }
  const parts = text.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || text;
}

export function buildManualRefinementServerCommand(outputPath) {
  const zipName = extractFileName(outputPath) || "refinement_tasks.zip";
  const argument = zipName.startsWith("-") ? `./${zipName}` : zipName;
  const quoted = /^[A-Za-z0-9_./-]+$/.test(argument) ? argument : `'${argument.replaceAll("'", "'\"'\"'")}'`;
  return `python .lib/tools/refine.py ${quoted}`;
}

export function buildManualRefinementExportBaseName({ projectName = "", chrName = "", scope = "all" } = {}) {
  const normalizedProject = normalizeString(projectName) || "project";
  const normalizedScope = normalizeManualRefinementExportScope(scope);
  const normalizedChr = normalizeString(chrName);
  if (normalizedScope === "current-chr" && normalizedChr) {
    return `${normalizedProject}_${normalizedChr}_refinement_tasks`;
  }
  return `${normalizedProject}_all_refinement_tasks`;
}

export function filterManualRefinementLociByScope(loci, { scope = "all", chrName = "" } = {}) {
  const list = (Array.isArray(loci) ? loci : [])
    .map(normalizeManualRefinementLocus)
    .filter(Boolean);
  const normalizedScope = normalizeManualRefinementExportScope(scope);
  if (normalizedScope === "current-chr") {
    const normalizedChr = normalizeString(chrName);
    return normalizedChr ? list.filter((item) => item.chr === normalizedChr) : [];
  }
  return list;
}

export function parseServerReadPathList(rawText) {
  const text = normalizeString(rawText);
  if (!text) {
    return [];
  }
  return text
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function isServerAbsolutePath(pathValue) {
  return pathValue.startsWith("/") && pathValue.length > 1;
}

export function resolveManualRefinementGapCandidate(finalPathEntry, segmentId, tool = "degap") {
  const chr = normalizeString(finalPathEntry?.chrName);
  const targetId = normalizeString(segmentId);
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  if (!chr || !targetId || segments.length < 3) {
    return null;
  }
  const index = segments.findIndex(
    (segment, idx) => (normalizeString(segment?.segmentId) || `seg-${idx + 1}`) === targetId,
  );
  if (index <= 0 || index >= segments.length - 1) {
    return null;
  }
  const target = segments[index];
  const left = segments[index - 1];
  const right = segments[index + 1];
  if (!isFinalPathGapSegment(target) || !isFinalPathCtgSegment(left) || !isFinalPathCtgSegment(right)) {
    return null;
  }
  const leftName = resolveFinalPathSegmentDisplayName(left) || left.segmentId || "left";
  const rightName = resolveFinalPathSegmentDisplayName(right) || right.segmentId || "right";
  const requestedTool = MANUAL_REFINEMENT_GAP_TOOLS.includes(normalizeString(tool).toLowerCase())
    ? normalizeString(tool).toLowerCase()
    : "degap";
  return normalizeManualRefinementLocus({
    chr,
    kind: "gap",
    segmentId: targetId,
    label: `${leftName} ↔ ${rightName}`,
    tool: requestedTool,
    tools: [requestedTool],
  });
}

export function resolveManualRefinementTelCandidate(finalPathEntry, segmentId, side) {
  const chr = normalizeString(finalPathEntry?.chrName);
  const targetId = normalizeString(segmentId);
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  const normalizedSide = normalizeString(side).toLowerCase();
  if (!chr || !targetId || !segments.length || (normalizedSide !== "left" && normalizedSide !== "right")) {
    return null;
  }
  const index = normalizedSide === "left" ? 0 : segments.length - 1;
  const endpoint = segments[index];
  const endpointId = normalizeString(endpoint?.segmentId) || `seg-${index + 1}`;
  if (endpointId !== targetId || !isFinalPathCtgSegment(endpoint)) {
    return null;
  }
  const ctgName = resolveFinalPathSegmentDisplayName(endpoint) || endpointId;
  return normalizeManualRefinementLocus({
    chr,
    kind: normalizedSide === "left" ? "tel_left" : "tel_right",
    segmentId: targetId,
    label: ctgName,
    tool: "degap",
    motif: "",
  });
}

export function resolveManualRefinementTerminalSides(finalPathEntry, segmentId) {
  const sides = [];
  if (resolveManualRefinementTelCandidate(finalPathEntry, segmentId, "left")) {
    sides.push("left");
  }
  if (resolveManualRefinementTelCandidate(finalPathEntry, segmentId, "right")) {
    sides.push("right");
  }
  return sides;
}

export function listManualRefinementCandidatesForEntry(finalPathEntry) {
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  const candidates = [];
  if (!segments.length) {
    return candidates;
  }
  const firstId = normalizeString(segments[0]?.segmentId) || "seg-1";
  const leftTel = resolveManualRefinementTelCandidate(finalPathEntry, firstId, "left");
  if (leftTel) {
    candidates.push(leftTel);
  }
  segments.forEach((segment, index) => {
    if (!isFinalPathGapSegment(segment)) {
      return;
    }
    const segId = normalizeString(segment?.segmentId) || `seg-${index + 1}`;
    const gap = resolveManualRefinementGapCandidate(finalPathEntry, segId);
    if (gap) {
      candidates.push(gap);
    }
  });
  const lastId = normalizeString(segments[segments.length - 1]?.segmentId) || `seg-${segments.length}`;
  const rightTel = resolveManualRefinementTelCandidate(finalPathEntry, lastId, "right");
  if (rightTel) {
    candidates.push(rightTel);
  }
  return candidates;
}

export function buildManualRefinementExportRequest(
  manualState,
  { scope = "all", chrName = "", locale = "zh" } = {},
) {
  const isEn = locale === "en";
  const normalizedScope = normalizeManualRefinementExportScope(scope);
  const normalizedChr = normalizeString(chrName);
  const normalized = normalizeManualRefinementState(manualState);
  const scopedLoci = filterManualRefinementLociByScope(normalized.loci, {
    scope: normalizedScope,
    chrName: normalizedChr,
  });

  if (!scopedLoci.length) {
    return {
      ok: false,
      scope: normalizedScope,
      chrName: normalizedChr,
      loci: [],
      error: normalizedScope === "current-chr"
        ? (isEn
          ? `No refinement tasks queued for the current chromosome (${normalizedChr || "-"}).`
          : `当前染色体（${normalizedChr || "-"}）暂无已登记的精修任务。`)
        : (isEn
          ? "No refinement tasks queued in this project. Queue at least one gap or terminal telomere locus before exporting."
          : "本项目暂无已登记的精修任务。请先在 Final Path 登记至少一个 Gap 或端粒位点再导出。"),
    };
  }

  const requestLoci = [];
  for (const locus of scopedLoci) {
    const entry = {
      chr: locus.chr,
      kind: locus.kind,
      segment_id: locus.segmentId,
      tools: locus.tools,
    };
    if (locus.kind !== "gap" && locus.motif) {
      const validMotif = normalizeManualRefinementMotif(locus.motif);
      if (!validMotif) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn
            ? `Invalid telomere motif for ${locus.chr}: use A/C/G/T letters only.`
            : `${locus.chr} 的端粒 motif 无效：仅支持 A/C/G/T 字母。`,
        };
      }
      entry.motif = validMotif;
    }
    requestLoci.push(entry);
  }

  const request = { loci: requestLoci };
  const toolParameters = buildManualRefinementToolParametersPayload(normalized.toolParams);
  if (toolParameters) {
    request.tool_parameters = toolParameters;
  }

  if (normalized.readsMode === "override") {
    const hifi = parseServerReadPathList(normalized.hifiReadsInput);
    const ont = parseServerReadPathList(normalized.ontReadsInput);
    const seenHifi = new Set();
    for (const item of hifi) {
      if (!isServerAbsolutePath(item)) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn
            ? `HiFi read path must be a Server absolute path starting with '/': ${item}`
            : `HiFi reads 必须填写以 / 开头的服务器绝对路径：${item}`,
        };
      }
      if (seenHifi.has(item)) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn ? `Duplicate HiFi read path: ${item}` : `HiFi reads 存在重复路径：${item}`,
        };
      }
      seenHifi.add(item);
    }
    const seenOnt = new Set();
    for (const item of ont) {
      if (!isServerAbsolutePath(item)) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn
            ? `ONT read path must be a Server absolute path starting with '/': ${item}`
            : `ONT reads 必须填写以 / 开头的服务器绝对路径：${item}`,
        };
      }
      if (seenOnt.has(item)) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn ? `Duplicate ONT read path: ${item}` : `ONT reads 存在重复路径：${item}`,
        };
      }
      if (seenHifi.has(item)) {
        return {
          ok: false,
          scope: normalizedScope,
          chrName: normalizedChr,
          loci: scopedLoci,
          error: isEn
            ? `The same read file cannot be placed in both HiFi and ONT: ${item}`
            : `同一个 reads 文件不能同时填入 HiFi 和 ONT：${item}`,
        };
      }
      seenOnt.add(item);
    }
    request.hifi_reads = hifi;
    request.ont_reads = ont;
  }

  return {
    ok: true,
    scope: normalizedScope,
    chrName: normalizedChr,
    loci: scopedLoci,
    request,
  };
}
