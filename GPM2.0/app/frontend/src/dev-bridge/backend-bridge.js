import { resolveBackendRuntime } from "./backend-runtime.js";
import { createBackendOperations } from "./backend-operations.js";
import { createBackendBridgeMiddleware } from "./http.js";
import { createBackendBridgeRoutes } from "./route-registry.js";

export function backendBridgePlugin(options = {}) {
  const runtime = options.runtime || resolveBackendRuntime();
  const handlers = options.handlers || createBackendOperations(runtime);
  const routes = options.routes || createBackendBridgeRoutes(handlers);
  const middleware = createBackendBridgeMiddleware({
    backendExe: runtime.backendExe,
    routes,
  });

  return {
    name: "gpm-next-backend-bridge",
    configureServer(server) {
      server.middlewares.use("/api", middleware);
    },
  };
}
