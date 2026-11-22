import {
  MANUAL_REFINEMENT_GAP_TOOLS,
  MANUAL_REFINEMENT_TOOL_LABELS,
  buildManualRefinementServerCommand,
  filterManualRefinementLociByScope,
  listManualRefinementCandidatesForEntry,
  normalizeManualRefinementState,
  normalizeManualRefinementTool,
} from "./manual-refinement-state.js";

const COPY = {
  zh: {
    title: "精修任务",
    toggleOpen: "展开精修任务面板",
    toggleClose: "收起精修任务面板",
    scopeCurrentPill: "当前 {chr} · {count}",
    scopeCurrentFallback: "当前染色体 · {count}",
    scopeAllPill: "全项目 · {count}",
    empty: "暂未登记精修任务。右键上方 Final Path 中的 Gap 或两端 Contig，或从下方候选快速添加；每个 Gap 单选 1 个工具（默认 DEGAP）。",
    quickAddTitle: "快速添加 ({chr})",
    noCandidates: "当前染色体暂无符合条件的 Gap（需两侧直连 Contig）或端粒端点。",
    addedTag: "已加入",
    kindGap: "Gap",
    kindTelLeft: "左端粒",
    kindTelRight: "右端粒",
    toolGroupHint: "补洞工具（单选）",
    telToolShort: "DEGAP TelSeeker",
    telToolFull: "固定使用 DEGAP TelSeeker (telseeker_ctg)",
    motifLabel: "Motif",
    motifPlaceholder: "留空沿用项目规则，如 TTAGGG",
    motifAria: "{chr} {kind} 端粒 motif",
    removeLocus: "移除任务：{target}",
    readsSummaryInherit: "Server reads：沿用项目默认",
    readsSummaryOverride: "Server reads：本次手动覆盖",
    readsTitle: "Server 端测序 reads 策略（可选）",
    readsInherit: "沿用项目已校验 reads（不展示私有路径；若为空仍可导出，在 Server 传 --hifi / --ont）",
    readsOverride: "手动指定或清空 reads（填写服务器绝对路径，支持空 reads 导出）",
    hifiLabel: "HiFi reads（服务端绝对路径，分号或换行分隔）",
    ontLabel: "ONT reads（服务端绝对路径，分号或换行分隔）",
    clearReads: "清空",
    readsNote: "App 不探测本地路径，也不按后缀猜技术类型；空 reads 仍可导出并由 Server 端 --hifi / --ont 指定。",
    exportCurrentChr: "导出当前染色体 ({count})",
    exportCurrentChrTitle: "导出精修任务（当前染色体 {chr} 已选 · {count}）",
    exportAllProject: "预览并导出全项目 ({count})",
    exportAllProjectTitle: "打开全项目精修任务预览与导出确认（本项目全部已选 · {count}）",
    exporting: "正在导出精修任务...",
    clearDraft: "清空草稿",
    exportedTitle: "精修任务包已导出 · 等待 Server 运行",
    exportedScopeCurrent: "当前染色体 ({chr})",
    exportedScopeAll: "本项目全部已选",
    exportedMeta: "批次 {batch} · {loci} 位点 / {tasks} 任务",
    serverCmdLabel: "Server 命令",
    copyCmd: "复制",
    serverCmdHint: "将 ZIP 传到对应 Server 工作区运行（或 ~/bin/refine.py，按需加 --hifi / --ont）；完成后在「项目页 → 精修」导入结果。",
    scopeBoundaryNote: "全项目导出仅汇总本项目各染色体已登记位点，不扫描未选位点、不跨项目、不跟随轨道。",
  },
  en: {
    title: "Refinement Tasks",
    toggleOpen: "Expand refinement tasks panel",
    toggleClose: "Collapse refinement tasks panel",
    scopeCurrentPill: "{chr} · {count}",
    scopeCurrentFallback: "Current chr · {count}",
    scopeAllPill: "Project · {count}",
    empty: "No refinement tasks queued. Right-click a Gap or terminal contig in the Final Path above, or quick-add below; each Gap selects one tool (default: DEGAP).",
    quickAddTitle: "Quick add ({chr})",
    noCandidates: "No eligible Gap (requiring direct left/right contigs) or terminal telomere endpoint on this Final Path.",
    addedTag: "Queued",
    kindGap: "Gap",
    kindTelLeft: "Left Tel",
    kindTelRight: "Right Tel",
    toolGroupHint: "Gap filler tool (single choice)",
    telToolShort: "DEGAP TelSeeker",
    telToolFull: "Fixed to DEGAP TelSeeker (telseeker_ctg)",
    motifLabel: "Motif",
    motifPlaceholder: "Empty = project rule, e.g. TTAGGG",
    motifAria: "{chr} {kind} telomere motif",
    removeLocus: "Remove task: {target}",
    readsSummaryInherit: "Server reads: Project default",
    readsSummaryOverride: "Server reads: Custom override",
    readsTitle: "Server-side reads policy (optional)",
    readsInherit: "Inherit verified project reads (private paths stay hidden; empty reads remain exportable for Server --hifi / --ont)",
    readsOverride: "Override or clear reads for this export (Server absolute paths; empty reads allowed)",
    hifiLabel: "HiFi reads (Server absolute paths, separated by semicolon or newline)",
    ontLabel: "ONT reads (Server absolute paths, separated by semicolon or newline)",
    clearReads: "Clear",
    readsNote: "App never probes local paths or guesses technology from extensions; empty reads remain exportable for Server-side --hifi / --ont.",
    exportCurrentChr: "Export Current Chr ({count})",
    exportCurrentChrTitle: "Export Refinement Tasks (Current chr {chr} · {count})",
    exportAllProject: "Preview & Export All ({count})",
    exportAllProjectTitle: "Open preview & confirmation for all queued refinement tasks in project ({count})",
    exporting: "Exporting refinement tasks...",
    clearDraft: "Clear",
    exportedTitle: "Refinement archive exported · awaiting Server run",
    exportedScopeCurrent: "Current chr ({chr})",
    exportedScopeAll: "All queued in project",
    exportedMeta: "Batch {batch} · {loci} loci / {tasks} tasks",
    serverCmdLabel: "Server command",
    copyCmd: "Copy",
    serverCmdHint: "Copy the ZIP to the matching Server workspace and run (or ~/bin/refine.py, optionally with --hifi / --ont); then import from Project → Refinement.",
    scopeBoundaryNote: "All Queued exports only loci registered across this project (never scans unselected loci, crosses projects, or follows tracks).",
  },
};

