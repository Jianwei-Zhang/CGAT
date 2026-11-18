import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ALL_PARTITIONS, buildAssemblyNavigationModel, renderAssemblyNavigation, assemblyNavigationShouldStack,
  assemblyNavigationBusy, bindAssemblyNavigation, syncAssemblyNavigation } from "../assembly-navigation.js";
import { saveProjectLibrary } from "../../../services/project-library.js";
import { writeWorkspaceHistory } from "../../../services/workspace-history.js";

const library = { version: 1, collapsed: [], partitions: [
  { id: "plants", name: "植物", parentId: "" }, { id: "rice", name: "水稻", parentId: "plants" },
  { id: "maize", name: "玉米", parentId: "plants" }, { id: "empty", name: "空分区", parentId: "" },
] };
const records = [{ path: "/rice", projectName: "mh63", partitionId: "rice" },
  { path: "/rice2", projectName: "zh97", partitionId: "rice" }, { path: "/maize", projectName: "B73", partitionId: "maize" },
  { path: "/legacy", projectName: "Legacy" }];
const state = (partitionId = null, locale = "zh") => ({ activeRoute: "assembly", locale, session: { workspacePath: "/rice", projectId: 1, projectName: "mh63" },
  importer: {}, initializer: {}, assembly: { selectedChrName: "Chr1", chromosomes: [{ chrName: "Chr1", ctgCount: 4, placedBp: 2500000 }, { chrName: "unplaced", ctgCount: 2, placedBp: 0 }] },
  assemblyNavigation: { workspacePath: "/rice", partitionId, busy: false },
});
const model = (s = state()) => buildAssemblyNavigationModel(s, library, records);

test("initial navigation reflects current partition, parent filters include descendants, all and unpartitioned work", () => {
  assert.equal(model().filter, "rice");
  assert.deepEqual(model().projects.map(item => item.value), ["/rice", "/rice2"]);
  assert.deepEqual(new Set(model(state("plants")).projects.map(item => item.value)), new Set(["/maize", "/rice", "/rice2"]));
  assert.equal(model(state(ALL_PARTITIONS)).projects.length, 4);
  const unassigned = model(state(""));
  assert.equal(unassigned.projects.find(item => item.selected).value, "/rice");
  assert.match(unassigned.projects[0].description, /当前组装/);
  assert.ok(unassigned.projects.some(item => item.value === "/legacy"));
  assert.equal(model().partitions.find(item => item.value === "rice").label, "植物 / 水稻");
  assert.equal(model().partitions.find(item => item.value === "rice").caption, "水稻");
});

for (const locale of ["zh", "en"]) {
  test(`${locale} empty or unrelated filters never pretend to switch the active project`, () => {
    const s = state("empty", locale), before = structuredClone(s);
    const view = model(s);
    assert.equal(view.projects.find(item => item.selected).value, "/rice");
    assert.match(view.projects[0].description, locale === "zh" ? /不在所选项目内/ : /outside this project/);
    assert.ok(view.projects.some(item => item.disabled && !item.value));
    assert.deepEqual(s, before);
    const chr = view.chromosomes.find(item => item.selected);
    assert.equal(chr.value, "Chr1"); assert.equal(chr.description, "4 Contigs · 2.50 Mb");
  });
}

test("project changes reset stale partition filters, missing partitions safely resolve, and open unlisted projects remain visible", () => {
  const changed = state("rice"); changed.session = { workspacePath: "/maize", projectId: 2, projectName: "B73" };
  assert.equal(model(changed).filter, "maize");
  assert.equal(model(state("deleted")).filter, "rice");
  const missing = state(); missing.session.workspacePath = "/not-in-history";
  assert.ok(model(missing).projects.some(item => item.value === "/not-in-history" && item.selected));
});

test("busy includes loading, persistence switch lock and existing import/init guards", () => {
  for (const patch of [{ assembly: { loading: true } }, { assembly: { bootstrapping: true } }, { assembly: { mainViewHistory: { inFlight: true } } }, { assembly: { subviewRestoring: true } }, { importer: { inFlight: true } },
    { importer: { libraryDialog: {} } }, { initializer: { updating: true } }, { assemblyNavigation: { busy: true } }]) {
    assert.equal(assemblyNavigationBusy({ ...state(), ...patch }), true);
  }
  assert.equal(assemblyNavigationBusy(state()), false);
});

