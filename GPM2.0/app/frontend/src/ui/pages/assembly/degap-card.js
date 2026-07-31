import {
  buildDegapJobKey,
  normalizeDegapRuntimeState,
  normalizeDegapSettings,
  resolveDegapJobOutPath,
  resolveDegapJobSettings,
} from "./degap-state.js";
import { getAssemblyI18n } from "./i18n.js";

function normalizeString(value) {
  return String(value || "").trim();
}

function renderPathInputValue(value) {
  return (Array.isArray(value) ? value : []).join("; ");
}

function resolveDegapJobBadge(jobType = "gapfiller") {
  const normalized = normalizeString(jobType).toLowerCase().replace(/-/g, "_");
  if (normalized === "telseeker_ctg" || normalized === "telseeker") {
    return { label: "telseeker", className: " is-telseeker" };
  }
  return { label: "gapfiller", className: " is-gapfiller" };
}

function renderDegapSettingsFields({
  settings,
  escapeAttr,
  escapeHtml,
  labels,
  prefix = "global",
  includeOutRoot = true,
  outPath = "",
  jobType = "gapfiller",
}) {
  const normalized = normalizeDegapSettings(settings);
  const isTelseeker = normalizeString(jobType).toLowerCase().replace(/-/g, "_") === "telseeker_ctg";
  const fieldAttr = prefix === "job" ? "data-degap-job-field" : "data-degap-setting-field";
  const jobOutPathField = prefix === "job"
    ? `
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.jobOut)}</span>
          <input type="text" ${fieldAttr}="outPath" value="${escapeAttr(outPath)}" placeholder="/server/degap_out/job_id">
        </label>
      `
    : "";
  const mainOutRootField = includeOutRoot
    ? `
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.mainOut)}</span>
          <input type="text" ${fieldAttr}="outRoot" value="${escapeAttr(normalized.outRoot)}" placeholder="/server/degap_out">
        </label>
      `
    : "";
  return `
    <div class="degap-settings-fields">
    <fieldset class="degap-param-group">
      <legend>${escapeHtml(labels.requiredPaths)}</legend>
      <div class="degap-form-grid">
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.degapPath)}</span>
          <input type="text" ${fieldAttr}="degapPath" value="${escapeAttr(normalized.degapPath)}" placeholder="/opt/DEGAP/bin/DEGAP.py">
        </label>
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.hifiReadsPath)}</span>
          <input type="text" ${fieldAttr}="hifiReads" value="${escapeAttr(renderPathInputValue(normalized.hifiReads))}" placeholder="/server/reads/hifi.fastq.gz">
        </label>
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.ontReadsPath)}</span>
          <input type="text" ${fieldAttr}="ontReads" value="${escapeAttr(renderPathInputValue(normalized.ontReads))}" placeholder="/server/reads/ont.fastq.gz">
        </label>
        <label class="degap-form-field is-wide">
          <span>${escapeHtml(labels.gpmServerPath)}</span>
          <input type="text" ${fieldAttr}="gpmServerPath" value="${escapeAttr(normalized.gpmServerPath)}" placeholder="/server/gpm_server">
        </label>
        ${mainOutRootField}
        ${jobOutPathField}
        <p class="helper-hint degap-form-help">${escapeHtml(labels.readsHelp)}</p>
      </div>
    </fieldset>
    <fieldset class="degap-param-group">
      <legend>${escapeHtml(labels.recommendedParameters)}</legend>
      <div class="degap-form-grid">
        <label class="degap-check-field">
          <input type="checkbox" ${fieldAttr}="kmerFilter" ${normalized.kmerFilter ? "checked" : ""}>
          <span>kmer_filter</span>
        </label>
        <label class="degap-form-field">
          <span>MaximumExtensionRound</span>
          <input type="number" min="1" step="1" ${fieldAttr}="maximumExtensionRound" value="${escapeAttr(normalized.maximumExtensionRound)}">
        </label>
        <label class="degap-form-field">
          <span>thread</span>
          <input type="number" min="1" step="1" ${fieldAttr}="thread" value="${escapeAttr(normalized.thread)}">
        </label>
      </div>
    </fieldset>
    <fieldset class="degap-param-group">
      <legend>${escapeHtml(labels.otherGapfillerDefaults)}</legend>
      <div class="degap-form-grid">
        <label class="degap-form-field">
          <span>remove</span>
          <input type="number" min="1" step="1" ${fieldAttr}="remove" value="${escapeAttr(normalized.remove)}">
        </label>
        <label class="degap-form-field">
          <span>edge</span>
          <input type="number" min="1" step="1" ${fieldAttr}="edge" value="${escapeAttr(normalized.edge)}">
        </label>
        <label class="degap-form-field">
          <span>kmer_size</span>
          <input type="number" min="1" step="1" ${fieldAttr}="kmerSize" value="${escapeAttr(normalized.kmerSize)}">
        </label>
        <label class="degap-form-field">
          <span>kmer_num</span>
          <input type="number" min="1" step="1" ${fieldAttr}="kmerNum" value="${escapeAttr(normalized.kmerNum)}">
        </label>
        <label class="degap-form-field">
          <span>MaximumExtensionLength</span>
          <input type="number" min="1" step="1" ${fieldAttr}="maximumExtensionLength" value="${escapeAttr(normalized.maximumExtensionLength)}">
        </label>
        ${isTelseeker ? "" : `
          <label class="degap-form-field">
            <span>filterDepthHifi</span>
            <input type="number" min="0" step="0.01" ${fieldAttr}="filterDepthHifi" value="${escapeAttr(normalized.filterDepthHifi)}">
          </label>
          <label class="degap-form-field">
            <span>filterDepthOnt</span>
            <input type="number" min="0" step="0.01" ${fieldAttr}="filterDepthOnt" value="${escapeAttr(normalized.filterDepthOnt)}">
          </label>
        `}
        <label class="degap-form-field">
          <span>motif</span>
          <input type="text" ${fieldAttr}="motif" value="${escapeAttr(normalized.motif)}" placeholder="TTAGGG">
        </label>
        <label class="degap-form-field">
          <span>work</span>
          <input type="number" min="1" step="1" ${fieldAttr}="work" value="${escapeAttr(normalized.work)}">
        </label>
        <label class="degap-form-field">
          <span>tel-n</span>
          <input type="number" min="1" step="1" ${fieldAttr}="telN" value="${escapeAttr(normalized.telN)}">
        </label>
        <label class="degap-form-field">
          <span>tel-r</span>
          <input type="number" min="0.01" max="1" step="0.01" ${fieldAttr}="telR" value="${escapeAttr(normalized.telR)}">
        </label>
        <label class="degap-form-field">
          <span>tel-mm</span>
          <input type="number" min="0" max="1" step="1" ${fieldAttr}="telMm" value="${escapeAttr(normalized.telMm)}">
        </label>
      </div>
    </fieldset>
    </div>
  `;
}

