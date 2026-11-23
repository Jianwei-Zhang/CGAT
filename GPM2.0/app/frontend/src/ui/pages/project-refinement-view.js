import { projectIcon } from "./project-icons.js";
import { pickZipFilePath } from "../../services/backend-api.js";
import {
  getGrtProjectView,
  previewProjectRefinementVersion,
  getProjectAssemblyViewState,
  importManualRefinementResults,
  listManualRefinementResults,
  switchManualRefinementLocus,
  undoManualRefinementLocus,
} from "../../services/workflow-api.js";
import { clearAssemblySessionCache } from "../shell/assembly-session-cache.js";
import {
  MANUAL_REFINEMENT_TOOL_LABELS,
  buildManualRefinementServerCommand,
  normalizeManualRefinementState,
} from "./assembly/manual-refinement-state.js";
import { describeFinalPathRefinement } from "./assembly/final-path-presentation.js";
import {
  isFinalPathCtgSegment,
  normalizeFinalPathByChr,
  resolveFinalPathSegmentDisplayName,
} from "./assembly/final-path-state.js";
import { normalizeGrtProjectView } from "./assembly/grt-state.js";
import { flushAssemblyProjectState } from "./assembly-page.js";
import { reloadProjectOverviewData } from "./project-export-page.js";

const PROJECT_REFINEMENT_BOUND = Symbol("projectRefinementBound");

