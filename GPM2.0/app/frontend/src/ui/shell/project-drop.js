import { invokeCommand, isTauriRuntime } from "../../services/backend-api.js";
import { createProjectDropController, projectDropCopy } from "../../services/project-drop-controller.js";
import { flushAssemblyProjectState } from "../pages/assembly-page.js";
import { runImportExtractedFlow, runOpenWorkspaceFlow } from "../pages/importer-page.js";
import { requestAppNotice } from "./app-dialog.js";

export async function bindProjectDrop(root, store, { subscribe } = {}) {
  const doc = root.ownerDocument || globalThis.document;
  if (!doc?.body) return () => {};
  const layer = doc.createElement("div");
  layer.className = "project-drop-overlay";
  layer.hidden = true;
  layer.setAttribute("role", "status");
  layer.setAttribute("aria-live", "polite");
  const title = doc.createElement("strong");
  const hint = doc.createElement("span");
  layer.append(title, hint);
  doc.body.append(layer);
  const host = () => root.querySelector("#route-host");
  const refresh = () => globalThis.window.dispatchEvent(new Event("gpm-next:route-refresh"));
  const handle = createProjectDropController({
    store, inspect: (entryPath, timestamp) => invokeCommand("inspect_project_entry", { entryPath, timestamp }, store.getState()),
    prepareSwitch: () => flushAssemblyProjectState(host(), store),
    openWorkspace: path => runOpenWorkspaceFlow(host(), store, path, false),
    importExtracted: () => runImportExtractedFlow(host(), store),
    notice: message => requestAppNotice(message, { store }),
    modalOpen: () => Boolean(doc.querySelector("dialog[open], .modal-overlay, [role='dialog'][aria-modal='true']")),
    overlay: (visible, message, description) => {
      layer.hidden = !visible;
      if (visible) { title.textContent = message; hint.textContent = description; }
    }, refresh,
  });
  // Prevent browser navigation without interpreting browser filename-only drops.
  const preventFileNavigation = event => {
    if ([...(event.dataTransfer?.types || [])].includes("Files")) event.preventDefault();
  };
  doc.addEventListener("dragover", preventFileNavigation);
  doc.addEventListener("drop", preventFileNavigation);
  const clear = () => { layer.hidden = true; };
  globalThis.window?.addEventListener("blur", clear);
  let unlisten = () => {};
  try {
    if (subscribe) unlisten = await subscribe(handle);
    else if (isTauriRuntime()) {
      const current = globalThis.window.__TAURI__.webviewWindow?.getCurrentWebviewWindow?.();
      if (!current?.onDragDropEvent) throw new Error("native drag/drop API unavailable");
      unlisten = await current.onDragDropEvent(handle);
    }
  } catch (error) {
    console.error("GPM drag/drop registration failed", error);
    await requestAppNotice(projectDropCopy[store.getState().locale === "en" ? "en" : "zh"].unavailable, { store });
  }
  return () => {
    if (typeof unlisten === "function") unlisten();
    doc.removeEventListener("dragover", preventFileNavigation);
    doc.removeEventListener("drop", preventFileNavigation);
    globalThis.window?.removeEventListener("blur", clear);
    layer.remove();
  };
}
