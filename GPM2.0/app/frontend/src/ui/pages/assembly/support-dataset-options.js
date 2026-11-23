import { normalizeSupportDatasetId } from "./selection-state.js";

const LEGACY_MANUAL_REFINEMENT_DATASET_RE = /^degap_[0-9a-f]{24}$/;

export function isInternalRefinementPatchDataset(dataset, refinementDatasetNames = null) {
  if (!dataset || typeof dataset !== "object") {
    return false;
  }
  const role = String(dataset.role || "").trim().toLowerCase();
  if (role === "primary" || role === "reference") {
    return false;
  }
  const names = [dataset.originalName, dataset.name, dataset.displayName, dataset.label]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean);
  if (names.some((name) => name.startsWith("cgat_refinement_") || LEGACY_MANUAL_REFINEMENT_DATASET_RE.test(name))) {
    return true;
  }
  if (refinementDatasetNames instanceof Set && names.some((name) => refinementDatasetNames.has(name))) {
    return true;
  }
  const origin = String(dataset.origin || "").trim().toLowerCase();
  return origin.startsWith("refinement:");
}

// Project roles, not contig counts or current chromosome hits, define this menu.
// Internal Server/App refinement patch datasets are excluded from auxiliary tracks.
export function buildSupportDatasetOptions(project, datasets = []) {
  if (!project) return [];
  return (project.supportDatasetIds || [])
    .map(normalizeSupportDatasetId)
    .filter((datasetId) => datasetId !== null)
    .map((datasetId) => {
      const dataset = datasets.find((item) => Number(item.datasetId) === datasetId);
      if (isInternalRefinementPatchDataset(dataset)) {
        return null;
      }
      return { datasetId, label: dataset?.displayName || dataset?.name || dataset?.label || `ds-${datasetId}` };
    })
    .filter(Boolean);
}