function fmt(template, vars = {}) {
  return String(template || "").replace(/\{(\w+)\}/g, (_, key) => String(vars[key] ?? ""));
}

function kindLabel(kind, copy) {
  if (kind === "tel_left") return copy.kindTelLeft;
  if (kind === "tel_right") return copy.kindTelRight;
  return copy.kindGap;
}

function renderLocusRow(locus, index, { chrName, exporting, copy, escapeAttr, escapeHtml }) {
  const key = locus.locusKey;
  const isCurrentChr = Boolean(chrName && locus.chr === chrName);
  const selectedTool = normalizeManualRefinementTool(locus.tool ?? locus.tools, locus.kind);
  const radioName = `manual-ref-tool-${index}`;
  const kindText = kindLabel(locus.kind, copy);
  const displayTarget = locus.label || locus.segmentId;
  const srTargetSummary = locus.label && locus.label !== locus.segmentId
    ? `${locus.chr} ${kindText} ${locus.label} (${locus.segmentId})`
    : `${locus.chr} ${kindText} ${displayTarget}`;
  const removeLabel = fmt(copy.removeLocus, { target: `${locus.chr} ${displayTarget}` });

  const controlsMarkup = locus.kind === "gap"
    ? `<div
        class="manual-ref-tool-group"
        role="radiogroup"
        aria-label="${escapeAttr(`${locus.chr} ${displayTarget} ${copy.toolGroupHint}`)}"
      >
        ${MANUAL_REFINEMENT_GAP_TOOLS.map((tool) => {
          const checked = selectedTool === tool;
          const label = MANUAL_REFINEMENT_TOOL_LABELS[tool] || tool;
          return `<label class="manual-ref-tool-option${checked ? " is-selected" : ""}">
            <input
              type="radio"
              class="manual-ref-tool-radio"
              name="${escapeAttr(radioName)}"
              data-manual-ref-tool-select
              data-manual-ref-locus-key="${escapeAttr(key)}"
              value="${escapeAttr(tool)}"
              ${checked ? "checked" : ""}
              ${exporting ? "disabled" : ""}
            />
            <span class="manual-ref-tool-label">${escapeHtml(label)}</span>
          </label>`;
        }).join("")}
      </div>`
    : `<div class="manual-ref-tel-controls">
        <span
          class="manual-ref-fixed-tool"
          data-app-tooltip="${escapeAttr(copy.telToolFull)}"
        >${escapeHtml(copy.telToolShort)}</span>
        <label class="manual-ref-motif-field">
          <span class="manual-ref-motif-label">${escapeHtml(copy.motifLabel)}</span>
          <input
            type="text"
            class="manual-ref-motif-input"
            data-manual-ref-motif-input
            data-manual-ref-locus-key="${escapeAttr(key)}"
            aria-label="${escapeAttr(fmt(copy.motifAria, { chr: locus.chr, kind: kindText }))}"
            value="${escapeAttr(locus.motif || "")}"
            placeholder="${escapeAttr(copy.motifPlaceholder)}"
            autocomplete="off"
            spellcheck="false"
            ${exporting ? "disabled" : ""}
          />
        </label>
      </div>`;

  return `<div
    class="manual-ref-locus-row${isCurrentChr ? " is-current-chr" : ""}"
    data-manual-ref-locus-row="${escapeAttr(key)}"
  >
    <div class="manual-ref-locus-ident">
      <span class="manual-ref-chr-pill${isCurrentChr ? " is-current-chr" : ""}">${escapeHtml(locus.chr)}</span>
      <span class="manual-ref-kind-badge is-${escapeAttr(locus.kind)}">${escapeHtml(kindText)}</span>
      <span
        class="manual-ref-locus-target"
        data-app-tooltip="${escapeAttr(displayTarget)}"
        data-app-tooltip-overflow
      >${escapeHtml(displayTarget)}</span>
      <span class="manual-ref-sr-only">${escapeHtml(srTargetSummary)}</span>
    </div>
    <div class="manual-ref-locus-controls">
      ${controlsMarkup}
      <button
        type="button"
        class="manual-ref-remove-btn"
        data-manual-ref-remove="${escapeAttr(key)}"
        aria-label="${escapeAttr(removeLabel)}"
        data-app-tooltip="${escapeAttr(removeLabel)}"
        ${exporting ? "disabled" : ""}
      >×</button>
    </div>
  </div>`;
}

