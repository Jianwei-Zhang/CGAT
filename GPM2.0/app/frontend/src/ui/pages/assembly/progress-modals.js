export function createAssemblyProgressModalRenderer({
  escapeAttr,
  escapeHtml,
  getAssemblyI18n,
}) {
  function resolveFinalPathExportKindLabel(job, labels) {
    const kind = String(job?.kind || "").trim().toLowerCase();
    if (kind === "png") {
      return labels.finalPathExportPng || "图(.png)";
    }
    if (kind === "tsv") {
      return labels.finalPathExportTsv || "表(.tsv)";
    }
    if (kind === "fasta") {
      return labels.finalPathExportFasta || "序列(.fasta)";
    }
    if (kind === "log") {
      return labels.finalPathExportLog || "日志(.log)";
    }
    if (kind === "degap-jobs") {
      return labels.finalPathExportDegapJobs || "DEGAP-JOBS";
    }
    if (kind === "all") {
      return labels.finalPathExportAll || "All";
    }
    return kind || (labels.finalPathExport || "Export");
  }

  function resolveFinalPathExportStatusText(job, labels) {
    if (job?.status === "success") {
      return labels.finalPathExportCompleted || "已完成导出";
    }
    if (job?.status === "error") {
      return labels.finalPathExportFailed || "导出失败";
    }
    if (job?.status === "canceled") {
      return labels.finalPathExportCanceled || "已终止，已保留已导出的文件";
    }
    const template = labels.finalPathExportRunning || "正在执行：{step}";
    return template.replace("{step}", String(job?.currentStep || "").trim());
  }

  function renderFinalPathExportStepIcon(status) {
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

  function resolveFinalPathExportStepStatus(job, step) {
    const completedOutputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
    const completedStepIds = Array.isArray(job?.completedStepIds) ? job.completedStepIds : [];
    const currentStep = String(job?.currentStep || "").trim();
    const stepLabel = String(step?.label || "").trim();
    const stepId = String(step?.id || "").trim();
    if (stepId && completedStepIds.includes(stepId)) {
      return "done";
    }
    if (completedOutputs.includes(step?.outputPath)) {
      return "done";
    }
    if (
      job?.kind === "degap-jobs"
      && ["degap-prepare", "degap-job", "degap-manifest"].includes(step?.kind)
    ) {
      if (job?.status === "running") {
        return "running";
      }
      if (job?.status === "error") {
        return "error";
      }
    }
    if (job?.status === "running" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
      return "running";
    }
    if (job?.status === "error" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
      return "error";
    }
    if (job?.status === "canceled") {
      return "skipped";
    }
    return "pending";
  }

  function renderFinalPathExportSteps(job) {
    const displaySteps = Array.isArray(job?.displaySteps) ? job.displaySteps : [];
    const steps = displaySteps.length ? displaySteps : Array.isArray(job?.steps) ? job.steps : [];
    if (!steps.length) {
      return "";
    }
    return `
      <div class="assembly-final-path-export-steps">
        ${steps.map((step) => {
          const stepStatus = resolveFinalPathExportStepStatus(job, step);
          return `
            <div
              class="pipeline-step-row assembly-final-path-export-step ${stepStatus}"
              data-final-path-export-step-status="${escapeAttr(stepStatus)}"
            >
              <span class="pipeline-step-label">${escapeHtml(String(step?.label || ""))}</span>
              <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(stepStatus)}</span>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function renderFinalPathExportCompletedOutputs(job) {
    const outputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
    if (!outputs.length) {
      return "";
    }
    return `
      <ul class="assembly-final-path-export-output-list">
        ${outputs.map((outputPath) => `<li>${escapeHtml(String(outputPath || ""))}</li>`).join("")}
      </ul>
    `;
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
            <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(iconStatus)}</span>
          </div>
        `;
      }).join("")
      : `<div class="pipeline-step-row import-progress-step add-ctg-import-progress-step running">
          <span class="pipeline-step-label">${escapeHtml(runtimeI18n.addCtgImportNotStarted || "准备导入...")}</span>
          <span class="pipeline-step-icon">${renderFinalPathExportStepIcon("running")}</span>
        </div>`;
    const closeButton = isTerminal
      ? `<button type="button" class="button ghost tiny import-progress-close" data-add-ctg-import-close="1" title="${escapeAttr(runtimeI18n.addCtgImportClose || "关闭")}">x</button>`
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
                  <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(iconStatus)}</span>
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
    const kindLabel = resolveFinalPathExportKindLabel(job, pageI18n);
    const statusText = resolveFinalPathExportStatusText(job, pageI18n);
    const statusClass = job?.status === "success" ? "success" : "";
    return `
      <div class="modal-overlay assembly-final-path-export-overlay" data-final-path-export-overlay="true">
        <article
          class="card modal-dialog assembly-final-path-export-dialog"
          data-final-path-export-modal="true"
          role="dialog"
          aria-modal="true"
          aria-label="${escapeAttr(pageI18n.finalPathExportDialogTitle || "正在导出 final path")}"
        >
          <button
            type="button"
            class="button ghost tiny assembly-final-path-export-close"
            data-final-path-export-close="true"
          >x</button>
          <div class="assembly-final-path-export-body">
            <header class="assembly-final-path-export-head">
              <h4>${escapeHtml(pageI18n.finalPathExportDialogTitle || "正在导出 final path")}</h4>
              <p class="muted">${escapeHtml(`${String(job?.chrName || "").trim()} · ${kindLabel}`)}</p>
            </header>
            ${renderFinalPathExportSteps(job)}
            <p class="muted assembly-final-path-export-status ${escapeAttr(statusClass)}">${escapeHtml(statusText)}</p>
            ${job?.error ? `<p class="error-text">${escapeHtml(String(job.error || ""))}</p>` : ""}
            ${renderFinalPathExportCompletedOutputs(job)}
          </div>
        </article>
      </div>
    `;
  }

  return {
    renderAddCtgImportProgressModal,
    renderBatchDeleteProgressModal,
    renderFinalPathExportModal,
  };
}
