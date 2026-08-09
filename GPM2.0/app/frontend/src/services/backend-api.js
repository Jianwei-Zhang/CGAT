import { t } from "../ui/i18n/index.js";

export function isTauriRuntime() {
  return Boolean(window.__TAURI__?.core?.invoke);
}

export async function invokeCommand(command, args = {}, stateOrLocale = "zh") {
  if (!isTauriRuntime()) {
    const error = new Error(t(stateOrLocale, "importer.runtime.backendCommandUnavailable", { command }));
    error.code = "RUNTIME_ERROR";
    error.source = "browser-preview";
    error.operation = command;
    throw error;
  }
  return window.__TAURI__.core.invoke(command, args);
}

export async function listenBackendEvent(eventName, handler) {
  const listen = window.__TAURI__?.event?.listen;
  if (typeof listen !== "function") {
    return () => {};
  }
  const unlisten = await listen(eventName, handler);
  return typeof unlisten === "function" ? unlisten : () => {};
}

export async function pickZipFilePath(stateOrLocale = "zh") {
  if (!isTauriRuntime()) {
    const fallback = window.prompt(t(stateOrLocale, "importer.runtime.promptZipPath"));
    return (fallback || "").trim();
  }
  const selected = await invokeCommand("pick_zip_file_path", {}, stateOrLocale);
  return typeof selected === "string" ? selected : "";
}

export async function pickDirectoryPath(stateOrLocale = "zh") {
  if (!isTauriRuntime()) {
    if ("showDirectoryPicker" in window) {
      try {
        const handle = await window.showDirectoryPicker();
        return handle.name;
      } catch {
        return "";
      }
    }
    const fallback = window.prompt(t(stateOrLocale, "importer.runtime.promptDirectoryPath"));
    return (fallback || "").trim();
  }
  const selected = await invokeCommand("pick_directory_path", {}, stateOrLocale);
  return typeof selected === "string" ? selected : "";
}

export async function pickSaveFilePath({ defaultPath = "", filters = [] } = {}, stateOrLocale = "zh") {
  if (!isTauriRuntime()) {
    const fallback = window.prompt(String(defaultPath || "").trim());
    return (fallback || "").trim();
  }
  const selected = await invokeCommand("pick_save_file_path", {
    defaultPath,
    filters,
  }, stateOrLocale);
  return typeof selected === "string" ? selected : "";
}
