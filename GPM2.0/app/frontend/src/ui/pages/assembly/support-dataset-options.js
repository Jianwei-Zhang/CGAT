import { normalizeSupportDatasetId } from "./selection-state.js";

export function isInternalRefinementPatchDataset(dataset) {
  if (!dataset || typeof dataset !== "object") {
    return false;
  }
  const names = [dataset.name, dataset.displayName, dataset.label]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean);
  if (names.some((name) => name.startsWith("cgat_refinement_"))) {
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
