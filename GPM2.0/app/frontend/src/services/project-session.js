import { openWorkspace, initializeProject } from "./workflow-api.js";

export function defaultProjectName(path) {
  const parts = String(path || "").trim().split(/[\\/]+/).filter(Boolean);
  if (parts.at(-1)?.toLowerCase() === "gpm_server" && parts.length > 1) parts.pop();
  return parts.at(-1) || "Project";
}

const pending = new Map();

// Serialize opens for a directory so a retry cannot create a second project.
export function openProjectWorkspace({ workspaceRoot, projectName = "" }, deps = {}) {
  const key = String(workspaceRoot || "").trim().replace(/[\\/]+$/, "");
  if (pending.has(key)) return pending.get(key);
  const operation = (async () => {
    const options = await (deps.openWorkspace || openWorkspace)({ workspaceRoot });
    if (options.existingProjects?.length) return options;
    try {
      const created = await (deps.initializeProject || initializeProject)({
        workspaceRoot,
        projectName: String(projectName || "").trim() || defaultProjectName(workspaceRoot),
        phasedAssemblyEnabled: true,
      });
      return { ...options, existingProjects: created.existingProjects, grtProjectView: created.grtProjectView };
    } catch (cause) {
      const error = new Error(String(cause?.message || cause), { cause });
      error.pendingProjectPath = workspaceRoot;
      throw error;
    }
  })();
  pending.set(key, operation);
  operation.finally(() => pending.delete(key)).catch(() => {});
  return operation;
}
