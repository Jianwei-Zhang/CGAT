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

export function buildFinalPathTooltip(segment, { sourceCtgs = [], labels = {} } = {}) {
  const range = resolveFinalPathSourceRange(segment, sourceCtgs);
  const adopted = resolveFinalPathSegmentLengthBp(segment);
  if (!range || !adopted) return "";
  const number = value => Number(value).toLocaleString("en-US");
  return [
    resolveFinalPathSegmentDisplayName(segment),
    `${labels.finalPathAdoptedLength || "Adopted length"}: ${number(adopted)} bp`,
    ...(range.sourceLength ? [`${labels.finalPathSourceLength || "Source contig length"}: ${number(range.sourceLength)} bp`] : []),
    `${labels.finalPathSourceInterval || "Source interval"}: ${number(range.sourceStart)}–${number(range.sourceEnd)} bp`,
    `${labels.finalPathOrientation || "Orientation"}: ${range.orient}`,
  ].join("\n");
}