test("whole-group wrapping is independent of long names and preserves minimum useful widths", () => {
  const widths = { width: 1500, routesWidth: 150, toolsWidth: 250, labelWidths: [50, 40, 25] };
  assert.equal(assemblyNavigationShouldStack(widths), false);
  assert.equal(assemblyNavigationShouldStack({ ...widths, width: 800 }), true);
  const css = readFileSync(new URL("../../../styles/shell.css", import.meta.url), "utf8");
  assert.match(css, /\.app-nav\.is-assembly-nav-stacked > \.assembly-navigation[^}]*grid-column: 1 \/ -1;[^}]*grid-row: 2/);
  assert.match(css, /\.assembly-navigation\[hidden\][^}]*display: none/);
  assert.match(css, /\.app-nav\.has-assembly-navigation > \.route-nav[^}]*justify-self: start/);
  assert.match(css, /\.assembly-navigation \.shell-select-toggle[^}]*width: max-content;[^}]*min-width: min\(var\(--assembly-picker-min\), 100%\);[^}]*max-width: 100%/);
  assert.match(css, /\.assembly-navigation \{[^}]*max-width: 100%;[^}]*width: max-content;[^}]*justify-self: end/);
  for (const [kind, minimum, maximum] of [["partition", 7, 18], ["project", 18, 34], ["chr", 7, 14]]) {
    assert.ok(css.includes(`.assembly-navigation-${kind} { --assembly-picker-min: ${minimum}ch; --assembly-picker-max: ${maximum}ch; }`));
  }
  assert.doesNotMatch(css, /max-width: 940px|justify-self: center/);
  assert.equal(assemblyNavigationShouldStack({ ...widths, width: 1000, pickerMinWidths: [140, 320, 140] }), true);
  assert.equal(assemblyNavigationShouldStack({ ...widths, width: 1000 }), false);
});

test("measured wrapping follows container width, translated labels and font-sized picker minima", () => {
  const classes = new Set(), events = new Map();
  const buttons = ["min(70px, 100%)", "min(160px, 100%)", "min(70px, 100%)"].map(minWidth => ({ minWidth }));
  const labelNodes = [50, 40, 25].map(scrollWidth => ({ scrollWidth }));
  const navigation = { querySelector: () => null, querySelectorAll: selector => selector === ".assembly-navigation-label" ? labelNodes : buttons };
  const nav = { clientWidth: 1000, getBoundingClientRect() {},
    classList: { toggle(name, value) { value ? classes.add(name) : classes.delete(name); } },
    querySelector: selector => ({ getBoundingClientRect: () => ({ width: selector === ".route-nav" ? 150 : 250 }) }) };
  const view = { getComputedStyle: node => node === nav ? { paddingLeft: "10px", paddingRight: "10px" } : node,
    addEventListener: (name, callback) => events.set(name, callback), removeEventListener: name => events.delete(name) };
  const root = { ownerDocument: { defaultView: view }, querySelector: selector => selector === ".app-nav" ? nav : navigation };
  const store = { getState: () => state() };
  const dispose = bindAssemblyNavigation(root, store, {});
  try {
    assert.equal(classes.has("is-assembly-nav-stacked"), false);
    nav.clientWidth = 800; events.get("resize")();
    assert.equal(classes.has("is-assembly-nav-stacked"), true);
    nav.clientWidth = 1000; buttons.forEach(button => { button.minWidth = "min(250px, 100%)"; });
    events.get("resize")(); assert.equal(classes.has("is-assembly-nav-stacked"), true);
    nav.clientWidth = 1600; events.get("resize")();
    assert.equal(classes.has("is-assembly-nav-stacked"), false);
    labelNodes.forEach(label => { label.scrollWidth = 400; }); events.get("resize")();
    assert.equal(classes.has("is-assembly-nav-stacked"), true);
  } finally { dispose(); }
  assert.equal(events.size, 0);
});

async function fixture(fn, overrides = {}) {
  const previous = globalThis.window, data = new Map();
  globalThis.window = { localStorage: { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) } };
  try {
    saveProjectLibrary(library); writeWorkspaceHistory(records);
    let current = state();
    const store = { getState: () => current, setState: patch => { current = { ...current, ...patch }; } };
    const makeSelect = () => {
      const handlers = new Map();
      return { value: "", attrs: {}, innerHTML: "", disabled: false,
        setAttribute(key, value) { this.attrs[key] = value; }, closest: () => ({ querySelector: () => ({ replaceChildren() {} }) }),
        addEventListener: (key, fn) => handlers.set(key, fn), removeEventListener: key => handlers.delete(key),
        change(value) { this.value = value; return handlers.get("change")?.(); },
      };
    };
    const partition = makeSelect(), project = makeSelect(), chr = makeSelect();
    const navigation = { hidden: false, querySelector: key => ({ "#assembly-partition-select": partition, "#session-workspace-select": project, "#assembly-chromosome-select": chr }[key]), querySelectorAll: () => [] };
    const root = { querySelector: key => key === "[data-assembly-navigation]" ? navigation : null };
    const calls = [], notices = [];
    const deps = { flush: async () => calls.push("flush"), switchWorkspace: async path => {
      calls.push(["workspace", path]); store.setState({ session: { workspacePath: path, projectId: 2, projectName: "new" } }); return true;
    }, selectChromosome: async name => { calls.push(["chr", name]); store.setState({ assembly: { ...store.getState().assembly, selectedChrName: name } }); },
      refresh: () => calls.push("refresh"), notice: async message => notices.push(message), ...overrides };
    const dispose = bindAssemblyNavigation(root, store, deps);
    try { await fn({ root, store, partition, project, chr, navigation, calls, notices, deps }); }
    finally { dispose(); }
  } finally { globalThis.window = previous; }
}