const COPY = {
  zh: {
    sectionTitle: "精修",
    preview: "查看工具结果", previewHint: "这里展示该工具的原始结果，不会更改项目组装。", loadingVersion: "正在读取工具结果…",
    selectionReasons: { adopted: "项目已采用", joint_or_unmapped: "不能独立归到一个 Gap", path_changed_or_protected: "路径已变更或受保护", already_filled: "已保留先前采用结果", lower_priority: "另一个闭合工具优先", overlapping_edits: "改动区间重叠" },
    recordHeaders: ["染色体", "长度 (bp)", "片段数", "Gap 片段数"],
    importAction: "导入精修补丁",
    autoPatchImported: "已导入自动精修结果，本次按闭合与工具优先级采用 {n} 个 Gap。",
    projectAdoptions: "项目采用过 {n} 个 Gap",
    autoPatchHydrated: "已补齐已导入工具的来源序列，现有组装未变。",
    autoPatchDuplicate: "这些自动精修结果已在项目中，未重复导入。",
    tableColumns: ["来源", "工具 / 批次", "已闭合", "部分填补", "未填补", "拒绝", "结果"],
    tableHint: "自动行按原始缺口计数；手动行按所选 Gap 的候选结果计数，不代表已采用。— 表示无此项或未记录。",
    editCount: "接纳 {n} 处修改", legacySegments: "记录了 {n} 个接纳片段", unknownStats: "未留存逐缺口统计",
    appliedCount: "本次导回采用 {n} 处", lociCount: "{n} 个位点",
    importingAction: "正在导入精修结果...",
    workingAction: "正在更新精修状态...",
    dismissNotice: "关闭",
    autoTitle: "自动精修",
    manualTitle: "手动精修",
    statusAutoAccepted: "已接纳自动精修",
    statusAutoZero: "未接纳改动（保留 LGZ 基线）",
    statusAutoUnrefined: "未精修 LGZ 基线",
    statusManualExported: "等待 Server 运行与导回",
    statusManualDraft: "有待导出精修任务",
    statusManualIdle: "暂无手动精修记录",
    statusManualImported: "已导回精修结果",
    statusManualLegacyOnly: "仅记录旧版候选（未应用）",
    metricChromosomes: "涉及染色体",
    metricAcceptedSegments: "已接纳片段",
    metricAffectedGaps: "涉及原始缺口",
    metricSourceCards: "精修来源卡片",
    metricDraftLoci: "待导出位点",
    metricExportedBatches: "待导回批次",
    metricImportedResults: "已导回批次",
    metricActiveManualEdits: "当前生效手动精修",
    autoUnrefinedNote: "当前项目导入的是未精修 LGZ 基线，或不包含自动精修接纳片段；未改动片段不会被标记为已精修。",
    autoZeroNote: "当前包为精修协议（schema 5），但未检测到已接纳的自动精修片段，仍保持 LGZ 基线。",
    autoDetailsSummary: "查看自动精修明细（{count} 个片段）",
    manualImportedSummary: "已导回精修结果批次（{count}）",
    manualBatchesSummary: "已导出待运行 / 待导回批次（{count}）",
    manualDraftSummary: "当前项目待导出精修任务（{count}）",
    manualEmptyNote: "尚未登记精修任务或导回精修结果。进入「装配」页后，可在 Final Path 上按项目登记 Gap 或左/右端粒位点并导出精修任务包（.zip），在 Server 运行 refine.py 后点击右上角的导入补丁图标。",
    manualReceiptBoundary: "无后端导回记录前，已导出批次始终标记为「等待 Server 运行与导回」；卡片摘要不展示私有 reads 路径。",
    locateInFinalPath: "在 Final Path 中定位",
    copyCommand: "复制 Server 命令",
    copiedCommand: "已复制命令",
    undoLocus: "撤销采用",
    switchToTool: "切换到 {tool}",
    adoptTool: "采用 {tool}",
    activeBadge: "当前生效",
    undoneBadge: "已撤销",
    duplicateBadge: "重复导入",
    legacyCandidateBadge: "旧版候选 · 未应用",
    appliedSummary: "应用 {applied} · 结果 {sha}",
    batchPrefix: "批次",
    resultPrefix: "结果",
    kindGap: "Gap 补洞",
    kindTelLeft: "左端粒",
    kindTelRight: "右端粒",
    kindLegacy: "旧版候选",
    lociTasks: "{loci} 位点 / {tasks} 次工具运行",
    importDuplicateMsg: "该精修结果包（{sha}）已导入过，未重复修改 Final Path。",
    importAppliedMsg: "已导回并应用 {applied} 个精修位点（涉及染色体：{chrs}），已重新载入权威装配与预览数据。",
    importLegacyOnlyMsg: "已识别旧版 degap_results.zip（{sha}），仅记录旧版候选（未创建轨道、未修改 Final Path）。",
    importNoApplyMsg: "已导回结果包（{sha}），本次应用 0 个位点，请查看各位点判定状态。",
    importSwitchedProjectMsg: "导入期间当前项目已切换，未覆盖目标项目视图。",
    undoSuccessMsg: "已撤销 {chr} 位点 {locusId} 的手动精修（版本 r{rev}），已重新载入权威装配与预览数据。",
    switchSuccessMsg: "已将 {chr} 位点 {locusId} 切换为 {tool}（版本 r{rev}），已重新载入权威装配与预览数据。",
    noProjectError: "请先选择有效项目后再操作。",
    equivalentPrefix: "等价工具",
    activeToolPrefix: "当前工具",
    patchLengthPrefix: "补丁长度",
    dispositionLabels: {
      applied: "已应用",
      adopted: "已采用",
      duplicate: "重复",
      no_patch: "无补丁",
      no_candidate: "无候选",
      failed: "失败",
      skipped: "已跳过",
      stale: "基线已变更",
      conflict: "冲突",
      ambiguous: "待人工选择",
      undone: "已撤销",
      legacy_candidate_only: "旧版候选 · 未应用",
    },
  },
  en: {
    preview: "View tool result", previewHint: "This is the tool’s own result. Viewing it does not change the project assembly.", loadingVersion: "Loading tool result…",
    selectionReasons: { adopted: "Adopted", joint_or_unmapped: "Not independently attributable", path_changed_or_protected: "Changed or protected path", already_filled: "Kept earlier adoption", lower_priority: "Another closure had priority", overlapping_edits: "Overlapping edits" },
    recordHeaders: ["Chromosome", "Length (bp)", "Segments", "Gap segments"],
    sectionTitle: "Refinement",
    importAction: "Import refinement patch",
    autoPatchImported: "Automatic results imported; {n} gap closures adopted in this import.",
    projectAdoptions: "{n} gaps adopted by project",
    autoPatchHydrated: "Added missing sequences for existing tool results. The assembly is unchanged.",
    autoPatchDuplicate: "These automatic results are already in this project.",
    tableColumns: ["Source", "Tool / batch", "Closed", "Partial", "Unfilled", "Rejected", "Result"],
    tableHint: "Automatic rows count original gaps. Manual rows count candidate outcomes per selected Gap, not adoptions. A dash means not recorded or not applicable.",
    editCount: "{n} accepted edits", legacySegments: "{n} recorded accepted segments", unknownStats: "Gap outcomes not recorded",
    appliedCount: "{n} applied on import", lociCount: "{n} loci",
    importingAction: "Importing refinement results...",
    workingAction: "Updating refinement state...",
    dismissNotice: "Dismiss",
    autoTitle: "Automatic Refinement",
    manualTitle: "Manual Refinement",
    statusAutoAccepted: "Accepted",
    statusAutoZero: "Zero accepted edits (LGZ baseline)",
    statusAutoUnrefined: "Unrefined LGZ baseline",
    statusManualExported: "Exported · Awaiting Server & import",
    statusManualDraft: "Refinement tasks queued",
    statusManualIdle: "No manual refinement yet",
    statusManualImported: "Results imported",
    statusManualLegacyOnly: "Legacy candidates recorded (not applied)",
    metricChromosomes: "Chromosomes",
    metricAcceptedSegments: "Accepted segments",
    metricAffectedGaps: "Affected gaps",
    metricSourceCards: "Refinement sources",
    metricDraftLoci: "Queued tasks",
    metricExportedBatches: "Awaiting batches",
    metricImportedResults: "Imported results",
    metricActiveManualEdits: "Active manual edits",
    autoUnrefinedNote: "This project is an unrefined LGZ baseline or contains no accepted automatic refinement segments. Unchanged LGZ segments are never marked as refined.",
    autoZeroNote: "This package uses the refinement schema (schema 5) with zero accepted automatic edits; the LGZ baseline is retained.",
    autoDetailsSummary: "Inspect automatic refinement details ({count} segments)",
    manualImportedSummary: "Imported refinement result batches ({count})",
    manualBatchesSummary: "Exported batches awaiting Server / App import ({count})",
    manualDraftSummary: "Queued project refinement tasks ({count})",
    manualEmptyNote: "No refinement tasks or imported results yet. Open Assembly to queue Gap or Left/Right Telomere loci, export refinement tasks (.zip), run refine.py on Server, then use the import patch icon.",
    manualReceiptBoundary: "Exported batches remain marked awaiting Server/import until backed by an imported result record. Private Server read paths are never shown here.",
    locateInFinalPath: "Locate in Final Path",
    copyCommand: "Copy Server command",
    copiedCommand: "Copied",
    undoLocus: "Undo",
    switchToTool: "Switch to {tool}",
    adoptTool: "Adopt {tool}",
    activeBadge: "Active",
    undoneBadge: "Undone",
    duplicateBadge: "Duplicate",
    legacyCandidateBadge: "Legacy candidate · Not applied",
    appliedSummary: "Applied {applied} · result {sha}",
    batchPrefix: "Batch",
    resultPrefix: "Result",
    kindGap: "Gap fill",
    kindTelLeft: "Left telomere",
    kindTelRight: "Right telomere",
    kindLegacy: "Legacy candidate",
    lociTasks: "{loci} loci / {tasks} tool runs",
    importDuplicateMsg: "Refinement result archive ({sha}) was already imported; Final Path was not modified again.",
    importAppliedMsg: "Imported and applied {applied} locus edit(s) on {chrs}; reloaded authoritative Assembly and Preview data.",
    importLegacyOnlyMsg: "Recognized legacy degap_results.zip ({sha}); recorded legacy candidates only (no tracks created, Final Path unchanged).",
    importNoApplyMsg: "Imported result archive ({sha}) with 0 applied loci; inspect per-locus dispositions below.",
    importSwitchedProjectMsg: "Active project changed during import; skipped updating the newly selected project.",
    undoSuccessMsg: "Undid manual refinement on {chr} locus {locusId} (rev {rev}); reloaded authoritative Assembly and Preview data.",
    switchSuccessMsg: "Switched {chr} locus {locusId} to {tool} (rev {rev}); reloaded authoritative Assembly and Preview data.",
    noProjectError: "Select an active project first.",
    equivalentPrefix: "Equivalent",
    activeToolPrefix: "Active tool",
    patchLengthPrefix: "Patch length",
    dispositionLabels: {
      applied: "Applied",
      adopted: "Adopted",
      duplicate: "Duplicate",
      no_patch: "No patch",
      no_candidate: "No candidate",
      failed: "Failed",
      skipped: "Skipped",
      stale: "Stale baseline",
      conflict: "Conflict",
      ambiguous: "Needs selection",
      undone: "Undone",
      legacy_candidate_only: "Legacy candidate · Not applied",
    },
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

function buildProjectSessionKey(sessionOrIdentity) {
  const session = sessionOrIdentity?.session || sessionOrIdentity || {};
  const workspaceRoot = normalizeString(session.workspaceRoot ?? session.workspacePath);
  const projectId = Number(session.projectId || 0);
  if (!workspaceRoot || !Number.isFinite(projectId) || projectId <= 0) {
    return "";
  }
  return `${workspaceRoot}::${Math.trunc(projectId)}`;
}

function isSameProjectSession(state, { workspaceRoot, projectId }) {
  return (
    normalizeString(state?.session?.workspacePath) === normalizeString(workspaceRoot)
    && Number(state?.session?.projectId || 0) === Number(projectId || 0)
  );
}

function readScopedRefinementUi(state) {
  const currentKey = buildProjectSessionKey(state);
  const raw = state?.initializer?.projectRefinementUi;
  if (!raw || typeof raw !== "object" || !currentKey || raw.projectKey !== currentKey) {
    return {};
  }
  return raw;
}

function normalizeNonNegativeIntOrNull(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? Math.trunc(numeric) : null;
}

function resolveScopedProjectExport(state) {
  const projectId = Number(state?.session?.projectId || 0);
  const workspacePath = normalizeString(state?.session?.workspacePath);
  const pe = state?.projectExport;
  if (!pe || Number(pe.projectId || 0) !== projectId) {
    return null;
  }
  if (pe.workspacePath && workspacePath && normalizeString(pe.workspacePath) !== workspacePath) {
    return null;
  }
  return pe;
}

function resolveGrtProjectView(state) {
  const scoped = resolveScopedProjectExport(state);
  if (scoped?.grtProjectView?.recipe?.schemaVersion || Object.keys(scoped?.grtProjectView?.baselineFinalPathByChr || {}).length) {
    return scoped.grtProjectView;
  }
  return state?.assembly?.grtProjectView || { recipe: {}, baselineFinalPathByChr: {}, sourceCards: [] };
}

function resolveDegapProjectState(state) {
  const scoped = resolveScopedProjectExport(state);
  if (scoped?.degapProjectState && typeof scoped.degapProjectState === "object") {
    return scoped.degapProjectState;
  }
  return state?.assembly?.degapProjectState || state?.assembly?.degap || {};
}

function resolveFinalPathByChr(state) {
  const scoped = resolveScopedProjectExport(state);
  return {
    ...(scoped?.finalPathByChr || {}),
    ...(state?.assembly?.finalPathByChr || {}),
  };
}

function resolveImportedResults(state) {
  const scoped = resolveScopedProjectExport(state);
  if (Array.isArray(scoped?.manualRefinementResults)) {
    return scoped.manualRefinementResults;
  }
  return [];
}

function formatToolLabel(tool) {
  const normalized = normalizeString(tool).toLowerCase();
  return MANUAL_REFINEMENT_TOOL_LABELS[normalized] || normalizeString(tool);
}

function formatTools(tools) {
  return (Array.isArray(tools) ? tools : [])
    .map((tool) => formatToolLabel(tool))
    .filter(Boolean)
    .join(", ");
}

function formatTargetSummary(target) {
  if (!target) return "";
  if (typeof target === "string") return target;
  if (typeof target === "object") {
    const segId = normalizeString(target.segmentId || target.segment_id);
    const left = normalizeString(target.leftCtg || target.left_ctg);
    const right = normalizeString(target.rightCtg || target.right_ctg);
    const endpoint = normalizeString(target.endpointCtg || target.endpoint_ctg || target.ctgName || target.ctg_name);
    if (left && right) return `${left} — ${right}`;
    if (endpoint) return endpoint;
    if (segId) return segId;
  }
  return "";
}

function normalizeImportedCandidate(candidate) {
  if (!candidate || typeof candidate !== "object") {
    return null;
  }
  const tool = normalizeString(candidate.tool || candidate.name).toLowerCase();
  const status = normalizeString(candidate.status).toLowerCase();
  if (!tool) {
    return null;
  }
  const patchLengthBp = normalizeNonNegativeIntOrNull(
    candidate.patch?.length
    ?? candidate.patch?.lengthBp
    ?? candidate.patch?.length_bp
    ?? candidate.patchLengthBp
    ?? candidate.patch_length_bp
    ?? candidate.lengthBp
    ?? candidate.length_bp,
  );
  return {
    tool,
    status,
    isLegacyCandidate: status === "legacy_candidate_only",
    switchable: (status === "closed" || status === "extended") && status !== "legacy_candidate_only",
    patchLengthBp,
    ctgName: normalizeString(candidate.ctgName || candidate.ctg_name),
    sha256: normalizeString(candidate.sha256 || candidate.patch?.sha256),
    reason: normalizeString(candidate.reason || candidate.message),
  };
}

function normalizeImportedLocus(locus) {
  if (!locus || typeof locus !== "object") {
    return null;
  }
  const locusId = normalizeString(locus.locusId || locus.locus_id);
  const chr = normalizeString(locus.chr);
  const kind = normalizeString(locus.kind).toLowerCase();
  const disposition = normalizeString(locus.disposition).toLowerCase();
  const isLegacy = kind === "legacy" || disposition === "legacy_candidate_only";
  const adoptionState = isLegacy
    ? ""
    : normalizeString(locus.adoptionState || locus.adoption_state).toLowerCase();
  const rawRev = locus.adoptionRevision ?? locus.adoption_revision;
  const adoptionRevision = Number.isFinite(Number(rawRev)) && rawRev !== null && rawRev !== ""
    ? Math.trunc(Number(rawRev))
    : null;
  const activeResultSha256 = isLegacy
    ? ""
    : normalizeString(locus.activeResultSha256 || locus.active_result_sha256);
  const activeTool = isLegacy
    ? ""
    : normalizeString(locus.activeTool || locus.active_tool).toLowerCase();
  const appliedTool = isLegacy
    ? ""
    : normalizeString(locus.appliedTool || locus.applied_tool).toLowerCase();
  const locateSegmentId = isLegacy
    ? ""
    : normalizeString(
      locus.locateSegmentId
      ?? locus.locate_segment_id
      ?? locus.target?.segmentId
      ?? locus.target?.segment_id,
    );
  const patchLengthBp = normalizeNonNegativeIntOrNull(
    locus.activePatchLengthBp
    ?? locus.active_patch_length_bp
    ?? locus.patch?.length
    ?? locus.patch?.lengthBp
    ?? locus.patch?.length_bp
    ?? locus.patchLengthBp
    ?? locus.patch_length_bp,
  );
  const equivalentTools = Array.isArray(locus.equivalentTools || locus.equivalent_tools)
    ? (locus.equivalentTools || locus.equivalent_tools).map((item) => normalizeString(item).toLowerCase()).filter(Boolean)
    : [];
  const candidates = (Array.isArray(locus.candidates) ? locus.candidates : [])
    .map(normalizeImportedCandidate)
    .filter(Boolean);
  return {
    locusId,
    chr,
    kind,
    isLegacy,
    locateSegmentId,
    patchLengthBp,
    targetLabel: formatTargetSummary(locus.target),
    disposition,
    appliedTool,
    equivalentTools,
    adoptionState: adoptionState === "active" || adoptionState === "undone" ? adoptionState : "",
    adoptionRevision,
    activeResultSha256,
    activeTool,
    candidates,
  };
}

function normalizeImportedResult(result) {
  if (!result || typeof result !== "object") {
    return null;
  }
  const resultSha256 = normalizeString(result.resultSha256 || result.result_sha256);
  const batchSha256 = normalizeString(result.batchSha256 || result.batch_sha256);
  const loci = (Array.isArray(result.loci) ? result.loci : [])
    .map(normalizeImportedLocus)
    .filter(Boolean);
  const changedChromosomes = Array.isArray(result.changedChromosomes || result.changed_chromosomes)
    ? (result.changedChromosomes || result.changed_chromosomes).map(normalizeString).filter(Boolean)
    : [];
  const isLegacyOnly = loci.length > 0 && loci.every((locus) => locus.isLegacy);
  return {
    resultSha256,
    batchSha256,
    applied: Math.max(0, Number(result.applied || 0) || 0),
    duplicate: Boolean(result.duplicate),
    isLegacyOnly,
    changedChromosomes,
    loci,
  };
}

export function buildProjectRefinementModel(state) {
  const grtView = resolveGrtProjectView(state);
  const recipe = grtView?.recipe || state?.initializer?.grtRecipe || {};
  const schemaVersion = normalizeString(recipe.schemaVersion || recipe.schema_version);
  const isRefinementSchema = schemaVersion === "5";
  const baselineByChr = grtView?.baselineFinalPathByChr || {};
  const currentByChr = resolveFinalPathByChr(state);

  const autoSegments = [];
  const manualAppliedSegments = [];
  const autoChrSet = new Set();
  const autoGapSet = new Set();

  const inspectMap = (map, sourceOrigin) => {
    Object.entries(map || {}).forEach(([chrKey, entry]) => {
      const chrName = normalizeString(entry?.chrName || chrKey);
      const segments = Array.isArray(entry?.segments) ? entry.segments : [];
      segments.forEach((segment) => {
        if (!isFinalPathCtgSegment(segment)) {
          return;
        }
        const info = describeFinalPathRefinement(segment, state?.locale);
        if (!info) {
          return;
        }
        const item = {
          chrName,
          segmentId: normalizeString(segment.segmentId),
          displayName: resolveFinalPathSegmentDisplayName(segment),
          mode: info.mode,
          tool: info.tool,
          version: info.version,
          editId: info.editId,
          batchSha256: info.batchSha256,
          originalGapIds: info.originalGapIds,
        };
        if (info.mode === "manual") {
          manualAppliedSegments.push(item);
        } else if (sourceOrigin === "baseline") {
          autoSegments.push(item);
          if (chrName) autoChrSet.add(chrName);
          info.originalGapIds.forEach((id) => autoGapSet.add(`${chrName}:${id}`));
        }
      });
    });
  };

  inspectMap(baselineByChr, "baseline");
  inspectMap(currentByChr, "current");

  const refinementSourceCards = (Array.isArray(grtView?.sourceCards) ? grtView.sourceCards : [])
    .filter((card) => normalizeString(card?.placementMode).toLowerCase() === "refinement");

  const degapProjectState = resolveDegapProjectState(state);
  const frontendManualState = degapProjectState?.manualRefinement;
  const exportReceipts = resolveScopedProjectExport(state)?.manualRefinementExports;
  const manualState = normalizeManualRefinementState({
    ...frontendManualState,
    exportedBatches: [
      ...(Array.isArray(frontendManualState?.exportedBatches) ? frontendManualState.exportedBatches : []),
      ...(Array.isArray(exportReceipts) ? exportReceipts : []),
    ].sort((left, right) => {
      const time = (row) => Number(row?.exportedAtMs) || Date.parse(row?.exportedAt || "") || 0;
      return time(right) - time(left);
    }),
  });
  const importedResults = resolveImportedResults(state).map(normalizeImportedResult).filter(Boolean);
  const importedBatchShas = new Set(importedResults.map((item) => item.batchSha256).filter(Boolean));
  const awaitingExportedBatches = manualState.exportedBatches.filter(
    (batch) => !batch.batchSha256 || !importedBatchShas.has(batch.batchSha256),
  );

  const activeLocusIds = new Set();
  importedResults.forEach((batch) => {
    batch.loci.forEach((locus) => {
      if (!locus.isLegacy && locus.adoptionState === "active" && locus.locusId) {
        activeLocusIds.add(locus.locusId);
      }
    });
  });
  const activeManualCount = activeLocusIds.size || manualAppliedSegments.length;
  const hasNonLegacyImportedResults = importedResults.some((batch) => !batch.isLegacyOnly);
  const hasOnlyLegacyImportedResults = importedResults.length > 0 && !hasNonLegacyImportedResults && manualAppliedSegments.length === 0;

  const effects = Array.isArray(grtView?.autoRefinementEffects) ? grtView.autoRefinementEffects : [];
  let autoStatus = "unrefined";
  if (autoSegments.length || refinementSourceCards.length || effects.some((row) => (row.accepted_edits ?? row.acceptedEdits) > 0)) {
    autoStatus = "accepted";
  } else if (isRefinementSchema || effects.length) {
    autoStatus = effects.length ? "zero_accepted" : "not_recorded";
  }

  let manualStatus = "idle";
  if (hasNonLegacyImportedResults || manualAppliedSegments.length > 0) {
    manualStatus = "imported";
  } else if (awaitingExportedBatches.length > 0) {
    manualStatus = "exported";
  } else if (manualState.loci.length > 0) {
    manualStatus = "draft";
  } else if (hasOnlyLegacyImportedResults) {
    manualStatus = "legacy_only";
  }

  return {
    auto: {
      status: autoStatus,
      schemaVersion,
      effects,
      chromosomeCount: autoChrSet.size,
      acceptedSegmentCount: autoSegments.length,
      affectedGapCount: autoGapSet.size,
      sourceCardCount: refinementSourceCards.length,
      segments: autoSegments,
    },
    manual: {
      status: manualStatus,
      draftLoci: manualState.loci,
      exportedBatches: awaitingExportedBatches,
      importedResults,
      importedSegments: manualAppliedSegments,
      activeManualCount,
    },
  };
}

function kindLabel(kind, copy) {
  if (kind === "tel_left") return copy.kindTelLeft;
  if (kind === "tel_right") return copy.kindTelRight;
  if (kind === "legacy") return copy.kindLegacy;
  return copy.kindGap;
}

function dispositionLabel(disposition, copy) {
  return copy.dispositionLabels?.[disposition] || disposition || "";
}

function setRefinementUi(store, patch, identity = null) {
  const state = store.getState();
  const projectKey = identity
    ? buildProjectSessionKey(identity)
    : buildProjectSessionKey(state);
  const existing = state.initializer?.projectRefinementUi;
  const base = existing && existing.projectKey === projectKey ? existing : {};
  store.setState({
    initializer: {
      ...state.initializer,
      projectRefinementUi: {
        ...base,
        ...patch,
        projectKey,
      },
    },
  });
}

async function reloadAuthoritativeProjectStateAfterRefinement(host, store, { workspaceRoot, projectId }, deps = {}) {
  clearAssemblySessionCache();
  const getViewState = deps.getProjectAssemblyViewState || getProjectAssemblyViewState;
  const getGrtView = deps.getGrtProjectView || getGrtProjectView;
  const listResults = deps.listManualRefinementResults || listManualRefinementResults;
  const args = { workspaceRoot, projectId };
  const [viewState, rawGrtView, results] = await Promise.all([
    getViewState(args),
    getGrtView(args).catch(() => ({})),
    listResults(args).catch(() => []),
  ]);
  if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
    return false;
  }
  const authoritativeFinalPathByChr = normalizeFinalPathByChr(viewState?.finalPathByChr || {});
  const authoritativeGrtView = normalizeGrtProjectView(rawGrtView);
  const currentState = store.getState();
  // Replace in-memory assembly Final Path with authoritative DB state and clear
  // active chromosome view so stale drafts can never overwrite DB on reload.
  store.setState({
    assembly: {
      ...currentState.assembly,
      selectedChrName: "",
      chromosomes: [],
      chrCtgs: [],
      supportChrCtgs: [],
      finalPathByChr: authoritativeFinalPathByChr,
      degapProjectState: viewState?.degapProjectState || {},
      grtProjectView: authoritativeGrtView,
    },
    projectPreview: {
      ...(currentState.projectPreview || {}),
      loaded: false,
    },
    projectExport: {
      ...(currentState.projectExport || {}),
      loaded: false,
      projectId,
      workspacePath: workspaceRoot,
      finalPathByChr: authoritativeFinalPathByChr,
      degapProjectState: viewState?.degapProjectState || {},
      grtProjectView: authoritativeGrtView,
      manualRefinementResults: Array.isArray(results) ? results : [],
    },
  });
  await (deps.reloadProjectOverviewData || reloadProjectOverviewData)(host, store);
  return true;
}

export async function runImportManualRefinementResults(host, store, rerender, deps = {}) {
  const initialState = store.getState();
  const copy = COPY[initialState?.locale === "en" ? "en" : "zh"];
  const workspaceRoot = normalizeString(initialState?.session?.workspacePath);
  const projectId = Number(initialState?.session?.projectId || 0);
  if (!workspaceRoot || !projectId) {
    setRefinementUi(store, { error: copy.noProjectError, notice: "" });
    rerender?.(host, store);
    return false;
  }

  // Freeze project identity before opening the OS file picker.
  const pickZip = deps.pickZipFilePath || pickZipFilePath;
  const zipPath = normalizeString(await pickZip(initialState));
  if (!zipPath) {
    return false;
  }
  if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
    return false;
  }

  setRefinementUi(store, { inFlight: true, busyLabel: copy.importingAction, error: "", notice: "" }, { workspaceRoot, projectId });
  rerender?.(host, store);

  try {
    await (deps.flushAssemblyProjectState || flushAssemblyProjectState)(host, store);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    const importFn = deps.importManualRefinementResults || importManualRefinementResults;
    const rawResult = await importFn({
      workspaceRoot,
      projectId,
      zipPath,
      stateOrLocale: initialState,
    });
    const result = normalizeImportedResult(rawResult);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    await reloadAuthoritativeProjectStateAfterRefinement(host, store, { workspaceRoot, projectId }, deps);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    const shortSha = (result?.resultSha256 || "").slice(0, 12) || "-";
    let notice = "";
    if (rawResult?.kind === "automatic") {
      notice = rawResult.duplicate ? copy.autoPatchDuplicate
        : rawResult.sequenceObjectsAdded > 0 && !rawResult.applied && !rawResult.addedTools?.length ? copy.autoPatchHydrated
          : fmt(copy.autoPatchImported, { n: rawResult.applied ?? 0 });
    } else if (result?.isLegacyOnly) {
      notice = fmt(copy.importLegacyOnlyMsg, { sha: shortSha });
    } else if (result?.duplicate) {
      notice = fmt(copy.importDuplicateMsg, { sha: shortSha });
    } else if ((result?.applied || 0) > 0) {
      notice = fmt(copy.importAppliedMsg, {
        applied: result.applied,
        chrs: result.changedChromosomes.join(", ") || "-",
      });
    } else {
      notice = fmt(copy.importNoApplyMsg, { sha: shortSha });
    }
    setRefinementUi(store, { inFlight: false, busyLabel: "", error: "", notice }, { workspaceRoot, projectId });
    rerender?.(host, store);
    return true;
  } catch (error) {
    if (isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      setRefinementUi(store, {
        inFlight: false,
        busyLabel: "",
        notice: "",
        error: String(error?.message || error || "Failed to import refinement results."),
      }, { workspaceRoot, projectId });
      rerender?.(host, store);
    }
    return false;
  }
}

