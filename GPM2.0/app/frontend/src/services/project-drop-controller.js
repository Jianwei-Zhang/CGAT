import { workspacePathIdentity } from "./workspace-history.js";

export function localWorkspaceTimestamp(date = new Date()) {
  const pad = n => String(n).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

// The directory picker chooses a parent; keep the proposed new-directory leaf
// so selecting a folder does not accidentally select an existing import root.
export function relocateWorkspaceSuggestion(parent, current) {
  const root = workspacePathIdentity(parent);
  const leaf = workspacePathIdentity(current).split("/").at(-1);
  return root && leaf ? `${root.replace(/\/+$/, "")}/${leaf}` : String(parent || "").trim();
}

export const projectDropCopy = {
  zh: {
    overlay: "松开以导入交付包或打开项目", hint: "ZIP / tar.gz · 已解压交付目录 · 已有工作路径",
    busy: "当前有操作或对话框未完成，请完成后再拖入项目。",
    single: "一次只能拖入一个交付包或项目目录。",
    opened: "该工作路径已经打开，不会重复添加项目记录。",
    error: "无法导入或打开拖入的项目", unavailable: "桌面拖放监听不可用，请使用导入或打开按钮。",
  },
  en: {
    overlay: "Drop to import a delivery or open a project", hint: "ZIP / tar.gz · Extracted delivery · Existing workspace",
    busy: "Finish the current operation or dialog before dropping another project.",
    single: "Drop one delivery archive or project directory at a time.",
    opened: "This workspace is already open. No duplicate project record will be added.",
    error: "Unable to import or open the dropped project", unavailable: "Desktop drag and drop is unavailable. Use Import or Open instead.",
  },
};

export function projectEntryBusy(state, { includeResolving = true } = {}) {
  const importer = state.importer || {};
  const initializer = state.initializer || {};
  return Boolean(importer.inFlight || importer.restoringSession || (includeResolving && importer.entryResolving) || importer.importDialogOpen
    || importer.copyDialog?.open || importer.deleteConfirmOpen || initializer.loading || initializer.updating
    || initializer.autoPipelineRunning || initializer.createModalOpen || initializer.autoPipelineModalOpen);
}

// Native event payloads provide absolute filesystem paths; never use File.name
// or browser fake paths to decide which project to open.
export function createProjectDropController({ store, inspect, prepareSwitch = async () => {}, openWorkspace,
  importExtracted, notice = async () => {}, overlay = () => {}, refresh = () => {}, modalOpen = () => false,
  now = () => new Date() }) {
  let locked = false;
  let showingNotice = false;
  const labels = () => projectDropCopy[store.getState().locale === "en" ? "en" : "zh"];
  const busy = () => projectEntryBusy(store.getState(), { includeResolving: false }) || modalOpen();
  const resolving = value => store.setState({ importer: { ...store.getState().importer, entryResolving: value } });
  async function feedback(message) {
    if (showingNotice) return;
    showingNotice = true;
    try { await notice(message); } finally { showingNotice = false; }
  }
  return async function handle(event) {
    const payload = event?.payload || event;
    if (payload?.type === "enter" || payload?.type === "over") {
      overlay(true, busy() || locked ? labels().busy : labels().overlay, labels().hint);
      return false;
    }
    overlay(false);
    if (payload?.type !== "drop") return false;
    // A duplicated native event during the same operation is a no-op, not a
    // second import or a modal stacked over the pending confirmation.
    if (locked) return false;
    const paths = Array.isArray(payload.paths) ? payload.paths : [];
    if (paths.length !== 1 || typeof paths[0] !== "string" || !paths[0].trim()) {
      await feedback(labels().single); return false;
    }
    if (busy()) { await feedback(labels().busy); return false; }
    locked = true;
    resolving(true);
    try {
      const entry = await inspect(paths[0], localWorkspaceTimestamp(now()));
      if (busy()) { await feedback(labels().busy); return false; }
      if (!["archive", "extracted", "workspace"].includes(entry?.kind) || !entry.path) {
        throw new Error(labels().error);
      }
      if (entry.kind === "workspace" && workspacePathIdentity(entry.path) === workspacePathIdentity(store.getState().session?.workspacePath)) {
        await feedback(labels().opened); return true;
      }
      await prepareSwitch();
      if (busy()) { await feedback(labels().busy); return false; }
      resolving(false);
      if (entry.kind === "archive") {
        if (!entry.suggestedWorkspace) throw new Error(labels().error);
        store.setState({ activeRoute: "importer", importer: { ...store.getState().importer,
          importDialogOpen: true, importSource: "zip", zipPath: entry.path,
          workspaceRoot: entry.suggestedWorkspace, requireNewWorkspace: true,
          projectNameInput: "", projectError: "", pendingProjectPath: "" } });
        refresh();
      } else if (entry.kind === "extracted") {
        store.setState({ activeRoute: "importer", importer: { ...store.getState().importer,
          extractedPath: entry.path, projectNameInput: "", projectError: "", pendingProjectPath: "" } });
        refresh();
        await importExtracted(entry.path);
      } else {
        const opened = await openWorkspace(entry.path);
        if (opened === false) throw new Error(store.getState().importer.summary || labels().error);
        store.setState({ activeRoute: "importer" });
        refresh();
      }
      return true;
    } catch (error) {
      await feedback(`${labels().error}: ${String(error?.message || error)}`);
      return false;
    } finally { resolving(false); locked = false; }
  };
}
