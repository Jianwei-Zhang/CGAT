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
    const workspaceRoot = String(snapshot.session?.workspacePath || "").trim();
    const projectId = Number(snapshot.session?.projectId || 0);
    const selectedChrName = String(snapshot.assembly?.selectedChrName || "").trim();
    const targetChr = String(payload.targetChr || selectedChrName).trim();
    const targetTrack = String(payload.targetTrack || "").trim();
    if (!workspaceRoot || !projectId || !targetChr || !targetTrack) {
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
      const importedMessage = result?.message
        || tAssembly(store.getState(), "runtime.addCtgImportDone");
      appendAddCtgImportStage(
        host,
        store,
        tAssembly(store.getState(), "runtime.addCtgImportRefreshStage"),
      );
      await selectChromosome(host, store, targetChr);
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
          addCtgImportProgress: {
            ...(latest.assembly?.addCtgImportProgress || {}),
            open: true,
            status: "success",
            summary: importedMessage,
            error: "",
          },
          actionStatus: tAssembly(latest, "runtime.addCtgImportDoneWithName", {
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
