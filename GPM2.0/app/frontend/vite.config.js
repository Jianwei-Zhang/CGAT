import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { backendBridgePlugin } from "./src/dev-bridge/backend-bridge.js";

// WKWebView popups inherit the opener's registered ipc: scheme handler. On
// macOS only, keep that transport out of the Local View document so Tauri
// uses the popup's own WKScriptMessageHandler and evaluates its existing ACL.
// Do not grant popup window commands to Main or retry a denied command there.
export function macLocalViewIpcPolicy(platform = process.env.TAURI_ENV_PLATFORM || process.platform) {
  return {
    name: "mac-local-view-ipc-policy",
    transformIndexHtml: {
      order: "post",
      handler(_html, { path, server }) {
        if (!["darwin", "macos"].includes(platform) || path.split("?")[0] !== "/local-view.html") return;
        // Same-origin assets remain accessible; only dev needs the Vite HMR socket.
        const content = server ? "connect-src 'self' ws://127.0.0.1:5174" : "connect-src 'self'";
        return [{ tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content }, injectTo: "head-prepend" }];
      },
    },
  };
}

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        localView: fileURLToPath(new URL("./local-view.html", import.meta.url)),
      },
      output: {
        // Split at existing static module boundaries. The popup keeps its tiny
        // shared IPC helper; PDF export stays lazy and isn't part of these groups.
        manualChunks: {
          "local-view-ipc": ["./src/ui/pages/assembly/subview-native-identity.js"],
          "final-path-drag": ["./src/ui/pages/assembly/final-path-append-drag-runtime.js"],
          "assembly-controls": ["./src/ui/pages/assembly/bindings.js"],
          "project-preview": ["./src/ui/pages/project-preview-preparation.js"],
          "assembly-page": ["./src/ui/pages/assembly-page.js"],
          "subview-fragments": ["./src/ui/pages/assembly/subview-fragment-sync-runtime.js"],
          "track-rendering": ["./src/ui/pages/assembly/render-tracks.js"],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  plugins: [backendBridgePlugin(), macLocalViewIpcPolicy()],
});
