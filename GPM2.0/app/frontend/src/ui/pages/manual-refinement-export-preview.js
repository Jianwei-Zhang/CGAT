import { pickSaveFilePath } from "../../services/backend-api.js";
import {
  exportManualRefinement,
  getProjectAssemblyViewState,
} from "../../services/workflow-api.js";
import {
  MANUAL_REFINEMENT_TOOL_LABELS,
  buildManualRefinementExportBaseName,
  buildManualRefinementExportRequest,
  buildManualRefinementServerCommand,
  extractFileName,
  normalizeManualRefinementState,
  normalizeManualRefinementTools,
} from "./assembly/manual-refinement-state.js";
import {
  buildTimestampedExportBaseName,
  resolveExportTimestamp,
} from "./assembly/final-path-export-runtime.js";

const COPY = {
  zh: {
    title: "导出精修任务包",
    subtitle: "{project} · 共 {loci} 个位点 / {chrs} 条染色体",
    empty: "本项目暂无已登记的精修任务。请先进入「装配」页，在 Final Path 上登记 Gap 或左/右端粒位点。",
    chrCount: "{count} 个任务",
    kindGap: "Gap",
    kindTelLeft: "左端粒",
    kindTelRight: "右端粒",
    telFixedTool: "DEGAP TelSeeker",
    motifPrefix: "Motif",
    readsInherit: "Server reads：沿用项目默认（不公开私有路径）",
    readsOverride: "Server reads：使用本次手动覆盖配置",
    cancel: "取消",
    close: "关闭",
    confirm: "确认导出",
    exporting: "正在导出...",
    successTitle: "精修任务包已导出，等待 Server 运行",
    batchMeta: "批次 {batch} · {loci} 位点 / {tasks} 次工具运行",
    serverCmdLabel: "Server 命令",
    copyCmd: "复制命令",
    copiedCmd: "已复制 Server 命令。",
    switchedError: "当前项目已切换，已取消导出以避免写入错误项目。",
    loading: "正在读取本项目已登记的精修任务...",
    scopeNote: "仅导出本项目各染色体已登记位点，不扫描未选位点、不跨项目、不跟随轨道。",
  },
  en: {
    title: "Export Refinement Task Bundle",
    subtitle: "{project} · {loci} loci across {chrs} chromosomes",
    empty: "No refinement tasks are queued in this project yet. Open Assembly to queue Gap or Left/Right Telomere loci on the Final Path.",
    chrCount: "{count} task(s)",
    kindGap: "Gap",
    kindTelLeft: "Left Tel",
    kindTelRight: "Right Tel",
    telFixedTool: "DEGAP TelSeeker",
    motifPrefix: "Motif",
    readsInherit: "Server reads: Inherit project default (private paths hidden)",
    readsOverride: "Server reads: Custom override configured",
    cancel: "Cancel",
    close: "Close",
    confirm: "Confirm Export",
    exporting: "Exporting...",
    successTitle: "Refinement archive exported · awaiting Server run",
    batchMeta: "Batch {batch} · {loci} loci / {tasks} tool runs",
    serverCmdLabel: "Server command",
    copyCmd: "Copy",
    copiedCmd: "Copied Server command.",
    switchedError: "Active project changed; export canceled to protect project data.",
    loading: "Loading queued refinement tasks for this project...",
    scopeNote: "Exports only loci registered across this project (never scans unselected loci, crosses projects, or follows tracks).",
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}

function fmt(template, vars = {}) {
  return String(template || "").replace(/\{(\w+)\}/g, (_, key) => String(vars[key] ?? ""));
}

function normalizeString(value) {
  return String(value ?? "").trim();
}

function kindLabel(kind, copy) {
  if (kind === "tel_left") return copy.kindTelLeft;
  if (kind === "tel_right") return copy.kindTelRight;
  return copy.kindGap;
}

export function isSameRefinementExportProject(state, identity) {
  const workspaceRoot = normalizeString(identity?.workspaceRoot ?? identity?.workspacePath);
  const projectId = Number(identity?.projectId || 0);
  if (!workspaceRoot || !projectId) {
    return false;
  }
  return (
    normalizeString(state?.session?.workspacePath) === workspaceRoot
    && Number(state?.session?.projectId || 0) === projectId
  );
}

export function groupManualRefinementLociByChr(loci) {
  const groups = new Map();
  (Array.isArray(loci) ? loci : []).forEach((locus) => {
    const chr = normalizeString(locus?.chr);
    if (!chr) {
      return;
    }
    const list = groups.get(chr) || [];
    list.push(locus);
    groups.set(chr, list);
  });
  return Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true }))
    .map(([chrName, items]) => ({ chrName, loci: items }));
}