export async function runUndoManualRefinementLocus(host, store, payload, rerender, deps = {}) {
  const initialState = store.getState();
  const copy = COPY[initialState?.locale === "en" ? "en" : "zh"];
  const workspaceRoot = normalizeString(initialState?.session?.workspacePath);
  const projectId = Number(initialState?.session?.projectId || 0);
  const locusId = normalizeString(payload?.locusId);
  const expectedRevision = Number(payload?.expectedRevision);
  if (!workspaceRoot || !projectId || !locusId || !Number.isFinite(expectedRevision)) {
    return false;
  }

  setRefinementUi(store, { inFlight: true, busyLabel: copy.workingAction, error: "", notice: "" }, { workspaceRoot, projectId });
  rerender?.(host, store);
  try {
    await (deps.flushAssemblyProjectState || flushAssemblyProjectState)(host, store);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    const undoFn = deps.undoManualRefinementLocus || undoManualRefinementLocus;
    const response = await undoFn({
      workspaceRoot,
      projectId,
      locusId,
      expectedRevision: Math.trunc(expectedRevision),
      stateOrLocale: initialState,
    });
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    await reloadAuthoritativeProjectStateAfterRefinement(host, store, { workspaceRoot, projectId }, deps);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    setRefinementUi(store, {
      inFlight: false,
      busyLabel: "",
      error: "",
      notice: fmt(copy.undoSuccessMsg, {
        chr: normalizeString(response?.chr || payload?.chr),
        locusId: normalizeString(response?.locusId || locusId),
        rev: response?.adoptionRevision ?? "",
      }),
    }, { workspaceRoot, projectId });
    rerender?.(host, store);
    return true;
  } catch (error) {
    if (isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      setRefinementUi(store, {
        inFlight: false,
        busyLabel: "",
        notice: "",
        error: String(error?.message || error || "Failed to undo manual refinement locus."),
      }, { workspaceRoot, projectId });
      rerender?.(host, store);
    }
    return false;
  }
}

