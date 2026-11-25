import { renderExportJobDialog } from "../export-job-dialog.js";
import { getAssemblyLocale } from "./i18n.js";

export function createAssemblyProgressModalRenderer({
  escapeAttr,
  escapeHtml,
  getAssemblyI18n,
}) {
  function renderProgressStepIcon(status) {
    if (status === "running") {
      return `<span class="pipeline-spinner" aria-hidden="true"></span>`;
    }
    if (status === "done") {
      return `<span class="pipeline-done" aria-hidden="true">&#10003;</span>`;
    }
    if (status === "error") {
      return `<span class="pipeline-error" aria-hidden="true">&#10007;</span>`;
    }
    if (status === "skipped") {
      return `<span class="pipeline-skipped" aria-hidden="true">-</span>`;
    }
    return `<span class="pipeline-pending" aria-hidden="true">&#9675;</span>`;
  }

  function resolveProgressIconStatus(status) {
    if (status === "success") {
      return "done";
    }
    if (status === "error") {
      return "error";
    }
    if (status === "running") {
      return "running";
    }
    return "pending";
  }

  function buildAssemblyImportProgressMeta(stages) {
    const list = Array.isArray(stages) ? stages : [];
    const progressOffset = list.findIndex((stage) => {
      if (!stage || typeof stage !== "object") {
        return false;
      }
      const progressIndex = Number(stage.progressIndex);
      return Number.isFinite(progressIndex) && progressIndex > 0;
    });
    const offset = progressOffset >= 0 ? progressOffset : 0;
    let latestProgressIndex = 0;
    let latestProgressTotal = 0;
    for (const stage of list) {
      if (stage && typeof stage === "object") {
        const progressIndex = Number(stage.progressIndex);
        const progressTotal = Number(stage.progressTotal);
        if (Number.isFinite(progressIndex) && progressIndex > latestProgressIndex) {
          latestProgressIndex = progressIndex;
        }
        if (Number.isFinite(progressTotal) && progressTotal > latestProgressTotal) {
          latestProgressTotal = progressTotal;
        }
      }
    }
    const current = latestProgressIndex > 0
      ? Math.max(list.length, offset + latestProgressIndex)
      : list.length;
    const total = Math.max(
      list.length,
      latestProgressTotal > 0 ? offset + latestProgressTotal : list.length,
    );
    return {
      offset,
      current: Math.min(current, total),
      total,
    };
  }

  function formatAssemblyImportProgressStage(stage, index, progressMeta) {
    const label = stage && typeof stage === "object"
      ? String(stage.label || stage.text || "")
      : String(stage || "");
    const progressIndex = stage && typeof stage === "object" ? Number(stage.progressIndex) : 0;
    const displayIndex = Number.isFinite(progressIndex) && progressIndex > 0
      ? progressMeta.offset + progressIndex
      : index + 1;
    if (!progressMeta.total) {
      return label;
    }
    return `${label} (${displayIndex}/${progressMeta.total})`;
  }

  function renderAddCtgImportProgressModal(state) {
    const progress = state.assembly?.addCtgImportProgress;
    if (!progress?.open) {
      return "";
    }
    const runtimeI18n = getAssemblyI18n(state).runtime || {};
    const allStages = Array.isArray(progress.stages) ? progress.stages : [];
    const recentOffset = Math.max(0, allStages.length - 60);
    const recentStages = allStages.slice(recentOffset);
    const progressMeta = buildAssemblyImportProgressMeta(allStages);
    const status = String(progress.status || "running");
    const isTerminal = status === "success" || status === "error";
    const title = runtimeI18n.addCtgImportProgressTitle || "add_ctg 导入进度";
    const summary = String(
      progress.summary
      || runtimeI18n.addCtgImportProgressSubtitle
      || "正在导入 add_ctg 包。",
    );
    const stageItems = recentStages.length
      ? recentStages.map((stage, index) => {
        const absoluteIndex = recentOffset + index;
        const rowStatus = isTerminal && index === recentStages.length - 1
          ? status
          : index === recentStages.length - 1
            ? "running"
            : "done";
        const iconStatus = resolveProgressIconStatus(rowStatus);
        return `
          <div class="pipeline-step-row import-progress-step add-ctg-import-progress-step ${escapeAttr(rowStatus)}">
            <span class="pipeline-step-label">${escapeHtml(formatAssemblyImportProgressStage(stage, absoluteIndex, progressMeta))}</span>
            <span class="pipeline-step-icon">${renderProgressStepIcon(iconStatus)}</span>
          </div>
        `;
      }).join("")
      : `<div class="pipeline-step-row import-progress-step add-ctg-import-progress-step running">
          <span class="pipeline-step-label">${escapeHtml(runtimeI18n.addCtgImportNotStarted || "准备导入...")}</span>
          <span class="pipeline-step-icon">${renderProgressStepIcon("running")}</span>
        </div>`;
    const closeButton = isTerminal
      ? `<button type="button" class="button ghost tiny import-progress-close" data-add-ctg-import-close="1" data-app-tooltip="${escapeAttr(runtimeI18n.addCtgImportClose || "关闭")}">x</button>`
      : "";
    const percent = progressMeta.total > 0
      ? Math.max(0, Math.min(100, (progressMeta.current / progressMeta.total) * 100))
      : 0;
    const meter = progressMeta.total > 0
      ? `<div class="import-progress-meter" aria-label="${escapeAttr(`${progressMeta.current}/${progressMeta.total}`)}">
          <div class="import-progress-meter-track">
            <div class="import-progress-meter-fill" style="width: ${escapeAttr(percent.toFixed(1))}%;"></div>
          </div>
          <span class="import-progress-meter-text">${escapeHtml(`${progressMeta.current}/${progressMeta.total}`)}</span>
        </div>`
      : "";
    return `
      <div class="modal-overlay import-progress-overlay add-ctg-import-progress-overlay" data-add-ctg-import-progress-overlay="true">
        <article class="card modal-dialog import-progress-dialog add-ctg-import-progress-dialog" role="dialog" aria-modal="true" aria-label="${escapeAttr(title)}">
          ${closeButton}
          <div class="import-progress-heading">
            ${isTerminal ? "" : `<span class="pipeline-spinner" aria-hidden="true"></span>`}
            <div>
              <div class="import-progress-title-row">
                <h4>${escapeHtml(title)}</h4>
                ${meter}
              </div>
              <p class="muted">${escapeHtml(summary)}</p>
              ${progress.error ? `<p class="error-text">${escapeHtml(String(progress.error))}</p>` : ""}
            </div>
          </div>
          <div class="import-progress-list add-ctg-import-progress-list">${stageItems}</div>
        </article>
      </div>
    `;
  }

  function renderBatchDeleteProgressModal(state) {
    const progress = state.assembly?.batchDeleteProgress;
    if (!progress?.open) {
      return "";
    }
    const runtimeI18n = getAssemblyI18n(state).runtime || {};
    const items = Array.isArray(progress.items) ? progress.items : [];
    const total = Math.max(0, Number(progress.total) || items.length);
    const current = Math.min(total, Math.max(0, Number(progress.current) || 0));
    const percent = total > 0 ? Math.round((current / total) * 100) : 0;
    const title = runtimeI18n.batchDeleteProgressTitle || "批量删除进度";
    const subtitle = runtimeI18n.batchDeleteProgressSubtitle || "正在删除选中的 contig。";
    return `
      <div
        class="modal-overlay import-progress-overlay batch-delete-progress-overlay"
        data-batch-delete-progress-overlay="true"
      >
        <article
          class="card modal-dialog import-progress-dialog batch-delete-progress-dialog"
          data-batch-delete-progress-modal="true"
          role="dialog"
          aria-modal="true"
          aria-label="${escapeAttr(title)}"
        >
          <div class="import-progress-heading">
            <span class="pipeline-spinner" aria-hidden="true"></span>
            <div>
              <div class="import-progress-title-row">
                <h4>${escapeHtml(title)}</h4>
                <div class="import-progress-meter" aria-label="${escapeAttr(`${current}/${total}`)}">
                  <div class="import-progress-meter-track">
                    <div class="import-progress-meter-fill" style="width: ${escapeAttr(percent)}%;"></div>
                  </div>
                  <span class="import-progress-meter-text">${escapeHtml(`${current}/${total}`)}</span>
                </div>
              </div>
              <p class="muted">${escapeHtml(subtitle)}</p>
            </div>
          </div>
          <div class="import-progress-list batch-delete-progress-list">
            ${items.map((item) => {
              const status = String(item?.status || "pending");
              const iconStatus = resolveProgressIconStatus(status);
              const label = String(item?.label || `Ctg${item?.assemblyCtgId ?? ""}`).trim();
              const idText = `assembly_ctg_id=${item?.assemblyCtgId ?? ""}`;
              return `
                <div
                  class="pipeline-step-row import-progress-step batch-delete-progress-step ${escapeAttr(status)}"
                  data-batch-delete-progress-row="${escapeAttr(item?.assemblyCtgId ?? "")}"
                  data-batch-delete-progress-status="${escapeAttr(status)}"
                >
                  <span class="pipeline-step-label">
                    ${escapeHtml(label)}
                    <span class="muted">${escapeHtml(idText)}</span>
                    ${item?.error ? `<span class="error-text">${escapeHtml(String(item.error))}</span>` : ""}
                  </span>
                  <span class="pipeline-step-icon">${renderProgressStepIcon(iconStatus)}</span>
                </div>
              `;
            }).join("")}
          </div>
        </article>
      </div>
    `;
  }

  function renderFinalPathExportModal(state) {
    const job = state.assembly?.finalPathExportJob;
    if (!job?.open) {
      return "";
    }
    const pageI18n = getAssemblyI18n(state).page || {};
    const kind = String(job?.kind || "").trim().toLowerCase();
    const isRefinementExport = kind === "refinement-current-chr" || kind === "refine-jobs";
    const refinementReceipt = isRefinementExport && job?.status === "success" && (job?.batchSha256 || job?.serverCommand)
      ? `<div class="manual-ref-receipt">
          ${job.batchSha256 ? `<p class="muted"><code>batch ${escapeHtml(String(job.batchSha256).slice(0, 12))}</code>${Number.isFinite(Number(job.lociCount)) ? ` · ${escapeHtml(`${job.lociCount} / ${job.tasksCount ?? job.lociCount}`)}` : ""}</p>` : ""}
          ${job.serverCommand ? `<div class="manual-ref-cmd-row"><code class="manual-ref-cmd">${escapeHtml(String(job.serverCommand))}</code></div>` : ""}
        </div>`
      : "";
    return renderExportJobDialog({
      job, locale: getAssemblyLocale(state), scope: "assembly", escapeHtml, receipt: refinementReceipt,
      stepLabel: kind => pageI18n[{
        png: "finalPathExportPng", tsv: "finalPathExportTsv", log: "finalPathExportLog",
        fasta: "finalPathExportFasta", agp: "finalPathExportAgp",
      }[kind]] || kind,
    });
  }

  return {
    renderAddCtgImportProgressModal,
    renderBatchDeleteProgressModal,
    renderFinalPathExportModal,
  };
}