export function renderManualRefinementExportPreviewModal(modal, state) {
  if (!modal?.open || !isSameRefinementExportProject(state, modal)) {
    return "";
  }
  const copy = COPY[state?.locale === "en" ? "en" : "zh"];
  const groups = groupManualRefinementLociByChr(modal.loci);
  const totalLoci = Array.isArray(modal.loci) ? modal.loci.length : 0;
  const isExporting = modal.status === "exporting";
  const isSuccess = modal.status === "success";
  const isLoading = modal.status === "loading";
  const canConfirm = !isLoading && !isExporting && !isSuccess && Boolean(modal.request?.loci?.length) && !modal.validationError;
  const subtitle = isLoading
    ? copy.loading
    : fmt(copy.subtitle, {
      project: modal.projectName || `Project ${modal.projectId}`,
      loci: totalLoci,
      chrs: groups.length,
    });
  const readsSummary = modal.readsMode === "override" ? copy.readsOverride : copy.readsInherit;

  const groupsMarkup = isLoading
    ? `<p class="muted manual-ref-empty">${escapeHtml(copy.loading)}</p>`
    : groups.length
      ? `<div class="manual-ref-preview-groups">
          ${groups.map((group) => `<section class="manual-ref-preview-group" data-refinement-export-preview-chr="${escapeAttr(group.chrName)}">
            <header class="manual-ref-preview-group-head">
              <strong>${escapeHtml(group.chrName)}</strong>
              <span class="muted">${escapeHtml(fmt(copy.chrCount, { count: group.loci.length }))}</span>
            </header>
            <ul class="manual-ref-preview-list">
              ${group.loci.map((locus) => {
                const targetText = locus.label || locus.segmentId;
                const toolText = locus.kind === "gap"
                  ? normalizeManualRefinementTools(locus.tools ?? locus.tool).map((tool) => MANUAL_REFINEMENT_TOOL_LABELS[tool]).join(", ")
                  : copy.telFixedTool;
                return `<li class="manual-ref-preview-row">
                  <span class="manual-ref-kind-badge is-${escapeAttr(locus.kind)}">${escapeHtml(kindLabel(locus.kind, copy))}</span>
                  <span class="manual-ref-locus-target" data-app-tooltip="${escapeAttr(targetText)}" data-app-tooltip-overflow>${escapeHtml(targetText)}</span>
                  <span class="manual-ref-preview-tool">${escapeHtml(toolText)}</span>
                  ${locus.kind !== "gap" && locus.motif ? `<code class="manual-ref-preview-motif">${escapeHtml(`${copy.motifPrefix}: ${locus.motif}`)}</code>` : ""}
                </li>`;
              }).join("")}
            </ul>
          </section>`).join("")}
        </div>`
      : `<p class="muted manual-ref-empty">${escapeHtml(copy.empty)}</p>`;

  const receiptMarkup = isSuccess && modal.receipt
    ? `<div class="manual-ref-receipt" data-refinement-export-preview-receipt role="status">
        <div class="manual-ref-receipt-head">
          <strong>${escapeHtml(copy.successTitle)}</strong>
          <span class="manual-ref-status-pill is-pending">${escapeHtml(fmt(copy.batchMeta, {
            batch: String(modal.receipt.batchSha256 || "").slice(0, 12),
            loci: modal.receipt.lociCount,
            tasks: modal.receipt.tasksCount,
          }))}</span>
        </div>
        ${modal.receipt.outputPath ? `<div class="manual-ref-receipt-path"><code data-app-tooltip="${escapeAttr(modal.receipt.outputPath)}" data-app-tooltip-overflow>${escapeHtml(modal.receipt.outputPath)}</code></div>` : ""}
        <div class="manual-ref-command-row">
          <span class="manual-ref-command-label">${escapeHtml(copy.serverCmdLabel)}</span>
          <code class="manual-ref-command-code">${escapeHtml(modal.receipt.serverCommand || buildManualRefinementServerCommand(modal.receipt.outputPath))}</code>
          <button type="button" class="button ghost tiny" data-refinement-export-preview-copy="${escapeAttr(modal.receipt.serverCommand || buildManualRefinementServerCommand(modal.receipt.outputPath))}">${escapeHtml(copy.copyCmd)}</button>
        </div>
      </div>`
    : "";

  return `<div class="modal-overlay assembly-final-path-export-overlay" data-refinement-export-preview-overlay="true">
    <article
      class="card modal-dialog manual-ref-preview-modal"
      data-refinement-export-preview-modal="true"
      role="dialog"
      aria-modal="true"
      aria-label="${escapeAttr(copy.title)}"
      aria-busy="${isLoading || isExporting ? "true" : "false"}"
    >
      <header class="manual-ref-preview-head">
        <div>
          <h4>${escapeHtml(copy.title)}</h4>
          <p class="muted manual-ref-hint">${escapeHtml(subtitle)}</p>
        </div>
        <button
          type="button"
          class="button ghost tiny"
          data-refinement-export-preview-cancel="true"
          aria-label="${escapeAttr(copy.close)}"
          ${isExporting ? "disabled" : ""}
        >×</button>
      </header>
      <div class="manual-ref-preview-body">
        ${groupsMarkup}
        ${!isLoading && groups.length ? `<p class="muted manual-ref-hint">${escapeHtml(readsSummary)}</p>` : ""}
        ${modal.validationError ? `<p class="error-text manual-ref-feedback is-error" role="alert">${escapeHtml(modal.validationError)}</p>` : ""}
        ${modal.error ? `<p class="error-text manual-ref-feedback is-error" role="alert">${escapeHtml(modal.error)}</p>` : ""}
        ${modal.copyFeedback ? `<p class="manual-ref-feedback is-ok" role="status">${escapeHtml(modal.copyFeedback)}</p>` : ""}
        ${receiptMarkup}
      </div>
      <footer class="manual-ref-preview-foot">
        <span class="muted manual-ref-hint">${escapeHtml(copy.scopeNote)}</span>
        <div class="manual-ref-foot-actions">
          <button
            type="button"
            class="button ghost tiny"
            data-refinement-export-preview-cancel="true"
            ${isExporting ? "disabled" : ""}
          >${escapeHtml(isSuccess ? copy.close : copy.cancel)}</button>
          ${isSuccess ? "" : `<button
            type="button"
            class="button primary tiny"
            data-refinement-export-preview-confirm="true"
            ${canConfirm ? "" : "disabled"}
          >${escapeHtml(isExporting ? copy.exporting : copy.confirm)}</button>`}
        </div>
      </footer>
    </article>
  </div>`;
}

