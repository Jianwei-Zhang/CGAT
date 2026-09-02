const ROUTE_GROUPS = Object.freeze({
  imports: [
    ["/import-zip", "importZip"],
    ["/import-extracted", "importExtracted"],
    ["/import-add-dataset-package", "importAddDatasetPackage"],
  ],
  workspace: [
    ["/open-workspace", "openWorkspace"],
    ["/list-project-initializer-options", "listProjectInitializerOptions"],
    ["/initialize-project", "initializeProject"],
    ["/get-grt-project-view", "getGrtProjectView"],
    ["/update-project", "updateProject"],
    ["/delete-project", "deleteProject"],
    ["/bootstrap-project-assembly", "bootstrapProjectAssembly"],
    ["/auto-assign-chr", "autoAssignChr"],
    ["/auto-orient-contigs", "autoOrientContigs"],
    ["/set-project-auto-pipeline-done", "setProjectAutoPipelineDone"],
    ["/list-project-chromosomes", "listProjectChromosomes"],
    ["/list-new-sequences", "listNewSequences"],
  ],
  assembly: [
    ["/list-chr-view-ctgs", "listChrViewCtgs"],
    ["/list-reference-track-members", "listReferenceTrackMembers"],
    ["/list-phased-chr-tracks", "listPhasedChrTracks"],
    ["/create-phased-chr-track", "createPhasedChrTrack"],
    ["/delete-phased-chr-track", "deletePhasedChrTrack"],
    ["/add-ctg-to-phased-chr-track", "addCtgToPhasedChrTrack"],
    ["/remove-phased-chr-track-item", "removePhasedChrTrackItem"],
    ["/reorder-phased-chr-track-items", "reorderPhasedChrTrackItems"],
    ["/list-deleted-ctgs", "listDeletedCtgs"],
    ["/get-ctg-detail", "getCtgDetail"],
    ["/restore-deleted-ctg", "restoreDeletedCtg"],
    ["/list-ctg-edit-candidates", "listCtgEditCandidates"],
    ["/ctg-editor-action", "runCtgEditorAction"],
    ["/main-view-history-status", "getMainViewHistoryStatus"],
    ["/inspect-main-view-delete", "inspectMainViewDelete"],
    ["/main-view-editor-action", "runMainViewEditorAction"],
    ["/main-view-layout-action", "runMainViewLayoutAction"],
    ["/main-view-batch-delete", "runMainViewBatchDelete"],
    ["/main-view-history-action", "executeMainViewHistoryAction"],
    ["/get-junction-inspection", "getJunctionInspection"],
  ],
  audit: [
    ["/list-export-records", "listExportRecords"],
    ["/list-edit-audit-logs", "listEditAuditLogs"],
    ["/append-edit-audit-log", "appendEditAuditLog"],
    ["/clear-edit-audit-logs", "clearEditAuditLogs"],
  ],
  runtime: [
    ["/runtime-settings-get", "getRuntimeSettings"],
    ["/runtime-settings-set", "setRuntimeSettings"],
    ["/export-degap-jobs", "exportDegapJobs"],
  ],
});

export function createBackendBridgeRoutes(handlers) {
  const routes = new Map();
  for (const [group, definitions] of Object.entries(ROUTE_GROUPS)) {
    for (const [pathname, handlerName] of definitions) {
      const handler = handlers?.[handlerName];
      if (typeof handler !== "function") {
        throw new TypeError(`missing dev bridge handler ${handlerName} for ${group}`);
      }
      routes.set(`POST ${pathname}`, { group, handler, pathname });
    }
  }
  return routes;
}

export function listBackendBridgeRouteGroups() {
  return Object.fromEntries(
    Object.entries(ROUTE_GROUPS).map(([group, definitions]) => [
      group,
      definitions.map(([pathname]) => pathname),
    ]),
  );
}
