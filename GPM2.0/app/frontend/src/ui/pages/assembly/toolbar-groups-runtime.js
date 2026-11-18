import { placeAnchoredPanel, clearAnchoredPanelPlacement } from "./anchored-panel-placement.js";

const BOUND = Symbol("toolbarGroups");
const TOOLBARS = "[data-main-track-toolbar], [data-subview-toolbar]";
const GROUP = "[data-toolbar-group]";

// Prefer direct access to display/filter controls. Compact whole groups only;
// the very narrow fallback is horizontal scrolling, never truncated controls.
export function resolveCompactToolbarGroups(available, groups, gap = 8) {
  let width = groups.reduce((sum, group) => sum + group.width, 0) + Math.max(0, groups.length - 1) * gap;
  const compact = [];
  for (const kind of ["edit", "filter", "display"]) {
    if (width <= available) break;
    const group = groups.find(item => item.kind === kind);
    if (!group || group.width <= group.compactWidth) continue;
    width -= group.width - group.compactWidth;
    compact.push(kind);
  }
  return compact;
}

export function bindToolbarGroups(host) {
  if (host?.[BOUND]) { host[BOUND].refresh(); return host[BOUND].destroy; }
  if (!host?.querySelectorAll || !host.addEventListener) return () => {};
  if (!host.querySelectorAll(GROUP).length) return () => {};
  const win = host.ownerDocument?.defaultView;
  let observer;
  const groups = () => [...host.querySelectorAll(GROUP)];
  const panel = group => group.querySelector("[data-toolbar-group-content]");
  const trigger = group => group.querySelector("[data-toolbar-group-toggle]");
  const close = (group, focus = false) => {
    if (focus) trigger(group)?.focus();
    group.removeAttribute("data-toolbar-group-open");
    trigger(group)?.setAttribute("aria-expanded", group.hasAttribute("data-toolbar-compact") ? "false" : "true");
    clearAnchoredPanelPlacement(panel(group));
  };
  const position = () => {
    for (const group of groups()) if (group.hasAttribute("data-toolbar-group-open")) {
      placeAnchoredPanel(trigger(group), panel(group), { preferredWidth: 320, matchAnchorWidth: false });
    }
  };
  const layout = () => {
    for (const toolbar of host.querySelectorAll(TOOLBARS)) {
      if (!toolbar.clientWidth) continue;
      const children = [...toolbar.children];
      const ownGroups = children.filter(child => child.matches(GROUP));
      if (!ownGroups.length) continue;
      // Measure the same live controls expanded, then apply the final state in
      // this synchronous turn. No clones, changed field values or DOM reparenting.
      for (const group of ownGroups) {
        group.removeAttribute("data-toolbar-compact");
        clearAnchoredPanelPlacement(panel(group));
      }
      const gap = parseFloat(win?.getComputedStyle?.(toolbar)?.columnGap) || 8;
      const extras = children.filter(child => !child.matches(GROUP)).reduce((sum, child) => sum + child.getBoundingClientRect().width + gap, 0);
      const metrics = ownGroups.map(group => ({ kind: group.dataset.toolbarGroup,
        width: group.getBoundingClientRect().width,
        compactWidth: trigger(group).getBoundingClientRect().width + 24 }));
      const compact = resolveCompactToolbarGroups(toolbar.clientWidth - extras, metrics, gap);
      for (const group of ownGroups) {
        const collapsed = compact.includes(group.dataset.toolbarGroup);
        group.toggleAttribute("data-toolbar-compact", collapsed);
        if (!collapsed) close(group);
        else {
          trigger(group).setAttribute("aria-expanded", String(group.hasAttribute("data-toolbar-group-open")));
          if (!group.hasAttribute("data-toolbar-group-open") && panel(group).contains(host.ownerDocument?.activeElement)) trigger(group).focus();
        }
      }
    }
    position();
  };
  const click = event => {
    const button = event.target?.closest?.("[data-toolbar-group-toggle]");
    const group = button?.closest(GROUP);
    if (!group?.hasAttribute("data-toolbar-compact")) return;
    const open = !group.hasAttribute("data-toolbar-group-open");
    groups().forEach(item => close(item));
    if (open) {
      group.setAttribute("data-toolbar-group-open", "");
      button.setAttribute("aria-expanded", "true");
      position();
    }
  };
  const outside = event => {
    for (const group of groups()) if (!group.contains(event.target)) close(group);
  };
  const keydown = event => {
    if (event.key !== "Escape") return;
    const group = event.target?.closest?.(GROUP);
    // Let an open child picker handle Escape before closing its parent group.
    if (!group?.hasAttribute("data-toolbar-group-open") || event.target?.closest?.(".assembly-track-combo.is-open, .grt-result-layer-menu[open]")) return;
    close(group, true);
    event.preventDefault();
  };
  const refresh = () => {
    observer?.disconnect();
    for (const toolbar of host.querySelectorAll(TOOLBARS)) observer?.observe(toolbar);
    layout();
  };
  const destroy = () => {
    observer?.disconnect();
    host.removeEventListener("click", click);
    host.removeEventListener("keydown", keydown);
    host.removeEventListener("scroll", position, true);
    host.ownerDocument?.removeEventListener?.("pointerdown", outside, true);
    win?.removeEventListener("resize", layout);
    win?.removeEventListener("scroll", position, true);
    host.ownerDocument?.fonts?.removeEventListener?.("loadingdone", layout);
    delete host[BOUND];
  };
  if (win?.ResizeObserver) observer = new win.ResizeObserver(layout);
  host.addEventListener("click", click);
  host.addEventListener("keydown", keydown);
  host.addEventListener("scroll", position, true);
  host.ownerDocument?.addEventListener?.("pointerdown", outside, true);
  win?.addEventListener("resize", layout);
  win?.addEventListener("scroll", position, true);
  host.ownerDocument?.fonts?.addEventListener?.("loadingdone", layout);
  host[BOUND] = { refresh, destroy };
  refresh();
  return destroy;
}
