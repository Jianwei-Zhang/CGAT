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

function normalizeString(value) {
  return String(value ?? "").trim();
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

// Each Gap job selects a single tool (default: degap). Telomere endpoints are
// fixed to DEGAP TelSeeker. The wire format still carries a 1-element tools array.
export function normalizeManualRefinementTool(value, kind = "gap") {
  if (kind !== "gap") {
    return "degap";
  }
  const candidate = Array.isArray(value)
    ? value.map((item) => normalizeString(item).toLowerCase()).find((item) => MANUAL_REFINEMENT_GAP_TOOLS.includes(item))
    : normalizeString(value).toLowerCase();
  return candidate && MANUAL_REFINEMENT_GAP_TOOLS.includes(candidate) ? candidate : "degap";
}

export function normalizeManualRefinementTools(tools, kind = "gap") {
  return [normalizeManualRefinementTool(tools, kind)];
}

export function normalizeManualRefinementExportScope(scope) {
  const normalized = normalizeString(scope).toLowerCase();
  if (normalized === "current-chr" || normalized === "refinement-current-chr" || normalized === "current_chr") {
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
  const selectedTool = normalizeManualRefinementTool(value.tool ?? value.tools, kind);
  return {
    locusKey: buildManualRefinementLocusKey({ chr, kind, segmentId }),
    chr,
    kind,
    segmentId,
    label: normalizeString(value.label),
    tool: selectedTool,
    tools: [selectedTool],
    motif,
  };
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
    : loci.length;
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
  return {
    loci,
    readsMode: source.readsMode === "override" ? "override" : "inherit",
    hifiReadsInput: normalizeString(source.hifiReadsInput),
    ontReadsInput: normalizeString(source.ontReadsInput),
    panelOpen: typeof source.panelOpen === "boolean" ? source.panelOpen : (loci.length > 0 || Boolean(source.lastExport)),
    exporting: source.exporting === true,
    feedback: normalizeString(source.feedback),
    error: normalizeString(source.error),
    lastExport: normalizeExportedBatch(source.lastExport),
    exportedBatches,
  };
}

export function buildManualRefinementStateForPersistence(value) {
  const normalized = normalizeManualRefinementState(value);
  if (!normalized.loci.length && !normalized.exportedBatches.length && normalized.readsMode === "inherit") {
    return null;
  }
  return {
    loci: normalized.loci,
    readsMode: normalized.readsMode,
    hifiReadsInput: normalized.readsMode === "override" ? normalized.hifiReadsInput : "",
    ontReadsInput: normalized.readsMode === "override" ? normalized.ontReadsInput : "",
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

export function resolveManualRefinementGapCandidate(finalPathEntry, segmentId) {
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
  return normalizeManualRefinementLocus({
    chr,
    kind: "gap",
    segmentId: targetId,
    label: `${leftName} ↔ ${rightName}`,
    tool: "degap",
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
    const selectedTool = normalizeManualRefinementTool(locus.tool ?? locus.tools, locus.kind);
    const entry = {
      chr: locus.chr,
      kind: locus.kind,
      segment_id: locus.segmentId,
      tools: [selectedTool],
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
