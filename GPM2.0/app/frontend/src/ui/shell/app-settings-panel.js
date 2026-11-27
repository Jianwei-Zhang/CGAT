import { bindShellSelects, renderShellSelect } from "./shell-select-runtime.js";
import { buildDiagnosticSummary, renderUpdateSettings } from "./app-update-panel.js";
import { requestAppConfirm } from "./app-dialog.js";
import { clearSkippedConfirmations, skippedConfirmationCount } from "./confirmation-session.js";
import {
  DEFAULT_APP_SETTINGS,
  getAppliedAppTheme,
  getAppSettings,
  resetAppLayoutPreferences,
  setAppSettings,
} from "../../services/app-settings.js";
import {
  DEFAULT_TRACK_BASE_COLORS,
  DEFAULT_TRACK_COLOR_OVERRIDES,
  TRACK_COLOR_KEYS,
  TRACK_COLOR_PRESETS,
  applyTrackColorVariables,
  detectTrackColorPreset,
  hasCustomTrackColors,
  normalizeHexColor,
  normalizeTrackColors,
  resolveEffectiveTrackBaseColors,
} from "../../services/track-colors.js";
import { importParserWorkerChoices, recommendedImportParserWorkers } from "../../services/import-parallelism.js";

export const SETTINGS_TABS = Object.freeze(["general", "appearance", "editing", "updates"]);
const HISTORY_PRESETS = Object.freeze([0, 50, 100, 200]);

