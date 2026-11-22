import { pickSaveFilePath } from "../../../services/backend-api.js";
import { exportManualRefinement } from "../../../services/workflow-api.js";
import {
  buildDegapProjectStateForPersistence,
  normalizeDegapRuntimeState,
} from "./degap-state.js";
import {
  getCurrentChrFinalPath,
  resolveCurrentFinalPathChrName,
} from "./final-path-state.js";
import {
  buildManualRefinementExportBaseName,
  buildManualRefinementExportRequest,
  extractFileName,
  normalizeManualRefinementState,
  normalizeManualRefinementTool,
  resolveManualRefinementGapCandidate,
  resolveManualRefinementTelCandidate,
} from "./manual-refinement-state.js";

const MANUAL_REF_CARD_BOUND = Symbol("manualRefinementCardBound");

function normalizeString(value) {
  return String(value ?? "").trim();
}

function getManualRefinementState(store) {
  const degap = normalizeDegapRuntimeState(store.getState()?.assembly?.degap);
  return normalizeManualRefinementState(degap.manualRefinement);
}

function isSameProjectSession(store, { workspaceRoot, projectId }) {
  const latest = store.getState();
  return (
    normalizeString(latest?.session?.workspacePath) === normalizeString(workspaceRoot)
    && Number(latest?.session?.projectId || 0) === Number(projectId || 0)
  );
}

function formatCompactTimestamp(now = new Date()) {
  const pad = (n) => String(Math.trunc(Number(n) || 0)).padStart(2, "0");
  return [
    String(now.getFullYear()).padStart(4, "0"),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join("");
}

function updateManualRefinementState(host, store, updater, deps = {}, { persist = false } = {}) {
  const state = store.getState();
  const currentDegap = normalizeDegapRuntimeState(state?.assembly?.degap);
  const currentManual = normalizeManualRefinementState(currentDegap.manualRefinement);
  const patch = typeof updater === "function" ? updater(currentManual) : updater;
  const nextManual = normalizeManualRefinementState({
    ...currentManual,
    ...(patch || {}),
  });
  const nextDegap = normalizeDegapRuntimeState({
    ...currentDegap,
    manualRefinement: nextManual,
  });
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      degap: nextDegap,
      degapProjectState: buildDegapProjectStateForPersistence(nextDegap),
    },
  });
  deps.rerender?.(host, store);
  if (persist && typeof deps.persistDegapProjectState === "function") {
    void deps.persistDegapProjectState(host, store);
  }
  return nextManual;
}

export function recordManualRefinementExportReceipt(host, store, receipt, deps = {}) {
  const latest = getManualRefinementState(store);
  const state = store.getState();
  const isEn = state?.locale === "en";
  if (Number(state.projectExport?.projectId || 0) === Number(state.session?.projectId || 0)
      && normalizeString(state.projectExport?.workspacePath) === normalizeString(state.session?.workspacePath)) {
    store.setState({ projectExport: { ...state.projectExport, manualRefinementExports: [receipt,
      ...(state.projectExport?.manualRefinementExports || []).filter(row => row.batchSha256 !== receipt.batchSha256),
    ].slice(0, 20) } });
  }
  const scopeLabel = receipt.scope === "current-chr"
    ? (isEn ? `current chromosome (${receipt.chrName})` : `当前染色体（${receipt.chrName}）`)
    : (isEn ? "all queued loci in project" : "本项目全部已选位点");
  return updateManualRefinementState(host, store, {
    exporting: false,
    error: "",
    feedback: isEn
      ? `Exported refinement tasks (${scopeLabel}): ${receipt.lociCount} loci / ${receipt.tasksCount} tasks. Run refine.py on Server next.`
      : `已导出精修任务（${scopeLabel}）：${receipt.lociCount} 个位点 / ${receipt.tasksCount} 个任务，请传到 Server 运行 refine.py。`,
    lastExport: receipt,
    exportedBatches: [
      receipt,
      ...latest.exportedBatches.filter((item) => item.batchSha256 !== receipt.batchSha256),
    ].slice(0, 20),
  }, deps);
}