export async function runSwitchManualRefinementLocus(host, store, payload, rerender, deps = {}) {
  const initialState = store.getState();
  const copy = COPY[initialState?.locale === "en" ? "en" : "zh"];
  const workspaceRoot = normalizeString(initialState?.session?.workspacePath);
  const projectId = Number(initialState?.session?.projectId || 0);
  const locusId = normalizeString(payload?.locusId);
  const resultSha256 = normalizeString(payload?.resultSha256);
  const tool = normalizeString(payload?.tool).toLowerCase();
  const expectedRevision = Number(payload?.expectedRevision);
  if (!workspaceRoot || !projectId || !locusId || !resultSha256 || !tool || !Number.isFinite(expectedRevision)) {
    return false;
  }

  setRefinementUi(store, { inFlight: true, busyLabel: copy.workingAction, error: "", notice: "" }, { workspaceRoot, projectId });
  rerender?.(host, store);
  try {
    await (deps.flushAssemblyProjectState || flushAssemblyProjectState)(host, store);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    const switchFn = deps.switchManualRefinementLocus || switchManualRefinementLocus;
    const response = await switchFn({
      workspaceRoot,
      projectId,
      locusId,
      expectedRevision: Math.trunc(expectedRevision),
      resultSha256,
      tool,
      stateOrLocale: initialState,
    });
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    await reloadAuthoritativeProjectStateAfterRefinement(host, store, { workspaceRoot, projectId }, deps);
    if (!isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      return false;
    }
    setRefinementUi(store, {
      inFlight: false,
      busyLabel: "",
      error: "",
      notice: fmt(copy.switchSuccessMsg, {
        chr: normalizeString(response?.chr || payload?.chr),
        locusId: normalizeString(response?.locusId || locusId),
        tool: formatToolLabel(response?.activeTool || tool),
        rev: response?.adoptionRevision ?? "",
      }),
    }, { workspaceRoot, projectId });
    rerender?.(host, store);
    return true;
  } catch (error) {
    if (isSameProjectSession(store.getState(), { workspaceRoot, projectId })) {
      setRefinementUi(store, {
        inFlight: false,
        busyLabel: "",
        notice: "",
        error: String(error?.message || error || "Failed to switch manual refinement candidate."),
      }, { workspaceRoot, projectId });
      rerender?.(host, store);
    }
    return false;
  }
}

