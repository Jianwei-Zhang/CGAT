import { workspacePathIdentity } from "./workspace-history.js";
import { openWorkspace, initializeProject } from "./workflow-api.js";

export function defaultProjectName(path) {
  const parts = String(path || "").trim().split(/[\\/]+/).filter(Boolean);
  if (parts.at(-1)?.toLowerCase() === "gpm_server" && parts.length > 1) parts.pop();
  return parts.at(-1) || "Project";
}

const pending = new Map();
const initializing = new Map();

// Serialize opens for a directory so a retry cannot create a second project.
export function openProjectWorkspace({ workspaceRoot, projectName = "", createIfMissing = true }, deps = {}) {
  const key = `${createIfMissing}:${workspacePathIdentity(workspaceRoot)}`;
  if (pending.has(key)) return pending.get(key);
  const operation = (async () => {
    const options = await (deps.openWorkspace || openWorkspace)({ workspaceRoot });
    if (options.existingProjects?.length || !createIfMissing) return options;
    const canonical = options.workspaceRoot || workspaceRoot;
    const identity = workspacePathIdentity(canonical);
    if (initializing.has(identity)) return initializing.get(identity);
    const creation = (async () => {
      try {
        const created = await (deps.initializeProject || initializeProject)({
          workspaceRoot: canonical,
          projectName: String(projectName || "").trim() || defaultProjectName(canonical),
          phasedAssemblyEnabled: true,
        });
        return { ...options, workspaceRoot: canonical, existingProjects: created.existingProjects, grtProjectView: created.grtProjectView };
      } catch (cause) {
        const error = new Error(String(cause?.message || cause), { cause });
        error.pendingProjectPath = canonical;
        throw error;
      }
    })();
    initializing.set(identity, creation);
    creation.finally(() => initializing.delete(identity)).catch(() => {});
    return creation;
  })();
  pending.set(key, operation);
  operation.finally(() => pending.delete(key)).catch(() => {});
  return operation;
}