export function openManualRefinementPanel(host, store, deps = {}) {
  updateManualRefinementState(host, store, { panelOpen: true, error: "" }, deps);
}

export function registerManualRefinementLocus(host, store, payload = {}, deps = {}) {
  const state = store.getState();
  const isEn = state?.locale === "en";
  const chrName = normalizeString(payload.chrName || payload.chr);
  const kind = normalizeString(payload.kind).toLowerCase();
  const segmentId = normalizeString(payload.segmentId || payload.segment_id);
  const finalPathEntry = chrName
    ? state.assembly?.finalPathByChr?.[chrName] || getCurrentChrFinalPath(state.assembly)
    : getCurrentChrFinalPath(state.assembly);

  let candidate = null;
  if (kind === "gap") {
    candidate = resolveManualRefinementGapCandidate(finalPathEntry, segmentId);
  } else if (kind === "tel_left") {
    candidate = resolveManualRefinementTelCandidate(finalPathEntry, segmentId, "left");
  } else if (kind === "tel_right") {
    candidate = resolveManualRefinementTelCandidate(finalPathEntry, segmentId, "right");
  }

  if (!candidate) {
    updateManualRefinementState(host, store, {
      panelOpen: true,
      feedback: "",
      error: kind === "gap"
        ? (isEn
          ? "Cannot queue this gap: refinement requires direct contig flanks immediately before and after the gap."
          : "无法登记该 Gap：精修任务要求缺口紧邻左右两侧均为 Contig。")
        : (isEn
          ? "Cannot queue this telomere endpoint: only the first or last contig segment of the Final Path is eligible."
          : "无法登记该端粒位点：仅 Final Path 首位或末位 Contig 端点可用。"),
    }, deps);
    return false;
  }

  const current = getManualRefinementState(store);
  const exists = current.loci.some((item) => item.locusKey === candidate.locusKey);
  if (exists) {
    updateManualRefinementState(host, store, {
      panelOpen: true,
      error: "",
      feedback: isEn
        ? `Refinement task already queued: ${candidate.chr} · ${candidate.label || candidate.segmentId}`
        : `该位点已在精修任务清单中：${candidate.chr} · ${candidate.label || candidate.segmentId}`,
    }, deps);
    return false;
  }

  updateManualRefinementState(host, store, {
    panelOpen: true,
    loci: [...current.loci, candidate],
    error: "",
    feedback: isEn
      ? `Added refinement task: ${candidate.chr} · ${candidate.label || candidate.segmentId}`
      : `已加入精修任务：${candidate.chr} · ${candidate.label || candidate.segmentId}`,
  }, deps, { persist: true });
  return true;
}

