import { renderImporterPage } from "../pages/importer-page.js";
import { bindAssemblyPage, renderAssemblyPage, syncAssemblySubviewTools, syncAssemblyTransientInteractions } from "../pages/assembly-page.js";
import { bindImporterPage } from "../pages/importer-page.js";
import { bindProjectExportPage, renderProjectExportPage, releaseProjectOverviewPreview, releaseProjectPathOverview } from "../pages/project-export-page.js";
import { getMessages, t } from "../i18n/index.js";
import {
  buildAssemblyDomCacheKey,
  rememberAssemblyDom,
  restoreAssemblyDom,
} from "./assembly-session-cache.js";

const routeRenderers = {
  importer: renderImporterPage,
  workspace: renderImporterPage,
  assembly: renderAssemblyPage,
  projectExport: renderProjectExportPage,
};

const routeBinders = {
  importer: bindImporterPage,
  workspace: bindImporterPage,
  assembly: bindAssemblyPage,
  projectExport: bindProjectExportPage,
};

const RENDERING = Symbol("routeRendering");
const RENDER_REVISION = Symbol("routeRenderRevision");
export const normalizeAppRoute = route => ["projectPreview", "overview"].includes(route) ? "projectExport" : route;

export function registerRoutes(root, store, onRouteChanged) {
  const buttons = root.querySelectorAll(".route-button");
  for (const button of buttons) {
    button.addEventListener("click", () => {
      const route = normalizeAppRoute(button.dataset.route);
      const revision = root[RENDER_REVISION] || 0;
      store.setState({ activeRoute: route });
      // Production store subscriptions already render changed routes. Keep the
      // callback contract for standalone callers without rendering twice.
      if ((root[RENDER_REVISION] || 0) === revision) onRouteChanged();
    });
  }
}

export function renderCurrentRoute(root, store) {
  if (root[RENDERING]) return;
  root[RENDERING] = true;
  try { return renderRoute(root, store); }
  finally { root[RENDERING] = false; root[RENDER_REVISION] = (root[RENDER_REVISION] || 0) + 1; }
}

function renderRoute(root, store) {
  let state = store.getState();
  const canonical = normalizeAppRoute(state.activeRoute);
  if (canonical !== state.activeRoute) { store.setState({ activeRoute: canonical }); state = store.getState(); }
  const requiresProject = ["projectPreview", "assembly", "projectExport"].includes(state.activeRoute);
  if (state.activeRoute === "workspace" || (requiresProject && (!state.session?.workspacePath || !state.session?.projectId))) {
    store.setState({ activeRoute: "importer" });
    state = store.getState();
  }
  const host = root.querySelector("#route-host");
  const previousRoute = String(host?.dataset?.route || "");
  if (["importer", "workspace"].includes(previousRoute)) releaseProjectPathOverview(host);
  if (state.activeRoute === "importer" && previousRoute && previousRoute !== "importer" && state.initializer?.projectCatalog) {
    store.setState({ initializer: { ...state.initializer, projectCatalog: null } });
    state = store.getState();
  }
  const previousAssemblyDomCacheKey = String(host?.dataset?.assemblyDomCacheKey || "");
  if (["projectExport", "projectPreview"].includes(previousRoute)) releaseProjectOverviewPreview(host);
  if (previousRoute === "assembly") {
    rememberAssemblyDom(host, state);
  }
  const renderer = routeRenderers[state.activeRoute];
  const shellMessages = getMessages(state, "shell");
  if (!renderer) {
    host.innerHTML = `<p>${escapeHtml(t(state, "shell.routeNotFound", { route: state.activeRoute }))}</p>`;
    setRouteHostDataset(host, state.activeRoute, "");
    return;
  }

  try {
    const nextAssemblyDomCacheKey = state.activeRoute === "assembly"
      ? buildAssemblyDomCacheKey(state)
      : "";
    const restoredAssemblyDom = state.activeRoute === "assembly"
      && !state.assembly?.projectExportScrollToBottom
      && !state.assembly?.previewRequestedChrName
      && previousRoute
      && previousAssemblyDomCacheKey !== nextAssemblyDomCacheKey
      && restoreAssemblyDom(host, state);
    if (!restoredAssemblyDom) {
      host.innerHTML = renderer(state);
      setRouteHostDataset(host, state.activeRoute, nextAssemblyDomCacheKey);
      const binder = routeBinders[state.activeRoute];
      if (binder) {
        binder(host, store);
      }
    } else {
      setRouteHostDataset(host, state.activeRoute, nextAssemblyDomCacheKey);
      syncAssemblySubviewTools(host, store);
      syncAssemblyTransientInteractions(host, store);
    }
  } catch (error) {
    const message = String(error?.stack || error?.message || error || "unknown route render error");
    host.innerHTML = `
      <article class="card">
        <h4>${escapeHtml(shellMessages.routeRenderFailed)}</h4>
        <p class="muted">${escapeHtml(t(state, "shell.currentRoute", { route: state.activeRoute }))}</p>
        <pre class="muted">${escapeHtml(message)}</pre>
      </article>
    `;
    setRouteHostDataset(host, state.activeRoute, "");
  }
  root.querySelectorAll(".route-button").forEach((button) => {
    const requiresProject = ["projectPreview", "assembly", "projectExport"].includes(button.dataset.route);
    button.disabled = requiresProject && (!state.session?.workspacePath || !state.session?.projectId);
    button.title = button.disabled ? (state.locale === "en" ? "Open a project first" : "请先打开项目") : "";
    const active = button.dataset.route === state.activeRoute;
    button.classList.toggle("is-active", active);
  });
}

function setRouteHostDataset(host, route, assemblyDomCacheKey) {
  if (!host?.dataset) {
    return;
  }
  host.dataset.route = String(route || "");
  if (assemblyDomCacheKey) {
    host.dataset.assemblyDomCacheKey = assemblyDomCacheKey;
  } else {
    delete host.dataset.assemblyDomCacheKey;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
