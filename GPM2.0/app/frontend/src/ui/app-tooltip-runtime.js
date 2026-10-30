import { resolveTooltipColors } from "./tooltip-colors.js";

const owners = new WeakMap();
const ATTRIBUTES = ["data-app-tooltip", "data-final-path-tooltip", "data-member-tooltip", "data-subview-band-tooltip"];
let nextId = 0;
const element = value => value?.nodeType === 3 ? value.parentElement : value;
const contains = (root, node) => root === node || Boolean(root?.contains?.(node));
const point = event => ({ x: Number(event.clientX || 0), y: Number(event.clientY || 0) });
const rect = node => node?.getBoundingClientRect?.();
const inside = (p, r) => Boolean(r && p.x >= r.left && p.x <= r.right && p.y >= r.top && p.y <= r.bottom);

function payload(node) {
  for (const attribute of ATTRIBUTES) {
    const text = node?.getAttribute?.(attribute);
    if (text) return attribute === "data-subview-band-tooltip" ? text.replaceAll(" | ", "\n").replaceAll(" · ", "\n") : text;
  }
  const desc = [...(node?.children || [])].find(child => String(child.tagName).toLowerCase() === "desc" && child.hasAttribute?.("data-app-tooltip-source"));
  return String(desc?.textContent || "").replaceAll(" | ", "\n");
}

export function findAppTooltipTarget(target) {
  for (let node = element(target); node?.getAttribute; node = node.parentElement) {
    if (node.matches?.(".app-tooltip, .settings-help.is-open")) return null;
    if (payload(node)) return node;
    // SVG labels and the painted rectangle share the same object/description.
    if (String(node.tagName || "").toLowerCase() === "g") {
      for (const shape of node.children || []) {
        if (String(shape.tagName).toLowerCase() === "rect" && payload(shape)) return shape;
      }
    }
  }
  return null;
}

export function tooltipPosition({ x, y, width, height, viewportWidth, viewportHeight }) {
  const margin = 8, offset = 14;
  const left = x + offset + width <= viewportWidth - margin ? x + offset : x - offset - width;
  const top = y + offset + height <= viewportHeight - margin ? y + offset : y - offset - height;
  return { left: Math.max(margin, Math.min(left, viewportWidth - width - margin)),
    top: Math.max(margin, Math.min(top, viewportHeight - height - margin)) };
}

// A geometric corridor, not a close timer. It lets the pointer cross the 14px
// gap and enter/select/scroll the panel without making unrelated hover sticky.
export function inTooltipCorridor(p, anchor, panelRect) {
  if (!anchor || !panelRect) return false;
  if (inside(p, panelRect)) return true;
  if (inside(anchor, panelRect)) return false;
  if (p.x < Math.min(anchor.x, panelRect.left) - 3 || p.x > Math.max(anchor.x, panelRect.right) + 3
    || p.y < Math.min(anchor.y, panelRect.top) - 3 || p.y > Math.max(anchor.y, panelRect.bottom) + 3) return false;
  const x = Math.max(panelRect.left, Math.min(anchor.x, panelRect.right));
  const y = Math.max(panelRect.top, Math.min(anchor.y, panelRect.bottom));
  const horizontal = Math.abs(x - anchor.x) >= Math.abs(y - anchor.y);
  const points = horizontal
    ? [{ x: anchor.x, y: anchor.y - 3 }, { x, y: panelRect.top }, { x, y: panelRect.bottom }, { x: anchor.x, y: anchor.y + 3 }]
    : [{ x: anchor.x - 3, y: anchor.y }, { x: panelRect.left, y }, { x: panelRect.right, y }, { x: anchor.x + 3, y: anchor.y }];
  let positive = false, negative = false;
  for (let i = 0; i < points.length; i++) {
    const a = points[i], b = points[(i + 1) % points.length];
    const cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
    if (cross > .001) positive = true;
    if (cross < -.001) negative = true;
  }
  return !(positive && negative);
}

function eventOwner(root) {
  const doc = root?.nodeType === 9 ? root : root?.ownerDocument;
  return { doc, events: doc?.addEventListener ? doc : root };
}

