import { readProjectLibrary, partitionChoices, partitionAncestors, projectPartition } from "../../services/project-library.js";
import { readWorkspaceHistory, workspacePathIdentity } from "../../services/workspace-history.js";
import { defaultProjectName } from "../../services/project-session.js";
import { projectEntryBusy } from "../../services/project-drop-controller.js";
import { renderShellSelect, syncShellSelect } from "./shell-select-runtime.js";

export const ALL_PARTITIONS = "__all__";
export const assemblyNavigationVisible = state => state.activeRoute === "assembly";
const labels = state => state.locale === "en" ? {
  partition: "Partition", project: "Project", chr: "Chr", all: "All projects", unassigned: "Unpartitioned",
  empty: "No projects in this partition", chooseProject: "Choose project", chooseChr: "Choose chromosome", current: "Current project · outside this filter",
  switchFailed: "Unable to switch. The current project has been kept.",
} : {
  partition: "分区", project: "项目", chr: "Chr", all: "全部项目", unassigned: "未分区",
  empty: "此分区暂无项目", chooseProject: "选择项目", chooseChr: "选择染色体", current: "当前项目 · 不在所选分区内",
  switchFailed: "切换失败，已保留当前项目。",
};
const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const samePath = (a, b) => workspacePathIdentity(a) === workspacePathIdentity(b);

export function assemblyNavigationBusy(state) {
  return Boolean(projectEntryBusy(state) || state.assemblyNavigation?.busy || state.assembly?.loading || state.assembly?.bootstrapping || state.assembly?.mainViewHistory?.inFlight || state.assembly?.subviewRestoring);
}

export function buildAssemblyNavigationModel(state, library = readProjectLibrary(), records = readWorkspaceHistory()) {
  const copy = labels(state), currentPath = state.session?.workspacePath || "";
  const current = records.find(record => samePath(record.path, currentPath)) || { path: currentPath, projectName: state.session?.projectName };
  const ownPartition = projectPartition(library, current);
  const navigation = state.assemblyNavigation || {};
  let filter = samePath(navigation.workspacePath, currentPath) && navigation.partitionId != null ? navigation.partitionId : ownPartition;
  if (filter !== ALL_PARTITIONS && filter && !library.partitions.some(node => node.id === filter)) filter = ownPartition;
  const choices = partitionChoices(library);
  const partitions = [
    { value: ALL_PARTITIONS, label: copy.all }, { value: "", label: copy.unassigned },
    ...choices.map(node => ({ value: node.id, label: node.path, caption: node.name })),
  ].map(item => ({ ...item, selected: item.value === filter }));
  const allowed = new Set(filter && filter !== ALL_PARTITIONS
    ? choices.filter(node => partitionAncestors(library, node.id).some(parent => parent.id === filter)).map(node => node.id) : [""]);
  const within = record => filter === ALL_PARTITIONS || allowed.has(projectPartition(library, record));
  const all = currentPath && !records.some(record => samePath(record.path, currentPath)) ? [...records, current] : records;
  const name = record => (samePath(record.path, currentPath) && state.session?.projectName) || record.projectName || defaultProjectName(record.path);
  const candidates = all.filter(within).sort((a, b) => name(a).localeCompare(name(b), state.locale, { numeric: true }));
  const pathLabel = record => choices.find(node => node.id === projectPartition(library, record))?.path || copy.unassigned;
  const projects = candidates.map(record => ({ value: record.path, label: name(record), selected: samePath(record.path, currentPath), description: pathLabel(record) }));
  if (currentPath && !within(current)) projects.unshift({ value: currentPath, label: name(current), selected: true, description: copy.current });
  if (!candidates.length) projects.push({ value: "", label: copy.empty, disabled: true, selected: !currentPath });
  if (!projects.some(item => item.selected)) projects.unshift({ value: "", label: copy.chooseProject, selected: true, disabled: true });
  const chromosomes = (state.assembly?.chromosomes || []).map(chr => ({ value: chr.chrName, label: chr.chrName,
    selected: chr.chrName === state.assembly?.selectedChrName,
    description: `${Number(chr.ctgCount) || 0} Contigs · ${(Number(chr.placedBp || 0) / 1e6).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Mb`,
  }));
  if (!chromosomes.some(item => item.selected)) chromosomes.unshift({ value: "", label: copy.chooseChr, selected: true, disabled: true });
  return { copy, partitions, projects, chromosomes, filter, busy: assemblyNavigationBusy(state) };
}

export function renderAssemblyNavigation(state) {
  const model = buildAssemblyNavigationModel(state);
  const field = (kind, id, text, options) => `<label class="assembly-navigation-field assembly-navigation-${kind}" for="${id}-toggle"><span class="assembly-navigation-label">${text}</span>${renderShellSelect(id, text, options, { bounded: true })}</label>`;
  return `<div class="assembly-navigation" data-assembly-navigation ${assemblyNavigationVisible(state) ? "" : "hidden"}>
    ${field("partition", "assembly-partition-select", model.copy.partition, model.partitions)}
    ${field("project", "session-workspace-select", model.copy.project, model.projects)}
    ${field("chr", "assembly-chromosome-select", model.copy.chr, model.chromosomes)}
  </div>`;
}

export function assemblyNavigationShouldStack({ width, routesWidth, toolsWidth, labelWidths = [] }) {
  // Budget useful minimum name widths, not current project-name lengths.
  return width < routesWidth + toolsWidth + labelWidths.reduce((sum, value) => sum + value, 0) + 110 + 180 + 90 + 60;
}