test("partition selection changes only filter state and keeps project/assembly references untouched", () => fixture(async h => {
  const before = h.store.getState(); await h.partition.change("maize");
  assert.equal(h.store.getState().session, before.session); assert.equal(h.store.getState().assembly, before.assembly);
  assert.equal(h.store.getState().assemblyNavigation.partitionId, "maize");
  assert.deepEqual(h.calls, []); assert.match(h.project.innerHTML, /B73/); assert.match(h.project.innerHTML, /当前组装/);
  await h.partition.change("empty"); assert.match(h.project.innerHTML, /此项目暂无组装/);
}));

test("workspace selection flushes once, remains in assembly, updates filter only after successful switch", () => fixture(async h => {
  await h.partition.change("plants"); await h.project.change("/maize");
  assert.deepEqual(h.calls, ["flush", ["workspace", "/maize"], "refresh"]);
  assert.equal(h.store.getState().activeRoute, "assembly"); assert.equal(h.store.getState().session.workspacePath, "/maize");
  assert.equal(h.store.getState().assemblyNavigation.partitionId, null);
  assert.equal(h.store.getState().assemblyNavigation.busy, false);
}));

test("chr selection uses the existing callback after saving and rejects same or missing chromosome", () => fixture(async h => {
  await h.chr.change("Chr1"); await h.chr.change("missing"); assert.deepEqual(h.calls, []);
  await h.chr.change("unplaced"); assert.deepEqual(h.calls, ["flush", ["chr", "unplaced"]]);
  assert.equal(h.store.getState().session.workspacePath, "/rice");
  assert.equal(h.store.getState().assembly.selectedChrName, "unplaced");
}));

for (const failure of ["flush", "switchWorkspace"]) test(`${failure} failure leaves the current project and route intact and surfaces the error`, () => fixture(async h => {
  await h.project.change("/rice2");
  assert.equal(h.store.getState().session.workspacePath, "/rice");
  assert.equal(h.store.getState().activeRoute, "assembly");
  assert.equal(h.store.getState().assemblyNavigation.busy, false);
  assert.match(h.notices[0], /broken/);
  if (failure === "flush") assert.deepEqual(h.calls, []);
}, { [failure]: async () => { throw new Error("broken"); } }));

test("loading vetoes filter/project/chr actions; leaving assembly hides the whole group", () => fixture(async h => {
  h.store.setState({ assembly: { ...h.store.getState().assembly, loading: true } });
  await h.partition.change("plants"); await h.project.change("/rice2"); await h.chr.change("unplaced");
  assert.deepEqual(h.calls, []); assert.equal(h.store.getState().assemblyNavigation.partitionId, null);
  h.store.setState({ activeRoute: "importer" }); syncAssemblyNavigation(h.root, h.store.getState()); assert.equal(h.navigation.hidden, true);
}));

test("pending save serializes navigation and drops stale work when the project changes", async () => {
  let resolve;
  await fixture(async h => {
    const pending = h.project.change("/rice2");
    assert.equal(h.store.getState().assemblyNavigation.busy, true);
    await h.chr.change("unplaced");
    h.store.setState({ session: { workspacePath: "/different", projectId: 3 } });
    resolve(); await pending;
    assert.deepEqual(h.calls, []); assert.equal(h.store.getState().assemblyNavigation.busy, false);
  }, { flush: () => new Promise(done => { resolve = done; }) });
});

test("rendered navigation escapes user names, has one switch per scope and is absent visually on Project", async () => fixture(async () => {
  const s = state(); s.session.projectName = '<img onerror="bad">';
  const markup = renderAssemblyNavigation(s);
  assert.doesNotMatch(markup, /<img/); assert.match(markup, /&lt;img/);
  for (const id of ["assembly-partition-select", "session-workspace-select", "assembly-chromosome-select"]) assert.equal((markup.match(new RegExp(`id="${id}"`, "g")) || []).length, 1);
  assert.match(renderAssemblyNavigation({ ...s, activeRoute: "importer" }), /data-assembly-navigation hidden/);
}));


test("all-assemblies option has bilingual copy without changing its filter value", () => {
  for (const locale of ["zh", "en"]) {
    const view = model(state(ALL_PARTITIONS, locale));
    const all = view.partitions.find(item => item.value === ALL_PARTITIONS);
    assert.equal(all.label, locale === "en" ? "All assemblies" : "全部组装");
    assert.equal(all.selected, true);
    assert.equal(view.projects.length, records.length);
  }
});
