import { invokeCommand, isTauriRuntime } from "./backend-api.js";
import { callDevBridge } from "./workflow/dev-transport.js";

export function revealCatalogLocation(request) {
  return invokeCommand("reveal_catalog_location", request);
}

export function listProjectCatalog({ workspaceRoot, projectId }) {
  return isTauriRuntime()
    ? invokeCommand("list_project_catalog", { workspaceRoot, projectId })
    : callDevBridge("/api/list-project-catalog", { workspaceRoot, projectId });
}

export function updateProjectCatalog({ workspaceRoot, ...request }) {
  return isTauriRuntime()
    ? invokeCommand("update_project_catalog", { workspaceRoot, request })
    : callDevBridge("/api/update-project-catalog", { workspaceRoot, ...request });
}
