// Resize has a chart boundary, not a route boundary. The already-rebased
// measured/world viewport is used to render geometry, while all surrounding
// control, popup, navigation and table-editor owners remain mounted.
export function refreshViewportGeometry(host, store, { resolveRouteHost, renderPage, bindGraph, syncViewport, syncInteractions }) {
  const state = store.getState();
  if (state.activeRoute && state.activeRoute !== "assembly") return;
  const root = resolveRouteHost(host), doc = root?.ownerDocument;
  if (!doc?.createElement || state.assembly?.loading) return;
  const plots = [
    [".assembly-track-unified .assembly-track-layout:not(.subview-track-layout)", "main"],
    [".subview-track-layout", "subview"],
    ["[data-final-path-graph-viewport]", "final-path"],
  ];
  const collect = (parent, selector) => {
    const nodes = Array.from(parent.querySelectorAll?.(selector) || []);
    return nodes.length ? nodes : [parent.querySelector?.(selector)].filter(Boolean);
  };
  const identity = (node, scope) => scope === "final-path"
    ? node.closest?.("[data-final-path-all-card]")?.dataset.finalPathAllCard
      || node.closest?.("[data-final-path-target-chr-name]")?.dataset.finalPathTargetChrName || "single"
    : scope;
  const finalPathScroll = new Map(collect(root, "[data-final-path-graph-viewport]").map(node => [identity(node, "final-path"),
    { left: Number(node.scrollLeft || 0), top: Number(node.scrollTop || 0) }]));
  let mounted = [];
  // Replace all stale-scale geometry before any global navigation can inspect
  // it. One correction pass accommodates a changed plot gutter/scrollbar width.
  for (let pass = 0; pass < 2; pass++) {
    const template = doc.createElement("template");
    template.innerHTML = renderPage(store.getState());
    mounted = [];
    for (const [selector, scope] of plots) {
      const incoming = new Map(collect(template.content, selector).map(node => [identity(node, scope), node]));
      for (const current of collect(root, selector)) {
        const next = incoming.get(identity(current, scope));
        if (!next) continue;
        current.replaceWith(next); mounted.push({ node: next, scope });
      }
    }
    if (!syncViewport(root, store)) break;
  }
  // All mode has one graph per path, not one positional slot. Keep each live
  // path's own scroll without adding a new persisted viewport schema.
  for (const { node, scope } of mounted) {
    if (scope === "final-path") {
      const scroll = finalPathScroll.get(identity(node, scope));
      if (scroll) { node.scrollLeft = scroll.left; node.scrollTop = scroll.top; }
    }
    bindGraph(node, store, scope);
  }
  syncInteractions(root, store);
}
