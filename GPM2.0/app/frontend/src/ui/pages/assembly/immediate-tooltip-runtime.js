// Final Path has no hover dwell time. This delegated surface does not select,
// persist, rebuild a graph, or interfere with the existing pointer/drag owners.
const BOUND = Symbol("immediateTooltipsBound");

export function bindImmediateTooltips(host, { attribute, className }) {
  const TARGET = `[${attribute}]`;
  host = host?.closest?.("#route-host") || host;
  if (host?.[BOUND]?.has(attribute)) {
    host[BOUND].get(attribute).refresh();
    return;
  }
  if (!host?.addEventListener || !host.ownerDocument?.createElement) return;
  host[BOUND] ||= new Map();
  const doc = host.ownerDocument;
  const win = doc.defaultView || globalThis.window;
  const tooltip = doc.createElement("div");
  tooltip.className = `subview-band-tooltip ${className} is-hidden`;
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
    const text = node.getAttribute(attribute) || "";
    if (!text) return hide();
    if (!host.contains(tooltip)) host.append(tooltip);
    active = node;
    tooltip.textContent = text;
    tooltip.classList.remove("is-hidden");
    tooltip.setAttribute("aria-hidden", "false");
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
  const destroy = () => {
    hide(); tooltip.remove?.();
    win?.removeEventListener?.("scroll", onViewportChange, true);
    win?.removeEventListener?.("resize", onViewportChange);
  };
  const onViewportChange = () => {
    if (host.isConnected === false) destroy(); else hide();
  };
  win?.addEventListener?.("scroll", onViewportChange, true);
  win?.addEventListener?.("resize", onViewportChange);
  host[BOUND].set(attribute, { hide, destroy, refresh() { if (active?.isConnected === false) hide(); } });
}

export function hideImmediateTooltips(host, attribute) {
  const owners = (host?.closest?.("#route-host") || host)?.[BOUND];
  if (attribute) owners?.get(attribute)?.hide();
  else for (const owner of owners?.values() || []) owner.hide();
}

export function destroyImmediateTooltips(host) {
  const root = host?.closest?.("#route-host") || host;
  for (const owner of root?.[BOUND]?.values() || []) owner.destroy();
}
