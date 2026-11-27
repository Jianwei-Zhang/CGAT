import {
  MANUAL_REFINEMENT_GAP_TOOLS,
  MANUAL_REFINEMENT_TOOL_LABELS,
  QUARTET_MINIMAP_OPTIONS,
  TGS_HIFI_MINIMAP_OPTIONS,
  TGS_ONT_MINIMAP_OPTIONS,
  buildManualRefinementServerCommand,
  countManualRefinementJobs,
  filterManualRefinementLociByScope,
  hasCustomManualRefinementToolParams,
  isToolParamBlockCustomized,
  normalizeManualRefinementState,
} from "./manual-refinement-state.js";

const COPY = {
  zh: {
    title: "精修任务",
    toggleOpen: "展开精修任务面板",
    toggleClose: "收起精修任务面板",
    empty: "右键上方 Final Path 中的 Gap 或首尾 Contig 添加精修任务。",
    gapBlockTitle: "Gap",
    telBlockTitle: "Tel",
    kindGap: "Gap",
    kindTelLeft: "左端粒",
    kindTelRight: "右端粒",
    telToolShort: "DEGAP TelSeeker",
    telToolFull: "固定使用 DEGAP TelSeeker (telseeker_ctg)",
    motifLabel: "Motif",
    motifPlaceholder: "项目默认",
    motifAria: "{chr} {kind} 端粒 motif",
    removeLocus: "移除任务：{target}",
    removeGapTool: "移除任务：{target} · {tool}",
    settingsBtn: "参数设置",
    settingsBtnTitle: "当前项目精修参数与 Server reads 设置",
    settingsTitle: "精修参数设置",
    settingsProjectNotice: "仅保存于当前项目，修改自动生效",
    settingsTabReads: "Server Reads",
    settingsResetTab: "恢复本页默认",
    settingsResetAll: "重置全部",
    settingsDone: "完成",
    settingsClose: "关闭设置",
    unlimited: "不限",
    degapGapGroup: "Gap 延伸",
    degapTelGroup: "TelSeeker",
    degapMaxRounds: "最大延伸轮数",
    degapMaxRoundsTip: "DEGAP MaximumExtensionRound：最大迭代延伸轮数",
    degapMaxBp: "最大延伸长度 (bp)",
    degapMaxBpTip: "DEGAP MaximumExtensionLength：单侧最大延伸碱基长度",
    degapKmerFilter: "k-mer 过滤",
    degapKmerFilterTip: "DEGAP kmer_filter：启用后按 k-mer 过滤候选延伸 reads",
    degapKmerSize: "k-mer 长度",
    degapKmerSizeTip: "DEGAP kmer_size：过滤用 k-mer 长度",
    degapKmerNum: "k-mer 数量",
    degapKmerNumTip: "DEGAP kmer_num：过滤所需最小 k-mer 命中数",
    degapEdge: "边界长度",
    degapEdgeTip: "DEGAP edge：用于末端比对的边界序列长度 (bp)",
    degapFilterHifi: "HiFi 深度过滤",
    degapFilterHifiTip: "DEGAP filterDepthHifi（0~1），留空不启用",
    degapFilterOnt: "ONT 深度过滤",
    degapFilterOntTip: "DEGAP filterDepthOnt（0~1），留空不启用",
    degapOptionalPlaceholder: "留空关闭",
    degapTelN: "端粒窗口",
    degapTelNTip: "DEGAP tel-n：端粒扫描窗口长度 (bp)",
    degapTelR: "端粒比例",
    degapTelRTip: "DEGAP tel-r：窗口内端粒重复比例阈值 (0~1)",
    degapTelMm: "允许错配",
    degapTelMmTip: "DEGAP tel-mm：端粒 motif 允许错配数",
    lrIterations: "迭代次数",
    lrIterationsTip: "LR_Gapcloser -r：迭代补洞轮数",
    lrTagPartitions: "标签分区数",
    lrTagPartitionsTip: "LR_Gapcloser -n：reads 分区并行数",
    tgsHifiGroup: "HiFi",
    tgsOntGroup: "ONT",
    tgsCorrection: "纠错模式",
    tgsCorrectionTip: "关闭纠错 (--ne) 或启用 Racon 纠错 (--racon)",
    tgsCorrectionNone: "关闭",
    tgsCorrectionRacon: "Racon",
    tgsRaconRounds: "Racon 轮数",
    tgsRaconRoundsTip: "TGS-GapCloser --r_round：Racon 纠错迭代轮数",
    tgsMinimap: "Minimap2 预设",
    tgsMinimapTip: "TGS-GapCloser --minmap_arg：比对预设参数",
    quartetMinimap: "Minimap2 预设",
    quartetMinimapTip: "quarTeT GapFiller --minimapoption：比对预设参数",
    readsInherit: "沿用项目默认 reads",
    readsInheritTip: "自动复用项目已校验 reads（不展示路径；为空时可在 Server 传 --hifi / --ont）",
    readsOverride: "自定义 Server 路径",
    readsOverrideTip: "填写服务器绝对路径，多文件用分号或换行分隔",
    hifiLabel: "HiFi",
    ontLabel: "ONT",
    clearReads: "清空",
    exportBtn: "导出 ({count})",
    exportBtnTitle: "导出精修任务 refine-jobs（当前染色体 {chr} · {count} 项）",
    exporting: "正在导出...",
    clearDraft: "清空",
    clearDraftTitle: "清空当前已登记的精修任务",
    exportedTitle: "已导出 · 等待 Server 运行",
    exportedScopeCurrent: "{chr}",
    exportedScopeAll: "全项目",
    exportedMeta: "批次 {batch} · {loci} 位点 / {tasks} 任务",
    serverCmdLabel: "命令",
    copyCmd: "复制",
    dismissReceipt: "关闭回执",
  },
  en: {
    title: "Refinement Tasks",
    toggleOpen: "Expand refinement tasks panel",
    toggleClose: "Collapse refinement tasks panel",
    empty: "Right-click a Gap or terminal Contig in the Final Path above to queue refinement jobs.",
    gapBlockTitle: "Gap",
    telBlockTitle: "Tel",
    kindGap: "Gap",
    kindTelLeft: "Left Tel",
    kindTelRight: "Right Tel",
    telToolShort: "DEGAP TelSeeker",
    telToolFull: "Fixed to DEGAP TelSeeker (telseeker_ctg)",
    motifLabel: "Motif",
    motifPlaceholder: "Default",
    motifAria: "{chr} {kind} telomere motif",
    removeLocus: "Remove job: {target}",
    removeGapTool: "Remove job: {target} · {tool}",
    settingsBtn: "Settings",
    settingsBtnTitle: "Project-level refinement parameters and Server reads",
    settingsTitle: "Refinement Settings",
    settingsProjectNotice: "Saved per project · changes apply automatically",
    settingsTabReads: "Server Reads",
    settingsResetTab: "Reset Tab",
    settingsResetAll: "Reset All",
    settingsDone: "Done",
    settingsClose: "Close settings",
    unlimited: "Unlimited",
    degapGapGroup: "Gap Extension",
    degapTelGroup: "TelSeeker",
    degapMaxRounds: "Max rounds",
    degapMaxRoundsTip: "DEGAP MaximumExtensionRound: maximum extension iterations",
    degapMaxBp: "Max length (bp)",
    degapMaxBpTip: "DEGAP MaximumExtensionLength: maximum extension length in bp",
    degapKmerFilter: "k-mer filter",
    degapKmerFilterTip: "DEGAP kmer_filter: filter candidate extension reads by k-mers",
    degapKmerSize: "k-mer size",
    degapKmerSizeTip: "DEGAP kmer_size: k-mer length for filtering",
    degapKmerNum: "k-mer count",
    degapKmerNumTip: "DEGAP kmer_num: minimum k-mer hits for filtering",
    degapEdge: "Edge length",
    degapEdgeTip: "DEGAP edge: terminal flank length (bp) used for alignment",
    degapFilterHifi: "HiFi depth filter",
    degapFilterHifiTip: "DEGAP filterDepthHifi (0–1), leave empty to disable",
    degapFilterOnt: "ONT depth filter",
    degapFilterOntTip: "DEGAP filterDepthOnt (0–1), leave empty to disable",
    degapOptionalPlaceholder: "Off",
    degapTelN: "Telomere window",
    degapTelNTip: "DEGAP tel-n: telomere scan window length (bp)",
    degapTelR: "Telomere ratio",
    degapTelRTip: "DEGAP tel-r: minimum telomere repeat ratio (0–1)",
    degapTelMm: "Mismatches",
    degapTelMmTip: "DEGAP tel-mm: allowed telomere motif mismatches",
    lrIterations: "Iterations",
    lrIterationsTip: "LR_Gapcloser -r: number of gap-closing iterations",
    lrTagPartitions: "Tag partitions",
    lrTagPartitionsTip: "LR_Gapcloser -n: read tag partitions",
    tgsHifiGroup: "HiFi",
    tgsOntGroup: "ONT",
    tgsCorrection: "Correction",
    tgsCorrectionTip: "Disable correction (--ne) or enable Racon (--racon)",
    tgsCorrectionNone: "Off",
    tgsCorrectionRacon: "Racon",
    tgsRaconRounds: "Racon rounds",
    tgsRaconRoundsTip: "TGS-GapCloser --r_round: Racon polishing iterations",
    tgsMinimap: "Minimap2 preset",
    tgsMinimapTip: "TGS-GapCloser --minmap_arg: alignment preset",
    quartetMinimap: "Minimap2 preset",
    quartetMinimapTip: "quarTeT GapFiller --minimapoption: alignment preset",
    readsInherit: "Inherit project default reads",
    readsInheritTip: "Reuse verified project reads (paths stay hidden; empty reads can use Server --hifi / --ont)",
    readsOverride: "Custom Server paths",
    readsOverrideTip: "Server absolute paths, separated by semicolon or newline",
    hifiLabel: "HiFi",
    ontLabel: "ONT",
    clearReads: "Clear",
    exportBtn: "Export ({count})",
    exportBtnTitle: "Export refine-jobs (Current chr {chr} · {count} jobs)",
    exporting: "Exporting...",
    clearDraft: "Clear",
    clearDraftTitle: "Clear queued refinement tasks",
    exportedTitle: "Exported · awaiting Server run",
    exportedScopeCurrent: "{chr}",
    exportedScopeAll: "Project",
    exportedMeta: "Batch {batch} · {loci} loci / {tasks} jobs",
    serverCmdLabel: "Cmd",
    copyCmd: "Copy",
    dismissReceipt: "Dismiss receipt",
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

function renderGapJobRow(locus, tool, { chrName, showChrPill, exporting, copy, escapeAttr, escapeHtml }) {
  const key = locus.locusKey;
  const isCurrentChr = Boolean(chrName && locus.chr === chrName);
  const displayTarget = locus.label || locus.segmentId;
  const label = MANUAL_REFINEMENT_TOOL_LABELS[tool] || tool;
  const removeLabel = fmt(copy.removeGapTool, { target: `${locus.chr} ${displayTarget}`, tool: label });
  const srTargetSummary = locus.label && locus.label !== locus.segmentId
    ? `${locus.chr} Gap ${locus.label} (${locus.segmentId})`
    : `${locus.chr} Gap ${displayTarget}`;

  return `<div
    class="manual-ref-gap-row${isCurrentChr ? " is-current-chr" : ""}"
    data-manual-ref-gap-row="${escapeAttr(key)}"
    data-manual-ref-gap-tool-row="${escapeAttr(key)}"
    data-manual-ref-tool="${escapeAttr(tool)}"
    role="listitem"
  >
    <div class="manual-ref-locus-ident">
      ${showChrPill ? `<span class="manual-ref-chr-pill${isCurrentChr ? " is-current-chr" : ""}">${escapeHtml(locus.chr)}</span>` : ""}
      <span
        class="manual-ref-locus-target"
        data-app-tooltip="${escapeAttr(displayTarget)}"
        data-app-tooltip-overflow
      >${escapeHtml(displayTarget)}</span>
      <span class="manual-ref-sr-only">${escapeHtml(srTargetSummary)}</span>
    </div>
    <div class="manual-ref-gap-job-actions">
      <span class="manual-ref-tool-badge is-tool-${escapeAttr(tool)}">${escapeHtml(label)}</span>
      <button
        type="button"
        class="manual-ref-remove-btn"
        data-manual-ref-remove-tool
        data-manual-ref-locus-key="${escapeAttr(key)}"
        data-manual-ref-tool="${escapeAttr(tool)}"
        aria-label="${escapeAttr(removeLabel)}"
        data-app-tooltip="${escapeAttr(removeLabel)}"
        ${exporting ? "disabled" : ""}
      >×</button>
    </div>
  </div>`;
}

function renderTelRow(locus, { chrName, showChrPill, exporting, copy, escapeAttr, escapeHtml }) {
  const key = locus.locusKey;
  const isCurrentChr = Boolean(chrName && locus.chr === chrName);
  const kindText = kindLabel(locus.kind, copy);
  const displayTarget = locus.label || locus.segmentId;
  const removeLabel = fmt(copy.removeLocus, { target: `${locus.chr} ${kindText} ${displayTarget}` });

  return `<div
    class="manual-ref-tel-row${isCurrentChr ? " is-current-chr" : ""}"
    data-manual-ref-tel-row="${escapeAttr(key)}"
    role="listitem"
  >
    <div class="manual-ref-locus-ident">
      ${showChrPill ? `<span class="manual-ref-chr-pill${isCurrentChr ? " is-current-chr" : ""}">${escapeHtml(locus.chr)}</span>` : ""}
      <span class="manual-ref-kind-badge is-${escapeAttr(locus.kind)}">${escapeHtml(kindText)}</span>
      <span
        class="manual-ref-locus-target"
        data-app-tooltip="${escapeAttr(displayTarget)}"
        data-app-tooltip-overflow
      >${escapeHtml(displayTarget)}</span>
    </div>
    <div class="manual-ref-tel-controls">
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

function renderLastExportReceipt(lastExport, { dismissed, copy, escapeAttr, escapeHtml }) {
  if (!lastExport || dismissed) {
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
      <div class="manual-ref-receipt-head-right">
        <span class="manual-ref-status-pill is-pending">${escapeHtml(scopeText)} · ${escapeHtml(fmt(copy.exportedMeta, {
          batch: shortBatch,
          loci: lastExport.lociCount,
          tasks: lastExport.tasksCount,
        }))}</span>
        <button
          type="button"
          class="manual-ref-remove-btn"
          data-manual-ref-dismiss-receipt
          aria-label="${escapeAttr(copy.dismissReceipt)}"
        >×</button>
      </div>
    </div>
    <div class="manual-ref-command-row">
      <span class="manual-ref-command-label">${escapeHtml(copy.serverCmdLabel)}</span>
      <code class="manual-ref-command-code">${escapeHtml(command)}</code>
      <button type="button" class="button ghost tiny" data-manual-ref-copy-cmd="${escapeAttr(command)}">${escapeHtml(copy.copyCmd)}</button>
    </div>
  </div>`;
}

function renderSelectOptions(options, selectedValue, { escapeAttr, escapeHtml }) {
  return options.map((opt) => {
    const value = typeof opt === "string" ? opt : opt.value;
    const label = typeof opt === "string" ? opt : opt.label;
    return `<option value="${escapeAttr(value)}"${value === selectedValue ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function renderSettingsTabBody(state, { copy, escapeAttr, escapeHtml }) {
  const tab = state.settingsTab;
  const params = state.toolParams;
  const disabledAttr = state.exporting ? " disabled" : "";

  if (tab === "degap") {
    const d = params.degap;
    const roundsUnlimited = d.max_extension_rounds === "unlimited";
    const bpUnlimited = d.max_extension_bp === "unlimited";
    return `<div class="manual-ref-settings-pane" data-manual-ref-settings-pane="degap">
      <fieldset class="manual-ref-settings-group">
        <legend>${escapeHtml(copy.degapGapGroup)}</legend>
        <div class="manual-ref-settings-grid">
          <div class="manual-ref-param-field">
            <label for="mr-degap-rounds" data-app-tooltip="${escapeAttr(copy.degapMaxRoundsTip)}">${escapeHtml(copy.degapMaxRounds)}</label>
            <div class="manual-ref-limit-row">
              <input id="mr-degap-rounds" type="number" min="1" max="1000" step="1"
                data-manual-ref-param-tool="degap" data-manual-ref-param-field="max_extension_rounds"
                value="${escapeAttr(roundsUnlimited ? "10" : String(d.max_extension_rounds))}"
                ${roundsUnlimited || state.exporting ? "disabled" : ""} />
              <label class="manual-ref-inline-check">
                <input type="checkbox" data-manual-ref-param-tool="degap" data-manual-ref-param-unlimited="max_extension_rounds"
                  ${roundsUnlimited ? "checked" : ""}${disabledAttr} />
                <span>${escapeHtml(copy.unlimited)}</span>
              </label>
            </div>
          </div>
          <div class="manual-ref-param-field">
            <label for="mr-degap-bp" data-app-tooltip="${escapeAttr(copy.degapMaxBpTip)}">${escapeHtml(copy.degapMaxBp)}</label>
            <div class="manual-ref-limit-row">
              <input id="mr-degap-bp" type="number" min="1000" max="100000000" step="10000"
                data-manual-ref-param-tool="degap" data-manual-ref-param-field="max_extension_bp"
                value="${escapeAttr(bpUnlimited ? "500000" : String(d.max_extension_bp))}"
                ${bpUnlimited || state.exporting ? "disabled" : ""} />
              <label class="manual-ref-inline-check">
                <input type="checkbox" data-manual-ref-param-tool="degap" data-manual-ref-param-unlimited="max_extension_bp"
                  ${bpUnlimited ? "checked" : ""}${disabledAttr} />
                <span>${escapeHtml(copy.unlimited)}</span>
              </label>
            </div>
          </div>
          <label class="manual-ref-check-row is-wide" data-app-tooltip="${escapeAttr(copy.degapKmerFilterTip)}">
            <input type="checkbox" data-manual-ref-param-tool="degap" data-manual-ref-param-field="kmer_filter"
              ${d.kmer_filter ? "checked" : ""}${disabledAttr} />
            <span>${escapeHtml(copy.degapKmerFilter)}</span>
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapKmerSizeTip)}">${escapeHtml(copy.degapKmerSize)}</span>
            <input type="number" min="11" max="127" step="1"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="kmer_size"
              value="${escapeAttr(String(d.kmer_size))}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapKmerNumTip)}">${escapeHtml(copy.degapKmerNum)}</span>
            <input type="number" min="1" max="1000" step="1"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="kmer_num"
              value="${escapeAttr(String(d.kmer_num))}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapEdgeTip)}">${escapeHtml(copy.degapEdge)}</span>
            <input type="number" min="50" max="50000" step="50"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="edge"
              value="${escapeAttr(String(d.edge))}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapFilterHifiTip)}">${escapeHtml(copy.degapFilterHifi)}</span>
            <input type="number" min="0.01" max="0.99" step="0.05"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="filter_depth_hifi"
              value="${escapeAttr(d.filter_depth_hifi === null ? "" : String(d.filter_depth_hifi))}"
              placeholder="${escapeAttr(copy.degapOptionalPlaceholder)}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapFilterOntTip)}">${escapeHtml(copy.degapFilterOnt)}</span>
            <input type="number" min="0.01" max="0.99" step="0.05"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="filter_depth_ont"
              value="${escapeAttr(d.filter_depth_ont === null ? "" : String(d.filter_depth_ont))}"
              placeholder="${escapeAttr(copy.degapOptionalPlaceholder)}"${disabledAttr} />
          </label>
        </div>
      </fieldset>
      <fieldset class="manual-ref-settings-group">
        <legend>${escapeHtml(copy.degapTelGroup)}</legend>
        <div class="manual-ref-settings-grid is-three-col">
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapTelNTip)}">${escapeHtml(copy.degapTelN)}</span>
            <input type="number" min="10" max="10000" step="10"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="tel_n"
              value="${escapeAttr(String(d.tel_n))}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapTelRTip)}">${escapeHtml(copy.degapTelR)}</span>
            <input type="number" min="0.01" max="1" step="0.05"
              data-manual-ref-param-tool="degap" data-manual-ref-param-field="tel_r"
              value="${escapeAttr(String(d.tel_r))}"${disabledAttr} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.degapTelMmTip)}">${escapeHtml(copy.degapTelMm)}</span>
            <select data-manual-ref-param-tool="degap" data-manual-ref-param-field="tel_mm"${disabledAttr}>
              ${renderSelectOptions(["0", "1"], String(d.tel_mm), { escapeAttr, escapeHtml })}
            </select>
          </label>
        </div>
      </fieldset>
    </div>`;
  }

  if (tab === "lrgapcloser") {
    const lr = params.lrgapcloser;
    return `<div class="manual-ref-settings-pane" data-manual-ref-settings-pane="lrgapcloser">
      <div class="manual-ref-settings-grid">
        <label class="manual-ref-param-field">
          <span data-app-tooltip="${escapeAttr(copy.lrIterationsTip)}">${escapeHtml(copy.lrIterations)}</span>
          <input type="number" min="1" max="20" step="1"
            data-manual-ref-param-tool="lrgapcloser" data-manual-ref-param-field="iterations"
            value="${escapeAttr(String(lr.iterations))}"${disabledAttr} />
        </label>
        <label class="manual-ref-param-field">
          <span data-app-tooltip="${escapeAttr(copy.lrTagPartitionsTip)}">${escapeHtml(copy.lrTagPartitions)}</span>
          <input type="number" min="1" max="16" step="1"
            data-manual-ref-param-tool="lrgapcloser" data-manual-ref-param-field="tag_partitions"
            value="${escapeAttr(String(lr.tag_partitions))}"${disabledAttr} />
        </label>
      </div>
    </div>`;
  }

  if (tab === "tgsgapcloser") {
    const tgs = params.tgsgapcloser;
    const correctionOptions = [
      { value: "none", label: copy.tgsCorrectionNone },
      { value: "native_racon", label: copy.tgsCorrectionRacon },
    ];
    return `<div class="manual-ref-settings-pane" data-manual-ref-settings-pane="tgsgapcloser">
      <fieldset class="manual-ref-settings-group">
        <legend>${escapeHtml(copy.tgsHifiGroup)}</legend>
        <div class="manual-ref-settings-grid is-three-col">
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsCorrectionTip)}">${escapeHtml(copy.tgsCorrection)}</span>
            <select data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="hifi_correction"${disabledAttr}>
              ${renderSelectOptions(correctionOptions, tgs.hifi_correction, { escapeAttr, escapeHtml })}
            </select>
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsRaconRoundsTip)}">${escapeHtml(copy.tgsRaconRounds)}</span>
            <input type="number" min="1" max="5" step="1"
              data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="hifi_racon_rounds"
              value="${escapeAttr(String(tgs.hifi_racon_rounds))}"
              ${tgs.hifi_correction !== "native_racon" || state.exporting ? "disabled" : ""} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsMinimapTip)}">${escapeHtml(copy.tgsMinimap)}</span>
            <select data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="hifi_minimap"${disabledAttr}>
              ${renderSelectOptions(TGS_HIFI_MINIMAP_OPTIONS, tgs.hifi_minimap, { escapeAttr, escapeHtml })}
            </select>
          </label>
        </div>
      </fieldset>
      <fieldset class="manual-ref-settings-group">
        <legend>${escapeHtml(copy.tgsOntGroup)}</legend>
        <div class="manual-ref-settings-grid is-three-col">
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsCorrectionTip)}">${escapeHtml(copy.tgsCorrection)}</span>
            <select data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="ont_correction"${disabledAttr}>
              ${renderSelectOptions(correctionOptions, tgs.ont_correction, { escapeAttr, escapeHtml })}
            </select>
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsRaconRoundsTip)}">${escapeHtml(copy.tgsRaconRounds)}</span>
            <input type="number" min="1" max="5" step="1"
              data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="ont_racon_rounds"
              value="${escapeAttr(String(tgs.ont_racon_rounds))}"
              ${tgs.ont_correction !== "native_racon" || state.exporting ? "disabled" : ""} />
          </label>
          <label class="manual-ref-param-field">
            <span data-app-tooltip="${escapeAttr(copy.tgsMinimapTip)}">${escapeHtml(copy.tgsMinimap)}</span>
            <select data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="ont_minimap"${disabledAttr}>
              ${renderSelectOptions(TGS_ONT_MINIMAP_OPTIONS, tgs.ont_minimap, { escapeAttr, escapeHtml })}
            </select>
          </label>
        </div>
      </fieldset>
    </div>`;
  }

  if (tab === "quartet") {
    const q = params.quartet;
    return `<div class="manual-ref-settings-pane" data-manual-ref-settings-pane="quartet">
      <div class="manual-ref-settings-grid">
        <label class="manual-ref-param-field">
          <span data-app-tooltip="${escapeAttr(copy.quartetMinimapTip)}">${escapeHtml(copy.quartetMinimap)}</span>
          <select data-manual-ref-param-tool="quartet" data-manual-ref-param-field="minimap"${disabledAttr}>
            ${renderSelectOptions(QUARTET_MINIMAP_OPTIONS, q.minimap, { escapeAttr, escapeHtml })}
          </select>
        </label>
      </div>
    </div>`;
  }

  return `<div class="manual-ref-settings-pane" data-manual-ref-settings-pane="reads">
    <div class="manual-ref-reads-modes">
      <label class="manual-ref-radio" data-app-tooltip="${escapeAttr(copy.readsInheritTip)}">
        <input type="radio" name="manual-ref-reads-mode" data-manual-ref-reads-mode value="inherit" ${state.readsMode !== "override" ? "checked" : ""}${disabledAttr} />
        <span>${escapeHtml(copy.readsInherit)}</span>
      </label>
      <label class="manual-ref-radio" data-app-tooltip="${escapeAttr(copy.readsOverrideTip)}">
        <input type="radio" name="manual-ref-reads-mode" data-manual-ref-reads-mode value="override" ${state.readsMode === "override" ? "checked" : ""}${disabledAttr} />
        <span>${escapeHtml(copy.readsOverride)}</span>
      </label>
    </div>
    ${state.readsMode === "override"
      ? `<div class="manual-ref-reads-inputs">
          <div class="manual-ref-read-field">
            <label for="manual-ref-hifi-input">${escapeHtml(copy.hifiLabel)}</label>
            <div class="manual-ref-read-input-row">
              <input id="manual-ref-hifi-input" type="text" data-manual-ref-reads-field="hifi" value="${escapeAttr(state.hifiReadsInput)}" placeholder="/server/reads/hifi.fastq.gz" autocomplete="off" spellcheck="false"${disabledAttr} />
              <button type="button" class="button ghost tiny" data-manual-ref-clear-reads="hifi"${disabledAttr}>${escapeHtml(copy.clearReads)}</button>
            </div>
          </div>
          <div class="manual-ref-read-field">
            <label for="manual-ref-ont-input">${escapeHtml(copy.ontLabel)}</label>
            <div class="manual-ref-read-input-row">
              <input id="manual-ref-ont-input" type="text" data-manual-ref-reads-field="ont" value="${escapeAttr(state.ontReadsInput)}" placeholder="/server/reads/ont.fastq.gz" autocomplete="off" spellcheck="false"${disabledAttr} />
              <button type="button" class="button ghost tiny" data-manual-ref-clear-reads="ont"${disabledAttr}>${escapeHtml(copy.clearReads)}</button>
            </div>
          </div>
        </div>`
      : ""}
  </div>`;
}

function renderSettingsModal(state, { copy, escapeAttr, escapeHtml }) {
  if (!state.settingsOpen) {
    return "";
  }
  const tabs = [
    ...MANUAL_REFINEMENT_GAP_TOOLS.map((tool) => ({
      id: tool,
      label: MANUAL_REFINEMENT_TOOL_LABELS[tool],
      customized: isToolParamBlockCustomized(tool, state.toolParams),
    })),
    {
      id: "reads",
      label: copy.settingsTabReads,
      customized: state.readsMode === "override",
    },
  ];
  return `<div class="modal-overlay manual-ref-settings-overlay" data-manual-ref-settings-modal>
    <article
      class="card modal-dialog manual-ref-settings-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="${escapeAttr(copy.settingsTitle)}"
    >
      <header class="manual-ref-settings-head">
        <h4>${escapeHtml(copy.settingsTitle)}</h4>
        <button
          type="button"
          class="dialog-close-button"
          data-manual-ref-settings-close
          aria-label="${escapeAttr(copy.settingsClose)}"
          data-app-tooltip="${escapeAttr(copy.settingsClose)}"
        >×</button>
      </header>
      <p class="manual-ref-settings-scope-notice" data-manual-ref-settings-scope-notice role="note">${escapeHtml(copy.settingsProjectNotice)}</p>
      <div class="manual-ref-settings-tabs" role="tablist">
        ${tabs.map((item) => `<button
          type="button"
          role="tab"
          class="manual-ref-settings-tab${state.settingsTab === item.id ? " is-active" : ""}${item.customized ? " is-customized" : ""}"
          data-manual-ref-settings-tab="${escapeAttr(item.id)}"
          aria-selected="${state.settingsTab === item.id ? "true" : "false"}"
        >${escapeHtml(item.label)}${item.customized ? `<span class="manual-ref-custom-dot" aria-hidden="true"></span>` : ""}</button>`).join("")}
      </div>
      <div class="manual-ref-settings-body">
        ${renderSettingsTabBody(state, { copy, escapeAttr, escapeHtml })}
      </div>
      <footer class="manual-ref-settings-foot">
        <div class="manual-ref-settings-foot-left">
          <button type="button" class="button ghost" data-manual-ref-settings-reset-tab ${state.exporting ? "disabled" : ""}>${escapeHtml(copy.settingsResetTab)}</button>
          <button type="button" class="button ghost" data-manual-ref-settings-reset-all ${state.exporting ? "disabled" : ""}>${escapeHtml(copy.settingsResetAll)}</button>
        </div>
        <button type="button" class="button primary" data-manual-ref-settings-close>${escapeHtml(copy.settingsDone)}</button>
      </footer>
    </article>
  </div>`;
}

export function renderManualRefinementToast({ manualRefinement }, { escapeHtml }) {
  const state = normalizeManualRefinementState(manualRefinement);
  const errorText = String(state.error || "").trim();
  const feedbackText = String(state.feedback || "").trim();
  if (!errorText && !feedbackText) {
    return "";
  }
  if (errorText) {
    return `<div class="final-path-toast-wrap" data-final-path-toast aria-live="polite"><p class="final-path-toast is-error" role="alert">${escapeHtml(errorText)}</p></div>`;
  }
  return `<div class="final-path-toast-wrap" data-final-path-toast aria-live="polite"><p class="final-path-toast is-ok" role="status">${escapeHtml(feedbackText)}</p></div>`;
}

export function renderManualRefinementSettingsModal(
  { manualRefinement, locale = "zh" },
  { escapeAttr, escapeHtml },
) {
  const copy = COPY[locale === "en" ? "en" : "zh"];
  const state = normalizeManualRefinementState(manualRefinement);
  return renderSettingsModal(state, { copy, escapeAttr, escapeHtml });
}

export function renderManualRefinementCard(
  { chrName, manualRefinement, locale = "zh", includeSettingsModal = true },
  { escapeAttr, escapeHtml },
) {
  const copy = COPY[locale === "en" ? "en" : "zh"];
  const state = normalizeManualRefinementState(manualRefinement);
  const normalizedChrName = String(chrName || "").trim();
  const currentChrLoci = filterManualRefinementLociByScope(state.loci, {
    scope: "current-chr",
    chrName: normalizedChrName,
  });
  const currentChrJobsCount = countManualRefinementJobs(currentChrLoci);
  const allJobsCount = countManualRefinementJobs(state.loci);
  const visibleLoci = normalizedChrName ? currentChrLoci : state.loci;
  const visibleJobsCount = normalizedChrName ? currentChrJobsCount : allJobsCount;
  const receiptMatchesChr = Boolean(
    state.lastExport
    && !state.receiptDismissed
    && (!normalizedChrName
      || !state.lastExport.chrName
      || state.lastExport.scope === "all"
      || state.lastExport.chrName === normalizedChrName),
  );
  if (!visibleLoci.length && !receiptMatchesChr) {
    return includeSettingsModal && state.settingsOpen
      ? renderSettingsModal(state, { copy, escapeAttr, escapeHtml })
      : "";
  }
  const gapLoci = visibleLoci.filter((locus) => locus.kind === "gap");
  const telLoci = visibleLoci.filter((locus) => locus.kind !== "gap");
  const gapJobsCount = countManualRefinementJobs(gapLoci);
  const showChrPill = !normalizedChrName;

  const isOpen = state.panelOpen;
  const toggleLabel = isOpen ? copy.toggleClose : copy.toggleOpen;
  const hasCustomSettings = hasCustomManualRefinementToolParams(state.toolParams) || state.readsMode === "override";
  const exportBtnTitle = fmt(copy.exportBtnTitle, {
    chr: normalizedChrName || "-",
    count: currentChrJobsCount,
  });

  const gapSectionMarkup = gapLoci.length
    ? `<div class="manual-ref-block is-gap" data-manual-ref-gap-section>
        <div class="manual-ref-block-head">
          <span class="manual-ref-block-title">${escapeHtml(copy.gapBlockTitle)}</span>
          <span class="manual-ref-block-count">${escapeHtml(String(gapJobsCount))}</span>
        </div>
        <div class="manual-ref-block-list" role="list">
          ${gapLoci.flatMap((locus) => locus.tools.map((tool) => renderGapJobRow(locus, tool, { chrName: normalizedChrName, showChrPill, exporting: state.exporting, copy, escapeAttr, escapeHtml }))).join("")}
        </div>
      </div>`
    : "";

  const telSectionMarkup = telLoci.length
    ? `<div class="manual-ref-block is-tel" data-manual-ref-tel-section>
        <div class="manual-ref-block-head">
          <span class="manual-ref-block-title">${escapeHtml(copy.telBlockTitle)}</span>
          <span class="manual-ref-block-count">${escapeHtml(String(telLoci.length))}</span>
        </div>
        <div class="manual-ref-block-list" role="list">
          ${telLoci.map((locus) => renderTelRow(locus, { chrName: normalizedChrName, showChrPill, exporting: state.exporting, copy, escapeAttr, escapeHtml })).join("")}
        </div>
      </div>`
    : "";

  const blocksMarkup = (gapLoci.length || telLoci.length)
    ? `<div class="manual-ref-blocks">${gapSectionMarkup}${telSectionMarkup}</div>`
    : `<p class="muted manual-ref-empty">${escapeHtml(copy.empty)}</p>`;

  const bodyMarkup = isOpen
    ? `<div class="manual-ref-body" data-manual-ref-body>
        ${blocksMarkup}
        ${receiptMatchesChr ? renderLastExportReceipt(state.lastExport, { dismissed: state.receiptDismissed, copy, escapeAttr, escapeHtml }) : ""}
      </div>`
    : "";

  return `<section class="degap-job-card manual-ref-card${isOpen ? "" : " is-collapsed"}${state.exporting ? " is-exporting" : ""}" data-manual-ref-card data-manual-ref-card-chr="${escapeAttr(normalizedChrName)}" aria-busy="${state.exporting ? "true" : "false"}">
    <div class="degap-jobs-head manual-ref-head">
      <div class="manual-ref-head-left">
        <button
          type="button"
          class="degap-job-card-toggle manual-ref-toggle"
          data-manual-ref-toggle
          aria-expanded="${isOpen ? "true" : "false"}"
          aria-label="${escapeAttr(toggleLabel)}"
        >
          <strong>${escapeHtml(copy.title)}</strong>
          <span class="manual-ref-title-count" data-manual-ref-count>· ${escapeHtml(String(visibleJobsCount))}</span>
        </button>
      </div>
      <div class="manual-ref-head-actions">
        ${state.exporting ? `<span class="manual-ref-exporting-pill"><span class="pipeline-spinner" aria-hidden="true"></span>${escapeHtml(copy.exporting)}</span>` : ""}
        <button
          type="button"
          class="button ghost tiny manual-ref-settings-btn${hasCustomSettings ? " is-customized" : ""}"
          data-manual-ref-settings-open
          data-app-tooltip="${escapeAttr(copy.settingsBtnTitle)}"
          aria-label="${escapeAttr(copy.settingsBtnTitle)}"
        ><span aria-hidden="true">⚙</span><span>${escapeHtml(copy.settingsBtn)}</span>${hasCustomSettings ? `<span class="manual-ref-custom-dot" aria-hidden="true"></span>` : ""}</button>
        ${visibleLoci.length
          ? `<button
              type="button"
              class="button ghost tiny manual-ref-clear-btn"
              data-manual-ref-clear-all
              data-manual-ref-chr="${escapeAttr(normalizedChrName)}"
              data-app-tooltip="${escapeAttr(copy.clearDraftTitle)}"
              ${state.exporting ? "disabled" : ""}
            >${escapeHtml(copy.clearDraft)}</button>`
          : ""}
        <button
          type="button"
          class="button primary tiny manual-ref-export-primary"
          data-manual-ref-export="current-chr"
          data-manual-ref-chr="${escapeAttr(normalizedChrName)}"
          data-app-tooltip="${escapeAttr(exportBtnTitle)}"
          ${!currentChrLoci.length || state.exporting ? "disabled" : ""}
        >${escapeHtml(state.exporting ? copy.exporting : fmt(copy.exportBtn, { count: currentChrJobsCount }))}</button>
      </div>
    </div>
    ${bodyMarkup}
    ${includeSettingsModal ? renderSettingsModal(state, { copy, escapeAttr, escapeHtml }) : ""}
  </section>`;
}
