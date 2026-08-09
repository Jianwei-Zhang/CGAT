import { normalizeWorkflowError } from "./contracts.js";

export async function callDevBridge(path, payload, { fetchImpl = globalThis.fetch } = {}) {
  const response = await fetchImpl(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw normalizeWorkflowError(
      body.error || body.message || `dev bridge error: ${response.status}`,
      {
        code: body.code || "DEV_BRIDGE_ERROR",
        source: "dev-bridge",
        operation: body.operation || path,
        detail: body.detail || null,
        data: body.data || null,
      },
    );
  }
  return body;
}