async function exportCurrentChrRefinementTasks(host, store, deps = {}) {
  // Freeze project identity, scope, and queued loci BEFORE opening the file picker
  // so switching project/chromosome mid-dialog can never send the export elsewhere.
  const initialState = store.getState();
  const isEn = initialState?.locale === "en";
  const frozenWorkspaceRoot = normalizeString(initialState?.session?.workspacePath);
  const frozenProjectId = Number(initialState?.session?.projectId || 0);
  const frozenProjectName = normalizeString(initialState?.session?.projectName || frozenProjectId || "project");
  const frozenScope = "current-chr";
  const frozenChrName = normalizeString(resolveCurrentFinalPathChrName(initialState?.assembly));
  const frozenManual = getManualRefinementState(store);

  if (!frozenWorkspaceRoot || !frozenProjectId) {
    updateManualRefinementState(host, store, {
      error: isEn ? "Open a project before exporting refinement tasks." : "请先打开有效项目再导出精修任务。",
      feedback: "",
    }, deps);
    return false;
  }

  const built = buildManualRefinementExportRequest(frozenManual, {
    scope: frozenScope,
    chrName: frozenChrName,
    locale: initialState?.locale,
  });
  if (!built.ok) {
    updateManualRefinementState(host, store, { error: built.error, feedback: "" }, deps);
    return false;
  }

  const timestamp = typeof deps.getExportTimestamp === "function"
    ? String(deps.getExportTimestamp() || "")
    : formatCompactTimestamp();
  const baseName = buildManualRefinementExportBaseName({
    projectName: frozenProjectName,
    chrName: frozenChrName,
    scope: frozenScope,
  });
  const defaultZipName = timestamp ? `${baseName}_${timestamp}.zip` : `${baseName}.zip`;

  const pickSave = deps.pickSaveFilePath || pickSaveFilePath;
  const outputPath = await pickSave({
    defaultPath: defaultZipName,
    filters: [{ name: "ZIP", extensions: ["zip"] }],
  }, initialState);
  if (!outputPath) {
    return false;
  }

  if (!isSameProjectSession(store, { workspaceRoot: frozenWorkspaceRoot, projectId: frozenProjectId })) {
    return false;
  }

  updateManualRefinementState(host, store, {
    exporting: true,
    error: "",
    feedback: isEn ? "Saving current Final Path and exporting refinement tasks (.zip)..." : "正在保存当前 Final Path 并导出精修任务包（.zip）...",
  }, deps);

  try {
    if (typeof deps.flushAssemblyProjectState === "function") {
      await deps.flushAssemblyProjectState(host, store);
    }
    if (!isSameProjectSession(store, { workspaceRoot: frozenWorkspaceRoot, projectId: frozenProjectId })) {
      return false;
    }
    const exportFn = deps.exportManualRefinement || exportManualRefinement;
    const summary = await exportFn({
      workspaceRoot: frozenWorkspaceRoot,
      projectId: frozenProjectId,
      outputPath,
      request: built.request,
      stateOrLocale: initialState,
    });
    const batchSha256 = normalizeString(summary?.batch_sha256 || summary?.batchSha256);
    const receipt = {
      batchSha256: batchSha256 || "exported",
      exportedAt: new Date().toISOString(),
      outputPath,
      outputFileName: extractFileName(outputPath) || "refinement_tasks.zip",
      scope: frozenScope,
      chrName: frozenChrName,
      lociCount: Number(summary?.loci ?? built.request.loci.length),
      tasksCount: Number(summary?.tasks ?? built.request.loci.length),
      readsMode: frozenManual.readsMode,
      loci: built.loci,
      status: "exported_awaiting_server",
    };
    if (isSameProjectSession(store, { workspaceRoot: frozenWorkspaceRoot, projectId: frozenProjectId })) {
      recordManualRefinementExportReceipt(host, store, receipt, deps);
    }
    return true;
  } catch (error) {
    if (isSameProjectSession(store, { workspaceRoot: frozenWorkspaceRoot, projectId: frozenProjectId })) {
      updateManualRefinementState(host, store, {
        exporting: false,
        feedback: "",
        error: String(error?.message || error || (isEn ? "Failed to export refinement tasks." : "导出精修任务失败。")),
      }, deps);
    }
    return false;
  }
}

async function copyTextToClipboard(text) {
  if (globalThis.navigator?.clipboard?.writeText) {
    await globalThis.navigator.clipboard.writeText(text);
    return true;
  }
  return false;
}

