import { workflowRuntime } from "../runtime.js";

// Unsupported browser/development backends deliberately report a cache miss;
// a mocked persistent hit must never conceal edits in a real project.
export async function getProjectPreviewCache(args) {
  if (workflowRuntime.isTauriRuntime()) return workflowRuntime.tauri.getProjectPreviewCache(args);
  return { available: false };
}

export async function putProjectPreviewCache(args) {
  if (workflowRuntime.isTauriRuntime()) return workflowRuntime.tauri.putProjectPreviewCache(args);
  return { stored: false };
}
