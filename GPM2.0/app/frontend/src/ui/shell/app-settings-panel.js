import { bindShellSelects, renderShellSelect } from "./shell-select-runtime.js";
import { renderUpdateSettings } from "./app-update-panel.js";
import { requestAppConfirm } from "./app-dialog.js";
import { DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings } from "../../services/app-settings.js";

export const SETTINGS_TABS = Object.freeze(["general", "appearance", "editing", "updates"]);

export const APP_SETTINGS_COPY = {
  zh: {
    title: "App 设置", close: "关闭", categories: "设置分类",
    general: "常规", generalDesc: "界面语言与本机通用偏好。",
    display: "外观", displayDesc: "调整配色主题、界面字号与图内文字比例。",
    themeGroup: "配色主题", typography: "文字与图内排版",
    theme: "主题", system: "跟随系统", light: "浅色", dark: "深色", size: "界面字号", graph: "图内字号",
    follow: "跟随界面", language: "语言",
    languageHint: "立即切换菜单、标签与弹窗语言，并与顶部语言栏保持同步。",
    history: "编辑", historyDesc: "配置装配视图的撤销与回溯记录容量。", capacity: "回溯容量",
    updates: "更新", updateAvailableBadge: "有可用更新",
    custom: "自定义…", unlimited: "不限步数", steps: "步", enterSteps: "输入步数",
    preview: "预览文字效果", previewTitle: "装配视图", previewBody: "正文与控件名称",
    previewHint: "提示文字示例", button: "操作按钮", smallButton: "小按钮", reset: "恢复默认",
    graphHint: "控制 Contig 名称、刻度等图内文字。默认跟随界面字号，也可单独调整。",
    historyHint: "主视图和子视图分别计数。降低容量后，下次新增编辑时裁剪旧记录，已裁剪记录无法恢复。不限步数可能增加存储和读写耗时。",
    invalid: "请输入 1–1000000 的整数，或选择不限步数。", failed: "保存失败，请检查本机存储。",
    restoreConfirm: "恢复默认设置？回溯容量将恢复为不限步数。",
    scope: "本机设置 · 自动保存", applied: "已保存", choose: "选择回溯容量",
  },
  en: {
    title: "App Settings", close: "Close", categories: "Settings Categories",
    general: "General", generalDesc: "Display language and local application preferences.",
    display: "Appearance", displayDesc: "Adjust color theme, interface text size, and graph typography.",
    themeGroup: "Color Theme", typography: "Typography",
    theme: "Theme", system: "Follow System", light: "Light", dark: "Dark", size: "Interface text", graph: "Graph text",
    follow: "Follow Interface", language: "Language",
    languageHint: "Applies immediately to menus, labels, and dialogs, staying in sync with the top bar.",
    history: "Editing", historyDesc: "Configure undo and rollback history capacity for assembly views.", capacity: "History capacity",
    updates: "Updates", updateAvailableBadge: "Update available",
    custom: "Custom…", unlimited: "Unlimited", steps: "steps", enterSteps: "Enter steps",
    preview: "Preview typography", previewTitle: "Assembly view", previewBody: "Body text and control labels",
    previewHint: "Example hint text", button: "Action button", smallButton: "Small button", reset: "Restore defaults",
    graphHint: "Text inside graphs, including contig names and ticks. Follows the interface size unless set separately.",
    historyHint: "Counted separately for main and local views. A lower limit trims old entries on the next new edit; trimmed entries cannot be recovered. Unlimited history may increase storage and slow saving and loading.",
    invalid: "Enter a whole number from 1 to 1000000, or choose Unlimited.", failed: "Could not save. Check local storage.",
    restoreConfirm: "Restore defaults? History capacity will return to unlimited.",
    scope: "This computer · Auto-save", applied: "Saved", choose: "Choose history capacity",
  },
};