function formatPatchLengthBadge(lengthBp, copy) {
  if (lengthBp === null || lengthBp === undefined) {
    return "";
  }
  const formatted = `${Math.trunc(Number(lengthBp)).toLocaleString("en-US")} bp`;
  return `<span class="muted">${escapeHtml(`${copy.patchLengthPrefix}: ${formatted}`)}</span>`;
}

function renderImportedLocusRow(batch, locus, copy, busy) {
  if (locus.isLegacy) {
    const legacyDetails = locus.candidates
      .map((candidate) => {
        const parts = [
          formatToolLabel(candidate.tool),
          candidate.ctgName || "",
          candidate.sha256 ? candidate.sha256.slice(0, 12) : "",
        ].filter(Boolean);
        return parts.join(" · ");
      })
      .filter(Boolean);
    return `<li class="project-refinement-item" data-project-refinement-legacy-locus="1">
      <div class="project-refinement-item-main">
        ${locus.chr ? `<span class="project-refinement-chr">${escapeHtml(locus.chr)}</span>` : ""}
        <span class="project-refinement-badge is-neutral">${escapeHtml(copy.legacyCandidateBadge)}</span>
        ${locus.targetLabel ? `<span class="muted">${escapeHtml(locus.targetLabel)}</span>` : ""}
        ${legacyDetails.map((detail) => `<code class="project-refinement-tag">${escapeHtml(detail)}</code>`).join("")}
      </div>
    </li>`;
  }

  const isActive = locus.adoptionState === "active";
  const isUndone = locus.adoptionState === "undone";
  const canMutate = Boolean(locus.locusId) && locus.adoptionRevision !== null && !busy;
  const activeTool = locus.activeTool || locus.appliedTool;
  const activeCandidate = locus.candidates.find((candidate) => candidate.tool === activeTool) || null;
  const displayPatchLength = locus.patchLengthBp ?? activeCandidate?.patchLengthBp ?? null;
  const switchableCandidates = locus.candidates.filter((candidate) => candidate.switchable);
  const candidateActions = switchableCandidates
    .filter((candidate) => {
      const sameAsActive = isActive
        && locus.activeResultSha256 === batch.resultSha256
        && activeTool === candidate.tool;
      return !sameAsActive;
    })
    .map((candidate) => {
      const baseLabel = isUndone
        ? fmt(copy.adoptTool, { tool: formatToolLabel(candidate.tool) })
        : fmt(copy.switchToTool, { tool: formatToolLabel(candidate.tool) });
      const lengthSuffix = candidate.patchLengthBp !== null
        ? ` (${candidate.patchLengthBp.toLocaleString("en-US")} bp)`
        : "";
      return `<button
        type="button"
        class="button ghost project-refinement-locate"
        data-project-refinement-switch
        data-locus-id="${escapeAttr(locus.locusId)}"
        data-locus-chr="${escapeAttr(locus.chr)}"
        data-expected-revision="${escapeAttr(locus.adoptionRevision ?? "")}"
        data-result-sha256="${escapeAttr(batch.resultSha256)}"
        data-tool="${escapeAttr(candidate.tool)}"
        ${canMutate ? "" : "disabled"}
      >${escapeHtml(`${baseLabel}${lengthSuffix}`)}</button>`;
    })
    .join("");
  const undoButton = isActive && locus.locusId && locus.adoptionRevision !== null
    ? `<button
        type="button"
        class="button ghost project-refinement-locate"
        data-project-refinement-undo
        data-locus-id="${escapeAttr(locus.locusId)}"
        data-locus-chr="${escapeAttr(locus.chr)}"
        data-expected-revision="${escapeAttr(locus.adoptionRevision)}"
        ${busy ? "disabled" : ""}
      >${escapeHtml(copy.undoLocus)}</button>`
    : "";

  const stateBadge = isActive
    ? `<span class="project-refinement-badge is-ok">${escapeHtml(copy.activeBadge)}</span>`
    : isUndone
      ? `<span class="project-refinement-badge is-neutral">${escapeHtml(copy.undoneBadge)}</span>`
      : locus.disposition
        ? `<span class="project-refinement-badge is-neutral">${escapeHtml(dispositionLabel(locus.disposition, copy))}</span>`
        : "";

  return `<li class="project-refinement-item">
    <div class="project-refinement-item-main">
      <span class="project-refinement-chr">${escapeHtml(locus.chr)}</span>
      <span>${escapeHtml(kindLabel(locus.kind, copy))}</span>
      ${locus.targetLabel ? `<span class="muted">${escapeHtml(locus.targetLabel)}</span>` : ""}
      ${stateBadge}
      ${activeTool ? `<span class="project-refinement-tag">${escapeHtml(`${copy.activeToolPrefix}: ${formatToolLabel(activeTool)}`)}</span>` : ""}
      ${formatPatchLengthBadge(displayPatchLength, copy)}
      ${locus.equivalentTools.length ? `<span class="muted">${escapeHtml(`${copy.equivalentPrefix}: ${formatTools(locus.equivalentTools)}`)}</span>` : ""}
    </div>
    <div class="project-refinement-item-actions">
      ${candidateActions}
      ${undoButton}
      ${locus.chr ? `<button type="button" class="button ghost project-refinement-locate" data-project-refinement-locate-chr="${escapeAttr(locus.chr)}"${locus.locateSegmentId ? ` data-project-refinement-locate-segment-id="${escapeAttr(locus.locateSegmentId)}"` : ""}>${escapeHtml(copy.locateInFinalPath)}</button>` : ""}
    </div>
  </li>`;
}

