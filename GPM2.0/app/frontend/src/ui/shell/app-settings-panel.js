import { DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings } from "../../services/app-settings.js";

const copy = {
  zh: { title: "App 设置", close: "关闭", display: "字体与显示", size: "界面字号", graph: "图内字号", follow: "跟随界面", language: "界面语言", history: "编辑历史", capacity: "回溯容量", custom: "自定义", unlimited: "不限步数", steps: "步", preview: "文字预览", previewTitle: "装配视图", previewBody: "正文与控件名称", previewHint: "提示：字号调整后，控件和文字间距会同步适配。", button: "操作按钮", reset: "恢复默认", hint: "同时用于主视图和子视图，各自独立计数。降低容量后，在各视图下一次新增编辑时裁剪超额旧记录；已裁剪记录无法恢复。", unlimitedHint: "不限步数会持续增加项目存储量，并可能影响保存和读取速度。", invalid: "请输入 1–1000000 的整数步数。", failed: "设置保存失败，请检查本机存储。", restoreConfirm: "恢复默认设置？回溯容量将恢复为 50 步，下一次新增编辑时可能裁剪旧记录。", scope: "保存在本机，对所有项目生效。", live: "显示设置即时生效", save: "应用容量", applied: "已保存" },
  en: { title: "App settings", close: "Close", display: "Typography", size: "Interface text", graph: "Graph text", follow: "Follow interface", language: "Language", history: "Edit history", capacity: "History capacity", custom: "Custom", unlimited: "Unlimited", steps: "steps", preview: "Preview", previewTitle: "Assembly view", previewBody: "Body text and control labels", previewHint: "Hint: controls and spacing adapt to the selected text size.", button: "Action button", reset: "Restore defaults", hint: "Applies separately to the main and local views. A lower limit trims old entries on the next new edit in each view. Trimmed entries cannot be recovered.", unlimitedHint: "Unlimited history increases project storage and may slow saving and loading.", invalid: "Enter a whole number from 1 to 1000000.", failed: "Could not save settings. Check local storage.", restoreConfirm: "Restore defaults? History capacity will return to 50 steps; old entries may be trimmed on the next new edit.", scope: "Saved on this computer for all projects.", live: "Display changes apply immediately", save: "Apply capacity", applied: "Saved" },
};

export function renderSettingsContent(locale, settings = getAppSettings()) {
  const c = copy[locale === "en" ? "en" : "zh"];
  const options = (values, selected) => values.map(value => `<option value="${value}" ${value === selected ? "selected" : ""}>${value} px</option>`).join("");
  const preset = [0, 50, 100, 200].includes(settings.historyCapacity) ? settings.historyCapacity : "custom";
  return `<div class="settings-heading"><h2 id="app-settings-title">${c.title}</h2><button type="button" class="button" data-settings-close>${c.close}</button></div>
    <p class="settings-hint">${c.scope}</p>
    <fieldset><legend>${c.display}</legend>
      <label class="settings-row">${c.size}<select name="fontSize">${options([12, 14, 16, 18], settings.fontSize)}</select></label>
      <label class="settings-row">${c.graph}<select name="graphFontSize"><option value="" ${settings.graphFontSize === null ? "selected" : ""}>${c.follow}</option>${options([10, 12, 14, 16], settings.graphFontSize)}</select></label>
      <label class="settings-row">${c.language}<select name="language"><option value="zh" ${locale !== "en" ? "selected" : ""}>中文</option><option value="en" ${locale === "en" ? "selected" : ""}>English</option></select></label>
      <div class="settings-preview" aria-label="${c.preview}"><h3>${c.previewTitle}</h3><p>${c.previewBody}</p><p class="settings-hint">${c.previewHint}</p><div class="settings-preview-actions"><button type="button" class="button">${c.button}</button><button type="button" class="button tiny">${c.close}</button></div><svg viewBox="0 0 320 54" role="img" aria-label="contig / bp"><rect x="8" y="28" width="295" height="14" rx="2" fill="#d2dfef"/><text class="track-ctg-label" x="12" y="23">contig_001</text><text class="track-tick-label" x="230" y="23">100 kb</text></svg></div>
    </fieldset>
    <fieldset><legend>${c.history}</legend><label class="settings-row">${c.capacity}<select name="historyPreset">${[50,100,200].map(n=>`<option value="${n}" ${preset === n ? "selected" : ""}>${n} ${c.steps}</option>`).join("")}<option value="custom" ${preset === "custom" ? "selected" : ""}>${c.custom}</option><option value="0" ${preset === 0 ? "selected" : ""}>${c.unlimited}</option></select></label>
      <div class="settings-custom" ${preset === "custom" ? "" : "hidden"}><label>${c.steps}<input name="historyCustom" type="number" min="1" max="1000000" step="1" value="${settings.historyCapacity || 50}"></label><button type="button" class="button" data-settings-capacity>${c.save}</button></div>
      <p class="settings-hint">${c.hint}</p><p class="settings-hint">${c.unlimitedHint}</p></fieldset>
    <p class="settings-status" role="status" aria-live="polite"></p><div class="settings-footer"><span class="settings-hint">${c.live}</span><button type="button" class="button" data-settings-reset>${c.reset}</button></div>`;
}

export function bindAppSettings(root, { getLocale, onTypographyChange, onLanguageChange }) {
  const opener = root.querySelector("[data-app-settings]");
  opener?.addEventListener("click", () => {
    const dialog = document.createElement("dialog");
    dialog.className = "app-settings-dialog";
    dialog.setAttribute("aria-labelledby", "app-settings-title");
    const render = () => { dialog.innerHTML = renderSettingsContent(getLocale()); };
    const save = (patch) => {
      try {
        setAppSettings({ ...getAppSettings(), ...patch });
        if ("fontSize" in patch || "graphFontSize" in patch) onTypographyChange();
        dialog.querySelector(".settings-status").textContent = copy[getLocale()].applied;
        return true;
      } catch {
        render();
        dialog.querySelector(".settings-status").textContent = copy[getLocale()].failed;
        return false;
      }
    };
    render();
    document.body.append(dialog);
    dialog.addEventListener("close", () => { dialog.remove(); root.querySelector("[data-app-settings]")?.focus(); }, { once: true });
    dialog.addEventListener("change", event => {
      const { name, value } = event.target;
      if (name === "fontSize") save({ fontSize: Number(value) });
      if (name === "graphFontSize") save({ graphFontSize: value === "" ? null : Number(value) });
      if (name === "language") { onLanguageChange(value); render(); }
      if (name === "historyPreset") {
        dialog.querySelector(".settings-custom").hidden = value !== "custom";
        if (value !== "custom") save({ historyCapacity: Number(value) });
      }
    });
    dialog.addEventListener("click", event => {
      if (event.target.closest("[data-settings-close]")) dialog.close();
      if (event.target.closest("[data-settings-reset]")) {
        if (getAppSettings().historyCapacity !== 0 && getAppSettings().historyCapacity <= 50
          || window.confirm(copy[getLocale()].restoreConfirm)) {
          if (save(DEFAULT_APP_SETTINGS)) { onLanguageChange("zh"); render(); }
        }
      }
      if (event.target.closest("[data-settings-capacity]")) {
        const input = dialog.querySelector("[name=historyCustom]");
        if (!input.value || !input.checkValidity()) {
          dialog.querySelector(".settings-status").textContent = copy[getLocale()].invalid;
          input.reportValidity();
        } else save({ historyCapacity: Number(input.value) });
      }
    });
    dialog.showModal();
  });
}
