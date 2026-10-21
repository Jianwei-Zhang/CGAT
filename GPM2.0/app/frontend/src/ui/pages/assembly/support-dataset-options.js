import { normalizeSupportDatasetId } from "./selection-state.js";

// Project roles, not contig counts or current chromosome hits, define this menu.
// A four-dataset project must retain all three supports, including empty tracks.
export function buildSupportDatasetOptions(project, datasets = []) {
  if (!project) return [];
  return (project.supportDatasetIds || [])
    .map(normalizeSupportDatasetId)
    .filter(datasetId => datasetId !== null)
    .map(datasetId => {
      const dataset = datasets.find(item => Number(item.datasetId) === datasetId);
      return { datasetId, label: dataset?.displayName || dataset?.name || dataset?.label || `ds-${datasetId}` };
    });
}