function renderGlobalSettingsModal({ degap, escapeAttr, escapeHtml, labels }) {
  const settings = normalizeDegapSettings(degap.settings);
  return `
    <div class="degap-settings-modal-overlay" data-degap-settings-modal>
      <div class="degap-settings-dialog" role="dialog" aria-modal="true" aria-label="${escapeAttr(labels.settingsTitle)}">
        <div class="degap-settings-head">
          <strong>${escapeHtml(labels.settingsTitle)}</strong>
          <button type="button" class="button ghost tiny degap-icon-button" data-degap-settings-close aria-label="${escapeAttr(labels.close)}">×</button>
        </div>
        <div class="degap-settings-body" data-degap-settings-panel>
          ${renderDegapSettingsFields({ settings, escapeAttr, escapeHtml, labels })}
        </div>
        <div class="degap-settings-foot">
          <span class="${degap.error ? "danger" : "muted"}">${escapeHtml(degap.error || degap.feedback || "")}</span>
          <button type="button" class="button primary tiny" data-degap-settings-save>${escapeHtml(labels.save)}</button>
        </div>
      </div>
    </div>
  `;
}

function renderJobEditor(job, degap, escapeAttr, escapeHtml, labels) {
  const settings = resolveDegapJobSettings(job, degap.settings);
  const jobKey = buildDegapJobKey(job);
  return `
    <div class="degap-job-editor" data-degap-job-editor data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}">
      ${renderDegapSettingsFields({
        settings,
        escapeAttr,
        escapeHtml,
        labels,
        prefix: "job",
        includeOutRoot: false,
        outPath: resolveDegapJobOutPath(job, degap.settings),
        jobType: job.jobType,
      })}
      <div class="degap-job-editor-foot">
        <button type="button" class="button ghost tiny" data-degap-job-reset data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}">${escapeHtml(labels.reset)}</button>
        <button type="button" class="button primary tiny" data-degap-job-save data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}">${escapeHtml(labels.save)}</button>
      </div>
    </div>
  `;
}

