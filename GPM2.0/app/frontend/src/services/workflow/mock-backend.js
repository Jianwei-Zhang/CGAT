import { createMockAssemblyOperations } from "./mock/assembly.js";
import { createMockWorkspaceOperations } from "./mock/imports-workspace.js";
import { createWorkflowMockStore } from "./mock/state.js";
import { createMockViewStateOperations } from "./mock/view-state.js";

export function createWorkflowMockBackend() {
  const store = createWorkflowMockStore();
  return {
    ...createMockWorkspaceOperations(store),
    ...createMockAssemblyOperations(store),
    ...createMockViewStateOperations(store),
    getPackageMetadata() {
      return store.packageMetadata;
    },
  };
}

export const workflowMockBackend = createWorkflowMockBackend();
