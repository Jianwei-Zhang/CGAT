export function createScopePopoverFixture() {
  const events = new Map(), documentEvents = new Map(), windowEvents = new Map();
  const add = (map, type, fn) => { const list = map.get(type) || []; list.push(fn); map.set(type, list); };
  const regions = {}, triggers = {}, panels = {}, nodes = new Map();
  const win = { innerWidth: 1000, innerHeight: 700, addEventListener: (t, f) => add(windowEvents, t, f), removeEventListener() {} };
  const doc = { defaultView: win, addEventListener: (t, f) => add(documentEvents, t, f), removeEventListener() {} };
  for (const [kind, triggerSelector, panelSelector] of [["chromosomes", "#assembly-chr-picker-toggle", "#assembly-chr-picker-panel"],
    ["members", "[data-members-card-toggle='1']", "#assembly-members-panel-popover"]]) {
    const region = { classList: { toggle() {} }, contains: node => node?.region === kind };
    regions[kind] = region;
    const trigger = { region: kind, disabled: false, attrs: {}, focusCount: 0, ownerDocument: doc,
      getBoundingClientRect: () => ({ left: 100, right: 300, top: 100, bottom: 130 }),
      setAttribute(key, value) { this.attrs[key] = value; }, querySelector: () => null,
      closest: selector => selector === triggerSelector ? trigger : selector === ".assembly-members-panel" ? region : null,
      focus() { this.focusCount++; } };
    const panel = { region: kind, style: {}, hidden: true, scrollTop: 75, scrollHeight: 200,
      getBoundingClientRect: () => ({ width: 500, height: 200 }) };
    triggers[kind] = trigger; panels[kind] = panel;
    nodes.set(triggerSelector, trigger); nodes.set(panelSelector, panel); nodes.set(`[data-assembly-popup="${kind}"]`, region);
  }
  const host = { ownerDocument: doc, isConnected: true, closest() { return this; },
    querySelector: selector => nodes.get(selector) || null, querySelectorAll: () => [],
    addEventListener: (t, f) => add(events, t, f), contains: () => true };
  const emit = (type, target, extra = {}, map = events) => {
    const event = { target, preventDefault() { this.defaultPrevented = true; }, ...extra };
    map.get(type)?.forEach(fn => fn(event)); return event;
  };
  const child = kind => ({ region: kind, closest: () => null });
  return { host, triggers, panels, regions, events, documentEvents, windowEvents, nodes, emit, child };
}

export function withPopoverClock(run) {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const timers = new Map(); let id = 0;
  globalThis.setTimeout = (fn, delay) => { timers.set(++id, { fn, delay }); return id; };
  globalThis.clearTimeout = key => timers.delete(key);
  try { return run(timers); } finally { globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
}
