import { isTauriRuntime } from "../backend-api.js";
import { callDevBridge } from "./dev-transport.js";
import { workflowMockBackend } from "./mock-backend.js";
import { createTauriTransport } from "./tauri-transport.js";

const tauriTransport = createTauriTransport({
  getPackageMetadataFallback: () => workflowMockBackend.getPackageMetadata(),
});

export const workflowRuntime = Object.freeze({
  isTauriRuntime,
  callDevBridge,
  mock: workflowMockBackend,
  tauri: tauriTransport,
});