function renderJobRows({ jobs, degap, escapeAttr, escapeHtml, labels }) {
  return jobs.map((job) => {
    const jobKey = buildDegapJobKey(job);
    const jobBadge = resolveDegapJobBadge(job.jobType);
    const expanded = normalizeString(degap.expandedJobId) === jobKey
      || normalizeString(degap.expandedJobId) === job.jobId;
    return `
      <div class="degap-job-shell">
        <div class="degap-job-row" data-degap-job-row data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}" data-degap-job-chr-name="${escapeAttr(job.chrName || "")}">
          <button type="button" class="degap-job-remove" data-degap-job-remove data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}" aria-label="${escapeAttr(labels.removeJobAria)}">×</button>
          <span class="degap-job-type-badge${jobBadge.className}">${escapeHtml(jobBadge.label)}</span>
          <span class="degap-job-label">${escapeHtml(job.label || job.jobId)}</span>
          <button type="button" class="degap-job-expand" data-degap-job-toggle data-degap-job-id="${escapeAttr(job.jobId)}" data-degap-job-key="${escapeAttr(jobKey)}" aria-expanded="${expanded ? "true" : "false"}">${expanded ? "▴" : "▾"}</button>
        </div>
        ${expanded ? renderJobEditor(job, degap, escapeAttr, escapeHtml, labels) : ""}
      </div>
    `;
  }).join("");
}

function renderDegapToast({ runtime, shouldShowSettings, escapeHtml }) {
  if (shouldShowSettings) {
    return "";
  }
  const message = runtime.error || runtime.feedback || "";
  if (!message) {
    return "";
  }
  const toneClass = runtime.error ? " is-danger" : "";
  return `
    <div class="degap-toast${toneClass}" data-degap-toast role="status">${escapeHtml(message)}</div>
  `;
}

function resolveDegapLabels(i18n) {
  const labels = i18n?.degap || getAssemblyI18n(i18n?.locale || "zh").degap;
  return {
    ...getAssemblyI18n("zh").degap,
    ...labels,
    locale: i18n?.locale || labels?.locale || "zh",
  };
}

export function renderDegapRuntime({ degap }, { escapeAttr, escapeHtml, i18n }) {
  const runtime = normalizeDegapRuntimeState(degap);
  const labels = resolveDegapLabels(i18n);
  return `
    <div class="degap-panel degap-runtime" data-degap-panel data-degap-runtime>
      ${runtime.panelOpen ? renderGlobalSettingsModal({ degap: runtime, escapeAttr, escapeHtml, labels }) : ""}
      ${renderDegapToast({ runtime, shouldShowSettings: runtime.panelOpen, escapeHtml })}
    </div>
  `;
}

export function renderDegapJobCard({ chrName, degap }, { escapeAttr, escapeHtml, i18n }) {
  const runtime = normalizeDegapRuntimeState(degap);
  const labels = resolveDegapLabels(i18n);
  const normalizedChrName = normalizeString(chrName);
  const jobs = runtime.jobs.filter((job) => normalizeString(job.chrName) === normalizedChrName);
  if (!normalizedChrName || !jobs.length) {
    return "";
  }
  const collapsed = runtime.collapsedJobCardChrNames.includes(normalizedChrName);
  const toggleLabel = collapsed ? labels.expandJobsCard : labels.collapseJobsCard;
  return `
    <section class="degap-jobs-panel degap-job-card${collapsed ? " is-collapsed" : ""}" data-degap-jobs-panel data-degap-job-card data-degap-job-card-chr-name="${escapeAttr(normalizedChrName)}">
      <div class="degap-jobs-head">
        <button type="button" class="degap-job-card-toggle" data-degap-job-card-toggle data-degap-job-card-chr-name="${escapeAttr(normalizedChrName)}" aria-expanded="${collapsed ? "false" : "true"}" aria-label="${escapeAttr(toggleLabel)}" title="${escapeAttr(toggleLabel)}">
          <span class="degap-job-card-indicator" aria-hidden="true">${collapsed ? "▸" : "▾"}</span>
          <strong>${escapeHtml(labels.jobsTitle)} (${jobs.length})</strong>
        </button>
        <button type="button" class="degap-settings-button" data-degap-settings-open aria-label="${escapeAttr(labels.settingsTitle)}" title="${escapeAttr(labels.settingsTitle)}">⚙</button>
      </div>
      ${collapsed ? "" : `<div class="degap-job-list" data-degap-job-card-body>${renderJobRows({ jobs, degap: runtime, escapeAttr, escapeHtml, labels })}</div>`}
    </section>
  `;
}
