import {
  isFinalPathRefSegment,
  resolveFinalPathRefSegmentAbsoluteRange,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
} from "./final-path-state.js";

const positive = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
const text = value => String(value || "").trim();

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
  const tool = text(trace?.tool);
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
  const originalGapIds = Array.isArray(trace?.originalGapIds) ? trace.originalGapIds.filter(Boolean) : [];
  const isEn = locale === "en";
  const shortLabel = isEn ? "Refined" : "精修";
  const modeLabel = mode === "manual"
    ? (isEn ? "Manual refinement" : "手动精修")
    : (isEn ? "Automatic refinement" : "自动精修");
  const badgeLabel = tool ? `${modeLabel} · ${tool}` : modeLabel;
  const detailLines = [
    `${isEn ? "Refinement" : "精修来源"}: ${badgeLabel}${version ? ` v${version}` : ""}`,
    ...(locusId ? [`${isEn ? "Locus ID" : "位点标识"}: ${locusId}`] : []),
    ...(batchSha256 ? [`${isEn ? "Batch / Run" : "批次 / 运行"}: ${batchSha256.slice(0, 16)}`] : []),
    ...(resultSha256 ? [`${isEn ? "Result SHA-256" : "结果摘要"}: ${resultSha256.slice(0, 16)}`] : []),
    ...(patchSha256 ? [`${isEn ? "Patch SHA-256" : "补丁摘要"}: ${patchSha256.slice(0, 16)}`] : []),
    ...(attemptId ? [`${isEn ? "Attempt ID" : "尝试标识"}: ${attemptId}`] : []),
    ...(revision ? [`${isEn ? "Tool revision" : "工具修订"}: ${revision}`] : []),
    ...(adoptionRevision !== null ? [`${isEn ? "Adoption revision" : "采纳版本"}: r${adoptionRevision}`] : []),
    ...(editId ? [`${isEn ? "Edit ID" : "改动标识"}: ${editId}`] : []),
    ...(originalGapIds.length ? [`${isEn ? "Original gap(s)" : "原缺口"}: ${originalGapIds.join(", ")}`] : []),
    ...(text(trace?.switchedFrom) ? [`${isEn ? "Switched from" : "替换自"}: ${text(trace.switchedFrom)}`] : []),
  ];
  return {
    mode,
    isAdoptedPatch,
    shortLabel,
    badgeLabel,
    tool,
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
  const refinement = describeFinalPathRefinement(segment, locale || labels?.locale || "zh");
  return [
    resolveFinalPathSegmentDisplayName(segment),
    `${labels.finalPathAdoptedLength || "Adopted length"}: ${number(adopted)} bp`,
    ...(range.sourceLength ? [`${labels.finalPathSourceLength || "Source contig length"}: ${number(range.sourceLength)} bp`] : []),
    `${labels.finalPathSourceInterval || "Source interval"}: ${number(range.sourceStart)}–${number(range.sourceEnd)} bp`,
    `${labels.finalPathOrientation || "Orientation"}: ${range.orient}`,
    ...(refinement ? refinement.detailLines : []),
  ].join("\n");
}
