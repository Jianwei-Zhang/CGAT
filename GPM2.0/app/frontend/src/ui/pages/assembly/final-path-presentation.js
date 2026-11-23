import {
  isFinalPathRefSegment,
  resolveFinalPathRefSegmentAbsoluteRange,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
} from "./final-path-state.js";

const positive = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
const text = value => String(value || "").trim();

const REFINEMENT_TOOL_DISPLAY_NAMES = Object.freeze({
  degap: "DEGAP",
  lrgapcloser: "LR_Gapcloser",
  tgsgapcloser: "TGS-GapCloser",
  quartet: "quarTeT",
});

function inferRefinementToolId(segment, trace) {
  const explicit = text(trace?.tool).toLowerCase();
  if (explicit) {
    return explicit;
  }
  const candidates = [
    text(trace?.editId).toLowerCase(),
    text(segment?.source?.dataset).toLowerCase(),
    text(segment?.datasetName).toLowerCase(),
    text(segment?.ctgName).toLowerCase(),
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    for (const key of Object.keys(REFINEMENT_TOOL_DISPLAY_NAMES)) {
      if (
        candidate.startsWith(`${key}-`)
        || candidate.startsWith(`cgat_refinement_${key}_`)
        || candidate.includes(`_${key}-`)
        || candidate.endsWith(` · ${key}`)
      ) {
        return key;
      }
    }
  }
  return "";
}

function formatRefinementToolLabel(toolId, { isTelomere = false } = {}) {
  if (!toolId) {
    return "";
  }
  const normalized = toolId.toLowerCase();
  if (normalized === "degap" && isTelomere) {
    return "DEGAP TelSeeker";
  }
  return REFINEMENT_TOOL_DISPLAY_NAMES[normalized] || toolId;
}

function formatShortRefinementId(rawValue) {
  const raw = text(rawValue);
  if (!raw) {
    return "";
  }
  const prefixedHex = raw.match(/^([a-z0-9_]+)-([0-9a-f]{8,})$/i);
  if (prefixedHex) {
    const [, prefix, hex] = prefixedHex;
    if (prefix.toLowerCase() === "gap") {
      return `gap-${hex.slice(0, 6)}`;
    }
    return `#${hex.slice(0, 6)}`;
  }
  if (/^[0-9a-f]{12,}$/i.test(raw)) {
    return `#${raw.slice(0, 6)}`;
  }
  return raw.length > 20 ? `${raw.slice(0, 18)}…` : raw;
}

export function collectFinalPathSourceCtgs(assembly = {}) {
  return [
    ...(assembly.chrCtgs || []), ...(assembly.supportChrCtgs || []), ...(assembly.supportMirroredCtgs || []),
    ...(assembly.subviewCompositionCandidates || []).map(candidate => candidate.ctg || candidate),
    ...(assembly.subview?.summary?.mode === "composition" ? assembly.subview.summary.members || [] : []),
  ];
}

// Source provenance can outlive a coordinate edit. The committed row's start /
// end are authoritative; never substitute its old source.start / source.end.
export function resolveFinalPathSourceRange(segment, sourceCtgs = []) {
  const start = positive(segment?.start), end = positive(segment?.end);
  const length = positive(segment?.overallLen);
  if (!start || !end || !length || start > length || end > length || segment?.type === "gap") return null;
  const orient = start > end ? "-" : "+";
  if (isFinalPathRefSegment(segment)) {
    const range = resolveFinalPathRefSegmentAbsoluteRange(segment);
    return range ? { sourceStart: range.startBp, sourceEnd: range.endBp, orient,
      referenceChrName: text(segment.referenceChrName), sourceLength: null } : null;
  }
  const id = positive(segment?.splitFragmentCtgId) || positive(segment?.assemblyCtgId);
  const matches = sourceCtgs.filter(candidate => id && positive(candidate?.assemblyCtgId) === id);
  const ctg = matches.find(candidate => candidate?.sourceFragment) || matches[0];
  const originalCoordinates = Boolean(text(segment?.source?.dataset) && text(segment?.source?.contig));
  const offset = originalCoordinates ? 0 : (positive(ctg?.sourceFragment?.sourceStart) || 1) - 1;
  return { sourceStart: Math.min(start, end) + offset, sourceEnd: Math.max(start, end) + offset,
    orient, assemblyCtgId: id, originalCoordinates,
    sourceSeqId: positive(ctg?.sourceFragment?.sourceSeqId ?? ctg?.originSourceSeqId),
    datasetName: text(segment?.source?.dataset || segment?.datasetName || ctg?.datasetName),
    contigName: text(segment?.source?.contig || segment?.originId || segment?.ctgName),
    sourceLength: positive(ctg?.sourceFragment?.sourceLength) || positive(segment?.overallLen),
  };
}

const NON_ACCEPTED_REFINEMENT_STATUSES = new Set([
  "unmodified",
  "unchanged",
  "zero_accepted",
  "no_candidate",
  "rejected",
  "failed",
  "missing_reads",
  "input_unavailable",
  "candidate_only",
  "pending_app_import",
]);