function renderLastExportReceipt(lastExport, { copy, escapeAttr, escapeHtml }) {
  if (!lastExport) {
    return "";
  }
  const command = buildManualRefinementServerCommand(lastExport.outputPath || lastExport.outputFileName);
  const shortBatch = lastExport.batchSha256.slice(0, 12);
  const scopeText = lastExport.scope === "current-chr"
    ? fmt(copy.exportedScopeCurrent, { chr: lastExport.chrName || "-" })
    : copy.exportedScopeAll;
  return `<div class="manual-ref-receipt" data-manual-ref-receipt role="status">
    <div class="manual-ref-receipt-head">
      <strong>${escapeHtml(copy.exportedTitle)}</strong>
      <span class="manual-ref-status-pill is-pending">${escapeHtml(scopeText)} · ${escapeHtml(fmt(copy.exportedMeta, {
        batch: shortBatch,
        loci: lastExport.lociCount,
        tasks: lastExport.tasksCount,
      }))}</span>
    </div>
    ${lastExport.outputPath ? `<div class="manual-ref-receipt-path"><code data-app-tooltip="${escapeAttr(lastExport.outputPath)}" data-app-tooltip-overflow>${escapeHtml(lastExport.outputPath)}</code></div>` : ""}
    <div class="manual-ref-command-row">
      <span class="manual-ref-command-label">${escapeHtml(copy.serverCmdLabel)}</span>
      <code class="manual-ref-command-code">${escapeHtml(command)}</code>
      <button type="button" class="button ghost tiny" data-manual-ref-copy-cmd="${escapeAttr(command)}">${escapeHtml(copy.copyCmd)}</button>
    </div>
    <p class="muted manual-ref-hint">${escapeHtml(copy.serverCmdHint)}</p>
  </div>`;
}

