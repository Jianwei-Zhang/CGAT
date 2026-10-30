import { FLOATING_MENU_CLOSE_DELAY_MS } from "../floating-menu-runtime.js";
import { placeAnchoredPanel, clearAnchoredPanelPlacement } from "./anchored-panel-placement.js";
import { bindImmediateTooltips } from "./immediate-tooltip-runtime.js";

const BOUND = Symbol("assemblyScopePopovers");
const config = {
  chromosomes: { trigger: "#assembly-chr-picker-toggle", panel: "#assembly-chr-picker-panel", width: 720 },
  members: { trigger: "[data-members-card-toggle='1']", panel: "#assembly-members-panel-popover", width: 820 },
};

// Trim only unused trailing space after the normal width-limited flex layout.
// Measuring the widest occupied row preserves card widths, order and wrapping;
// never use the full-width deleted-group separator as an occupied card edge.
export function resolveMembersPopoverWidth({ panelRect, gridRect, contentRects = [], scrollbarWidth = 0 }) {
  const width = Number(panelRect?.width), left = Number(panelRect?.left);
  if (!(width > 0) || !Number.isFinite(left)) return null;
  const right = contentRects.reduce((edge, rect) => {
    const value = Number(rect?.right);
    return Number.isFinite(value) ? Math.max(edge, value) : edge;
  }, left);
  if (right <= left) return width;
  const inset = Math.max(0, (Number(gridRect?.left) || left) - left);
  return Math.min(width, Math.ceil(right - left + inset
    + Math.max(0, Number(scrollbarWidth) || 0) + 2));
}

function fitMembersPopover(trigger, panel, initialWidth) {
  const grid = panel.querySelector?.(".ctg-chip-grid");
  const content = panel.querySelectorAll?.(".ctg-chip, .assembly-members-popover-tools > *");
  if (!grid?.getBoundingClientRect || !content?.length) return;
  const width = resolveMembersPopoverWidth({ panelRect: panel.getBoundingClientRect(),
    gridRect: grid.getBoundingClientRect(),
    contentRects: [...content].map(node => node.getBoundingClientRect()),
    scrollbarWidth: Math.max(0, (grid.offsetWidth || 0) - (grid.clientWidth || 0)),
  });
  if (width && width < initialWidth) {
    placeAnchoredPanel(trigger, panel, { preferredWidth: width, matchAnchorWidth: false });
  }
}

