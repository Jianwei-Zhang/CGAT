export function createWorkflowMockStore() {
return {
  grtRecipe: {
    workflow: "gpm_grt_precomputed_v2",
    schemaVersion: "2",
    finalPathSchemaVersion: "1",
    recipeId: "mock-grt-recipe",
    primaryDataset: "hifiasm",
    supportDatasets: ["flye", "wtdbg2"],
    readsQcEnabled: false,
    donorSetId: "mock-d0",
    telDonorSetId: "mock-dtel",
  },
  packageMetadata: {
    packageMode: "fast",
    sequenceLayout: "partitioned",
    preassignedChr: true,
    chrAssignmentMinCoveragePercent: 60,
    selfAlignmentScope: "chr_partition",
    crossAlignmentScope: "chr_partition",
  },
  references: [
    {
      referenceGenomeId: 1,
      label: "Ref #1 (Chr01-12 + Chloroplast)",
    },
  ],
  datasets: [
    { datasetId: 1, label: "hifiasm", contigCount: 1154, totalLengthBp: 408532119, selfAlignmentAvailable: true },
    { datasetId: 2, label: "flye", contigCount: 1327, totalLengthBp: 401886542, selfAlignmentAvailable: true },
    { datasetId: 3, label: "wtdbg2", contigCount: 1899, totalLengthBp: 395447286, selfAlignmentAvailable: true },
  ],
  existingProjects: [],
  phasedChrTracks: [],
  nextPhasedTrackId: 1,
  nextPhasedTrackItemId: 1,
};
}