export function bindManualRefinementCard(host, store, deps = {}) {
  if (typeof host?.addEventListener !== "function" || host[MANUAL_REF_CARD_BOUND]) {
    return;
  }
  host.addEventListener("click", (event) => {
    const toggle = event.target?.closest?.("[data-manual-ref-toggle]");
    if (toggle) {
      const current = getManualRefinementState(store);
      updateManualRefinementState(host, store, { panelOpen: !current.panelOpen }, deps);
      return;
    }

    const quickAdd = event.target?.closest?.("[data-manual-ref-quick-add]");
    if (quickAdd) {
      registerManualRefinementLocus(host, store, {
        chr: quickAdd.dataset.manualRefChr,
        kind: quickAdd.dataset.manualRefKind,
        segmentId: quickAdd.dataset.manualRefSegmentId,
      }, deps);
      return;
    }

    const removeBtn = event.target?.closest?.("[data-manual-ref-remove]");
    if (removeBtn) {
      const key = normalizeString(removeBtn.dataset.manualRefRemove);
      updateManualRefinementState(host, store, (current) => ({
        loci: current.loci.filter((item) => item.locusKey !== key),
        error: "",
        feedback: "",
      }), deps, { persist: true });
      return;
    }

    const clearReadsBtn = event.target?.closest?.("[data-manual-ref-clear-reads]");
    if (clearReadsBtn) {
      const field = normalizeString(clearReadsBtn.dataset.manualRefClearReads);
      updateManualRefinementState(host, store, () => ({
        ...(field === "ont" ? { ontReadsInput: "" } : { hifiReadsInput: "" }),
        readsMode: "override",
        error: "",
      }), deps, { persist: true });
      return;
    }

    const clearAll = event.target?.closest?.("[data-manual-ref-clear-all]");
    if (clearAll) {
      updateManualRefinementState(host, store, {
        loci: [],
        error: "",
        feedback: "",
      }, deps, { persist: true });
      return;
    }

    const copyBtn = event.target?.closest?.("[data-manual-ref-copy-cmd]");
    if (copyBtn) {
      const command = normalizeString(copyBtn.dataset.manualRefCopyCmd);
      if (!command) return;
      const isEn = store.getState()?.locale === "en";
      void copyTextToClipboard(command).then((copied) => {
        updateManualRefinementState(host, store, {
          error: "",
          feedback: copied
            ? (isEn ? "Copied Server command." : "已复制 Server 执行命令。")
            : (isEn ? "Copy manually from the command box." : "请直接选中命令文本手动复制。"),
        }, deps);
      }).catch(() => {
        updateManualRefinementState(host, store, {
          error: "",
          feedback: isEn ? "Copy manually from the command box." : "请直接选中命令文本手动复制。",
        }, deps);
      });
      return;
    }

    const exportBtn = event.target?.closest?.('[data-manual-ref-export="current-chr"]');
    if (exportBtn) {
      void exportCurrentChrRefinementTasks(host, store, deps);
    }
  });

  host.addEventListener("change", (event) => {
    const toolSelect = event.target?.closest?.("[data-manual-ref-tool-select]");
    if (toolSelect) {
      const key = normalizeString(toolSelect.dataset.manualRefLocusKey);
      const selectedTool = normalizeManualRefinementTool(toolSelect.value, "gap");
      updateManualRefinementState(host, store, (current) => ({
        loci: current.loci.map((item) => {
          if (item.locusKey !== key || item.kind !== "gap") {
            return item;
          }
          return {
            ...item,
            tool: selectedTool,
            tools: [selectedTool],
          };
        }),
        error: "",
      }), deps, { persist: true });
      return;
    }

    const readsModeInput = event.target?.closest?.("[data-manual-ref-reads-mode]");
    if (readsModeInput) {
      const mode = readsModeInput.value === "override" ? "override" : "inherit";
      updateManualRefinementState(host, store, {
        readsMode: mode,
        error: "",
      }, deps, { persist: true });
      return;
    }

    const motifInput = event.target?.closest?.("[data-manual-ref-motif-input]");
    if (motifInput) {
      const key = normalizeString(motifInput.dataset.manualRefLocusKey);
      const motif = normalizeString(motifInput.value).toUpperCase();
      updateManualRefinementState(host, store, (current) => ({
        loci: current.loci.map((item) => (item.locusKey === key ? { ...item, motif } : item)),
        error: "",
      }), deps, { persist: true });
      return;
    }

    const readsField = event.target?.closest?.("[data-manual-ref-reads-field]");
    if (readsField) {
      const field = normalizeString(readsField.dataset.manualRefReadsField);
      const value = normalizeString(readsField.value);
      updateManualRefinementState(host, store, {
        readsMode: "override",
        ...(field === "ont" ? { ontReadsInput: value } : { hifiReadsInput: value }),
        error: "",
      }, deps, { persist: true });
    }
  });

  host[MANUAL_REF_CARD_BOUND] = true;
}