export const APP_SETTINGS_COPY = {
  zh: {
    title: "App 设置",
    close: "关闭",
    categories: "设置分类",
    general: "常规",
    generalDesc: "语言、启动行为与新项目导入默认偏好。",
    generalStartupGroup: "语言与启动",
    generalWorkspaceGroup: "导入与工作区",
    language: "界面语言",
    languageDesc: "立即切换菜单、标签与弹窗语言。",
    restoreLastWorkspace: "启动时自动恢复上次组装",
    restoreLastWorkspaceDesc: "打开 App 时自动载入上次关闭前的组装工作区；关闭后始终进入首页列表。",
    defaultWorkspaceRoot: "默认新建工作区目录",
    defaultWorkspaceRootDesc: "导入压缩包或复制组装时默认存放到该目录；留空则沿用源包所在目录。",
    defaultWorkspacePlaceholder: "默认跟随源交付包所在目录",
    browse: "浏览",
    clear: "清除",
    importParallelism: "默认并行导入线程",
    importParallelismDesc: "导入交付包解压与 PAF 解析时的默认并发数，单次导入仍可调整。",
    importParallelismAuto: "自动（推荐 {number} 线程）",
    importThreadsUnit: "{number} 线程",
    display: "外观",
    displayDesc: "配色主题、字号排版与界面面板布局。",
    themeGroup: "配色主题",
    themeDesc: "切换明暗配色；独立图表导出仍保持浅色出版画布。",
    theme: "主题",
    system: "跟随系统",
    light: "浅色",
    dark: "深色",
    trackColorsGroup: "轨道与条带配色",
    trackColorsDesc: "选择各条带主色，系统自动派生描边、高对比文字与深色模式适配色；共线性比对带自动跟随轨道色相，图表导出同步生效。",
    trackColorsResetAll: "恢复默认配色",
    trackColorsResetOne: "恢复此项默认颜色",
    trackPresetDefault: "默认经典",
    trackPresetOkabe: "色盲友好",
    trackPresetNature: "学术出版",
    trackPresetVivid: "高对比度",
    trackColorPrimary: "主组装",
    trackColorCompanion: "辅助组装",
    trackColorRef: "参考基因组",
    trackColorSelection: "选中高亮",
    trackColorGrt: "GRT 叠加层",
    trackPreviewLabel: "条带与比对带预览",
    typography: "文字与图内排版",
    size: "界面字号",
    sizeDesc: "控制菜单、列表、按钮与弹窗正文大小。",
    graph: "图内字号",
    graphDesc: "控制 Contig 名称与标尺刻度文字大小。",
    follow: "跟随界面",
    previewTitle: "实时排版预览",
    previewHeading: "装配视图 · Chr01",
    previewBody: "正文标签与工具栏控件示例",
    previewHint: "说明文字与次级提示",
    button: "操作按钮",
    smallButton: "小按钮",
    layoutGroup: "界面布局",
    resetLayoutTitle: "侧边栏与浮动工具箱布局",
    resetLayoutDesc: "恢复首页项目库默认宽度，并重置局部视图浮动工具箱的位置与尺寸。",
    resetLayoutButton: "恢复默认布局",
    layoutResetDone: "已恢复默认面板布局",
    history: "编辑与视图",
    historyDesc: "配置撤销回溯容量、局部视图窗口行为与安全确认策略。",
    historyGroup: "撤销与回溯",
    capacity: "回溯容量",
    capacityDesc: "主视图和局部视图分别计数。降低容量后，下次新增编辑时裁剪旧记录；不限步数可能增加读写耗时。",
    unlimited: "不限步数",
    steps: "步",
    customSteps: "自定义步数",
    localViewGroup: "局部视图窗口",
    localViewDefaultMode: "默认打开方式",
    localViewDefaultModeDesc: "新建局部比对任务时默认停靠在底部，或直接以独立浮动窗口打开。",
    docked: "底部停靠",
    floating: "独立窗口",
    localViewDefaultPinned: "独立窗口默认置顶",
    localViewDefaultPinnedDesc: "保持独立局部视图窗口浮在主窗口上方，避免点击主图时被遮挡。",
    safetyGroup: "操作安全与确认",
    deleteHotkey: "Delete 键快捷删除选中 Contig",
    deleteHotkeyDesc: "在装配轨道中按 Delete 键快速删除已选 Contig（按 Esc 可取消框选）。",
    confirmationsTitle: "已跳过的操作确认提示",
    confirmationsNone: "本次运行尚未跳过任何确认弹窗。",
    confirmationsCount: "本次运行已跳过 {count} 项操作确认提示。",
    restoreConfirmations: "恢复全部",
    confirmationsRestored: "已恢复所有操作确认提示",
    updates: "更新与关于",
    updateAvailableBadge: "有可用更新",
    diagnosticsCopied: "已复制诊断信息到剪贴板",
    diagnosticsCopyFailed: "复制失败，请检查剪贴板权限。",
    snoozeCleared: "已恢复更新提醒",
    reset: "恢复默认设置",
    invalid: "请输入 1–1000000 的整数，或选择不限步数。",
    failed: "保存失败，请检查本机存储。",
    restoreConfirm: "确定恢复所有本机默认设置？界面语言将保持不变，回溯容量将恢复为不限步数。",
    scope: "本机设置 · 自动保存",
    applied: "已保存",
  },
  en: {
    title: "App Settings",
    close: "Close",
    categories: "Settings Categories",
    general: "General",
    generalDesc: "Language, startup behavior, and default import preferences.",
    generalStartupGroup: "Language & Startup",
    generalWorkspaceGroup: "Import & Workspace",
    language: "Language",
    languageDesc: "Applies immediately to menus, labels, and dialogs.",
    restoreLastWorkspace: "Reopen last assembly on launch",
    restoreLastWorkspaceDesc: "Automatically restore your previous workspace when opening the App.",
    defaultWorkspaceRoot: "Default workspace folder",
    defaultWorkspaceRootDesc: "Suggested parent folder for archive imports and copies; leave blank to follow the source archive.",
    defaultWorkspacePlaceholder: "Follow source archive folder",
    browse: "Browse",
    clear: "Clear",
    importParallelism: "Default import workers",
    importParallelismDesc: "Default concurrency for archive extraction and PAF parsing; can still be adjusted per import.",
    importParallelismAuto: "Auto (Recommended {number})",
    importThreadsUnit: "{number} workers",
    display: "Appearance",
    displayDesc: "Color theme, typography scale, and interface panel layout.",
    themeGroup: "Color Theme",
    themeDesc: "Switch interface appearance; standalone figure exports always use a light publication canvas.",
    theme: "Theme",
    system: "Follow System",
    light: "Light",
    dark: "Dark",
    trackColorsGroup: "Track & Strip Colors",
    trackColorsDesc: "Pick one base color per role; borders, high-contrast ink, and dark-mode tones derive automatically. Collinearity ribbons follow track hues and apply to figure exports.",
    trackColorsResetAll: "Reset colors",
    trackColorsResetOne: "Reset to default color",
    trackPresetDefault: "Classic",
    trackPresetOkabe: "Colorblind Safe",
    trackPresetNature: "Academic (NPG)",
    trackPresetVivid: "High Contrast",
    trackColorPrimary: "Primary",
    trackColorCompanion: "Auxiliary",
    trackColorRef: "Reference",
    trackColorSelection: "Selection",
    trackColorGrt: "GRT Overlay",
    trackPreviewLabel: "Track & Ribbon Preview",
    typography: "Typography",
    size: "Interface text",
    sizeDesc: "Controls menus, lists, buttons, and body labels.",
    graph: "Graph text",
    graphDesc: "Controls contig labels and ruler tick labels inside plots.",
    follow: "Follow Interface",
    previewTitle: "Live Typography Preview",
    previewHeading: "Assembly View · Chr01",
    previewBody: "Body text and toolbar control labels",
    previewHint: "Secondary helper text and hints",
    button: "Action",
    smallButton: "Compact",
    layoutGroup: "Panel Layout",
    resetLayoutTitle: "Sidebar & floating tools layout",
    resetLayoutDesc: "Restore the default project library width and Local View tools window position.",
    resetLayoutButton: "Reset layout",
    layoutResetDone: "Panel layout reset to defaults",
    history: "Editing & Views",
    historyDesc: "Configure undo history capacity, Local View windows, and safety prompts.",
    historyGroup: "Undo & History",
    capacity: "History capacity",
    capacityDesc: "Counted separately for main and local views. Lower limits trim old entries on the next edit; unlimited may slow saves.",
    unlimited: "Unlimited",
    steps: "steps",
    customSteps: "Custom",
    localViewGroup: "Local View Windows",
    localViewDefaultMode: "Default open mode",
    localViewDefaultModeDesc: "Open new Local View comparisons docked below or directly in a floating window.",
    docked: "Docked",
    floating: "Floating",
    localViewDefaultPinned: "Pin floating windows above Main",
    localViewDefaultPinnedDesc: "Keep floating Local View windows above the Main window while inspecting tracks.",
    safetyGroup: "Safety & Confirmations",
    deleteHotkey: "Delete key removes selected contigs",
    deleteHotkeyDesc: "Allow pressing Delete in assembly tracks to delete selected contigs (Esc clears selection).",
    confirmationsTitle: "Skipped confirmation prompts",
    confirmationsNone: "No confirmation prompts skipped during this session.",
    confirmationsCount: "{count} confirmation prompt(s) skipped during this session.",
    restoreConfirmations: "Restore all",
    confirmationsRestored: "All confirmation prompts restored",
    updates: "Updates & About",
    updateAvailableBadge: "Update available",
    diagnosticsCopied: "Diagnostic info copied to clipboard",
    diagnosticsCopyFailed: "Could not copy diagnostic info.",
    snoozeCleared: "Update reminders resumed",
    reset: "Restore defaults",
    invalid: "Enter a whole number from 1 to 1000000, or choose Unlimited.",
    failed: "Could not save. Check local storage.",
    restoreConfirm: "Restore all local preferences to defaults? Display language stays unchanged and history capacity returns to unlimited.",
    scope: "This computer · Auto-save",
    applied: "Saved",
  },
};