// One delegated owner survives section patches. Toggles only hidden/aria/state;
// they never re-render, reparent content, load a chromosome or move a plot.
export function bindAssemblyScopePopovers(host, store, { persistMembers } = {}) {
  host = host?.closest?.("#route-host") || host;
  if (!host?.addEventListener || !host.querySelector) return;
  if (host[BOUND]) { host[BOUND].refresh(); return host[BOUND]; }
  const doc = host.ownerDocument, win = doc?.defaultView || globalThis.window;
  const timers = new Map();
  let memberLeaveAfterGesture = false;
  let scope = JSON.stringify([store.getState().session?.workspacePath, store.getState().session?.projectId]);
  const isOpen = kind => kind === "members"
    ? store.getState().assembly?.membersCardCollapsed === false && !store.getState().assembly?.loading
    : store.getState().assembly?.chrPickerOpen === true;
  const cancel = kind => {
    const timer = timers.get(kind);
    if (timer) clearTimeout(timer);
    timers.delete(kind);
  };
  const paint = kind => {
    const c = config[kind], trigger = host.querySelector(c.trigger), panel = host.querySelector(c.panel);
    if (!trigger || !panel) return;
    const open = isOpen(kind);
    panel.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    const chevron = trigger.querySelector?.("[data-popup-chevron]");
    if (chevron) chevron.textContent = open ? "▴" : "▾";
    if (kind === "members") trigger.closest?.(".assembly-members-panel")?.classList.toggle("is-collapsed", !open);
    if (open) {
      const placed = placeAnchoredPanel(trigger, panel, { preferredWidth: c.width, matchAnchorWidth: false });
      if (kind === "members" && placed) fitMembersPopover(trigger, panel, placed.width);
    } else clearAnchoredPanelPlacement(panel);
  };
  const setOpen = (kind, open, restoreFocus = false) => {
    cancel(kind);
    if (kind === "members" && !open) memberLeaveAfterGesture = false;
    const state = store.getState();
    if (isOpen(kind) !== open) {
      store.setState({ ...state, assembly: { ...state.assembly,
        ...(kind === "members" ? { membersCardCollapsed: !open } : { chrPickerOpen: open }) } });
      if (kind === "members") void persistMembers?.(host, store);
    }
    paint(kind);
    if (restoreFocus) host.querySelector(config[kind].trigger)?.focus?.({ preventScroll: true });
  };
  const region = (node, kind) => Boolean(node && (
    host.querySelector(`[data-assembly-popup="${kind}"]`)?.contains?.(node)
    || (kind === "members" && node.closest?.("#assembly-context-menu[data-members-popover-owner='1']:not(.is-hidden)"))
  ));
  const schedule = kind => {
    cancel(kind);
    if (!isOpen(kind)) return;
    const scheduledScope = JSON.stringify([store.getState().session?.workspacePath, store.getState().session?.projectId]);
    timers.set(kind, setTimeout(() => {
      timers.delete(kind);
      const currentScope = JSON.stringify([store.getState().session?.workspacePath, store.getState().session?.projectId]);
      if (host.isConnected !== false && currentScope === scheduledScope) setOpen(kind, false);
    }, FLOATING_MENU_CLOSE_DELAY_MS));
  };
  const refresh = () => {
    const nextScope = JSON.stringify([store.getState().session?.workspacePath, store.getState().session?.projectId]);
    if (scope !== nextScope) { for (const kind of Object.keys(config)) cancel(kind); scope = nextScope; }
    for (const kind of Object.keys(config)) { if (!isOpen(kind)) cancel(kind); paint(kind); }
    bindImmediateTooltips(host);
  };
  const onOutside = event => {
    if (host.isConnected === false) return destroy();
    for (const kind of Object.keys(config)) if (isOpen(kind) && !region(event.target, kind)) setOpen(kind, false);
  };
  const reposition = () => {
    if (host.isConnected === false) return destroy();
    for (const kind of Object.keys(config)) if (isOpen(kind)) paint(kind);
  };
  const onGestureEnd = event => {
    if (!memberLeaveAfterGesture) return;
    memberLeaveAfterGesture = false;
    if (!region(event.target, "members")) schedule("members");
  };
  const onViewportScroll = event => { if (!host.contains?.(event.target)) reposition(); };
  const destroy = () => {
    for (const kind of Object.keys(config)) cancel(kind);
    doc?.removeEventListener?.("pointerdown", onOutside, true);
    win?.removeEventListener?.("resize", reposition);
    win?.removeEventListener?.("scroll", onViewportScroll, true);
    win?.removeEventListener?.("pointerup", onGestureEnd);
    win?.removeEventListener?.("pointercancel", onGestureEnd);
    delete host[BOUND];
  };
  host.addEventListener("click", event => {
    for (const [kind, c] of Object.entries(config)) {
      const trigger = event.target?.closest?.(c.trigger);
      if (!trigger || trigger.disabled) continue;
      event.preventDefault(); setOpen(kind, !isOpen(kind)); return;
    }
  });
  host.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    for (const kind of Object.keys(config)) if (isOpen(kind)) {
      event.preventDefault(); setOpen(kind, false, region(event.target, kind));
    }
  });
  host.addEventListener("pointerover", event => {
    for (const kind of Object.keys(config)) if (region(event.target, kind)) {
      cancel(kind); if (kind === "members") memberLeaveAfterGesture = false;
    }
  });
  host.addEventListener("pointerout", event => {
    for (const kind of Object.keys(config)) if (region(event.target, kind) && !region(event.relatedTarget, kind)) {
      if (kind === "members" && host.querySelector(".assembly-member-chip-region[data-member-marquee-active='1']")) {
        cancel(kind); memberLeaveAfterGesture = true;
      } else schedule(kind);
    }
  });
  host.addEventListener("scroll", reposition, true);
  doc?.addEventListener?.("pointerdown", onOutside, true);
  win?.addEventListener?.("resize", reposition);
  win?.addEventListener?.("scroll", onViewportScroll, true);
  win?.addEventListener?.("pointerup", onGestureEnd);
  win?.addEventListener?.("pointercancel", onGestureEnd);
  const owner = { refresh, destroy, setOpen }; host[BOUND] = owner;
  refresh(); return owner;
}

export function destroyAssemblyScopePopovers(host) {
  (host?.closest?.("#route-host") || host)?.[BOUND]?.destroy();
}
