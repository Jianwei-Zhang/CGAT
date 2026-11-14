import { tAssembly } from "./i18n.js";

export function createAddCtgImportController({
  importAddCtgPackage,
  mapAssemblyError,
  pickZipFilePath,
  rerender,
  selectChromosome,
}) {
  function createAddCtgImportRunId() {
    const randomPart = Math.random().toString(36).slice(2, 10);
    return `add-ctg-${Date.now()}-${randomPart}`;
  }

  function setAddCtgImportProgress(host, store, progress) {
    const state = store.getState();
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        addCtgImportProgress: progress,
      },
    });
    rerender(host, store);
  }

  function appendAddCtgImportStage(host, store, stage) {
    const state = store.getState();
    const current = state.assembly?.addCtgImportProgress || {};
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        addCtgImportProgress: {
          ...current,
          stages: [...(Array.isArray(current.stages) ? current.stages : []), stage],
        },
      },
    });
    rerender(host, store);
  }

  async function importAddCtgIntoTrack(host, store, payload = {}) {
    const snapshot = store.getState();
    if (snapshot.assembly?.addCtgImportProgress?.status === "running") return;
    const workspaceRoot = String(snapshot.session?.workspacePath || "").trim();
    const projectId = Number(snapshot.session?.projectId || 0);
    const selectedChrName = String(snapshot.assembly?.selectedChrName || "").trim();
    const isDegap = payload.degapResults === true;
    const targetChr = isDegap ? "" : String(payload.targetChr || selectedChrName).trim();
    const targetTrack = String(payload.targetTrack || "").trim();
    if (!workspaceRoot || !projectId || (!isDegap && (!targetChr || !targetTrack))) {
      store.setState({
        assembly: {
          ...snapshot.assembly,
          actionStatus: "",
          actionError: tAssembly(snapshot, "runtime.addCtgImportMissingTarget"),
        },
      });
      rerender(host, store);
      return;
    }
    const zipPath = await pickZipFilePath(snapshot);
    if (!zipPath) {
      return;
    }
    const runId = createAddCtgImportRunId();
    setAddCtgImportProgress(host, store, {
      open: true,
      status: "running",
      runId,
      summary: tAssembly(snapshot, "runtime.addCtgImportProgressSubtitle"),
      stages: [
        `workspace_root=${workspaceRoot}`,
        `project_id=${projectId}`,
        `target=${targetChr}/${targetTrack}`,
        `add_ctg_zip_path=${zipPath}`,
      ],
      error: "",
    });
    try {
      const result = await importAddCtgPackage({
        workspaceRoot,
        projectId,
        zipPath,
        expectedTargetChr: targetChr,
        expectedTargetTrack: targetTrack,
        ...(isDegap ? { degapResultsOnly: true } : {}),
        runId,
        stateOrLocale: snapshot,
        onStage: (stage) => {
          if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
            return;
          }
          appendAddCtgImportStage(host, store, stage);
        },
      });
      if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
        return;
      }
      const importedMessage = Array.isArray(result?.degapResults) && result.degapResults.length
        ? tAssembly(store.getState(), Number(result.degapIncompleteCount) > 0 ? "degap.resultsImportedPartial" : "degap.resultsImported",
          { count: result.degapResults.length, pending: Number(result.degapIncompleteCount) || 0 })
        : result?.message || tAssembly(store.getState(), "runtime.addCtgImportDone");
      appendAddCtgImportStage(
        host,
        store,
        tAssembly(store.getState(), "runtime.addCtgImportRefreshStage"),
      );
      const degapResults = Array.isArray(result?.degapResults) ? result.degapResults : [];
      const refreshChr = targetChr || result?.targetChr || selectedChrName;
      await selectChromosome(host, store, refreshChr);
      const latest = store.getState();
      store.setState({
        ...latest,
        initializer: {
          ...latest.initializer,
          ...(Array.isArray(result?.datasets) ? { datasets: result.datasets } : {}),
          ...(Array.isArray(result?.existingProjects)
            ? { existingProjects: result.existingProjects }
            : {}),
          ...(Array.isArray(result?.references) ? { references: result.references } : {}),
          ...(result?.packageMetadata ? { packageMetadata: result.packageMetadata } : {}),
        },
        assembly: {
          ...latest.assembly,
          ...(degapResults.length ? { degap: {
            ...latest.assembly?.degap,
            jobs: (latest.assembly?.degap?.jobs || []).map((job) => ({
              ...job,
              importedResults: [...(job.importedResults || []), ...degapResults.filter(
                (item) => item.jobId === job.jobId && item.chrName === job.chrName
                  && !(job.importedResults || []).some((old) => old.token === item.token),
              )],
            })),
          } } : {}),
          addCtgImportProgress: {
            ...(latest.assembly?.addCtgImportProgress || {}),
            open: true,
            status: "success",
            summary: importedMessage,
            error: "",
          },
          actionStatus: degapResults.length ? importedMessage : tAssembly(latest, "runtime.addCtgImportDoneWithName", {
            ctgName: result?.ctgName || "-",
            targetTrack,
          }),
          actionError: "",
        },
      });
      rerender(host, store);
    } catch (error) {
      if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
        return;
      }
      const latest = store.getState();
      const mappedError = mapAssemblyError({ error, stateOrLocale: latest });
      store.setState({
        ...latest,
        assembly: {
          ...latest.assembly,
          addCtgImportProgress: {
            ...(latest.assembly?.addCtgImportProgress || {}),
            open: true,
            status: "error",
            summary: tAssembly(latest, "runtime.addCtgImportFailed"),
            stages: [
              ...(latest.assembly?.addCtgImportProgress?.stages || []),
              tAssembly(latest, "runtime.addCtgImportFailed"),
            ],
            error: mappedError.userMessage,
          },
          actionStatus: tAssembly(latest, "runtime.addCtgImportFailed"),
          actionError: mappedError.userMessage,
        },
      });
      rerender(host, store);
    }
  }

  return { importAddCtgIntoTrack };
}
