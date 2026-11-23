import { projectIcon } from "./project-icons.js";
import { pickZipFilePath } from "../../services/backend-api.js";
import {
  getGrtProjectView,
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
    importAction: "导入精修补丁",
    autoPatchImported: "已加入自动精修结果：{tools}。当前工作路径未改变。",
    autoPatchDuplicate: "这些自动精修结果已在项目中，未重复导入。",
    tableColumns: ["来源 / 批次", "工具", "填补 / 总数", "涉及 Chr", ""],
    importingAction: "正在导入精修结果...",
    workingAction: "正在更新精修状态...",
    dismissNotice: "关闭",
    autoTitle: "自动精修",
    manualTitle: "手动精修",
    pendingTag: "待导回",
    legacyTag: "旧版候选",
    manageBatch: "管理",
    emptyNote: "暂无精修记录，可点击右上角导入精修补丁。",
    locateInFinalPath: "定位",
    copyCommand: "复制命令",
    copiedCommand: "已复制命令",
    undoLocus: "撤销",
    switchToTool: "切换 {tool}",
    adoptTool: "采用 {tool}",
    activeBadge: "生效中",
    undoneBadge: "已撤销",
    legacyCandidateBadge: "旧版候选 · 未应用",
    kindGap: "Gap",
    kindTelLeft: "左端粒",
    kindTelRight: "右端粒",
    kindLegacy: "旧版",
    importDuplicateMsg: "该精修结果包（{sha}）已导入过，未重复修改 Final Path。",
    importAppliedMsg: "已导回并应用 {applied} 个精修位点（涉及染色体：{chrs}），已重新载入权威装配与预览数据。",
    importLegacyOnlyMsg: "已识别旧版 degap_results.zip（{sha}），仅记录旧版候选（未创建轨道、未修改 Final Path）。",
    importNoApplyMsg: "已导回结果包（{sha}），本次应用 0 个位点，可展开对应批次查看详情。",
    undoSuccessMsg: "已撤销 {chr} 位点 {locusId} 的手动精修（版本 r{rev}）。",
    switchSuccessMsg: "已将 {chr} 位点 {locusId} 切换为 {tool}（版本 r{rev}）。",
    noProjectError: "请先选择有效项目后再操作。",
    equivalentPrefix: "等价",
    activeToolPrefix: "当前",
    patchLengthPrefix: "长度",
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
      ambiguous: "待选择",
      undone: "已撤销",
      legacy_candidate_only: "旧版候选 · 未应用",
    },
  },
  en: {
    sectionTitle: "Refinement",
    importAction: "Import refinement patch",
    autoPatchImported: "Added automatic results: {tools}. The working path has not changed.",
    autoPatchDuplicate: "These automatic results are already in this project.",
    tableColumns: ["Source / Batch", "Tool", "Filled / Total", "Chr", ""],
    importingAction: "Importing refinement results...",
    workingAction: "Updating refinement state...",
    dismissNotice: "Dismiss",
    autoTitle: "Automatic",
    manualTitle: "Manual",
    pendingTag: "Pending",
    legacyTag: "Legacy",
    manageBatch: "Manage",
    emptyNote: "No refinement records yet. Click the import icon above to import refinement patches.",
    locateInFinalPath: "Locate",
    copyCommand: "Copy cmd",
    copiedCommand: "Copied",
    undoLocus: "Undo",
    switchToTool: "Use {tool}",
    adoptTool: "Adopt {tool}",
    activeBadge: "Active",
    undoneBadge: "Undone",
    legacyCandidateBadge: "Legacy · Not applied",
    kindGap: "Gap",
    kindTelLeft: "Left Tel",
    kindTelRight: "Right Tel",
    kindLegacy: "Legacy",
    importDuplicateMsg: "Refinement result archive ({sha}) was already imported; Final Path was not modified again.",
    importAppliedMsg: "Imported and applied {applied} locus edit(s) on {chrs}; reloaded authoritative Assembly and Preview data.",
    importLegacyOnlyMsg: "Recognized legacy degap_results.zip ({sha}); recorded legacy candidates only (no tracks created, Final Path unchanged).",
    importNoApplyMsg: "Imported result archive ({sha}) with 0 applied loci; expand the batch to inspect details.",
    undoSuccessMsg: "Undid manual refinement on {chr} locus {locusId} (rev {rev}).",
    switchSuccessMsg: "Switched {chr} locus {locusId} to {tool} (rev {rev}).",
    noProjectError: "Select an active project first.",
    equivalentPrefix: "Equivalent",
    activeToolPrefix: "Active",
    patchLengthPrefix: "Length",
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
      legacy_candidate_only: "Legacy · Not applied",
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
      notice = rawResult.duplicate ? copy.autoPatchDuplicate : fmt(copy.autoPatchImported, { tools: formatTools(rawResult.addedTools) });
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

function buildRefinementOverviewGroups({ auto, manual }, copy) {
  const groups = [];
  const autoChrByTool = new Map();
  const autoSegCountByTool = new Map();
  for (const segment of auto.segments) {
    const toolKey = normalizeString(segment.tool).toLowerCase() || "unknown";
    if (!autoChrByTool.has(toolKey)) autoChrByTool.set(toolKey, new Set());
    if (segment.chrName) autoChrByTool.get(toolKey).add(segment.chrName);
    autoSegCountByTool.set(toolKey, (autoSegCountByTool.get(toolKey) || 0) + 1);
  }

  const autoRows = [];
  const reportedTools = new Set();
  for (const effect of auto.effects) {
    const toolKey = normalizeString(effect.tool).toLowerCase();
    reportedTools.add(toolKey);
    const filled = normalizeNonNegativeIntOrNull(effect.accepted_edits ?? effect.acceptedEdits ?? effect.closed);
    const explicitTotal = normalizeNonNegativeIntOrNull(effect.original_gaps ?? effect.originalGaps);
    const summedTotal = [effect.closed, effect.partial, effect.unfilled, effect.rejected]
      .every((v) => normalizeNonNegativeIntOrNull(v) !== null)
      ? Number(effect.closed) + Number(effect.partial) + Number(effect.unfilled) + Number(effect.rejected)
      : null;
    const total = explicitTotal ?? summedTotal;
    const chrSet = autoChrByTool.get(toolKey);
    const explicitChrCount = normalizeNonNegativeIntOrNull(effect.chromosome_count ?? effect.chromosomeCount);
    const chrCount = explicitChrCount
      ?? (chrSet && chrSet.size > 0 ? chrSet.size : (auto.effects.length === 1 && auto.chromosomeCount > 0 ? auto.chromosomeCount : (filled === 0 ? 0 : null)));
    autoRows.push({
      tool: formatToolLabel(effect.tool) || "—",
      filled,
      total,
      chrCount,
    });
  }
  for (const [toolKey, count] of autoSegCountByTool.entries()) {
    if (reportedTools.has(toolKey)) continue;
    autoRows.push({
      tool: toolKey === "unknown" ? "—" : formatToolLabel(toolKey),
      filled: count,
      total: null,
      chrCount: autoChrByTool.get(toolKey)?.size ?? null,
    });
  }
  if (autoRows.length) {
    groups.push({
      key: "auto",
      kind: "auto",
      headerTitle: copy.autoTitle,
      batchShort: "",
      tag: "",
      rows: autoRows,
    });
  }

  for (const batch of manual.importedResults) {
    const batchKey = `imported:${batch.batchSha256 || batch.resultSha256}`;
    const shortId = (batch.batchSha256 || batch.resultSha256 || "").slice(0, 6);
    const toolStats = new Map();
    const ensureTool = (toolKey) => {
      if (!toolStats.has(toolKey)) {
        toolStats.set(toolKey, { total: 0, filled: 0, filledChrs: new Set(), allChrs: new Set() });
      }
      return toolStats.get(toolKey);
    };
    for (const locus of batch.loci) {
      if (locus.isLegacy) {
        const legacyTools = locus.candidates.length ? locus.candidates.map((c) => c.tool) : ["degap"];
        for (const toolKey of new Set(legacyTools)) {
          const stat = ensureTool(toolKey);
          stat.total += 1;
          if (locus.chr) stat.allChrs.add(locus.chr);
        }
        continue;
      }
      for (const candidate of locus.candidates) {
        const stat = ensureTool(candidate.tool);
        stat.total += 1;
        if (locus.chr) stat.allChrs.add(locus.chr);
        if (candidate.status === "closed" || candidate.status === "extended" || candidate.status === "partial") {
          stat.filled += 1;
          if (locus.chr) stat.filledChrs.add(locus.chr);
        }
      }
    }
    const manualRows = [];
    for (const [toolKey, stat] of toolStats.entries()) {
      manualRows.push({
        tool: formatToolLabel(toolKey) || "—",
        filled: batch.isLegacyOnly ? null : stat.filled,
        total: stat.total,
        chrCount: batch.isLegacyOnly
          ? stat.allChrs.size
          : (stat.filled > 0 ? stat.filledChrs.size : 0),
      });
    }
    if (!manualRows.length) {
      manualRows.push({
        tool: "—",
        filled: batch.applied,
        total: batch.loci.length || batch.applied,
        chrCount: batch.changedChromosomes.length,
      });
    }
    groups.push({
      key: batchKey,
      kind: "manual-imported",
      headerTitle: copy.manualTitle,
      batchShort: shortId ? `#${shortId}` : "",
      tag: batch.isLegacyOnly ? copy.legacyTag : "",
      batch,
      rows: manualRows,
    });
  }

  for (const batch of manual.exportedBatches) {
    const batchKey = `pending:${batch.batchSha256}`;
    const shortId = (batch.batchSha256 || "").slice(0, 6);
    const toolStats = new Map();
    for (const locus of batch.loci) {
      for (const toolKey of locus.tools || []) {
        if (!toolStats.has(toolKey)) {
          toolStats.set(toolKey, { total: 0, chrs: new Set() });
        }
        const stat = toolStats.get(toolKey);
        stat.total += 1;
        if (locus.chr) stat.chrs.add(locus.chr);
      }
    }
    const pendingRows = [];
    for (const [toolKey, stat] of toolStats.entries()) {
      pendingRows.push({
        tool: formatToolLabel(toolKey) || "—",
        filled: null,
        total: stat.total,
        chrCount: stat.chrs.size,
      });
    }
    if (!pendingRows.length) {
      pendingRows.push({
        tool: "—",
        filled: null,
        total: batch.lociCount || null,
        chrCount: null,
      });
    }
    groups.push({
      key: batchKey,
      kind: "manual-pending",
      headerTitle: copy.manualTitle,
      batchShort: shortId ? `#${shortId}` : "",
      tag: copy.pendingTag,
      batch,
      command: buildManualRefinementServerCommand(batch.outputPath || batch.outputFileName),
      rows: pendingRows,
    });
  }

  return groups;
}

function renderRatioCell({ filled, total }) {
  const hasFilled = filled !== null && filled !== undefined;
  const hasTotal = total !== null && total !== undefined;
  if (!hasFilled && !hasTotal) {
    return `<span class="muted">—</span>`;
  }
  const text = `${hasFilled ? filled : "—"} / ${hasTotal ? total : "—"}`;
  const pct = hasFilled && hasTotal && total > 0 ? Math.min(100, Math.round((filled / total) * 100)) : 0;
  return `<div class="project-refinement-ratio">
    <span class="project-refinement-ratio-text">${escapeHtml(text)}</span>
    ${hasFilled && hasTotal && total > 0
      ? `<span class="project-refinement-bar" aria-hidden="true"><span class="project-refinement-bar-fill" style="width:${pct}%"></span></span>`
      : ""}
  </div>`;
}

export function renderProjectRefinementCard(state) {
  const copy = COPY[state?.locale === "en" ? "en" : "zh"];
  const model = buildProjectRefinementModel(state);
  const ui = readScopedRefinementUi(state);
  const inFlightForCurrentProject = Boolean(ui.inFlight);
  const busy = Boolean(state?.importer?.inFlight || state?.initializer?.autoPipelineRunning || inFlightForCurrentProject);
  const expandedBatchKey = normalizeString(ui.expandedBatchKey);

  const groups = buildRefinementOverviewGroups(model, copy);
  const rowCount = groups.reduce((sum, group) => sum + group.rows.length, 0);
  const formattedRowCount = rowCount.toLocaleString(state?.locale === "en" ? "en-US" : "zh-CN");
  const importLabel = inFlightForCurrentProject ? (ui.busyLabel || copy.importingAction) : copy.importAction;

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

  const tbodyMarkup = groups.map((group, groupIndex) => {
    const rowSpan = group.rows.length;
    const isExpanded = group.kind === "manual-imported" && expandedBatchKey === group.key;
    const hasDetailRow = isExpanded && Boolean(group.batch?.loci?.length);
    const spanEndClass = groupIndex === groups.length - 1 && !hasDetailRow ? " is-last-row-span" : "";
    const groupHeaderCell = `<td class="project-refinement-group-cell${spanEndClass}" rowspan="${rowSpan}">
      <div class="project-refinement-group-label">
        <span class="project-refinement-group-title">${escapeHtml(group.headerTitle)}</span>
        ${group.batchShort ? `<code class="project-refinement-batch-id">${escapeHtml(group.batchShort)}</code>` : ""}
        ${group.tag ? `<span class="project-refinement-badge ${group.kind === "manual-pending" ? "is-warn" : "is-neutral"}">${escapeHtml(group.tag)}</span>` : ""}
      </div>
    </td>`;
    const actionCell = group.kind === "manual-imported" && group.batch?.loci?.length
      ? `<td class="project-refinement-action-cell${spanEndClass}" rowspan="${rowSpan}">
          <button
            type="button"
            class="button ghost project-refinement-locate"
            data-project-refinement-toggle-batch="${escapeAttr(group.key)}"
            aria-expanded="${isExpanded ? "true" : "false"}"
          >${escapeHtml(copy.manageBatch)} ${isExpanded ? "▴" : "▾"}</button>
        </td>`
      : group.kind === "manual-pending" && group.command
        ? `<td class="project-refinement-action-cell${spanEndClass}" rowspan="${rowSpan}">
            <button
              type="button"
              class="button ghost project-refinement-locate"
              data-project-refinement-copy="${escapeAttr(group.command)}"
              data-app-tooltip="${escapeAttr(group.command)}"
            >${escapeHtml(copy.copyCommand)}</button>
          </td>`
        : `<td class="project-refinement-action-cell${spanEndClass}" rowspan="${rowSpan}"></td>`;

    const toolRowsHtml = group.rows.map((row, idx) => `<tr class="project-refinement-row${idx === 0 ? " is-group-start" : ""}">
      ${idx === 0 ? groupHeaderCell : ""}
      <th scope="row" class="project-refinement-tool-cell">${escapeHtml(row.tool)}</th>
      <td class="project-refinement-ratio-cell numeric">${renderRatioCell(row)}</td>
      <td class="project-refinement-chr-cell numeric">${escapeHtml(row.chrCount !== null && row.chrCount !== undefined ? String(row.chrCount) : "—")}</td>
      ${idx === 0 ? actionCell : ""}
    </tr>`).join("");

    const detailRowHtml = hasDetailRow
      ? `<tr class="project-refinement-detail-row" data-project-refinement-batch-detail="${escapeAttr(group.key)}">
          <td colspan="5">
            <ul class="project-refinement-sublist">
              ${group.batch.loci.map((locus) => renderImportedLocusRow(group.batch, locus, copy, busy)).join("")}
            </ul>
          </td>
        </tr>`
      : "";

    return `${toolRowsHtml}${detailRowHtml}`;
  }).join("");

  return `<section id="project-refinement" class="project-refinement" aria-labelledby="project-refinement-title" aria-busy="${inFlightForCurrentProject}">
    <header class="project-section-divider project-refinement-divider">
      <h3 id="project-refinement-title">${escapeHtml(copy.sectionTitle)}</h3>
      <span class="project-section-count"><span aria-hidden="true">·</span>${escapeHtml(formattedRowCount)}</span>
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
    ${groups.length
      ? `<div class="project-refinement-table-scroll" tabindex="0" role="region" aria-label="${escapeAttr(copy.sectionTitle)}"><table class="project-refinement-table" aria-labelledby="project-refinement-title">
          <thead><tr>${copy.tableColumns.map((col) => `<th scope="col">${escapeHtml(col)}</th>`).join("")}</tr></thead>
          <tbody>${tbodyMarkup}</tbody>
        </table></div>`
      : `<p class="muted project-refinement-note">${escapeHtml(copy.emptyNote)}</p>`}
  </section>`;
}

export function bindProjectRefinementCard(host, store, rerender, deps = {}) {
  if (typeof host?.addEventListener !== "function" || host[PROJECT_REFINEMENT_BOUND]) {
    return;
  }
  host.addEventListener("click", (event) => {
    const toggleBatchBtn = event.target?.closest?.("[data-project-refinement-toggle-batch]");
    if (toggleBatchBtn) {
      const key = normalizeString(toggleBatchBtn.dataset.projectRefinementToggleBatch);
      const currentKey = normalizeString(readScopedRefinementUi(store.getState()).expandedBatchKey);
      setRefinementUi(store, { expandedBatchKey: currentKey === key ? "" : key });
      rerender?.(host, store);
      return;
    }

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