const bindings = new WeakMap();
const signatures = new WeakMap();
export function syncAssemblyNavigation(root, state) {
  const navigation = root.querySelector("[data-assembly-navigation]");
  if (!navigation) return;
  const visible = assemblyNavigationVisible(state);
  navigation.hidden = !visible;
  const nav = root.querySelector(".app-nav");
  nav?.classList.toggle("has-assembly-navigation", visible);
  if (!visible) {
    navigation.querySelectorAll("[data-shell-select-menu]").forEach(menu => menu.classList.add("is-hidden"));
    navigation.querySelectorAll("[data-shell-select-toggle]").forEach(button => button.setAttribute("aria-expanded", "false"));
    nav?.classList.remove("is-assembly-nav-stacked");
    return;
  }
  const model = buildAssemblyNavigationModel(state);
  for (const [id, title, options] of [["assembly-partition-select", model.copy.partition, model.partitions],
    ["session-workspace-select", model.copy.project, model.projects], ["assembly-chromosome-select", model.copy.chr, model.chromosomes]]) {
    const select = navigation.querySelector(`#${id}`);
    if (!select) continue;
    const signature = JSON.stringify(options);
    if (signatures.get(select) !== signature) {
      select.innerHTML = options.map(item => `<option value="${escape(item.value)}" ${item.selected ? "selected" : ""} ${item.disabled ? "disabled" : ""}${item.caption != null ? ` data-caption="${escape(item.caption)}"` : ""}${item.description ? ` data-description="${escape(item.description)}"` : ""}>${escape(item.label)}</option>`).join("");
      signatures.set(select, signature);
    }
    select.setAttribute("aria-label", title);
    const selected = options.find(item => item.selected);
    select.setAttribute("data-app-tooltip", selected?.label || title);
    select.closest("label")?.querySelector(".assembly-navigation-label")?.replaceChildren(title);
    select.disabled = model.busy || (id === "assembly-chromosome-select" && !state.assembly?.chromosomes?.length);
    syncShellSelect(select);
  }
  bindings.get(root)?.layout();
}

export function bindAssemblyNavigation(root, store, { flush, switchWorkspace, selectChromosome, refresh, notice }) {
  bindings.get(root)?.dispose();
  const navigation = root.querySelector("[data-assembly-navigation]");
  if (!navigation) return;
  const cleanups = [];
  const on = (node, type, callback) => { if (!node) return; node.addEventListener(type, callback); cleanups.push(() => node.removeEventListener(type, callback)); };
  const sync = () => syncAssemblyNavigation(root, store.getState());
  const patch = value => store.setState({ assemblyNavigation: { ...store.getState().assemblyNavigation, ...value } });
  const run = async action => {
    const initial = store.getState();
    if (!assemblyNavigationVisible(initial) || assemblyNavigationBusy(initial)) { sync(); return; }
    patch({ busy: true }); sync();
    try {
      await flush();
      const current = store.getState();
      if (current.activeRoute !== "assembly" || !samePath(current.session.workspacePath, initial.session.workspacePath)
        || current.session.projectId !== initial.session.projectId) return;
      await action();
    } catch (error) { await notice(`${labels(store.getState()).switchFailed}\n${String(error?.message || error)}`); }
    finally { patch({ busy: false }); sync(); }
  };
  const partition = navigation.querySelector("#assembly-partition-select");
  on(partition, "change", () => {
    if (!assemblyNavigationVisible(store.getState()) || assemblyNavigationBusy(store.getState())) { sync(); return; }
    patch({ partitionId: partition.value, workspacePath: store.getState().session.workspacePath });
    sync();
  });
  const project = navigation.querySelector("#session-workspace-select");
  on(project, "change", async () => {
    const path = project.value;
    if (!path || samePath(path, store.getState().session?.workspacePath)) { sync(); return; }
    // Revalidate the selection against fresh history/partition state before starting I/O.
    const model = buildAssemblyNavigationModel(store.getState());
    if (!model.projects.some(item => item.value === path && !item.disabled)) { sync(); return; }
    await run(async () => {
      const changed = await switchWorkspace(path);
      if (changed === false) return;
      patch({ partitionId: null, workspacePath: store.getState().session.workspacePath });
      refresh();
    });
  });
  const chromosome = navigation.querySelector("#assembly-chromosome-select");
  on(chromosome, "change", async () => {
    const name = chromosome.value;
    if (!name || name === store.getState().assembly?.selectedChrName || !store.getState().assembly?.chromosomes?.some(chr => chr.chrName === name)) { sync(); return; }
    await run(() => {
      if (store.getState().assembly?.chromosomes?.some(chr => chr.chrName === name)) return selectChromosome(name);
    });
  });
  const view = root.ownerDocument?.defaultView;
  const nav = root.querySelector(".app-nav");
  const layout = () => {
    if (!nav?.getBoundingClientRect || !assemblyNavigationVisible(store.getState())) return;
    const width = nav.clientWidth - 20;
    const routesWidth = nav.querySelector(".route-nav")?.getBoundingClientRect().width || 0;
    const toolsWidth = nav.querySelector(".nav-session-controls")?.getBoundingClientRect().width || 0;
    const labelWidths = [...navigation.querySelectorAll(".assembly-navigation-label")].map(label => label.scrollWidth);
    nav.classList.toggle("is-assembly-nav-stacked", assemblyNavigationShouldStack({ width, routesWidth, toolsWidth, labelWidths }));
  };
  let observer;
  if (view?.ResizeObserver && nav) { observer = new view.ResizeObserver(layout); observer.observe(nav); }
  on(view, "resize", layout);
  on(root.ownerDocument?.fonts, "loadingdone", layout);
  const dispose = () => { observer?.disconnect(); cleanups.splice(0).forEach(fn => fn()); bindings.delete(root); };
  bindings.set(root, { layout, dispose });
  sync();
  return dispose;
}
