// Final Path has no hover dwell time. This delegated surface does not select,
// persist, rebuild a graph, or interfere with the existing pointer/drag owners.
const BOUND = Symbol("finalPathTooltipBound");
const TARGET = "[data-final-path-tooltip]";

export function bindFinalPathTooltips(host) {
  host = host?.closest?.("#route-host") || host;
  if (host?.[BOUND]) {
    host[BOUND].refresh();
    return;
  }
  if (!host?.addEventListener || !host.ownerDocument?.createElement) return;
  const doc = host.ownerDocument;
  const tooltip = doc.createElement("div");
  tooltip.className = "subview-band-tooltip final-path-tooltip is-hidden";
  tooltip.setAttribute("role", "tooltip");
  tooltip.setAttribute("aria-hidden", "true");
  let active = null;
  const hide = () => {
    active = null;
    tooltip.classList.add("is-hidden");
    tooltip.setAttribute("aria-hidden", "true");
  };
  const show = (node, event) => {
    if (!node || Number(event.buttons || 0) !== 0 || node.isConnected === false || host.isConnected === false) return hide();
    const text = node.getAttribute("data-final-path-tooltip") || "";
    if (!text) return hide();
    if (!host.contains(tooltip)) host.append(tooltip);
    active = node;
    tooltip.textContent = text;
    tooltip.classList.remove("is-hidden");
    tooltip.setAttribute("aria-hidden", "false");
    const win = doc.defaultView || globalThis.window;
    const width = Number(win?.innerWidth || doc.documentElement?.clientWidth || 0);
    const height = Number(win?.innerHeight || doc.documentElement?.clientHeight || 0);
    tooltip.style.left = `${Math.max(8, Math.min(Number(event.clientX || 0) + 14, width - tooltip.offsetWidth - 8))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(Number(event.clientY || 0) + 14, height - tooltip.offsetHeight - 8))}px`;
  };
  const target = event => event.target?.closest?.(TARGET);
  host.addEventListener("pointerover", event => {
    const node = target(event);
    if (node && !node.contains?.(event.relatedTarget)) show(node, event);
  });
  host.addEventListener("pointermove", event => {
    const node = target(event);
    if (node && node === active) show(node, event);
  });
  host.addEventListener("pointerout", event => {
    const node = target(event);
    if (node === active && !node?.contains?.(event.relatedTarget)) hide();
  });
  host.addEventListener("pointerup", event => {
    const node = target(event); if (node) show(node, event);
  });
  for (const type of ["scroll", "pointerdown", "pointercancel", "contextmenu", "keydown"]) {
    host.addEventListener(type, hide, true);
  }
  host[BOUND] = { hide, refresh() { if (active?.isConnected === false) hide(); } };
}

export function hideFinalPathTooltips(host) {
  (host?.closest?.("#route-host") || host)?.[BOUND]?.hide();
}