export function bindAppTooltips(root = globalThis.document) {
  const { doc, events } = eventOwner(root);
  if (!events?.addEventListener || !doc?.createElement) return null;
  if (owners.has(events)) { owners.get(events).refresh(); return owners.get(events); }
  const win = doc.defaultView || globalThis.window;
  const panel = doc.createElement("div");
  panel.className = "app-tooltip is-hidden";
  panel.id = `app-tooltip-${++nextId}`;
  panel.setAttribute("role", "tooltip"); panel.setAttribute("aria-hidden", "true");
  let active = null, suppressed = null, bridge = null, dragging = false;
  const cleanups = [];
  const listen = (owner, type, callback, capture = true) => {
    owner?.addEventListener?.(type, callback, capture);
    cleanups.push(() => owner?.removeEventListener?.(type, callback, capture));
  };
  const removeDescription = node => {
    const value = String(node?.getAttribute?.("aria-describedby") || "").split(/\s+/).filter(id => id && id !== panel.id).join(" ");
    if (value) node.setAttribute("aria-describedby", value); else node?.removeAttribute?.("aria-describedby");
  };
  const hide = ({ suppress = false } = {}) => {
    if (!suppress) suppressed = null;
    else if (active) suppressed = active.node;
    removeDescription(active?.node);
    active = null; bridge = null;
    panel.classList.add("is-hidden"); panel.setAttribute("aria-hidden", "true");
  };
  const viewport = () => ({ width: Number(win?.innerWidth || doc.documentElement?.clientWidth || 0),
    height: Number(win?.innerHeight || doc.documentElement?.clientHeight || 0) });
  const mount = node => {
    const dialog = node.closest?.("dialog[open]");
    const surface = dialog || doc.body || root;
    if (panel.parentElement !== surface) surface.append(panel);
    return surface;
  };
  const render = text => {
    const lines = text.split("\n");
    if (lines.length < 2) { panel.textContent = text; return; }
    const title = doc.createElement("strong"), body = doc.createElement("span");
    title.className = "app-tooltip-heading"; title.textContent = lines.shift();
    body.className = "app-tooltip-body"; body.textContent = "\n" + lines.join("\n");
    panel.replaceChildren(title, body);
  };
  const place = (anchor, keyboard = false) => {
    const view = viewport();
    const above = keyboard ? anchor.top - 14 : anchor.y - 22;
    const below = keyboard ? view.height - anchor.bottom - 14 : view.height - anchor.y - 22;
    panel.style.maxHeight = `${Math.max(1, Math.min(view.height - 16, Math.max(above, below)))}px`;
    const width = panel.offsetWidth, height = panel.offsetHeight;
    // Keyboard has no meaningful pointer coordinates; anchor below the control.
    const position = keyboard
      ? { left: Math.max(8, Math.min(anchor.left, view.width - width - 8)),
          top: Math.max(8, anchor.bottom + 6 + height <= view.height - 8 ? anchor.bottom + 6 : anchor.top - height - 6) }
      : tooltipPosition({ ...anchor, width, height, viewportWidth: view.width, viewportHeight: view.height });
    panel.style.left = `${position.left}px`; panel.style.top = `${position.top}px`;
  };
  const paint = node => Object.assign(panel.style, resolveTooltipColors(node, {
    dark: doc.documentElement?.getAttribute?.("data-theme") === "dark",
    getStyle: win?.getComputedStyle?.bind(win),
  }));
  const show = (node, event, keyboard = false) => {
    if (!node || node.isConnected === false || dragging || Number(event.buttons || 0) !== 0) return;
    if (node === suppressed || node.closest?.(".settings-help.is-open")) return;
    const text = payload(node); if (!text) return;
    if (active?.node === node) return; // Stable placement, including child/label traversal.
    hide(); suppressed = null;
    const surface = mount(node);
    render(text); paint(node);
    panel.classList.remove("is-hidden"); panel.setAttribute("aria-hidden", "false");
    const existing = String(node.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    node.setAttribute("aria-describedby", [...new Set([...existing, panel.id])].join(" "));
    const anchor = keyboard ? rect(node) || { left: 8, top: 8, bottom: 8 } : point(event);
    active = { node, text, keyboard, anchor, surface };
    bridge = keyboard ? null : anchor;
    place(anchor, keyboard);
  };
  const refresh = () => {
    if (suppressed?.isConnected === false) suppressed = null;
    if (!active) return;
    if (active.node.isConnected === false || !contains(active.surface, active.node)
      || active.surface.matches?.("dialog:not([open])") || active.node.closest?.(".settings-help.is-open")) return hide();
    const text = payload(active.node);
    if (!text) return hide();
    if (text !== active.text) { active.text = text; render(text); place(active.anchor, active.keyboard); }
    paint(active.node);
  };
  const pointer = event => {
    if (contains(panel, event.target)) return;
    if (Number(event.buttons || 0) !== 0) { dragging = true; hide({ suppress: true }); return; }
    const node = findAppTooltipTarget(event.target);
    if (node) {
      if (active?.node === node) { bridge = point(event); return; }
      if (node !== suppressed) show(node, event);
      return;
    }
    suppressed = null;
    if (active && !inTooltipCorridor(point(event), bridge, rect(panel))) hide();
  };
  listen(events, "pointerover", pointer);
  listen(events, "pointermove", pointer);
  listen(events, "pointerout", event => {
    if (contains(panel, event.relatedTarget) || contains(active?.node, event.relatedTarget)) return;
    if (contains(panel, event.target) && contains(panel, event.relatedTarget)) return;
    if (suppressed && contains(suppressed, event.target)) suppressed = null;
    if (!active) return;
    if (event.relatedTarget == null) return hide();
    const next = findAppTooltipTarget(event.relatedTarget);
    if (next === active.node) return;
    if (next && next !== active.node) { hide(); return; }
    if (!inTooltipCorridor(point(event), bridge, rect(panel))) hide();
  });
  listen(events, "pointerdown", event => {
    if (!contains(panel, event.target)) { dragging = Number(event.buttons || 0) !== 0; hide({ suppress: true }); }
  });
  listen(events, "pointerup", event => {
    dragging = false;
    if (!contains(panel, event.target)) { hide({ suppress: true }); suppressed = findAppTooltipTarget(event.target); }
  });
  listen(events, "pointercancel", () => { dragging = false; hide({ suppress: true }); });
  for (const type of ["click", "contextmenu", "dragstart"]) listen(events, type, event => {
    if (!contains(panel, event.target)) hide({ suppress: true });
  });
  listen(events, "focusin", event => show(findAppTooltipTarget(event.target), event, true));
  listen(events, "focusout", event => {
    if (contains(suppressed, event.target) && !contains(suppressed, event.relatedTarget)) suppressed = null;
    if (active?.keyboard && !contains(active.node, event.relatedTarget) && !contains(panel, event.relatedTarget)) hide();
  });
  listen(events, "keydown", event => { if (event.key === "Escape") hide({ suppress: true }); });
  listen(events, "scroll", event => { if (!contains(panel, event.target)) hide({ suppress: true }); });
  listen(events, "visibilitychange", () => { if (doc.hidden) hide({ suppress: true }); });
  // A newly opened native modal is a separate top-layer owner, never a z-index contest.
  listen(events, "close", event => { if (active?.surface === event.target) hide(); });
  for (const type of ["blur", "resize", "gpm-next:route-refresh"]) listen(win, type, () => { dragging = false; hide({ suppress: true }); }, false);
  const generatedLabels = new WeakMap();
  const describe = scope => {
    const descriptions = [...(scope?.querySelectorAll?.("desc[data-app-tooltip-source]") || [])];
    if (scope?.matches?.("desc[data-app-tooltip-source]")) descriptions.push(scope);
    for (const desc of descriptions) {
      const node = desc.parentElement, existing = node?.getAttribute("aria-label");
      if (node && (!existing || existing === generatedLabels.get(node))) {
        node.setAttribute("aria-label", desc.textContent); generatedLabels.set(node, desc.textContent);
      }
    }
  };
  describe(doc);
  const Observer = win?.MutationObserver;
  const observer = Observer ? new Observer(records => {
    let changed = false;
    for (const record of records) {
      if (contains(panel, record.target)) continue;
      changed = true;
      for (const added of record.addedNodes || []) describe(added);
      if (record.type === "characterData") describe(record.target.parentElement);
      if (record.attributeName === "data-theme") hide();
      if (record.attributeName === "open" && record.target.open && active && !contains(record.target, active.node)) hide();
    }
    if (changed) refresh();
  }) : null;
  observer?.observe(doc.documentElement, { subtree: true, childList: true, characterData: true, attributes: true,
    attributeFilter: [...ATTRIBUTES, "data-theme", "open", "class", "style"] });
  const owner = { panel, hide, refresh, destroy() {
    hide(); observer?.disconnect(); for (const cleanup of cleanups) cleanup(); panel.remove?.(); owners.delete(events);
  } };
  owners.set(events, owner);
  return owner;
}

export function hideAppTooltips(root = globalThis.document) {
  const { events } = eventOwner(root); owners.get(events)?.hide();
}
