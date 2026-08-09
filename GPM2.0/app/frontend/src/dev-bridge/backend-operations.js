import { createAssemblyOperations } from "./operations/assembly.js";
import { createAuditOperations } from "./operations/audit.js";
import { createEditingOperations } from "./operations/editing.js";
import { createImportOperations } from "./operations/imports.js";
import { createInspectionOperations } from "./operations/inspection.js";
import { createRuntimeOperations } from "./operations/runtime.js";
import { createWorkspaceOperations } from "./operations/workspace.js";

export function createBackendOperations(runtime) {
  if (typeof runtime?.runBackend !== "function") {
    throw new TypeError("dev bridge runtime must provide runBackend(args)");
  }
  return {
    ...createImportOperations(runtime),
    ...createWorkspaceOperations(runtime),
    ...createAssemblyOperations(runtime),
    ...createEditingOperations(runtime),
    ...createInspectionOperations(runtime),
    ...createAuditOperations(runtime),
    ...createRuntimeOperations(runtime),
  };
}
