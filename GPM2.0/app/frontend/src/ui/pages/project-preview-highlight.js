const PART = "[data-preview-part-key][data-final-path-kind='ctg']";
const KEY = "[data-preview-part-key]";
const CARD = "[data-preview-chr]";
const HIGHLIGHT = "data-preview-highlighted";

// Paint-only, card-scoped correlation. Part keys come from the model's path
// name and index, never a contig label, dataset guess or display coordinate.
export function createProjectPreviewHighlight(host, { active }) {
  let running = false, selected = null;
  const clear = (card = null) => {
    if (card && selected?.card !== card) return;
    for (const node of selected?.nodes || []) node.removeAttribute(HIGHLIGHT);
    selected = null;
  };
  const target = node => {
    const part = node?.closest?.(PART), card = part?.closest?.(CARD);
    return part && card && host.contains(part)
      ? { card, key: part.getAttribute("data-preview-part-key") } : null;
  };
  const select = event => {
    if (!running || !active() || event.pointerType === "touch") { clear(); return; }
    const next = target(event.target);
    if (!next) {
      if (event.type === "focusin" || selected?.trigger !== "focus") clear();
      return;
    }
    const trigger = event.type === "focusin" ? "focus" : "hover";
    if (selected?.card === next.card && selected.key === next.key) {
      if (trigger === "focus" || selected.trigger !== "focus") selected.trigger = trigger;
      return;
    }
    clear();
    const nodes = [...next.card.querySelectorAll(KEY)]
      .filter(node => node.getAttribute("data-preview-part-key") === next.key);
    for (const node of nodes) node.setAttribute(HIGHLIGHT, "1");
    selected = { ...next, nodes, trigger };
  };
  const leave = event => {
    if (!selected || selected.trigger !== (event.type === "focusout" ? "focus" : "hover")) return;
    const next = target(event.relatedTarget);
    if (next?.card === selected.card && next.key === selected.key) return;
    clear();
  };
  const leaveHost = () => { if (selected?.trigger === "hover") clear(); };
  const cancel = () => clear();
  const escape = event => { if (event.key === "Escape") clear(); };
  const doc = host.ownerDocument, win = doc?.defaultView;
  const listeners = [
    [host, "pointerover", select], [host, "pointerout", leave],
    [host, "focusin", select], [host, "focusout", leave],
    [host, "pointerleave", leaveHost], [host, "pointercancel", cancel],
    [host, "pointerdown", cancel], [doc, "keydown", escape],
    [doc, "scroll", leaveHost, true], [win, "blur", cancel], [win, "resize", cancel],
  ];
  return {
    clear,
    start() {
      if (running) return;
      running = true;
      for (const [node, name, fn, capture] of listeners) node?.addEventListener?.(name, fn, capture);
    },
    stop() {
      running = false;
      clear();
      for (const [node, name, fn, capture] of listeners) node?.removeEventListener?.(name, fn, capture);
    },
  };
}
