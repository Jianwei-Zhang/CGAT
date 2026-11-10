import "./styles/base.css";
import "./styles/theme.css";
import "./styles/layout.css";
import "./styles/components.css";
import "./styles/tooltips.css";

// No application bootstrap, second store, independent persistence, or project
// loaders run here. The opener owns the existing controllers and scoped store.
const params = new URLSearchParams(location.search);
try {
  if (!window.opener?.__gpmLocalViews) throw new Error("Local View owner is unavailable");
  await window.opener.__gpmLocalViews.connect(params.get("view"), params.get("token"), window);
} catch (error) {
  try {
    window.opener?.__gpmLocalViews?.fail(params.get("view"), params.get("token"), String(error?.message || error));
  } finally {
    // The owner reports the error and restores the dock. Never leave an orphan
    // borderless error window when an opening raced with close/project switch.
    await window.__TAURI__?.window?.getCurrentWindow?.().destroy().catch(() => {});
  }
}