export function renderManualRefinementCard(
  { chrName, finalPathEntry, manualRefinement, locale = "zh" },
  { escapeAttr, escapeHtml },
) {
  const copy = COPY[locale === "en" ? "en" : "zh"];
  const state = normalizeManualRefinementState(manualRefinement);
  const currentChrLoci = filterManualRefinementLociByScope(state.loci, {
    scope: "current-chr",
    chrName,
  });
  const isOpen = state.panelOpen || state.loci.length > 0 || Boolean(state.lastExport);
  const candidates = listManualRefinementCandidatesForEntry(finalPathEntry);
  const queuedKeys = new Set(state.loci.map((item) => item.locusKey));
  const toggleLabel = isOpen ? copy.toggleClose : copy.toggleOpen;
  const currentPillText = chrName
    ? fmt(copy.scopeCurrentPill, { chr: chrName, count: currentChrLoci.length })
    : fmt(copy.scopeCurrentFallback, { count: currentChrLoci.length });
  const allPillText = fmt(copy.scopeAllPill, { count: state.loci.length });
  const readsSummaryText = state.readsMode === "override"
    ? copy.readsSummaryOverride
    : copy.readsSummaryInherit;

  const quickAddSection = chrName
    ? `<div class="manual-ref-quick-add">
        <span class="manual-ref-quick-label">${escapeHtml(fmt(copy.quickAddTitle, { chr: chrName }))}</span>
        ${candidates.length
          ? `<div class="manual-ref-quick-chips">${candidates.map((candidate) => {
            const queued = queuedKeys.has(candidate.locusKey);
            const targetText = candidate.label || candidate.segmentId;
            const chipText = `${kindLabel(candidate.kind, copy)} · ${targetText}`;
            return `<button
              type="button"
              class="button ghost tiny manual-ref-quick-btn${queued ? " is-queued" : ""}"
              data-manual-ref-quick-add
              data-manual-ref-chr="${escapeAttr(candidate.chr)}"
              data-manual-ref-kind="${escapeAttr(candidate.kind)}"
              data-manual-ref-segment-id="${escapeAttr(candidate.segmentId)}"
              data-app-tooltip="${escapeAttr(chipText)}"
              data-app-tooltip-overflow=".manual-ref-quick-btn-text"
              ${queued || state.exporting ? "disabled" : ""}
            ><span class="manual-ref-quick-btn-prefix" aria-hidden="true">${queued ? "✓" : "+"}</span><span class="manual-ref-quick-btn-text">${escapeHtml(chipText)}</span>${queued ? `<span class="manual-ref-sr-only"> (${escapeHtml(copy.addedTag)})</span>` : ""}</button>`;
          }).join("")}</div>`
          : `<span class="muted manual-ref-hint">${escapeHtml(copy.noCandidates)}</span>`}
      </div>`
    : "";

  const readsSection = `<details class="manual-ref-reads-disclosure"${state.readsMode === "override" ? " open" : ""}>
    <summary class="manual-ref-reads-summary">
      <span>${escapeHtml(readsSummaryText)}</span>
    </summary>
    <fieldset class="manual-ref-reads">
      <legend class="manual-ref-sr-only">${escapeHtml(copy.readsTitle)}</legend>
      <div class="manual-ref-reads-modes">
        <label class="manual-ref-radio">
          <input type="radio" name="manual-ref-reads-mode" data-manual-ref-reads-mode value="inherit" ${state.readsMode !== "override" ? "checked" : ""} ${state.exporting ? "disabled" : ""} />
          <span>${escapeHtml(copy.readsInherit)}</span>
        </label>
        <label class="manual-ref-radio">
          <input type="radio" name="manual-ref-reads-mode" data-manual-ref-reads-mode value="override" ${state.readsMode === "override" ? "checked" : ""} ${state.exporting ? "disabled" : ""} />
          <span>${escapeHtml(copy.readsOverride)}</span>
        </label>
      </div>
      ${state.readsMode === "override"
        ? `<div class="manual-ref-reads-inputs">
            <div class="manual-ref-read-field">
              <label for="manual-ref-hifi-input">${escapeHtml(copy.hifiLabel)}</label>
              <div class="manual-ref-read-input-row">
                <input id="manual-ref-hifi-input" type="text" data-manual-ref-reads-field="hifi" value="${escapeAttr(state.hifiReadsInput)}" placeholder="/server/reads/hifi.fastq.gz" autocomplete="off" spellcheck="false" ${state.exporting ? "disabled" : ""} />
                <button type="button" class="button ghost tiny" data-manual-ref-clear-reads="hifi" ${state.exporting ? "disabled" : ""}>${escapeHtml(copy.clearReads)}</button>
              </div>
            </div>
            <div class="manual-ref-read-field">
              <label for="manual-ref-ont-input">${escapeHtml(copy.ontLabel)}</label>
              <div class="manual-ref-read-input-row">
                <input id="manual-ref-ont-input" type="text" data-manual-ref-reads-field="ont" value="${escapeAttr(state.ontReadsInput)}" placeholder="/server/reads/ont.fastq.gz" autocomplete="off" spellcheck="false" ${state.exporting ? "disabled" : ""} />
                <button type="button" class="button ghost tiny" data-manual-ref-clear-reads="ont" ${state.exporting ? "disabled" : ""}>${escapeHtml(copy.clearReads)}</button>
              </div>
            </div>
            <p class="helper-hint manual-ref-hint">${escapeHtml(copy.readsNote)}</p>
          </div>`
        : ""}
    </fieldset>
  </details>`;

  const exportCurrentTitle = fmt(copy.exportCurrentChrTitle, {
    chr: chrName || "-",
    count: currentChrLoci.length,
  });
  const exportAllTitle = fmt(copy.exportAllProjectTitle, {
    count: state.loci.length,
  });

  const bodyMarkup = isOpen
    ? `<div class="manual-ref-body" data-manual-ref-body>
        ${quickAddSection}
        ${state.loci.length
          ? `<div class="manual-ref-loci-list" role="list">${state.loci.map((locus, idx) => renderLocusRow(locus, idx, { chrName, exporting: state.exporting, copy, escapeAttr, escapeHtml })).join("")}</div>`
          : `<p class="muted manual-ref-empty">${escapeHtml(copy.empty)}</p>`}
        ${readsSection}
        ${state.error ? `<p class="error-text manual-ref-feedback is-error" role="alert">${escapeHtml(state.error)}</p>` : ""}
        ${!state.error && state.feedback ? `<p class="manual-ref-feedback is-ok" role="status">${escapeHtml(state.feedback)}</p>` : ""}
        ${renderLastExportReceipt(state.lastExport, { copy, escapeAttr, escapeHtml })}
        <div class="manual-ref-foot">
          <span class="muted manual-ref-hint">${escapeHtml(copy.scopeBoundaryNote)}</span>
          <div class="manual-ref-foot-actions">
            ${state.loci.length ? `<button type="button" class="button ghost tiny manual-ref-clear-btn" data-manual-ref-clear-all ${state.exporting ? "disabled" : ""}>${escapeHtml(copy.clearDraft)}</button>` : ""}
            <button
              type="button"
              class="button tiny manual-ref-export-secondary"
              data-manual-ref-export="all"
              data-app-tooltip="${escapeAttr(exportAllTitle)}"
              ${!state.loci.length || state.exporting ? "disabled" : ""}
            >${escapeHtml(state.exporting ? copy.exporting : fmt(copy.exportAllProject, { count: state.loci.length }))}</button>
            <button
              type="button"
              class="button primary tiny manual-ref-export-primary"
              data-manual-ref-export="current-chr"
              data-app-tooltip="${escapeAttr(exportCurrentTitle)}"
              ${!currentChrLoci.length || state.exporting ? "disabled" : ""}
            >${escapeHtml(state.exporting ? copy.exporting : fmt(copy.exportCurrentChr, { count: currentChrLoci.length }))}</button>
          </div>
        </div>
      </div>`
    : "";

  return `<section class="degap-job-card manual-ref-card${isOpen ? "" : " is-collapsed"}${state.exporting ? " is-exporting" : ""}" data-manual-ref-card aria-busy="${state.exporting ? "true" : "false"}">
    <div class="degap-jobs-head manual-ref-head">
      <button
        type="button"
        class="degap-job-card-toggle manual-ref-toggle"
        data-manual-ref-toggle
        aria-expanded="${isOpen ? "true" : "false"}"
        aria-label="${escapeAttr(toggleLabel)}"
      >
        <span class="degap-job-card-indicator" aria-hidden="true">${isOpen ? "▾" : "▸"}</span>
        <strong>${escapeHtml(copy.title)}</strong>
      </button>
      <div class="manual-ref-scope-counts" aria-live="polite">
        <span class="manual-ref-count-pill${currentChrLoci.length ? " is-active" : ""}" data-manual-ref-count-current>${escapeHtml(currentPillText)}</span>
        <span class="manual-ref-count-pill${state.loci.length ? " is-total" : ""}" data-manual-ref-count-all>${escapeHtml(allPillText)}</span>
        ${state.exporting ? `<span class="manual-ref-exporting-pill"><span class="pipeline-spinner" aria-hidden="true"></span>${escapeHtml(copy.exporting)}</span>` : ""}
      </div>
    </div>
    ${bodyMarkup}
  </section>`;
}