export function describeFinalPathRefinement(segment, locale = "zh") {
  const trace = segment?.refinement && typeof segment.refinement === "object" && !Array.isArray(segment.refinement)
    ? segment.refinement
    : null;
  const isAdoptedPatch = text(segment?.sourceKind).toLowerCase() === "refinement_patch"
    && /^[0-9a-f]{64}$/.test(text(segment?.refinementPatchSha256 ?? segment?.refinement_patch_sha256));
  if (!trace && !isAdoptedPatch) {
    return null;
  }
  const status = text(trace?.status).toLowerCase();
  if (status && NON_ACCEPTED_REFINEMENT_STATUSES.has(status)) {
    return null;
  }
  const claimedMode = text(trace?.mode).toLowerCase();
  const hasAcceptedEvidence = isAdoptedPatch || (claimedMode !== "manual" && Boolean(
    text(trace?.editId) || trace?.source
    || (Array.isArray(trace?.originalGapIds) && trace.originalGapIds.length > 0),
  ));
  if (!hasAcceptedEvidence) {
    return null;
  }
  const mode = isAdoptedPatch ? "manual" : "automatic";
  const originalGapIds = Array.isArray(trace?.originalGapIds) ? trace.originalGapIds.filter(Boolean) : [];
  const isTelomere = isAdoptedPatch && originalGapIds.length === 0 && Boolean(text(trace?.parentSegmentId));
  const toolId = inferRefinementToolId(segment, trace);
  const toolLabel = formatRefinementToolLabel(toolId, { isTelomere });
  const version = text(trace?.version);
  const editId = text(trace?.editId);
  const batchSha256 = text(trace?.batchSha256);
  const locusId = text(trace?.locusId ?? segment?.locusId ?? segment?.locus_id);
  const resultSha256 = text(trace?.resultSha256 ?? segment?.resultSha256 ?? segment?.result_sha256);
  const attemptId = text(trace?.attemptId ?? segment?.attemptId ?? segment?.attempt_id);
  const revision = text(trace?.revision);
  const rawAdoptionRevision = trace?.adoptionRevision ?? segment?.adoptionRevision ?? segment?.adoption_revision;
  const adoptionRevision = Number.isSafeInteger(Number(rawAdoptionRevision))
    && rawAdoptionRevision !== null
    && rawAdoptionRevision !== ""
    ? Number(rawAdoptionRevision)
    : null;
  const patchSha256 = text(segment?.refinementPatchSha256 ?? segment?.refinement_patch_sha256);
  const isEn = locale === "en";
  const shortLabel = isEn ? "Refined" : "精修";
  const modeLabel = mode === "manual"
    ? (isEn ? "Manual refinement" : "手动精修")
    : (isEn ? "Automatic refinement" : "自动精修");
  const badgeLabel = toolLabel ? `${modeLabel} · ${toolLabel}` : modeLabel;
  const shortId = formatShortRefinementId(editId || patchSha256 || locusId);
  const compactTitle = toolLabel
    ? (isEn
      ? `${toolLabel} ${shortLabel}${shortId ? ` ${shortId}` : ""}`
      : `${toolLabel} 精修${shortId ? ` ${shortId}` : ""}`)
    : (isEn
      ? `${modeLabel}${shortId ? ` ${shortId}` : ""}`
      : `${modeLabel}${shortId ? ` ${shortId}` : ""}`);
  const shortGapLabels = originalGapIds.map(formatShortRefinementId).filter(Boolean);
  const switchedFrom = text(trace?.switchedFrom);
  const detailLines = [
    `${isEn ? "Source" : "精修方式"}: ${modeLabel}`,
    ...(toolLabel ? [`${isEn ? "Tool" : "工具"}: ${toolLabel}${version ? ` v${version}` : ""}`] : []),
    ...(shortId ? [`${isEn ? "Patch ID" : "补丁编号"}: ${shortId}`] : []),
    ...(shortGapLabels.length ? [`${isEn ? "Target gap" : "原缺口"}: ${shortGapLabels.join(", ")}`] : []),
    ...(switchedFrom ? [`${isEn ? "Switched from" : "替换自"}: ${formatRefinementToolLabel(switchedFrom) || switchedFrom}`] : []),
  ];
  return {
    mode,
    isAdoptedPatch,
    shortLabel,
    badgeLabel,
    compactTitle,
    shortId,
    tool: toolId,
    toolLabel,
    version,
    editId,
    locusId,
    batchSha256,
    resultSha256,
    attemptId,
    revision,
    adoptionRevision,
    patchSha256,
    originalGapIds,
    undoable: trace?.undoable === true,
    detailLines,
  };
}

export function buildFinalPathTooltip(segment, { sourceCtgs = [], labels = {}, locale = "" } = {}) {
  const range = resolveFinalPathSourceRange(segment, sourceCtgs);
  const adopted = resolveFinalPathSegmentLengthBp(segment);
  if (!range || !adopted) return "";
  const number = value => Number(value).toLocaleString("en-US");
  const resolvedLocale = locale || labels?.locale || "zh";
  const isEn = resolvedLocale === "en";
  const refinement = describeFinalPathRefinement(segment, resolvedLocale);
  if (refinement) {
    const isFullPatch = range.sourceStart === 1 && range.sourceEnd === adopted
      && (!range.sourceLength || range.sourceLength === adopted);
    return [
      refinement.compactTitle,
      isFullPatch
        ? `${isEn ? "Length" : "长度"}: ${number(adopted)} bp · ${labels.finalPathOrientation || (isEn ? "Orientation" : "方向")}: ${range.orient}`
        : `${labels.finalPathAdoptedLength || (isEn ? "Adopted length" : "采用片段长度")}: ${number(adopted)} bp (${number(range.sourceStart)}–${number(range.sourceEnd)} bp, ${range.orient})`,
      ...refinement.detailLines,
    ].join("\n");
  }
  return [
    resolveFinalPathSegmentDisplayName(segment),
    `${labels.finalPathAdoptedLength || "Adopted length"}: ${number(adopted)} bp`,
    ...(range.sourceLength ? [`${labels.finalPathSourceLength || "Source contig length"}: ${number(range.sourceLength)} bp`] : []),
    `${labels.finalPathSourceInterval || "Source interval"}: ${number(range.sourceStart)}–${number(range.sourceEnd)} bp`,
    `${labels.finalPathOrientation || "Orientation"}: ${range.orient}`,
  ].join("\n");
}
