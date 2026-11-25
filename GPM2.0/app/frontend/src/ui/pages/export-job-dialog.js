import { getMessages } from "../i18n/index.js";

function groupOutputPaths(paths) {
  const groups = new Map();
  for (const path of paths) {
    // A backslash is a legal filename character in an absolute macOS path.
    const slash = path.startsWith("/") ? path.lastIndexOf("/") : Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    const root = slash === 0 || (slash === 2 && path[1] === ":");
    const dir = slash < 0 ? "" : path.slice(0, slash + (root ? 1 : 0));
    if (!groups.has(dir)) groups.set(dir, []);
    groups.get(dir).push(path.slice(slash + 1));
  }
  return groups;
}

function exportTitle(job, count, text) {
  switch (job.status) {
    case "running": return job.cancelRequested ? text.canceling : text.running;
    case "canceled": return text.canceled;
    case "success":
      if (!count) return text.empty;
      return count === 1 ? text.success : text.count.replace("{count}", count);
    default: return text.failed;
  }
}

function renderFileGroups(paths, text, escapeHtml) {
  if (!paths.length) return "";
  const groups = Array.from(groupOutputPaths(paths), ([dir, names]) => `
    <section><ul>${names.map(name => `<li>${escapeHtml(name)}</li>`).join("")}</ul>
    ${dir ? `<p class="muted export-result-dir">${text.savedTo} <bdi>${escapeHtml(dir)}</bdi></p>` : ""}</section>`);
  return `<div class="export-result-files">${groups.join("")}</div>`;
}

export function renderExportJobDialog({ job, locale, scope, stepLabel, escapeHtml, receipt = "" }) {
  if (!job?.open) return "";
  const text = getMessages(locale, "exportDialog");
  const running = job.status === "running";
  const success = job.status === "success";
  const paths = [...new Set((job.completedOutputs || []).filter(path => typeof path === "string" && path))];
  const count = paths.length;
  const title = exportTitle(job, count, text);
  const prefix = scope === "project" ? "project-export" : "final-path-export";
  const icon = running ? `<span class="pipeline-spinner" aria-hidden="true"></span>`
    : success && count ? `<span class="pipeline-done" aria-hidden="true">✓</span>` : "";
  const steps = job.steps || [];
  const current = steps.findIndex(step => step.kind === job.currentStep);
  const progress = running && steps.length > 1 && current >= 0
    ? `${text.step.replace("{index}", current + 1).replace("{total}", steps.length)} · ${stepLabel(steps[current].kind)}` : "";
  const action = running
    ? `<button type="button" class="button ghost tiny" data-${prefix}-close="true" ${job.cancelRequested ? "disabled" : ""}>${text.cancel}</button>`
    : `<button type="button" class="button ghost tiny" data-${prefix}-close="true" aria-label="${text.close}" title="${text.close}">×</button>`;
  return `<div class="modal-overlay assembly-final-path-export-overlay" data-${prefix}-overlay="true">
    <article class="card modal-dialog export-job-dialog" data-${prefix}-modal="true" role="dialog" aria-modal="true" aria-labelledby="${prefix}-title">
      <header><h4 id="${prefix}-title">${icon}${title}</h4>${action}</header>
      ${progress ? `<p class="muted" role="status">${escapeHtml(progress)}</p>` : ""}
      ${job.error ? `<p class="error-text" role="alert">${escapeHtml(job.error)}</p>` : ""}
      ${!running && !success && count ? `<p>${count === 1 ? text.keptOne : text.kept.replace("{count}", count)}</p>` : ""}
      ${running ? "" : renderFileGroups(paths, text, escapeHtml)}${receipt}
    </article></div>`;
}