const TAB_ICONS = {
  general: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a13.5 13.5 0 0 1 0 18"/><path d="M12 3a13.5 13.5 0 0 0 0 18"/></svg>`,
  appearance: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`,
  editing: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></svg>`,
  updates: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>`,
};

function help(id, label, text, above = false) {
  const attr = value => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  return `<span class="settings-help"><button type="button" class="settings-help-button" aria-label="${attr(label)}" data-app-tooltip="${attr(text)}" aria-controls="${id}" aria-expanded="false">?</button><span id="${id}" role="note" class="settings-tooltip app-tooltip-surface${above ? " is-above" : ""}">${text}</span></span>`;
}

export function renderSettingsContent(locale, settings = getAppSettings(), activeTab = "general") {
  const c = APP_SETTINGS_COPY[locale === "en" ? "en" : "zh"];
  const currentTab = SETTINGS_TABS.includes(activeTab) ? activeTab : "general";
  const sizes = (values, selected) => values.map(value => ({ value, label: `${value} px`, selected: value === selected }));
  const select = (id, name, label, options) => renderShellSelect(id, label, options, { name });
  const capacity = settings.historyCapacity;
  const tabLabels = { general: c.general, appearance: c.display, editing: c.history, updates: c.updates };
  const nav = SETTINGS_TABS.map(id => {
    const active = id === currentTab;
    return `<button type="button" role="tab" id="settings-tab-${id}" class="settings-nav-item${active ? " is-active" : ""}" data-settings-tab="${id}" aria-selected="${active}" aria-controls="settings-panel-${id}" tabindex="${active ? "0" : "-1"}"><span class="settings-nav-icon" aria-hidden="true">${TAB_ICONS[id]}</span><span class="settings-nav-label">${tabLabels[id]}</span>${id === "updates" ? `<span class="settings-nav-dot" data-settings-update-dot hidden aria-label="${c.updateAvailableBadge}"></span>` : ""}</button>`;
  }).join("");
  return `<header class="settings-heading"><h2 id="app-settings-title">${c.title}</h2><button type="button" class="settings-close" data-settings-close aria-label="${c.close}">×</button></header>
    <div class="settings-body">
      <nav class="settings-nav" role="tablist" aria-label="${c.categories}" aria-orientation="vertical">${nav}</nav>
      <div class="settings-content">
        <section class="settings-section" role="tabpanel" id="settings-panel-general" data-settings-panel="general" aria-labelledby="settings-general-title"${currentTab !== "general" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-general-title">${c.general}</h3><p class="settings-panel-desc">${c.generalDesc}</p></header>
          <div class="settings-group">
            <div class="settings-row"><label for="settings-language-toggle">${c.language}</label>${select("settings-language", "language", c.language, [{ value: "zh", label: "中文", selected: locale !== "en" }, { value: "en", label: "English", selected: locale === "en" }])}</div>
            <p class="settings-field-note">${c.languageHint}</p>
          </div>
        </section>
        <section class="settings-section" role="tabpanel" id="settings-panel-appearance" data-settings-panel="appearance" aria-labelledby="settings-appearance-title"${currentTab !== "appearance" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-appearance-title">${c.display}</h3><p class="settings-panel-desc">${c.displayDesc}</p></header>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.themeGroup}</h4>
            <div class="settings-row"><label for="settings-theme-toggle">${c.theme}</label>${select("settings-theme", "theme", c.theme, ["system", "light", "dark"].map(theme => ({ value: theme, label: c[theme], selected: theme === (settings.theme || "system") })))}</div>
          </div>
          <div class="settings-group">
            <h4 class="settings-group-title">${c.typography}</h4>
            <div class="settings-row"><label for="settings-font-size-toggle">${c.size}</label>${select("settings-font-size", "fontSize", c.size, sizes([12, 14, 16, 18], settings.fontSize))}</div>
            <div class="settings-row"><div class="settings-field-label"><label for="settings-graph-size-toggle">${c.graph}</label>${help("settings-graph-help", c.graph, c.graphHint)}</div>${select("settings-graph-size", "graphFontSize", c.graph, [{ value: "", label: c.follow, selected: settings.graphFontSize === null }, ...sizes([10, 12, 14, 16], settings.graphFontSize)])}</div>
            <details class="settings-preview"><summary>${c.preview}</summary><div class="settings-preview-content"><h4>${c.previewTitle}</h4><p>${c.previewBody}</p><p class="settings-hint">${c.previewHint}</p><div class="settings-preview-actions"><button type="button" class="button">${c.button}</button><button type="button" class="button tiny">${c.smallButton}</button></div><svg viewBox="0 0 320 54" role="img" aria-label="contig / bp"><rect x="8" y="28" width="295" height="14" rx="2" fill="var(--ctg-primary-fill)"/><text class="track-ctg-label" x="12" y="23">contig_001</text><text class="track-tick-label" x="230" y="23">100 kb</text></svg></div></details>
          </div>
        </section>
        <section class="settings-section" role="tabpanel" id="settings-panel-editing" data-settings-panel="editing" aria-labelledby="settings-editing-title"${currentTab !== "editing" ? " hidden" : ""}>
          <header class="settings-panel-header"><h3 id="settings-editing-title">${c.history}</h3><p class="settings-panel-desc">${c.historyDesc}</p></header>
          <div class="settings-group">
            <div class="settings-row"><div class="settings-field-label"><label for="settings-history-input">${c.capacity}</label>${help("settings-history-help", c.capacity, c.historyHint)}</div>
              <div class="settings-combobox"><div class="settings-combobox-field"><input id="settings-history-input" name="historyCapacity" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="settings-history-options" aria-describedby="settings-history-help settings-status" placeholder="${c.enterSteps}" value="${capacity === 0 ? c.unlimited : capacity}"><span class="settings-unit" ${capacity === 0 ? "hidden" : ""}>${c.steps}</span><button type="button" class="settings-combobox-toggle" data-history-toggle aria-label="${c.choose}" tabindex="-1"><span aria-hidden="true">▾</span></button></div>
                <div id="settings-history-options" class="assembly-track-combo-menu settings-options" role="listbox" aria-label="${c.capacity}" hidden>${[0, 50, 100, 200, "custom"].map(value => `<div id="settings-history-option-${value}" class="assembly-track-combo-option" role="option" aria-selected="${value === capacity}" data-history-option="${value}">${value === "custom" ? c.custom : value === 0 ? c.unlimited : `${value} ${c.steps}`}</div>`).join("")}</div>
              </div>
            </div>
            <p class="settings-field-note">${c.historyHint}</p>
          </div>
        </section>
        <section class="settings-section" role="tabpanel" id="settings-panel-updates" data-settings-panel="updates" data-settings-update aria-labelledby="settings-update-title"${currentTab !== "updates" ? " hidden" : ""}>${renderUpdateSettings(locale)}</section>
      </div>
    </div>
    <footer class="settings-footer"><p id="settings-status" class="settings-status" role="status" aria-live="polite">${c.scope}</p><button type="button" class="settings-reset" data-settings-reset>${c.reset}</button></footer>`;
}

export function bindAppSettings(root, { getLocale, onTypographyChange, onLanguageChange, updater }) {
  root.querySelector("[data-app-settings]")?.addEventListener("click", () => {
    const dialog = document.createElement("dialog");
    dialog.className = "app-settings-dialog";
    dialog.setAttribute("aria-labelledby", "app-settings-title");
    const labels = () => APP_SETTINGS_COPY[getLocale() === "en" ? "en" : "zh"];
    const input = () => dialog.querySelector("[name=historyCapacity]");
    const list = () => dialog.querySelector(".settings-options");
    let activeOption = -1;
    let activeTab = "general";
    const closeHelpNotes = exceptButton => {
      dialog.querySelectorAll(".settings-help-button").forEach(button => {
        const open = button === exceptButton && button.getAttribute("aria-expanded") !== "true";
        button.setAttribute("aria-expanded", String(open));
        if (open) button.setAttribute("aria-describedby", button.getAttribute("aria-controls"));
        else button.removeAttribute("aria-describedby");
        button.parentElement?.classList?.toggle("is-open", open);
      });
    };
    const refreshUpdate = () => {
      const state = updater?.getState?.();
      const dot = dialog.querySelector("[data-settings-update-dot]");
      if (dot) dot.hidden = !(state?.version && !["checking", "installing"].includes(state.phase));
      const section = dialog.querySelector("[data-settings-update]");
      if (section && updater) {
        const focus = section.contains(document.activeElement) ? document.activeElement : null;
        const selector = focus?.hasAttribute("data-update-check") ? "[data-update-check]"
          : focus?.hasAttribute("data-update-view") ? "[data-update-view]" : null;
        section.innerHTML = renderUpdateSettings(getLocale(), state);
        if (selector) section.querySelector(selector)?.focus();
      }
    };
    let disposeSelects;
    const render = () => {
      disposeSelects?.();
      dialog.innerHTML = renderSettingsContent(getLocale(), getAppSettings(), activeTab);
      disposeSelects = bindShellSelects(dialog);
      activeOption = -1;
      refreshUpdate();
    };
    const unsubscribeUpdate = updater?.subscribe(refreshUpdate);
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
    const closeOptions = () => {
      const menu = list(), field = input();
      if (!menu || !field) return;
      menu.hidden = true;
      field.setAttribute("aria-expanded", "false");
      field.removeAttribute("aria-activedescendant");
      activeOption = -1;
    };
    const activateTab = (nextTab, { focus = false } = {}) => {
      if (!SETTINGS_TABS.includes(nextTab)) return;
      closeOptions();
      closeHelpNotes(null);
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
    const highlight = index => {
      const items = [...list().children];
      activeOption = (index + items.length) % items.length;
      items.forEach((item, i) => item.classList.toggle("is-highlighted", i === activeOption));
      input().setAttribute("aria-activedescendant", items[activeOption].id);
    };
    const openOptions = () => {
      list().hidden = false;
      input().setAttribute("aria-expanded", "true");
      const current = [...list().children].findIndex(item => item.dataset.historyOption === String(getAppSettings().historyCapacity));
      highlight(current < 0 ? 4 : current);
    };
    const syncCapacity = () => {
      const capacity = getAppSettings().historyCapacity;
      input().value = capacity === 0 ? labels().unlimited : String(capacity);
      input().removeAttribute("aria-invalid");
      dialog.querySelector(".settings-unit").hidden = capacity === 0;
      [...list().children].forEach(item => item.setAttribute("aria-selected", String(item.dataset.historyOption === String(capacity))));
    };
    const commitCapacity = () => {
      const raw = input().value.trim();
      const capacity = raw === labels().unlimited || raw === "0" ? 0 : /^\d+$/.test(raw) ? Number(raw) : NaN;
      if (!Number.isSafeInteger(capacity) || capacity < 0 || capacity > 1000000) {
        input().setAttribute("aria-invalid", "true");
        status(labels().invalid, true);
        return false;
      }
      if (capacity !== getAppSettings().historyCapacity && !save({ historyCapacity: capacity })) return false;
      syncCapacity();
      status(labels().applied);
      return true;
    };
    const chooseOption = value => {
      closeOptions();
      if (value === "custom") {
        if (getAppSettings().historyCapacity === 0) input().value = "";
        dialog.querySelector(".settings-unit").hidden = false;
        input().focus();
        input().select();
      } else {
        if (save({ historyCapacity: Number(value) })) syncCapacity();
        input().focus();
      }
    };
    render();
    document.body.append(dialog);
    dialog.addEventListener("close", () => { disposeSelects?.(); unsubscribeUpdate?.(); dialog.remove(); root.querySelector("[data-app-settings]")?.focus(); }, { once: true });
    dialog.addEventListener("input", event => {
      if (event.target.name !== "historyCapacity") return;
      closeOptions();
      input().removeAttribute("aria-invalid");
      dialog.querySelector(".settings-unit").hidden = false;
      status(labels().scope);
    });
    dialog.addEventListener("focusout", event => {
      if (event.target.name === "historyCapacity") { closeOptions(); commitCapacity(); }
    });
    dialog.addEventListener("change", event => {
      const { name, value } = event.target;
      if (name === "theme") save({ theme: value });
      if (name === "fontSize") save({ fontSize: Number(value) });
      if (name === "graphFontSize") save({ graphFontSize: value === "" ? null : Number(value) });
      if (name === "language") {
        onLanguageChange(value);
        render();
        dialog.querySelector("#settings-language-toggle")?.focus();
      }
    });
    // Keep the editable field focused while clicking its list or arrow.
    dialog.addEventListener("pointerdown", event => {
      if (event.target.closest("[data-history-option], [data-history-toggle]")) event.preventDefault();
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
      if (event.target.name !== "historyCapacity") return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (list().hidden) openOptions();
        else highlight(activeOption + (event.key === "ArrowDown" ? 1 : -1));
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (!list().hidden && activeOption >= 0) chooseOption(list().children[activeOption].dataset.historyOption);
        else commitCapacity();
      } else if (event.key === "Escape" && (!list().hidden || input().value !== (getAppSettings().historyCapacity === 0 ? labels().unlimited : String(getAppSettings().historyCapacity)))) {
        event.preventDefault();
        event.stopPropagation();
        closeOptions();
        syncCapacity();
        status(labels().scope);
      }
    });
    dialog.addEventListener("click", async event => {
      const tabButton = event.target.closest?.("[data-settings-tab]");
      if (tabButton) { activateTab(tabButton.dataset.settingsTab); return; }
      if (event.target.closest("[data-update-check]")) { void updater?.check({ manual: true }); return; }
      if (event.target.closest("[data-update-view]")) { updater?.notify(true); return; }
      const option = event.target.closest("[data-history-option]");
      if (option) { chooseOption(option.dataset.historyOption); return; }
      if (event.target.closest("[data-history-toggle]")) {
        input().focus();
        if (list().hidden) openOptions(); else closeOptions();
        return;
      }
      if (!event.target.closest(".settings-combobox")) closeOptions();
      closeHelpNotes(event.target.closest(".settings-help-button"));
      if (event.target.closest("[data-settings-close]")) dialog.close();
      if (event.target.closest("[data-settings-reset]")) {
        if ((getAppSettings().historyCapacity !== 0 && getAppSettings().historyCapacity <= 50)
          || await requestAppConfirm(labels().restoreConfirm, { confirmationKey: "reset-app-settings", locale: getLocale(), title: labels().reset, confirmLabel: labels().reset })) {
          if (save(DEFAULT_APP_SETTINGS)) { onLanguageChange("zh"); render(); }
        }
      }
    });
    dialog.showModal();
  });
}
