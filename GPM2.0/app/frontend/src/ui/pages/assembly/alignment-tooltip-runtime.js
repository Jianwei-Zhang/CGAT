// One delegated owner covers main/local bands and GRT overlays, including
// evidence nodes replaced in place without rebuilding their scroll container.
const BOUND = Symbol("alignmentTooltipBound");
const TARGET = "[data-subview-band-tooltip]";

function alignmentTooltipTone(node) {
  if (node?.matches?.(".track-collinearity-band")) {
    // Unknown identity is painted gray, not a measured blue/orange band.
    if (node.getAttribute("data-band-identity-pct") === "") return "neutral";
    return node.matches(".is-companion") ? "companion" : "primary";
  }
  if (node?.matches?.(".grt-display-evidence-band.is-mummer")) return "purple";
  if (node?.matches?.(".grt-display-evidence-band.is-minimap2")) return "teal";
  if (node?.matches?.(".grt-result-hover-proxy")) {
    return node.closest?.(".is-gap") ? "neutral" : "green";
  }
  return "neutral";
}

export function bindAlignmentTooltips(host, { createCoordinator, timerApi = globalThis } = {}) {
  host = host?.closest?.("#route-host") || host;
  if (!host?.addEventListener || host[BOUND] || !host.ownerDocument?.createElement) return;
  const tooltip = host.ownerDocument.createElement("div");
  tooltip.className = "subview-band-tooltip alignment-band-tooltip is-hidden";
  tooltip.setAttribute("role", "tooltip");
  tooltip.setAttribute("aria-hidden", "true");
  host.append(tooltip);
  const hide = () => { tooltip.classList.add("is-hidden"); tooltip.setAttribute("aria-hidden", "true"); };
  const show = ({ token, text, point }) => {
    if (token?.isConnected === false || host.isConnected === false) return hide();
    // A route rerender removes the previous panel but not the delegated owner.
    if (!host.contains(tooltip)) host.append(tooltip);
    tooltip.setAttribute("data-alignment-tone", alignmentTooltipTone(token));
    tooltip.textContent = text;
    tooltip.classList.remove("is-hidden");
    tooltip.setAttribute("aria-hidden", "false");
    const doc = host.ownerDocument, win = doc.defaultView || globalThis.window;
    const width = Number(win?.innerWidth || doc.documentElement?.clientWidth || 0);
    const height = Number(win?.innerHeight || doc.documentElement?.clientHeight || 0);
    tooltip.style.left = `${Math.max(8, Math.min(point.x + 14, width - tooltip.offsetWidth - 8))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(point.y + 14, height - tooltip.offsetHeight - 8))}px`;
  };
  const coordinator = createCoordinator({
    setTimeoutFn: timerApi.setTimeout.bind(timerApi), clearTimeoutFn: timerApi.clearTimeout.bind(timerApi),
    onShow: show, onMove: show, onHide: hide,
  });
  const target = event => event.target?.closest?.(TARGET);
  const context = (node, event) => ({ token: node,
    text: String(node.getAttribute("data-subview-band-tooltip") || "").replaceAll(" | ", "\n").replaceAll(" · ", "\n"),
    point: { x: Number(event.clientX || 0), y: Number(event.clientY || 0) },
  });
  host.addEventListener("pointerover", event => {
    const node = target(event);
    if (node && !node.contains?.(event.relatedTarget)) coordinator.enter(context(node, event));
  });
  host.addEventListener("pointermove", event => {
    const node = target(event); if (node) coordinator.move(context(node, event));
  });
  host.addEventListener("pointerout", event => {
    const node = target(event); if (node && !node.contains?.(event.relatedTarget)) coordinator.leave(node);
  });
  for (const type of ["scroll", "pointerdown", "contextmenu", "keydown"]) host.addEventListener(type, () => coordinator.hide(), true);
  host[BOUND] = coordinator;
}
