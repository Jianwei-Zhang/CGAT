import { bindShellSelects, renderShellSelect } from "./shell-select-runtime.js";
import { renderUpdateSettings } from "./app-update-panel.js";
import { requestAppConfirm } from "./app-dialog.js";
import { DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings } from "../../services/app-settings.js";

export const APP_SETTINGS_COPY = {
  zh: {
    title: "App 设置", close: "关闭", display: "外观", theme: "主题", system: "跟随系统", light: "浅色", dark: "深色", size: "界面字号", graph: "图内字号",
    follow: "跟随界面", language: "语言", history: "编辑", capacity: "回溯容量",
    custom: "自定义…", unlimited: "不限步数", steps: "步", enterSteps: "输入步数",
    preview: "预览文字效果", previewTitle: "装配视图", previewBody: "正文与控件名称",
    previewHint: "提示文字示例", button: "操作按钮", smallButton: "小按钮", reset: "恢复默认",
    graphHint: "控制 contig 名称、刻度等图内文字。默认跟随界面字号，也可单独调整。",
    historyHint: "主视图和子视图分别计数。降低容量后，下次新增编辑时裁剪旧记录，已裁剪记录无法恢复。不限步数可能增加存储和读写耗时。",
    invalid: "请输入 1–1000000 的整数，或选择不限步数。", failed: "保存失败，请检查本机存储。",
    restoreConfirm: "恢复默认设置？回溯容量将恢复为不限步数。",
    scope: "本机设置 · 自动保存", applied: "已保存", choose: "选择回溯容量",
  },
  en: {
    title: "App settings", close: "Close", display: "Appearance", theme: "Theme", system: "Follow system", light: "Light", dark: "Dark", size: "Interface text", graph: "Graph text",
    follow: "Follow interface", language: "Language", history: "Editing", capacity: "History capacity",
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

function help(id, label, text, above = false) {
  return `<span class="settings-help"><button type="button" class="settings-help-button" aria-label="${label}" aria-describedby="${id}" aria-expanded="false">?</button><span id="${id}" role="tooltip" class="settings-tooltip${above ? " is-above" : ""}">${text}</span></span>`;
}

export function renderSettingsContent(locale, settings = getAppSettings()) {
  const c = APP_SETTINGS_COPY[locale === "en" ? "en" : "zh"];
  const sizes = (values, selected) => values.map(value => ({ value, label: `${value} px`, selected: value === selected }));
  const select = (id, name, label, options) => renderShellSelect(id, label, options, { name });
  const capacity = settings.historyCapacity;
  return `<header class="settings-heading"><h2 id="app-settings-title">${c.title}</h2><button type="button" class="settings-close" data-settings-close aria-label="${c.close}">×</button></header>
    <section class="settings-section" aria-labelledby="settings-appearance-title">
      <h3 id="settings-appearance-title">${c.display}</h3>
      <div class="settings-row"><label for="settings-theme-toggle">${c.theme}</label>${select("settings-theme", "theme", c.theme, ["system", "light", "dark"].map(theme => ({ value: theme, label: c[theme], selected: theme === (settings.theme || "system") })))}</div>
      <div class="settings-row"><label for="settings-font-size-toggle">${c.size}</label>${select("settings-font-size", "fontSize", c.size, sizes([12, 14, 16, 18], settings.fontSize))}</div>
      <div class="settings-row"><div class="settings-field-label"><label for="settings-graph-size-toggle">${c.graph}</label>${help("settings-graph-help", c.graph, c.graphHint)}</div>${select("settings-graph-size", "graphFontSize", c.graph, [{ value: "", label: c.follow, selected: settings.graphFontSize === null }, ...sizes([10, 12, 14, 16], settings.graphFontSize)])}</div>
      <div class="settings-row"><label for="settings-language-toggle">${c.language}</label>${select("settings-language", "language", c.language, [{ value: "zh", label: "中文", selected: locale !== "en" }, { value: "en", label: "English", selected: locale === "en" }])}</div>
      <details class="settings-preview"><summary>${c.preview}</summary><div class="settings-preview-content"><h4>${c.previewTitle}</h4><p>${c.previewBody}</p><p class="settings-hint">${c.previewHint}</p><div class="settings-preview-actions"><button type="button" class="button">${c.button}</button><button type="button" class="button tiny">${c.smallButton}</button></div><svg viewBox="0 0 320 54" role="img" aria-label="contig / bp"><rect x="8" y="28" width="295" height="14" rx="2" fill="var(--ctg-primary-fill)"/><text class="track-ctg-label" x="12" y="23">contig_001</text><text class="track-tick-label" x="230" y="23">100 kb</text></svg></div></details>
    </section>
    <section class="settings-section" aria-labelledby="settings-editing-title"><h3 id="settings-editing-title">${c.history}</h3>
      <div class="settings-row"><div class="settings-field-label"><label for="settings-history-input">${c.capacity}</label>${help("settings-history-help", c.capacity, c.historyHint, true)}</div>
        <div class="settings-combobox"><div class="settings-combobox-field"><input id="settings-history-input" name="historyCapacity" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="settings-history-options" aria-describedby="settings-history-help settings-status" placeholder="${c.enterSteps}" value="${capacity === 0 ? c.unlimited : capacity}"><span class="settings-unit" ${capacity === 0 ? "hidden" : ""}>${c.steps}</span><button type="button" class="settings-combobox-toggle" data-history-toggle aria-label="${c.choose}" tabindex="-1"><span aria-hidden="true">▾</span></button></div>
          <div id="settings-history-options" class="assembly-track-combo-menu settings-options" role="listbox" aria-label="${c.capacity}" hidden>${[0, 50, 100, 200, "custom"].map(value => `<div id="settings-history-option-${value}" class="assembly-track-combo-option" role="option" aria-selected="${value === capacity}" data-history-option="${value}">${value === "custom" ? c.custom : value === 0 ? c.unlimited : `${value} ${c.steps}`}</div>`).join("")}</div>
        </div>
      </div>
    </section>
    <section class="settings-section" data-settings-update aria-labelledby="settings-update-title">${renderUpdateSettings(locale)}</section>
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
    const refreshUpdate = () => {
      const section = dialog.querySelector("[data-settings-update]");
      if (section && updater) {
        const focus = section.contains(document.activeElement) ? document.activeElement : null;
        const selector = focus?.hasAttribute("data-update-check") ? "[data-update-check]"
          : focus?.hasAttribute("data-update-view") ? "[data-update-view]" : null;
        section.innerHTML = renderUpdateSettings(getLocale(), updater.getState());
        if (selector) section.querySelector(selector)?.focus();
      }
    };
    let disposeSelects;
    const render = () => {
      disposeSelects?.();
      dialog.innerHTML = renderSettingsContent(getLocale());
      disposeSelects = bindShellSelects(dialog);
      activeOption = -1;
      refreshUpdate();
    };
    const unsubscribeUpdate = updater?.subscribe(refreshUpdate);
    const status = (message, error = false) => {
      const node = dialog.querySelector(".settings-status");
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
      list().hidden = true;
      input().setAttribute("aria-expanded", "false");
      input().removeAttribute("aria-activedescendant");
      activeOption = -1;
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
      if (name === "language") { onLanguageChange(value); render(); }
    });
    // Keep the editable field focused while clicking its list or arrow.
    dialog.addEventListener("pointerdown", event => {
      if (event.target.closest("[data-history-option], [data-history-toggle]")) event.preventDefault();
    });
    dialog.addEventListener("keydown", event => {
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
      const helpButton = event.target.closest(".settings-help-button");
      dialog.querySelectorAll(".settings-help-button").forEach(button => {
        const open = button === helpButton && button.getAttribute("aria-expanded") !== "true";
        button.setAttribute("aria-expanded", String(open));
        button.parentElement.classList.toggle("is-open", open);
      });
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
