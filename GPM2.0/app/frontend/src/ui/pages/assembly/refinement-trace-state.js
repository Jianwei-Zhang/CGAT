// Preserve sourced refinement lineage through the editable Final Path state.
// It is provenance only: no placement or sequence is inferred from these fields.
export function normalizeRefinementTrace(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const first = (...keys) => keys.map((key) => value[key]).find((item) => item !== undefined);
  const text = (item) => typeof item === "string" ? item.trim() : "";
  const result = {};
  const parent = text(first("parentSegmentId", "parent_segment_id"));
  const edit = text(first("editId", "refinement_edit_id"));
  const mode = text(first("mode", "origin", "refinement_mode", "refinement_origin")).toLowerCase();
  const tool = text(first("tool", "refinement_tool"));
  const version = text(first("toolVersion", "tool_version", "version"));
  const batchSha256 = text(first("batchSha256", "batch_sha256", "runId", "run_id"));
  const locusId = text(first("locusId", "locus_id"));
  const resultSha256 = text(first("resultSha256", "result_sha256"));
  const attemptId = text(first("attemptId", "attempt_id"));
  const revision = text(first("revision", "toolRevision", "tool_revision"));
  const rawAdoptionRevision = first("adoptionRevision", "adoption_revision");
  const adoptionRevision = Number.isSafeInteger(Number(rawAdoptionRevision))
    && rawAdoptionRevision !== null
    && rawAdoptionRevision !== ""
    ? Number(rawAdoptionRevision)
    : null;
  const status = text(first("status", "refinement_status")).toLowerCase();
  const switchedFrom = text(first("switchedFrom", "switched_from"));
  if (parent) result.parentSegmentId = parent;
  if (edit) result.editId = edit;
  if (mode === "automatic" || mode === "manual") result.mode = mode;
  if (tool) result.tool = tool;
  if (version) result.version = version;
  if (batchSha256) result.batchSha256 = batchSha256;
  if (locusId) result.locusId = locusId;
  if (resultSha256) result.resultSha256 = resultSha256;
  if (attemptId) result.attemptId = attemptId;
  if (revision) result.revision = revision;
  if (adoptionRevision !== null && adoptionRevision >= 0) result.adoptionRevision = adoptionRevision;
  if (status) result.status = status;
  if (switchedFrom) result.switchedFrom = switchedFrom;
  if (first("undoable") === true) result.undoable = true;
  const interval = first("parentInterval", "parent_interval");
  if (Array.isArray(interval) && interval.length === 2 && interval.every(Number.isSafeInteger)
      && interval[0] >= 0 && interval[1] > interval[0]) result.parentInterval = [...interval];
  const gaps = first("originalGapIds", "original_gap_ids");
  if (Array.isArray(gaps)) {
    const ids = [...new Set(gaps.map(text).filter(Boolean))];
    if (ids.length) result.originalGapIds = ids;
  }
  const origin = first("source", "refinement_source");
  if (origin && text(origin.dataset) && text(origin.contig) && Number.isSafeInteger(origin.start)
      && Number.isSafeInteger(origin.end) && origin.start > 0 && origin.end >= origin.start
      && ["+", "-"].includes(origin.orientation)) {
    result.source = { dataset: text(origin.dataset), contig: text(origin.contig), start: origin.start,
      end: origin.end, orientation: origin.orientation };
  }
  return Object.keys(result).length ? result : null;
}