export async function prepareFrozenManualRefinementAllPreview({
  host,
  store,
  workspaceRoot,
  projectId,
  projectName = "",
  locale = "zh",
  deps = {},
}) {
  const normalizedWorkspace = normalizeString(workspaceRoot);
  const normalizedProjectId = Number(projectId || 0);
  if (!normalizedWorkspace || !normalizedProjectId) {
    return null;
  }
  if (typeof deps.flushAssemblyProjectState === "function") {
    await deps.flushAssemblyProjectState(host, store);
  }
  if (!isSameRefinementExportProject(store.getState(), { workspaceRoot: normalizedWorkspace, projectId: normalizedProjectId })) {
    return null;
  }
  const getViewState = deps.getProjectAssemblyViewState || getProjectAssemblyViewState;
  const viewState = await getViewState({
    workspaceRoot: normalizedWorkspace,
    projectId: normalizedProjectId,
  });
  if (!isSameRefinementExportProject(store.getState(), { workspaceRoot: normalizedWorkspace, projectId: normalizedProjectId })) {
    return null;
  }
  const degapProjectState = viewState?.degapProjectState && typeof viewState.degapProjectState === "object"
    ? viewState.degapProjectState
    : {};
  const manualState = normalizeManualRefinementState(degapProjectState.manualRefinement);
  const built = buildManualRefinementExportRequest(manualState, {
    scope: "all",
    chrName: "",
    locale,
  });
  return {
    open: true,
    status: "ready",
    workspaceRoot: normalizedWorkspace,
    workspacePath: normalizedWorkspace,
    projectId: normalizedProjectId,
    projectName: normalizeString(projectName) || `Project ${normalizedProjectId}`,
    readsMode: manualState.readsMode,
    loci: built.loci,
    request: built.ok ? built.request : null,
    validationError: built.ok || !manualState.loci.length ? "" : built.error,
    error: "",
    copyFeedback: "",
    receipt: null,
  };
}