function refinementTableRows({ auto, manual }, copy) {
  const rows = [];
  const autoRow = (label, counts, result, version = null) => rows.push({ source: copy.autoTitle, label, cells: [...counts, result], version });
  const absent = [null, null, null, null];
  const reported = new Set();
  for (const effect of auto.effects) {
    reported.add(effect.tool);
    const id = effect.version_id ?? effect.versionId;
    const version = /^[a-f0-9]{64}$/.test(id || "") ? { id, tool: effect.tool } : null;
    const duplicateTool = auto.effects.some((other) => other !== effect && other.tool === effect.tool);
    const label = formatToolLabel(effect.tool) + (duplicateTool && version ? ` · ${id.slice(0, 8)}` : "");
    autoRow(label, [effect.closed, effect.partial, effect.unfilled, effect.rejected],
      [fmt(copy.editCount, { n: effect.accepted_edits ?? effect.acceptedEdits }),
        Number.isInteger(effect.project_adopted_gaps ?? effect.projectAdoptedGaps) ? fmt(copy.projectAdoptions, { n: effect.project_adopted_gaps ?? effect.projectAdoptedGaps }) : "",
      ].filter(Boolean).join(" · "), version);
  }
  // Old project databases retain accepted segments, not per-gap closure measurements.
  const legacy = new Map();
  for (const segment of auto.segments) {
    const tool = normalizeString(segment.tool).toLowerCase();
    if (!reported.has(tool)) legacy.set(tool, (legacy.get(tool) || 0) + 1);
  }
  for (const [tool, n] of legacy) autoRow(formatToolLabel(tool), absent, fmt(copy.legacySegments, { n }));
  if (!rows.length && auto.schemaVersion) autoRow(auto.schemaVersion === "5" ? "—" : "LGZ", absent,
    auto.schemaVersion === "5" ? copy.unknownStats : copy.statusAutoUnrefined);

  const toolNames = (ids) => formatTools([...new Set(ids.filter(Boolean))]);
  const manualRow = (label, counts, status) => rows.push({ source: copy.manualTitle, label, cells: [...counts, status] });
  for (const batch of manual.importedResults) {
    const gaps = batch.loci.filter((locus) => locus.kind === "gap" && !locus.isLegacy);
    const outcomes = gaps.map((gap) => {
      const states = new Set(gap.candidates.map((c) => c.status));
      if (states.has("closed")) return "closed";
      if (states.has("partial")) return "partial";
      if (states.size === 1 && states.has("no_candidate")) return "unfilled";
      if (states.size === 1 && states.has("rejected")) return "rejected";
      return null; // e.g. missing reads is neither rejection nor an unfilled measurement
    });
    const tools = toolNames(batch.loci.flatMap((l) => l.candidates.map((c) => c.tool)));
    const label = [tools, (batch.batchSha256 || batch.resultSha256).slice(0, 12)].filter(Boolean).join(" · ");
    manualRow(label, outcomes.some(Boolean)
      ? ["closed", "partial", "unfilled", "rejected"].map((k) => outcomes.filter((v) => v === k).length) : absent,
      batch.isLegacyOnly ? copy.statusManualLegacyOnly : fmt(copy.appliedCount, { n: batch.applied }));
  }
  for (const batch of manual.exportedBatches) manualRow([toolNames(batch.loci.flatMap((l) => l.tools)),
    batch.batchSha256.slice(0, 12)].filter(Boolean).join(" · "), absent, copy.statusManualExported);
  if (manual.draftLoci.length) manualRow(toolNames(manual.draftLoci.flatMap((l) => l.tools)), absent,
    `${copy.statusManualDraft} · ${fmt(copy.lociCount, { n: manual.draftLoci.length })}`);
  return rows;
}