const TAB_ICONS = {
  general: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a13.5 13.5 0 0 1 0 18"/><path d="M12 3a13.5 13.5 0 0 0 0 18"/></svg>`,
  appearance: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`,
  editing: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></svg>`,
  updates: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>`,
};

const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function renderSegmented(name, ariaLabel, options, extraClass = "") {
  const cls = extraClass ? `settings-segmented ${extraClass}` : "settings-segmented";
  return `<div class="${cls}" role="radiogroup" aria-label="${escapeHtml(ariaLabel)}" data-settings-radiogroup="${escapeHtml(name)}">${options.map(option => {
    const active = Boolean(option.selected);
    return `<button type="button" role="radio" class="settings-seg-btn${active ? " is-active" : ""}" data-settings-radio="${escapeHtml(name)}" data-settings-value="${escapeHtml(option.value)}" aria-checked="${active}" tabindex="${active ? "0" : "-1"}">${escapeHtml(option.label)}</button>`;
  }).join("")}</div>`;
}

function renderSwitch(id, name, checked) {
  return `<label class="settings-switch"><input id="${escapeHtml(id)}" type="checkbox" role="switch" name="${escapeHtml(name)}"${checked ? " checked" : ""}><span class="settings-switch-track" aria-hidden="true"></span></label>`;
}

function renderThemeCards(c, selectedTheme) {
  const items = [
    { value: "system", label: c.system, previewClass: "is-system" },
    { value: "light", label: c.light, previewClass: "is-light" },
    { value: "dark", label: c.dark, previewClass: "is-dark" },
  ];
  return `<div class="settings-theme-cards" role="radiogroup" aria-label="${escapeHtml(c.theme)}" data-settings-radiogroup="theme">${items.map(item => {
    const active = item.value === (selectedTheme || "system");
    return `<button type="button" role="radio" class="settings-theme-card${active ? " is-active" : ""}" data-settings-radio="theme" data-settings-value="${item.value}" aria-checked="${active}" tabindex="${active ? "0" : "-1"}">
      <span class="settings-theme-swatch ${item.previewClass}" aria-hidden="true">
        <span class="settings-theme-swatch-bar"></span>
        <span class="settings-theme-swatch-lines"><i></i><i></i></span>
      </span>
      <span class="settings-theme-card-label">${escapeHtml(item.label)}</span>
    </button>`;
  }).join("")}</div>`;
}

function renderTrackColorsGroup(copy, trackColors) {
  const normalized = normalizeTrackColors(trackColors);
  const effective = resolveEffectiveTrackBaseColors(normalized);
  const activePreset = detectTrackColorPreset(normalized);
  const hasCustom = hasCustomTrackColors(normalized);
  const presetLabels = {
    default: copy.trackPresetDefault,
    okabe: copy.trackPresetOkabe,
    nature: copy.trackPresetNature,
    vivid: copy.trackPresetVivid,
  };
  const roleLabels = {
    primary: copy.trackColorPrimary,
    companion: copy.trackColorCompanion,
    ref: copy.trackColorRef,
    selection: copy.trackColorSelection,
    grt: copy.trackColorGrt,
  };
  const presetsHtml = TRACK_COLOR_PRESETS.map(preset => {
    const active = activePreset === preset.id;
    const dots = preset.swatches.map(color => `<i style="background:${color}"></i>`).join("");
    return `<button type="button" class="settings-palette-preset${active ? " is-active" : ""}" data-settings-track-preset="${preset.id}" aria-pressed="${active}">
      <span class="settings-palette-dots" aria-hidden="true">${dots}</span>
      <span>${escapeHtml(presetLabels[preset.id] || preset.id)}</span>
    </button>`;
  }).join("");

  const pickersHtml = TRACK_COLOR_KEYS.map(key => {
    const label = roleLabels[key] || key;
    const hex = effective[key];
    const isCustom = normalized[key] !== null;
    return `<div class="settings-color-item${isCustom ? " is-custom" : ""}" data-settings-color-item="${key}">
      <label class="settings-color-swatch-wrap" for="settings-track-color-${key}">
        <input id="settings-track-color-${key}" class="settings-color-input" type="color" name="trackColor:${key}" data-settings-track-color="${key}" value="${hex}" aria-label="${escapeHtml(label)}">
        <span class="settings-color-meta">
          <span class="settings-color-label">${escapeHtml(label)}</span>
          <code class="settings-color-hex" data-settings-track-color-hex="${key}">${hex.toUpperCase()}</code>
        </span>
      </label>
      <button type="button" class="settings-color-reset" data-settings-track-color-reset="${key}" aria-label="${escapeHtml(`${copy.trackColorsResetOne}: ${label}`)}" data-app-tooltip="${escapeHtml(copy.trackColorsResetOne)}"${isCustom ? "" : " disabled"}>↺</button>
    </div>`;
  }).join("");

  return `<div class="settings-group">
    <div class="settings-group-head">
      <h4 class="settings-group-title">${copy.trackColorsGroup}</h4>
      <button type="button" class="settings-group-action" data-settings-reset-track-colors${hasCustom ? "" : " disabled"}>${copy.trackColorsResetAll}</button>
    </div>
    <p class="settings-group-desc">${copy.trackColorsDesc}</p>
    <div class="settings-palette-presets" role="group" aria-label="${escapeHtml(copy.trackColorsGroup)}">${presetsHtml}</div>
    <div class="settings-color-grid">${pickersHtml}</div>
    <div class="settings-track-preview" aria-label="${escapeHtml(copy.trackPreviewLabel)}">
      <svg viewBox="0 0 420 76" role="img" aria-label="${escapeHtml(copy.trackPreviewLabel)}">
        <rect x="6" y="6" width="408" height="10" rx="3" fill="var(--ctg-ref-fill)" stroke="var(--ctg-ref-stroke)" stroke-width="1"/>
        <text x="12" y="13.5" font-size="8.5" font-weight="600" fill="var(--ctg-ref-text)">Ref · Chr01</text>
        <path d="M 18 16 L 196 16 L 188 38 L 12 38 Z" fill="var(--alignment-legend-primary-high)"/>
        <path d="M 214 16 L 368 16 L 358 38 L 206 38 Z" fill="var(--alignment-legend-companion-high)"/>
        <rect x="12" y="38" width="176" height="15" rx="2.5" fill="var(--ctg-primary-fill)" stroke="var(--ctg-primary-stroke)" stroke-width="1"/>
        <text x="18" y="48.5" font-size="9.5" font-weight="600" fill="var(--ctg-primary-text)">primary_ctg1</text>
        <rect x="206" y="38" width="152" height="15" rx="2.5" fill="var(--ctg-companion-fill)" stroke="var(--ctg-companion-stroke)" stroke-width="1"/>
        <text x="212" y="48.5" font-size="9.5" font-weight="600" fill="var(--ctg-companion-text)">aux_ctg2</text>
        <rect x="12" y="38" width="176" height="15" rx="2.5" fill="var(--final-path-selection-fill)" stroke="var(--final-path-selection-stroke)" stroke-width="1.5"/>
        <rect x="366" y="38" width="46" height="15" rx="2.5" fill="var(--grt-result-fill, rgba(108, 143, 120, 0.38))" stroke="var(--grt-result-stroke, #718d79)" stroke-width="1"/>
        <text x="374" y="48.5" font-size="8.5" font-weight="600" fill="var(--text-primary)">GRT</text>
        <rect x="12" y="60" width="176" height="10" rx="2" fill="var(--ctg-primary-fill)" stroke="var(--final-path-selection-stroke)" stroke-width="1.4"/>
        <rect x="194" y="60" width="164" height="10" rx="2" fill="var(--ctg-companion-fill)" stroke="var(--ctg-companion-stroke)" stroke-width="1"/>
        <rect x="364" y="60" width="48" height="10" rx="2" fill="var(--ctg-ref-fill)" stroke="var(--ctg-ref-stroke)" stroke-width="1"/>
      </svg>
    </div>
  </div>`;
}

export function renderSettingsContent(locale, settings = getAppSettings(), activeTab = "general", context = {}) {
  const c = APP_SETTINGS_COPY[locale === "en" ? "en" : "zh"];
  const currentTab = SETTINGS_TABS.includes(activeTab) ? activeTab : "general";
  const capacity = settings.historyCapacity ?? 0;
  const isPresetCapacity = HISTORY_PRESETS.includes(capacity);
  const recommendedWorkers = recommendedImportParserWorkers();
  const workerOptions = [
    { value: "auto", label: c.importParallelismAuto.replace("{number}", recommendedWorkers), selected: (settings.importParallelism || "auto") === "auto" },
    ...importParserWorkerChoices().map(value => ({
      value,
      label: c.importThreadsUnit.replace("{number}", value),
      selected: String(settings.importParallelism || "auto") === value,
    })),
  ];
  const skippedCount = Number.isInteger(context.skippedConfirmations)
    ? context.skippedConfirmations
    : skippedConfirmationCount();
  const confirmationsDesc = skippedCount > 0
    ? c.confirmationsCount.replace("{count}", skippedCount)
    : c.confirmationsNone;

  const tabLabels = { general: c.general, appearance: c.display, editing: c.history, updates: c.updates };
  const nav = SETTINGS_TABS.map(id => {
    const active = id === currentTab;
    return `<button type="button" role="tab" id="settings-tab-${id}" class="settings-nav-item${active ? " is-active" : ""}" data-settings-tab="${id}" aria-selected="${active}" aria-controls="settings-panel-${id}" tabindex="${active ? "0" : "-1"}"><span class="settings-nav-icon" aria-hidden="true">${TAB_ICONS[id]}</span><span class="settings-nav-label">${tabLabels[id]}</span>${id === "updates" ? `<span class="settings-nav-dot" data-settings-update-dot hidden aria-label="${c.updateAvailableBadge}"></span>` : ""}</button>`;
  }).join("");

  return `<header class="settings-heading">
      <h2 id="app-settings-title">${c.title}</h2>
      <button type="button" class="settings-close" data-settings-close aria-label="${c.close}">×</button>
    </header>
    <div class="settings-body">
      <nav class="settings-nav" role="tablist" aria-label="${c.categories}" aria-orientation="vertical">${nav}</nav>
      <div class="settings-content">
        <section class="settings-section" role="tabpanel" id="settings-panel-general" data-settings-panel="general" aria-labelledby="settings-general-title"${currentTab !== "general" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-general-title">${c.general}</h3><p class="settings-panel-desc">${c.generalDesc}</p></header>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.generalStartupGroup}</h4>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.language}</span>
                <p class="settings-row-desc">${c.languageDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSegmented("language", c.language, [
                  { value: "zh", label: "中文", selected: locale !== "en" },
                  { value: "en", label: "English", selected: locale === "en" },
                ])}
              </div>
            </div>
            <div class="settings-row">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-restore-last-workspace">${c.restoreLastWorkspace}</label>
                <p class="settings-row-desc">${c.restoreLastWorkspaceDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSwitch("settings-restore-last-workspace", "restoreLastWorkspace", settings.restoreLastWorkspace !== false)}
              </div>
            </div>
          </div>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.generalWorkspaceGroup}</h4>
            <div class="settings-row settings-row-stacked">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-default-workspace-root">${c.defaultWorkspaceRoot}</label>
                <p class="settings-row-desc">${c.defaultWorkspaceRootDesc}</p>
              </div>
              <div class="settings-path-control">
                <input id="settings-default-workspace-root" class="settings-text-input" type="text" name="defaultWorkspaceRoot" value="${escapeHtml(settings.defaultWorkspaceRoot || "")}" placeholder="${escapeHtml(c.defaultWorkspacePlaceholder)}" autocomplete="off" spellcheck="false">
                <button type="button" class="button ghost tiny" data-settings-pick-workspace-root>${c.browse}</button>
                <button type="button" class="button ghost tiny" data-settings-clear-workspace-root${settings.defaultWorkspaceRoot ? "" : " disabled"}>${c.clear}</button>
              </div>
            </div>
            <div class="settings-row">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-import-parallelism-toggle">${c.importParallelism}</label>
                <p class="settings-row-desc">${c.importParallelismDesc}</p>
              </div>
              <div class="settings-row-control settings-row-control-select">
                ${renderShellSelect("settings-import-parallelism", c.importParallelism, workerOptions, { name: "importParallelism" })}
              </div>
            </div>
          </div>
        </section>

        <section class="settings-section" role="tabpanel" id="settings-panel-appearance" data-settings-panel="appearance" aria-labelledby="settings-appearance-title"${currentTab !== "appearance" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-appearance-title">${c.display}</h3><p class="settings-panel-desc">${c.displayDesc}</p></header>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.themeGroup}</h4>
            <p class="settings-group-desc">${c.themeDesc}</p>
            ${renderThemeCards(c, settings.theme)}
          </div>
          ${renderTrackColorsGroup(c, settings.trackColors)}
          <div class="settings-group">
            <h4 class="settings-group-title">${c.typography}</h4>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.size}</span>
                <p class="settings-row-desc">${c.sizeDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSegmented("fontSize", c.size, [12, 14, 16, 18].map(value => ({
                  value: String(value),
                  label: `${value}`,
                  selected: value === settings.fontSize,
                })), "is-compact")}
              </div>
            </div>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.graph}</span>
                <p class="settings-row-desc">${c.graphDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSegmented("graphFontSize", c.graph, [
                  { value: "", label: c.follow, selected: settings.graphFontSize === null },
                  ...[10, 12, 14, 16].map(value => ({
                    value: String(value),
                    label: `${value}`,
                    selected: value === settings.graphFontSize,
                  })),
                ], "is-compact")}
              </div>
            </div>
            <div class="settings-preview settings-preview-card" aria-label="${escapeHtml(c.previewTitle)}">
              <div class="settings-preview-head">
                <span class="settings-preview-badge">${c.previewTitle}</span>
                <div class="settings-preview-actions">
                  <button type="button" class="button" tabindex="-1">${c.button}</button>
                  <button type="button" class="button ghost tiny" tabindex="-1">${c.smallButton}</button>
                </div>
              </div>
              <div class="settings-preview-body">
                <h4>${c.previewHeading}</h4>
                <p>${c.previewBody} · <span class="settings-hint">${c.previewHint}</span></p>
              </div>
              <svg viewBox="0 0 360 44" role="img" aria-label="contig / bp">
                <rect x="6" y="22" width="210" height="14" rx="2.5" fill="var(--ctg-primary-fill)" stroke="var(--ctg-primary-stroke)" stroke-width="1"/>
                <rect x="224" y="22" width="128" height="14" rx="2.5" fill="var(--ctg-companion-fill)" stroke="var(--ctg-companion-stroke)" stroke-width="1"/>
                <text class="track-ctg-label" x="10" y="16">contig_001</text>
                <text class="track-ctg-label" x="228" y="16">contig_002</text>
                <text class="track-tick-label" x="312" y="16">100 kb</text>
              </svg>
            </div>
          </div>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.layoutGroup}</h4>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.resetLayoutTitle}</span>
                <p class="settings-row-desc">${c.resetLayoutDesc}</p>
              </div>
              <div class="settings-row-control">
                <button type="button" class="button ghost tiny" data-settings-reset-layout>${c.resetLayoutButton}</button>
              </div>
            </div>
          </div>
        </section>

        <section class="settings-section" role="tabpanel" id="settings-panel-editing" data-settings-panel="editing" aria-labelledby="settings-editing-title"${currentTab !== "editing" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-editing-title">${c.history}</h3><p class="settings-panel-desc">${c.historyDesc}</p></header>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.historyGroup}</h4>
            <div class="settings-row settings-row-stacked">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-history-input">${c.capacity}</label>
                <p class="settings-row-desc">${c.capacityDesc}</p>
              </div>
              <div class="settings-history-controls">
                <div class="settings-segmented is-compact" role="group" aria-label="${escapeHtml(c.capacity)}">
                  ${HISTORY_PRESETS.map(value => {
                    const active = capacity === value;
                    const label = value === 0 ? c.unlimited : `${value}`;
                    return `<button type="button" class="settings-seg-btn${active ? " is-active" : ""}" data-history-preset="${value}" aria-pressed="${active}">${label}</button>`;
                  }).join("")}
                </div>
                <div class="settings-custom-steps${!isPresetCapacity ? " is-active" : ""}">
                  <input id="settings-history-input" name="historyCapacity" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" aria-describedby="settings-status" placeholder="${escapeHtml(c.customSteps)}" value="${capacity === 0 ? "" : capacity}">
                  <span class="settings-unit">${c.steps}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.localViewGroup}</h4>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.localViewDefaultMode}</span>
                <p class="settings-row-desc">${c.localViewDefaultModeDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSegmented("localViewDefaultMode", c.localViewDefaultMode, [
                  { value: "docked", label: c.docked, selected: settings.localViewDefaultMode !== "floating" },
                  { value: "floating", label: c.floating, selected: settings.localViewDefaultMode === "floating" },
                ])}
              </div>
            </div>
            <div class="settings-row">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-local-view-pinned">${c.localViewDefaultPinned}</label>
                <p class="settings-row-desc">${c.localViewDefaultPinnedDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSwitch("settings-local-view-pinned", "localViewDefaultPinned", settings.localViewDefaultPinned !== false)}
              </div>
            </div>
          </div>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.safetyGroup}</h4>
            <div class="settings-row">
              <div class="settings-row-info">
                <label class="settings-row-title" for="settings-delete-hotkey">${c.deleteHotkey}</label>
                <p class="settings-row-desc">${c.deleteHotkeyDesc}</p>
              </div>
              <div class="settings-row-control">
                ${renderSwitch("settings-delete-hotkey", "deleteHotkeyEnabled", settings.deleteHotkeyEnabled !== false)}
              </div>
            </div>
            <div class="settings-row">
              <div class="settings-row-info">
                <span class="settings-row-title">${c.confirmationsTitle}</span>
                <p class="settings-row-desc" data-settings-confirmations-desc>${escapeHtml(confirmationsDesc)}</p>
              </div>
              <div class="settings-row-control">
                <button type="button" class="button ghost tiny" data-settings-reset-confirmations${skippedCount > 0 ? "" : " disabled"}>${c.restoreConfirmations}</button>
              </div>
            </div>
          </div>
        </section>

        <section class="settings-section" role="tabpanel" id="settings-panel-updates" data-settings-panel="updates" data-settings-update aria-labelledby="settings-update-title"${currentTab !== "updates" ? " hidden" : ""}>${renderUpdateSettings(locale, context.updateState || {}, { autoCheckUpdates: settings.autoCheckUpdates !== false, runtimeMode: context.runtimeMode, platform: context.platform })}</section>
      </div>
    </div>
    <footer class="settings-footer">
      <p id="settings-status" class="settings-status" role="status" aria-live="polite">${c.scope}</p>
      <button type="button" class="settings-reset" data-settings-reset>${c.reset}</button>
    </footer>`;
}

const settingsBindings = new WeakMap();

export function bindAppSettings(root, {
  getLocale,
  onTypographyChange = () => {},
  onLanguageChange = () => {},
  onPickDirectory = null,
  onLayoutReset = () => {},
  getRuntimeMode = () => "",
  updater = null,
} = {}) {
  settingsBindings.get(root)?.();

  let activeDialog = null;

  const open = (initialTab = "general") => {
    if (activeDialog) {
      if (SETTINGS_TABS.includes(initialTab)) {
        activeDialog.querySelector?.(`[data-settings-tab="${initialTab}"]`)?.click?.();
      }
      activeDialog.focus?.();
      return activeDialog;
    }

    const dialog = document.createElement("dialog");
    dialog.className = "app-settings-dialog";
    dialog.setAttribute("aria-labelledby", "app-settings-title");
    activeDialog = dialog;

    const labels = () => APP_SETTINGS_COPY[getLocale() === "en" ? "en" : "zh"];
    const historyInput = () => dialog.querySelector("[name=historyCapacity]");
    let activeTab = SETTINGS_TABS.includes(initialTab) ? initialTab : "general";

    const updateContext = () => ({
      updateState: updater?.getState?.() || {},
      runtimeMode: getRuntimeMode?.() || "",
      skippedConfirmations: skippedConfirmationCount(),
    });

    const refreshUpdate = () => {
      const state = updater?.getState?.();
      const dot = dialog.querySelector("[data-settings-update-dot]");
      if (dot) dot.hidden = !(state?.version && !["checking", "installing"].includes(state.phase));
      const section = dialog.querySelector("[data-settings-update]");
      if (section && updater) {
        const focus = section.contains(document.activeElement) ? document.activeElement : null;
        const selector = focus?.hasAttribute("data-update-check") ? "[data-update-check]"
          : focus?.hasAttribute("data-update-view") ? "[data-update-view]"
          : focus?.id === "settings-auto-check-updates" ? "#settings-auto-check-updates"
          : focus?.hasAttribute("data-update-clear-snooze") ? "[data-update-clear-snooze]"
          : focus?.hasAttribute("data-settings-copy-diagnostics") ? "[data-settings-copy-diagnostics]" : null;
        section.innerHTML = renderUpdateSettings(getLocale(), state, {
          autoCheckUpdates: getAppSettings().autoCheckUpdates !== false,
          runtimeMode: getRuntimeMode?.() || "",
        });
        if (selector) section.querySelector(selector)?.focus();
      }
    };

    let disposeSelects;
    const render = () => {
      disposeSelects?.();
      dialog.innerHTML = renderSettingsContent(getLocale(), getAppSettings(), activeTab, updateContext());
      disposeSelects = bindShellSelects(dialog);
      refreshUpdate();
    };

    const unsubscribeUpdate = updater?.subscribe?.(refreshUpdate);

    const status = (message, error = false) => {
      const node = dialog.querySelector(".settings-status");
      if (!node) return;
      node.textContent = message;
      node.classList.toggle("is-error", error);
    };

    const save = patch => {
      try {
        setAppSettings({ ...getAppSettings(), ...patch });
        if ("fontSize" in patch || "graphFontSize" in patch) onTypographyChange();
        status(labels().applied);
        return true;
      } catch {
        render();
        status(labels().failed, true);
        return false;
      }
    };

    const activateTab = (nextTab, { focus = false } = {}) => {
      if (!SETTINGS_TABS.includes(nextTab)) return;
      activeTab = nextTab;
      dialog.querySelectorAll("[data-settings-tab]").forEach(button => {
        const active = button.dataset.settingsTab === activeTab;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
      });
      dialog.querySelectorAll("[data-settings-panel]").forEach(panel => {
        panel.hidden = panel.dataset.settingsPanel !== activeTab;
      });
      const content = dialog.querySelector(".settings-content");
      if (content) content.scrollTop = 0;
      if (focus) dialog.querySelector(`[data-settings-tab="${activeTab}"]`)?.focus();
    };

    const syncRadioGroup = (name, selectedValue) => {
      dialog.querySelectorAll(`[data-settings-radio="${name}"]`).forEach(button => {
        const active = button.dataset.settingsValue === String(selectedValue);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-checked", String(active));
        button.tabIndex = active ? 0 : -1;
      });
    };

    const syncHistoryUI = () => {
      const capacity = getAppSettings().historyCapacity;
      const input = historyInput();
      if (input) {
        input.value = capacity === 0 ? "" : String(capacity);
        input.removeAttribute("aria-invalid");
      }
      dialog.querySelectorAll("[data-history-preset]").forEach(button => {
        const active = Number(button.dataset.historyPreset) === capacity;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      dialog.querySelector(".settings-custom-steps")?.classList?.toggle("is-active", !HISTORY_PRESETS.includes(capacity));
    };

    const commitCapacity = () => {
      const input = historyInput();
      if (!input) return true;
      const raw = input.value.trim();
      const capacity = raw === "" || raw === labels().unlimited || raw === "0"
        ? 0
        : /^\d+$/.test(raw) ? Number(raw) : NaN;
      if (!Number.isSafeInteger(capacity) || capacity < 0 || capacity > 1000000) {
        input.setAttribute("aria-invalid", "true");
        status(labels().invalid, true);
        return false;
      }
      if (capacity !== getAppSettings().historyCapacity && !save({ historyCapacity: capacity })) return false;
      syncHistoryUI();
      status(labels().applied);
      return true;
    };

    const commitDefaultWorkspaceRoot = value => {
      const normalized = String(value ?? "").trim();
      if (normalized !== getAppSettings().defaultWorkspaceRoot) {
        if (!save({ defaultWorkspaceRoot: normalized })) return false;
      }
      const input = dialog.querySelector("#settings-default-workspace-root");
      if (input) input.value = normalized;
      const clearBtn = dialog.querySelector("[data-settings-clear-workspace-root]");
      if (clearBtn) clearBtn.disabled = !normalized;
      return true;
    };

    const selectRadio = (name, value, { focus = false } = {}) => {
      if (name === "language") {
        onLanguageChange(value === "en" ? "en" : "zh");
        render();
        if (focus) dialog.querySelector(`[data-settings-radio="language"][data-settings-value="${value === "en" ? "en" : "zh"}"]`)?.focus();
        status(labels().applied);
        return;
      }
      let patch = null;
      if (name === "theme") patch = { theme: value };
      else if (name === "fontSize") patch = { fontSize: Number(value) };
      else if (name === "graphFontSize") patch = { graphFontSize: value === "" ? null : Number(value) };
      else if (name === "localViewDefaultMode") patch = { localViewDefaultMode: value === "floating" ? "floating" : "docked" };
      if (!patch) return;
      if (save(patch)) {
        syncRadioGroup(name, value);
        if (focus) dialog.querySelector(`[data-settings-radio="${name}"][data-settings-value="${value}"]`)?.focus();
      }
    };

    const syncConfirmationsRow = () => {
      const count = skippedConfirmationCount();
      const desc = dialog.querySelector("[data-settings-confirmations-desc]");
      if (desc) {
        desc.textContent = count > 0
          ? labels().confirmationsCount.replace("{count}", count)
          : labels().confirmationsNone;
      }
      const button = dialog.querySelector("[data-settings-reset-confirmations]");
      if (button) button.disabled = count === 0;
    };

    const syncTrackColorsUI = (trackColors = getAppSettings().trackColors) => {
      const normalized = normalizeTrackColors(trackColors);
      const effective = resolveEffectiveTrackBaseColors(normalized);
      const activePreset = detectTrackColorPreset(normalized);
      const hasCustom = hasCustomTrackColors(normalized);
      const resetAllBtn = dialog.querySelector("[data-settings-reset-track-colors]");
      if (resetAllBtn) resetAllBtn.disabled = !hasCustom;
      dialog.querySelectorAll("[data-settings-track-preset]").forEach(button => {
        const active = button.dataset.settingsTrackPreset === activePreset;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      for (const key of TRACK_COLOR_KEYS) {
        const hex = effective[key];
        const isCustom = normalized[key] !== null;
        const item = dialog.querySelector(`[data-settings-color-item="${key}"]`);
        item?.classList?.toggle("is-custom", isCustom);
        const input = dialog.querySelector(`[data-settings-track-color="${key}"]`);
        if (input && input.value.toLowerCase() !== hex) input.value = hex;
        const hexEl = dialog.querySelector(`[data-settings-track-color-hex="${key}"]`);
        if (hexEl) hexEl.textContent = hex.toUpperCase();
        const resetBtn = dialog.querySelector(`[data-settings-track-color-reset="${key}"]`);
        if (resetBtn) resetBtn.disabled = !isCustom;
      }
    };

    const updateTrackColors = (nextColors, { commit = true } = {}) => {
      const normalized = normalizeTrackColors(nextColors);
      if (commit) {
        if (save({ trackColors: normalized })) syncTrackColorsUI(normalized);
        return;
      }
      const rootEl = dialog.ownerDocument?.documentElement || globalThis.document?.documentElement;
      const isDark = rootEl?.dataset?.theme === "dark" || getAppliedAppTheme() === "dark";
      applyTrackColorVariables(rootEl, normalized, { dark: isDark });
      syncTrackColorsUI(normalized);
    };

    render();
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      disposeSelects?.();
      unsubscribeUpdate?.();
      activeDialog = null;
      dialog.remove();
      root.querySelector("[data-app-settings]")?.focus?.();
    }, { once: true });

    dialog.addEventListener("input", event => {
      if (event.target.dataset?.settingsTrackColor) {
        const key = event.target.dataset.settingsTrackColor;
        const hex = normalizeHexColor(event.target.value);
        if (hex && TRACK_COLOR_KEYS.includes(key)) {
          updateTrackColors({ ...getAppSettings().trackColors, [key]: hex }, { commit: false });
        }
        return;
      }
      if (event.target.name === "historyCapacity") {
        event.target.removeAttribute("aria-invalid");
        status(labels().scope);
      }
      if (event.target.name === "defaultWorkspaceRoot") {
        const clearBtn = dialog.querySelector("[data-settings-clear-workspace-root]");
        if (clearBtn) clearBtn.disabled = !event.target.value.trim();
      }
    });

    dialog.addEventListener("focusout", event => {
      if (event.target.name === "historyCapacity") commitCapacity();
      if (event.target.name === "defaultWorkspaceRoot") commitDefaultWorkspaceRoot(event.target.value);
    });

    dialog.addEventListener("change", event => {
      const target = event.target;
      if (target.dataset?.settingsTrackColor) {
        const key = target.dataset.settingsTrackColor;
        const hex = normalizeHexColor(target.value);
        if (hex && TRACK_COLOR_KEYS.includes(key)) {
          updateTrackColors({ ...getAppSettings().trackColors, [key]: hex }, { commit: true });
        }
        return;
      }
      const { name, type, value, checked } = target;
      if (type === "checkbox") {
        if (name === "restoreLastWorkspace") save({ restoreLastWorkspace: checked });
        if (name === "localViewDefaultPinned") save({ localViewDefaultPinned: checked });
        if (name === "deleteHotkeyEnabled") save({ deleteHotkeyEnabled: checked });
        if (name === "autoCheckUpdates") save({ autoCheckUpdates: checked });
        return;
      }
      if (name === "theme") save({ theme: value });
      if (name === "fontSize") save({ fontSize: Number(value) });
      if (name === "graphFontSize") save({ graphFontSize: value === "" ? null : Number(value) });
      if (name === "importParallelism") save({ importParallelism: value });
      if (name === "language") {
        onLanguageChange(value === "en" ? "en" : "zh");
        render();
      }
    });

    dialog.addEventListener("keydown", event => {
      const tabButton = event.target.closest?.("[data-settings-tab]");
      if (tabButton) {
        const index = SETTINGS_TABS.indexOf(tabButton.dataset.settingsTab);
        if (index >= 0) {
          if (event.key === "ArrowDown" || event.key === "ArrowRight") {
            event.preventDefault();
            activateTab(SETTINGS_TABS[(index + 1) % SETTINGS_TABS.length], { focus: true });
          } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
            event.preventDefault();
            activateTab(SETTINGS_TABS[(index - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length], { focus: true });
          } else if (event.key === "Home") {
            event.preventDefault();
            activateTab(SETTINGS_TABS[0], { focus: true });
          } else if (event.key === "End") {
            event.preventDefault();
            activateTab(SETTINGS_TABS.at(-1), { focus: true });
          }
        }
        return;
      }
      const radioButton = event.target.closest?.("[data-settings-radio]");
      if (radioButton && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        const name = radioButton.dataset.settingsRadio;
        const buttons = [...dialog.querySelectorAll(`[data-settings-radio="${name}"]`)];
        const index = buttons.indexOf(radioButton);
        if (index >= 0 && buttons.length > 1) {
          event.preventDefault();
          const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
          const next = buttons[(index + delta + buttons.length) % buttons.length];
          selectRadio(name, next.dataset.settingsValue, { focus: true });
        }
        return;
      }
      if (event.target.name === "defaultWorkspaceRoot" && event.key === "Enter") {
        event.preventDefault();
        commitDefaultWorkspaceRoot(event.target.value);
        return;
      }
      if (event.target.name === "historyCapacity") {
        if (event.key === "Enter") {
          event.preventDefault();
          commitCapacity();
        } else if (event.key === "Escape") {
          const expected = getAppSettings().historyCapacity === 0 ? "" : String(getAppSettings().historyCapacity);
          if (event.target.value !== expected) {
            event.preventDefault();
            event.stopPropagation();
            syncHistoryUI();
            status(labels().scope);
          }
        }
      }
    });

    dialog.addEventListener("click", async event => {
      const tabButton = event.target.closest?.("[data-settings-tab]");
      if (tabButton) { activateTab(tabButton.dataset.settingsTab); return; }

      const radioButton = event.target.closest?.("[data-settings-radio]");
      if (radioButton) {
        selectRadio(radioButton.dataset.settingsRadio, radioButton.dataset.settingsValue);
        return;
      }

      const presetButton = event.target.closest?.("[data-history-preset]");
      if (presetButton) {
        const nextCapacity = Number(presetButton.dataset.historyPreset);
        if (save({ historyCapacity: nextCapacity })) syncHistoryUI();
        return;
      }

      const trackPresetButton = event.target.closest?.("[data-settings-track-preset]");
      if (trackPresetButton) {
        const preset = TRACK_COLOR_PRESETS.find(item => item.id === trackPresetButton.dataset.settingsTrackPreset);
        if (preset) updateTrackColors(preset.colors, { commit: true });
        return;
      }

      const trackResetOne = event.target.closest?.("[data-settings-track-color-reset]");
      if (trackResetOne) {
        const key = trackResetOne.dataset.settingsTrackColorReset;
        if (TRACK_COLOR_KEYS.includes(key)) {
          updateTrackColors({ ...getAppSettings().trackColors, [key]: null }, { commit: true });
        }
        return;
      }

      if (event.target.closest?.("[data-settings-reset-track-colors]")) {
        updateTrackColors(DEFAULT_TRACK_COLOR_OVERRIDES, { commit: true });
        return;
      }

      if (event.target.closest?.("[data-settings-pick-workspace-root]")) {
        if (typeof onPickDirectory === "function") {
          try {
            const selected = await onPickDirectory();
            if (selected) commitDefaultWorkspaceRoot(selected);
          } catch {
            status(labels().failed, true);
          }
        }
        return;
      }

      if (event.target.closest?.("[data-settings-clear-workspace-root]")) {
        commitDefaultWorkspaceRoot("");
        return;
      }

      if (event.target.closest?.("[data-settings-reset-layout]")) {
        try {
          resetAppLayoutPreferences();
          onLayoutReset();
          status(labels().layoutResetDone);
        } catch {
          status(labels().failed, true);
        }
        return;
      }

      if (event.target.closest?.("[data-settings-reset-confirmations]")) {
        clearSkippedConfirmations();
        syncConfirmationsRow();
        status(labels().confirmationsRestored);
        return;
      }

      if (event.target.closest?.("[data-update-check]")) { void updater?.check?.({ manual: true }); return; }
      if (event.target.closest?.("[data-update-view]")) { updater?.notify?.(true); return; }
      if (event.target.closest?.("[data-update-clear-snooze]")) {
        if (updater?.clearSnooze?.()) {
          refreshUpdate();
          status(labels().snoozeCleared);
        }
        return;
      }

      if (event.target.closest?.("[data-settings-copy-diagnostics]")) {
        const text = buildDiagnosticSummary({
          version: updater?.getState?.()?.currentVersion || "",
          runtimeMode: getRuntimeMode?.() || "",
          platform: String(globalThis.navigator?.platform || ""),
          locale: getLocale(),
          settings: getAppSettings(),
        });
        try {
          if (!globalThis.navigator?.clipboard?.writeText) throw new Error("clipboard unavailable");
          await globalThis.navigator.clipboard.writeText(text);
          status(labels().diagnosticsCopied);
        } catch {
          status(labels().diagnosticsCopyFailed, true);
        }
        return;
      }

      if (event.target.closest?.("[data-settings-close]")) { dialog.close(); return; }

      if (event.target.closest?.("[data-settings-reset]")) {
        if (await requestAppConfirm(labels().restoreConfirm, {
          confirmationKey: "reset-app-settings",
          locale: getLocale(),
          title: labels().reset,
          confirmLabel: labels().reset,
        })) {
          if (save(DEFAULT_APP_SETTINGS)) render();
        }
      }
    });

    dialog.showModal();
    return dialog;
  };

  const button = root.querySelector("[data-app-settings]");
  const onClick = () => open();
  button?.addEventListener("click", onClick);
  settingsBindings.set(root, () => {
    button?.removeEventListener("click", onClick);
  });

  return {
    open,
    close: () => activeDialog?.close?.(),
    isOpen: () => Boolean(activeDialog),
  };
}
