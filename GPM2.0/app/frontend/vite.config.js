import { defineConfig } from "vite";
import { backendBridgePlugin } from "./src/dev-bridge/backend-bridge.js";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  plugins: [backendBridgePlugin()],
});