function versionTableRow({ source, label, cells, version }, ui, copy, locale) {
  const open = version && ui.previewId === version.id && ui.previewTool === version.tool;
  const button = version ? `<button type="button" class="button ghost project-refinement-locate" data-preview-version="${escapeAttr(version.id)}" data-version-tool="${escapeAttr(version.tool)}" aria-expanded="${Boolean(open)}" aria-label="${escapeAttr(`${copy.preview}: ${label}`)}">${escapeHtml(copy.preview)}</button>` : "";
  const row = `<tr><td>${escapeHtml(source)}</td><th scope="row">${escapeHtml(label || "—")} ${button}</th>${cells.map((v) => `<td>${escapeHtml(String(v ?? "—"))}</td>`).join("")}</tr>`;
  if (!open) return row;
  const data = ui.previewData;
  const counts = new Intl.NumberFormat(locale === "en" ? "en-US" : "zh-CN");
  const decisions = Object.entries(data?.decisions || {}).map(([key, n]) => `${copy.selectionReasons[key] || key}: ${counts.format(n)}`).join(" · ");
  const details = ui.previewError ? `<span role="alert">${escapeHtml(ui.previewError)}</span>`
    : !data ? `<span role="status">${escapeHtml(copy.loadingVersion)}</span>`
    : `<p class="muted">${escapeHtml(copy.previewHint)} <code>${escapeHtml(version.id.slice(0, 12))}</code></p>${decisions ? `<p>${escapeHtml(decisions)}</p>` : ""}<table><thead><tr>${copy.recordHeaders.map((h) => `<th scope="col">${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${data.chromosomes.map((c) => `<tr><th scope="row">${escapeHtml(c.chr)}</th>${[c.bp,c.segments,c.gapSegments].map((n) => `<td>${escapeHtml(counts.format(n))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  return `${row}<tr><td colspan="${cells.length + 2}">${details}</td></tr>`;
}

let previewRequest = 0;
async function toggleVersionPreview(host, store, button, rerender, deps) {
  const state = store.getState();
  const identity = { workspaceRoot: state.session?.workspacePath, projectId: Number(state.session?.projectId) };
  if (!buildProjectSessionKey(identity)) return;
  const versionId = button.dataset.previewVersion, tool = button.dataset.versionTool;
  const ui = readScopedRefinementUi(state), request = ++previewRequest;
  const close = ui.previewId === versionId && ui.previewTool === tool;
  setRefinementUi(store, { previewId: close ? null : versionId, previewTool: tool, previewRequest: request, previewData: null, previewError: "" }, identity);
  rerender?.(host, store);
  if (close) return;
  const current = () => isSameProjectSession(store.getState(), identity) && readScopedRefinementUi(store.getState()).previewRequest === request;
  try {
    const data = await (deps.previewProjectRefinementVersion || previewProjectRefinementVersion)({ ...identity, versionId, tool, stateOrLocale: state.locale });
    if (!current()) return;
    if (data?.versionId !== versionId || data.tool !== tool || !Array.isArray(data.chromosomes)) throw new Error(state.locale === "en" ? "Version identity mismatch" : "版本身份不匹配");
    setRefinementUi(store, { previewData: data }, identity);
  } catch (error) {
    if (!current()) return;
    setRefinementUi(store, { previewError: String(error?.message || error) }, identity);
  }
  rerender?.(host, store);
}

export function renderProjectRefinementCard(state) {
  const copy = COPY[state?.locale === "en" ? "en" : "zh"];
  const model = buildProjectRefinementModel(state);
  const ui = readScopedRefinementUi(state);
  const inFlightForCurrentProject = Boolean(ui.inFlight);
  const busy = Boolean(state?.importer?.inFlight || state?.initializer?.autoPipelineRunning || inFlightForCurrentProject);

  const rows = refinementTableRows(model, copy);
  const importLabel = inFlightForCurrentProject ? (ui.busyLabel || copy.importingAction) : copy.importAction;
  const autoDetails = model.auto.segments.length
    ? `<details class="project-refinement-details">
        <summary>${escapeHtml(fmt(copy.autoDetailsSummary, { count: model.auto.segments.length }))}</summary>
        <p class="muted project-refinement-note">${escapeHtml([
          `${copy.metricChromosomes}: ${model.auto.chromosomeCount}`, `${copy.metricAffectedGaps}: ${model.auto.affectedGapCount}`,
          `${copy.metricSourceCards}: ${model.auto.sourceCardCount}`,
        ].join(" · "))}</p>
        <ul class="project-refinement-list">
          ${model.auto.segments.map((item) => `<li class="project-refinement-item">
            <div class="project-refinement-item-main">
              <span class="project-refinement-chr">${escapeHtml(item.chrName)}</span>
              <strong>${escapeHtml(item.displayName || item.segmentId)}</strong>
              ${item.tool ? `<span class="project-refinement-tag">${escapeHtml(item.tool)}${item.version ? ` v${escapeHtml(item.version)}` : ""}</span>` : ""}
              ${item.originalGapIds.length ? `<span class="muted">${escapeHtml(item.originalGapIds.join(", "))}</span>` : ""}
            </div>
            <button type="button" class="button ghost project-refinement-locate" data-project-refinement-locate-chr="${escapeAttr(item.chrName)}">${escapeHtml(copy.locateInFinalPath)}</button>
          </li>`).join("")}
        </ul>
      </details>`
    : "";

  const manualImportedMarkup = model.manual.importedResults.length
    ? `<details class="project-refinement-details" open>
        <summary>${escapeHtml(fmt(copy.manualImportedSummary, { count: model.manual.importedResults.length }))}</summary>
        <ul class="project-refinement-list">
          ${model.manual.importedResults.map((batch) => `<li class="project-refinement-batch">
            <div class="project-refinement-item-main">
              <span class="project-refinement-badge ${batch.isLegacyOnly ? "is-neutral" : "is-ok"}">${escapeHtml(batch.isLegacyOnly ? copy.legacyCandidateBadge : batch.duplicate ? copy.duplicateBadge : copy.statusManualImported)}</span>
              ${batch.batchSha256 ? `<code>${escapeHtml(copy.batchPrefix)} ${escapeHtml(batch.batchSha256.slice(0, 12))}</code>` : ""}
              <span class="muted">${escapeHtml(fmt(copy.appliedSummary, { applied: batch.applied, sha: (batch.resultSha256 || "-").slice(0, 12) }))}</span>
              ${batch.changedChromosomes.length ? `<span class="muted">${escapeHtml(batch.changedChromosomes.join(", "))}</span>` : ""}
            </div>
            ${batch.loci.length ? `<ul class="project-refinement-sublist">
              ${batch.loci.map((locus) => renderImportedLocusRow(batch, locus, copy, busy)).join("")}
            </ul>` : ""}
          </li>`).join("")}
        </ul>
      </details>`
    : "";

  const manualBatchesMarkup = model.manual.exportedBatches.length
    ? `<details class="project-refinement-details" ${manualImportedMarkup ? "" : "open"}>
        <summary>${escapeHtml(fmt(copy.manualBatchesSummary, { count: model.manual.exportedBatches.length }))}</summary>
        <ul class="project-refinement-list">
          ${model.manual.exportedBatches.map((batch) => {
            const cmd = buildManualRefinementServerCommand(batch.outputPath || batch.outputFileName);
            return `<li class="project-refinement-batch">
              <div class="project-refinement-item-main">
                <span class="project-refinement-badge is-warn">${escapeHtml(copy.statusManualExported)}</span>
                <code>${escapeHtml(copy.batchPrefix)} ${escapeHtml(batch.batchSha256.slice(0, 12))}</code>
                <span class="muted">${escapeHtml(fmt(copy.lociTasks, { loci: batch.lociCount, tasks: batch.tasksCount }))}</span>
              </div>
              <div class="project-refinement-batch-actions">
                <code class="project-refinement-cmd">${escapeHtml(cmd)}</code>
                <button type="button" class="button ghost project-refinement-locate" data-project-refinement-copy="${escapeAttr(cmd)}">${escapeHtml(copy.copyCommand)}</button>
              </div>
              ${batch.loci.length ? `<ul class="project-refinement-sublist">
                ${batch.loci.map((locus) => `<li class="project-refinement-item">
                  <div class="project-refinement-item-main">
                    <span class="project-refinement-chr">${escapeHtml(locus.chr)}</span>
                    <span>${escapeHtml(kindLabel(locus.kind, copy))}</span>
                    <span class="muted">${escapeHtml(locus.label || locus.segmentId)}</span>
                    <span class="project-refinement-tag">${escapeHtml(formatTools(locus.tools))}</span>
                  </div>
                  <button type="button" class="button ghost project-refinement-locate" data-project-refinement-locate-chr="${escapeAttr(locus.chr)}">${escapeHtml(copy.locateInFinalPath)}</button>
                </li>`).join("")}
              </ul>` : ""}
            </li>`;
          }).join("")}
        </ul>
      </details>`
    : "";

  const manualDraftMarkup = model.manual.draftLoci.length
    ? `<details class="project-refinement-details">
        <summary>${escapeHtml(fmt(copy.manualDraftSummary, { count: model.manual.draftLoci.length }))}</summary>
        <ul class="project-refinement-list">
          ${model.manual.draftLoci.map((locus) => `<li class="project-refinement-item">
            <div class="project-refinement-item-main">
              <span class="project-refinement-chr">${escapeHtml(locus.chr)}</span>
              <span>${escapeHtml(kindLabel(locus.kind, copy))}</span>
              <span class="muted">${escapeHtml(locus.label || locus.segmentId)}</span>
              <span class="project-refinement-tag">${escapeHtml(formatTools(locus.tools))}</span>
            </div>
            <button type="button" class="button ghost project-refinement-locate" data-project-refinement-locate-chr="${escapeAttr(locus.chr)}">${escapeHtml(copy.locateInFinalPath)}</button>
          </li>`).join("")}
        </ul>
      </details>`
    : "";

  const feedbackBanner = ui.error
    ? `<div class="project-refinement-notice is-error" role="alert" data-project-refinement-notice>
        <p>${escapeHtml(ui.error)}</p>
        <button type="button" class="button ghost project-refinement-locate" data-project-refinement-dismiss-notice>${escapeHtml(copy.dismissNotice)}</button>
      </div>`
    : ui.notice
      ? `<div class="project-refinement-notice" role="status" data-project-refinement-notice>
          <p>${escapeHtml(ui.notice)}</p>
          <button type="button" class="button ghost project-refinement-locate" data-project-refinement-dismiss-notice>${escapeHtml(copy.dismissNotice)}</button>
        </div>`
      : "";

  const copyFeedbackMarkup = ui.copyFeedback
    ? `<p class="muted project-refinement-copy-status" role="status">${escapeHtml(ui.copyFeedback)}</p>`
    : "";

  return `<section id="project-refinement" class="project-refinement" aria-labelledby="project-refinement-title" aria-busy="${inFlightForCurrentProject}">
    <header class="project-section-divider project-refinement-divider">
      <h3 id="project-refinement-title">${escapeHtml(copy.sectionTitle)}</h3>
      <button
        type="button"
        class="button project-icon-button project-refinement-import-btn"
        aria-label="${escapeAttr(importLabel)}" data-app-tooltip="${escapeAttr(importLabel)}"
        data-project-refinement-import
        ${busy ? "disabled" : ""}
      >${projectIcon("import")}</button>
    </header>
    ${feedbackBanner}
    ${copyFeedbackMarkup}
    ${rows.length ? `<div class="project-refinement-table-scroll"><table class="project-refinement-table" aria-labelledby="project-refinement-title" aria-describedby="project-refinement-table-note">
      <thead><tr>${copy.tableColumns.map((col) => `<th scope="col">${escapeHtml(col)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => versionTableRow(row, ui, copy, state?.locale)).join("")}</tbody>
    </table></div><p id="project-refinement-table-note" class="muted project-refinement-note">${escapeHtml(copy.tableHint)}</p>` : ""}
    ${autoDetails}
    ${manualImportedMarkup ? `<p class="muted project-refinement-note">${escapeHtml(copy.metricActiveManualEdits)}: ${model.manual.activeManualCount}</p>` : ""}
    ${manualImportedMarkup}
    ${manualBatchesMarkup}
    ${manualDraftMarkup}
    ${!manualImportedMarkup && !manualBatchesMarkup && !manualDraftMarkup && !model.auto.effects.length && !model.auto.segments.length ? `<p class="muted project-refinement-note">${escapeHtml(copy.manualEmptyNote)}</p>` : ""}
  </section>`;
}

export function bindProjectRefinementCard(host, store, rerender, deps = {}) {
  if (typeof host?.addEventListener !== "function" || host[PROJECT_REFINEMENT_BOUND]) {
    return;
  }
  host.addEventListener("click", (event) => {
    const preview = event.target?.closest?.("[data-preview-version]");
    if (preview) { void toggleVersionPreview(host, store, preview, rerender, deps); return; }
    const importBtn = event.target?.closest?.("[data-project-refinement-import]");
    if (importBtn) {
      void runImportManualRefinementResults(host, store, rerender, deps);
      return;
    }

    const undoBtn = event.target?.closest?.("[data-project-refinement-undo]");
    if (undoBtn) {
      void runUndoManualRefinementLocus(
        host,
        store,
        {
          locusId: undoBtn.dataset.locusId,
          chr: undoBtn.dataset.locusChr,
          expectedRevision: undoBtn.dataset.expectedRevision,
        },
        rerender,
        deps,
      );
      return;
    }

    const switchBtn = event.target?.closest?.("[data-project-refinement-switch]");
    if (switchBtn) {
      void runSwitchManualRefinementLocus(
        host,
        store,
        {
          locusId: switchBtn.dataset.locusId,
          chr: switchBtn.dataset.locusChr,
          expectedRevision: switchBtn.dataset.expectedRevision,
          resultSha256: switchBtn.dataset.resultSha256,
          tool: switchBtn.dataset.tool,
        },
        rerender,
        deps,
      );
      return;
    }

    const dismissBtn = event.target?.closest?.("[data-project-refinement-dismiss-notice]");
    if (dismissBtn) {
      setRefinementUi(store, { notice: "", error: "" });
      rerender?.(host, store);
      return;
    }

    const copyBtn = event.target?.closest?.("[data-project-refinement-copy]");
    if (copyBtn) {
      const cmd = normalizeString(copyBtn.dataset.projectRefinementCopy);
      if (!cmd) return;
      const copy = COPY[store.getState()?.locale === "en" ? "en" : "zh"];
      void globalThis.navigator?.clipboard?.writeText?.(cmd).then(() => {
        setRefinementUi(store, { copyFeedback: `${copy.copiedCommand}: ${cmd}` });
        rerender?.(host, store);
      }).catch(() => {});
      return;
    }

    const locateBtn = event.target?.closest?.("[data-project-refinement-locate-chr]");
    if (locateBtn) {
      const chrName = normalizeString(locateBtn.dataset.projectRefinementLocateChr);
      const locateSegmentId = normalizeString(locateBtn.dataset.projectRefinementLocateSegmentId);
      if (!chrName) return;
      const state = store.getState();
      store.setState({
        activeRoute: "assembly",
        assembly: {
          ...state.assembly,
          activeTab: "assembly",
          previewRequestedChrName: chrName,
          ...(locateSegmentId ? { previewRequestedFinalPathSegmentId: locateSegmentId } : {}),
          projectExportScrollToBottom: true,
        },
      });
      globalThis.window?.dispatchEvent?.(new Event("gpm-next:route-refresh"));
    }
  });
  host[PROJECT_REFINEMENT_BOUND] = true;
}
