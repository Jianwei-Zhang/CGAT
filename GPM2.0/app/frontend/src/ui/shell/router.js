import { renderImporterPage } from "../pages/importer-page.js";
import { renderWorkspacePage } from "../pages/workspace-page.js";
import { bindAssemblyPage, renderAssemblyPage } from "../pages/assembly-page.js";
import { bindImporterPage } from "../pages/importer-page.js";
import { bindProjectExportPage, renderProjectExportPage } from "../pages/project-export-page.js";
import { bindWorkspacePage } from "../pages/workspace-page.js";
import { getMessages, t } from "../i18n/index.js";
import {
  buildAssemblyDomCacheKey,
  rememberAssemblyDom,
  restoreAssemblyDom,
} from "./assembly-session-cache.js";

const routeRenderers = {
  importer: renderImporterPage,
  workspace: renderWorkspacePage,
  assembly: renderAssemblyPage,
  projectExport: renderProjectExportPage,
};

const routeBinders = {
  importer: bindImporterPage,
  workspace: bindWorkspacePage,
  assembly: bindAssemblyPage,
  projectExport: bindProjectExportPage,
};

export function registerRoutes(root, store, onRouteChanged) {
  const buttons = root.querySelectorAll(".route-button");
  for (const button of buttons) {
    button.addEventListener("click", () => {
      const route = button.dataset.route;
      store.setState({ activeRoute: route });
      onRouteChanged();
    });
  }
}

export function renderCurrentRoute(root, store) {
  const state = store.getState();
  const host = root.querySelector("#route-host");
  const previousRoute = String(host?.dataset?.route || "");
  const previousAssemblyDomCacheKey = String(host?.dataset?.assemblyDomCacheKey || "");
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
