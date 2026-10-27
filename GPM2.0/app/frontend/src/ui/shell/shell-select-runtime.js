import { bindDelayedFloatingClose, cancelDelayedFloatingClose } from "../pages/floating-menu-runtime.js";

const SYNC = Symbol("shellSelectSync");
const bindings = new WeakMap();
const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

export function renderShellSelect(id, label, options, { name = "" } = {}) {
  const selected = options.find(option => option.selected) || options[0];
  return `<span class="shell-select" data-shell-select>
    <button type="button" id="${id}-toggle" class="shell-select-toggle" data-shell-select-toggle aria-label="${escape(label)}: ${escape(selected.label)}" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}-menu"><span data-shell-select-caption>${escape(selected.label)}</span><span class="shell-select-marker" aria-hidden="true">▾</span></button>
    <select id="${id}"${name ? ` name="${escape(name)}"` : ""} hidden aria-hidden="true" tabindex="-1" aria-label="${escape(label)}">${options.map(option => `<option value="${escape(option.value)}" ${option.selected ? "selected" : ""}>${escape(option.label)}</option>`).join("")}</select>
    <span id="${id}-menu" class="assembly-track-combo-menu shell-select-menu is-hidden" role="listbox" aria-label="${escape(label)}" data-shell-select-menu></span>
  </span>`;
}

export function syncShellSelect(select) { select?.[SYNC]?.(); }

export function bindShellSelects(root) {
  bindings.get(root)?.();
  const cleanups = [];
  for (const combo of root.querySelectorAll("[data-shell-select]")) {
    const select = combo.querySelector("select"), toggle = combo.querySelector("[data-shell-select-toggle]");
    const menu = combo.querySelector("[data-shell-select-menu]"), caption = combo.querySelector("[data-shell-select-caption]");
    const timerKey = Symbol("shellSelectClose");
    const listen = (node, type, handler) => {
      node.addEventListener(type, handler); cleanups.push(() => node.removeEventListener(type, handler));
    };
    const close = () => {
      cancelDelayedFloatingClose(combo, timerKey);
      menu.classList.add("is-hidden"); toggle.setAttribute("aria-expanded", "false");
    };
    const options = () => [...menu.children];
    let signature = "";
    const sync = () => {
      const values = [...select.options], selected = values.find(option => option.selected) || values[0];
      caption.textContent = selected?.textContent || "";
      toggle.title = select.title || caption.textContent;
      toggle.disabled = select.disabled;
      const width = select.style.getPropertyValue("--workspace-select-width");
      if (width) combo.style.setProperty("--workspace-select-width", width);
      toggle.setAttribute("aria-label", `${select.getAttribute("aria-label")}: ${caption.textContent}`);
      const nextSignature = JSON.stringify(values.map(option => [option.value, option.textContent, option.disabled]));
      if (signature !== nextSignature) {
        close(); signature = nextSignature;
        menu.replaceChildren(...values.map((option, index) => {
          const button = select.ownerDocument.createElement("button");
          button.type = "button"; button.className = "assembly-track-combo-option";
          button.setAttribute("role", "option"); button.tabIndex = -1;
          button.dataset.shellOptionIndex = String(index);
          button.textContent = option.textContent; button.title = option.textContent;
          button.disabled = option.disabled; return button;
        }));
      }
      options().forEach((button, index) => {
        const active = values[index] === selected;
        button.setAttribute("aria-selected", String(active)); button.classList.toggle("is-active", active);
      });
      if (select.disabled) close();
    };
    const open = (edge = "selected") => {
      sync(); if (select.disabled) return;
      root.querySelectorAll("[data-shell-select-toggle]").forEach(other => {
        if (other !== toggle) other.closest("[data-shell-select]").querySelector("[data-shell-select-menu]").classList.add("is-hidden");
        if (other !== toggle) other.setAttribute("aria-expanded", "false");
      });
      cancelDelayedFloatingClose(combo, timerKey);
      menu.classList.remove("is-hidden"); toggle.setAttribute("aria-expanded", "true");
      const available = options().filter(option => !option.disabled);
      (edge === "first" ? available[0] : edge === "last" ? available.at(-1)
        : available.find(option => option.getAttribute("aria-selected") === "true") || available[0])?.focus();
    };
    listen(toggle, "click", () => menu.classList.contains("is-hidden") ? open() : close());
    listen(menu, "click", event => {
      const option = event.target.closest("[data-shell-option-index]"); if (!option || option.disabled) return;
      const value = select.options[Number(option.dataset.shellOptionIndex)]?.value;
      const changed = select.value !== value;
      select.value = value; close(); sync(); toggle.focus();
      if (changed) select.dispatchEvent(new (select.ownerDocument.defaultView?.Event || Event)("change", { bubbles: true }));
    });
    listen(combo, "keydown", event => {
      if (event.key === "Escape") { event.preventDefault(); close(); toggle.focus(); return; }
      if (event.key === "Tab") { close(); toggle.focus(); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      if (menu.classList.contains("is-hidden")) { open(event.key === "Home" ? "first" : event.key === "End" ? "last" : "selected"); return; }
      const available = options().filter(option => !option.disabled);
      const index = available.indexOf(select.ownerDocument.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? available.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + available.length) % available.length;
      available[next]?.focus();
    });
    listen(combo, "focusout", event => { if (!combo.contains(event.relatedTarget)) close(); });
    const outside = event => { if (!combo.contains(event.target)) close(); };
    listen(root.ownerDocument, "pointerdown", outside);
    cleanups.push(bindDelayedFloatingClose(combo, close, { timerKey }));
    listen(select, "change", sync);
    select[SYNC] = sync; cleanups.push(() => { close(); delete select[SYNC]; }); sync();
  }
  const dispose = () => cleanups.splice(0).forEach(cleanup => cleanup());
  bindings.set(root, dispose);
  return dispose;
}
