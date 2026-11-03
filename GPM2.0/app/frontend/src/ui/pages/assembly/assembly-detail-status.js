import { missingSubviewReferenceEvidence } from "./reference-evidence-loading.js";
import { getMessages } from "../../i18n/index.js";
const html = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

export function renderAssemblyDetailStatus(state) {
  const assembly = state.assembly || {}, labels = getMessages(state, "assembly").runtime;
  let content = "";
  if (!assembly.loading && assembly.selectedCtgId) {
    if (assembly.ctgDetailLoading) content = `<span role="status">${html(labels.detailLoadingIndependent)}</span>`;
    else if (assembly.ctgDetailError) content = `<span role="alert">${html(labels.detailFailedIndependent)} ${html(assembly.ctgDetailError)}</span>
      <button type="button" class="button ghost tiny" data-assembly-detail-retry>${html(labels.detailRetry)}</button>`;
  }
  return `<div class="assembly-detail-status" data-assembly-detail-status aria-live="polite"${content ? "" : " hidden"}>${content}</div>`;
}

const BOUND = Symbol("assemblyDetailRetry");
export function bindAssemblyDetailRetry(host, retry, retryLocal) {
  if (!host?.addEventListener) return;
  if (host[BOUND]) { host[BOUND].retry = retry; host[BOUND].retryLocal = retryLocal; return; }
  const binding = { retry, retryLocal }; host[BOUND] = binding;
  host.addEventListener("click", event => {
    const detail = event.target?.closest?.("[data-assembly-detail-retry]");
    const local = event.target?.closest?.("[data-assembly-subview-retry]");
    if (detail && host.contains?.(detail)) { event.stopPropagation?.(); void binding.retry(); }
    else if (local && host.contains?.(local)) { event.stopPropagation?.(); void binding.retryLocal(); }
  });
}

export function patchAssemblyDetailStatus(host, state) {
  const current = host?.querySelector?.("[data-assembly-detail-status]");
  const doc = host?.ownerDocument;
  if (!current || !doc?.createElement) return;
  const template = doc.createElement("template"); template.innerHTML = renderAssemblyDetailStatus(state);
  current.replaceWith(template.content.firstElementChild);
}


export function renderAssemblyLocalRestoreStatus(assembly, i18n) {
  const missing = missingSubviewReferenceEvidence(assembly);
  if (missing.length) {
    const error = missing.find(member=>member.referenceEvidence?.status === "error")?.referenceEvidence?.error;
    return `<article class="subview-selection-panel" data-subview-panel="1" aria-busy="${!error}">
      <h4 class="assembly-view-title">${html(i18n.subview.panelTitle)}</h4>
      <p role="${error ? "alert" : "status"}" class="${error ? "error-text" : "muted"}">${html(error || i18n.subview.loadingReferenceEvidence)}</p>
      ${error ? `<button type="button" class="button ghost tiny" data-assembly-subview-retry>${html(i18n.runtime.detailRetry)}</button>` : ""}
    </article>`;
  }
  if (!(assembly.subviewRestoring || assembly.subviewRestoreError)
    || assembly.subviewRestoringSummary !== assembly.subview?.summary) return "";
  const failed = Boolean(assembly.subviewRestoreError);
  return `<article class="subview-selection-panel" data-subview-panel="1" aria-busy="${!failed}">
    <h4 class="assembly-view-title">${html(i18n.subview.panelTitle)}</h4>
    <p role="${failed ? "alert" : "status"}" class="${failed ? "error-text" : "muted"}">${html(failed ? assembly.subviewRestoreError : i18n.subview.loadingPairwiseEvidence)}</p>
    ${failed ? `<button type="button" class="button ghost tiny" data-assembly-subview-retry>${html(i18n.runtime.detailRetry)}</button>` : ""}
  </article>`;
}