export async function executeFrozenManualRefinementExport({
  host,
  store,
  modal,
  deps = {},
  isCurrent = () => true,
}) {
  if (!modal?.open || !modal?.request?.loci?.length) {
    return { ok: false, canceled: false, switched: false };
  }
  const frozenIdentity = {
    workspaceRoot: normalizeString(modal.workspaceRoot ?? modal.workspacePath),
    projectId: Number(modal.projectId || 0),
  };
  const ownsExport = () => isCurrent() && isSameRefinementExportProject(store.getState(), frozenIdentity);
  if (!ownsExport()) {
    return { ok: false, canceled: false, switched: true };
  }

  const stateBeforePicker = store.getState();
  const exportTimestamp = resolveExportTimestamp(deps);
  const baseName = buildTimestampedExportBaseName(
    buildManualRefinementExportBaseName({
      projectName: modal.projectName,
      chrName: "",
      scope: "all",
    }),
    exportTimestamp,
  );
  const pickSave = deps.pickSaveFilePath || pickSaveFilePath;
  const targetPath = normalizeString(await pickSave({
    defaultPath: `${baseName}.zip`,
    filters: [{ name: "ZIP", extensions: ["zip"] }],
  }, stateBeforePicker));
  if (!targetPath) {
    return { ok: false, canceled: true, switched: false };
  }
  if (!ownsExport()) {
    return { ok: false, canceled: false, switched: true };
  }
  if (typeof deps.flushAssemblyProjectState === "function") {
    await deps.flushAssemblyProjectState(host, store);
  }
  if (!ownsExport()) {
    return { ok: false, canceled: false, switched: true };
  }

  const exportFn = deps.exportManualRefinement || exportManualRefinement;
  const summary = await exportFn({
    workspaceRoot: frozenIdentity.workspaceRoot,
    projectId: frozenIdentity.projectId,
    outputPath: targetPath,
    request: modal.request,
    stateOrLocale: stateBeforePicker,
  });
  if (!ownsExport()) {
    return { ok: false, canceled: false, switched: true };
  }

  const batchSha256 = normalizeString(summary?.batch_sha256 || summary?.batchSha256) || "exported";
  const receipt = {
    batchSha256,
    exportedAt: new Date().toISOString(),
    outputPath: targetPath,
    outputFileName: extractFileName(targetPath) || "refinement_tasks.zip",
    scope: "all",
    chrName: "",
    lociCount: Number(summary?.loci ?? modal.request.loci.length),
    tasksCount: Number(summary?.tasks ?? modal.request.loci.reduce((n, locus) => n + locus.tools.length, 0)),
    readsMode: modal.readsMode === "override" ? "override" : "inherit",
    loci: modal.loci,
    status: "exported_awaiting_server",
    serverCommand: buildManualRefinementServerCommand(targetPath),
  };

  return {
    ok: true,
    canceled: false,
    switched: false,
    receipt,
  };
}
