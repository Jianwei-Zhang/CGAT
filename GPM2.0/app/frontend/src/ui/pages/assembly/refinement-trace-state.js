// Preserve sourced refinement lineage through the editable Final Path state.
// It is provenance only: no placement or sequence is inferred from these fields.
export function normalizeRefinementTrace(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const first = (...keys) => keys.map((key) => value[key]).find((item) => item !== undefined);
  const text = (item) => typeof item === "string" ? item.trim() : "";
  const result = {};
  const parent = text(first("parentSegmentId", "parent_segment_id"));
  const edit = text(first("editId", "refinement_edit_id"));
  if (parent) result.parentSegmentId = parent;
  if (edit) result.editId = edit;
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
