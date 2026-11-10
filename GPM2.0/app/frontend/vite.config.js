import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { backendBridgePlugin } from "./src/dev-bridge/backend-bridge.js";

export default defineConfig({
  build: { rollupOptions: { input: { main: fileURLToPath(new URL("./index.html", import.meta.url)), localView: fileURLToPath(new URL("./local-view.html", import.meta.url)) } } },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  plugins: [backendBridgePlugin()],
});
