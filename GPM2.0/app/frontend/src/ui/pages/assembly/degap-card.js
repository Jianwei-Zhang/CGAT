import { resolveTrackPrefs } from "./track-prefs.js";
import { renderFinalPathGraph } from "./final-path-card.js";
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

function normalizeDegapFinalPathEntries(finalPathEntry, finalPathEntries = []) {
  const entries = (Array.isArray(finalPathEntries) ? finalPathEntries : [])
    .map((entry) => {
      const entryFinalPath = entry?.finalPathEntry || null;
      const chrName = normalizeString(entry?.chrName || entryFinalPath?.chrName);
      if (!chrName || !entryFinalPath) {
        return null;
      }
      return {
        key: normalizeString(entry?.key),
        label: normalizeString(entry?.label) || chrName,
        chrName,
        finalPathEntry: entryFinalPath,
        graphPreviewSegmentOrder: Array.isArray(entry?.graphPreviewSegmentOrder)
          ? entry.graphPreviewSegmentOrder
          : null,
      };
    })
    .filter(Boolean);
  if (entries.length) {
    return entries;
  }
  const chrName = normalizeString(finalPathEntry?.chrName);
  return chrName && finalPathEntry
    ? [{ key: "", label: chrName, chrName, finalPathEntry, graphPreviewSegmentOrder: null }]
    : [];
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

function renderDegapContextMenu({ menu, escapeAttr, escapeHtml, labels }) {
  if (!menu) {
    return "";
  }
  const left = Math.max(0, Number(menu.x || 0));
  const top = Math.max(0, Number(menu.y || 0));
  if (menu.type === "ctg-end") {
    const endpointSides = (Array.isArray(menu.endpointSides) && menu.endpointSides.length
      ? menu.endpointSides
      : [menu.endpointSide || "left"])
      .map((side) => (normalizeString(side).toLowerCase() === "right" ? "right" : "left"));
    return `
      <div class="degap-gap-menu" data-degap-gap-menu style="left:${left}px;top:${top}px;">
        ${endpointSides.map((action) => {
          const label = action === "right" ? labels.addTelseekerRightJob : labels.addTelseekerLeftJob;
          return `<button type="button" data-degap-telseeker-action="${escapeAttr(action)}">${escapeHtml(label)}</button>`;
        }).join("")}
      </div>
    `;
  }
  return `
    <div class="degap-gap-menu" data-degap-gap-menu style="left:${left}px;top:${top}px;">
      <button type="button" data-degap-gap-action="left" data-degap-gap-segment-id="${escapeAttr(menu.gapSegmentId || "")}">${escapeHtml(labels.addLeftJob)}</button>
      <button type="button" data-degap-gap-action="right" data-degap-gap-segment-id="${escapeAttr(menu.gapSegmentId || "")}">${escapeHtml(labels.addRightJob)}</button>
      <button type="button" data-degap-gap-action="all" data-degap-gap-segment-id="${escapeAttr(menu.gapSegmentId || "")}">${escapeHtml(labels.addAllJob)}</button>
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

function groupJobsForAllMode(jobs, entries) {
  const groups = [];
  const usedKeys = new Set();
  entries.forEach((entry) => {
    const entryJobs = jobs.filter((job) => normalizeString(job.chrName) === entry.chrName);
    if (!entryJobs.length) {
      return;
    }
    entryJobs.forEach((job) => usedKeys.add(buildDegapJobKey(job)));
    groups.push({ chrName: entry.chrName, label: entry.label, jobs: entryJobs });
  });
  jobs.forEach((job) => {
    const jobKey = buildDegapJobKey(job);
    if (usedKeys.has(jobKey)) {
      return;
    }
    const chrName = normalizeString(job.chrName) || "__unassigned__";
    let group = groups.find((candidate) => candidate.chrName === chrName);
    if (!group) {
      group = {
        chrName,
        label: chrName === "__unassigned__" ? "Unassigned" : chrName,
        jobs: [],
      };
      groups.push(group);
    }
    group.jobs.push(job);
  });
  return groups;
}

function renderJobList({ degap, finalPathEntry, finalPathEntries, escapeAttr, escapeHtml, labels }) {
  const allJobs = Array.isArray(degap.jobs) ? degap.jobs : [];
  const entries = normalizeDegapFinalPathEntries(finalPathEntry, finalPathEntries);
  const isAllMode = entries.length > 1;
  const hasScopedJobs = allJobs.some((job) => normalizeString(job.chrName));
  const currentChrName = normalizeString(finalPathEntry?.chrName || entries[0]?.chrName);
  const jobs = isAllMode || !hasScopedJobs || !currentChrName
    ? allJobs
    : allJobs.filter((job) => normalizeString(job.chrName) === currentChrName);
  if (!jobs.length) {
    return `<div class="muted degap-empty">${escapeHtml(labels.noJobs)}</div>`;
  }
  if (isAllMode) {
    const groups = groupJobsForAllMode(jobs, entries).filter((group) => group.jobs.length);
    if (!groups.length) {
      return `<div class="muted degap-empty">${escapeHtml(labels.noJobs)}</div>`;
    }
    return `
      <div class="degap-job-group-list">
        ${groups.map((group) => `
          <section class="degap-job-group" data-degap-job-group="${escapeAttr(group.chrName)}">
            <div class="degap-job-group-head"><strong>${escapeHtml(group.label)}</strong></div>
            <div class="degap-job-list">
              ${renderJobRows({ jobs: group.jobs, degap, escapeAttr, escapeHtml, labels })}
            </div>
          </section>
        `).join("")}
      </div>
    `;
  }
  return `
    <div class="degap-job-list">
      ${renderJobRows({ jobs, degap, escapeAttr, escapeHtml, labels })}
    </div>
  `;
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

export function renderDegapPanel(
  {
    finalPathEntry,
    finalPathEntries = [],
    trackView,
    trackViewportPx = 1200,
    primaryDatasetName = "",
    degap,
  },
  {
    escapeAttr,
    escapeHtml,
    i18n,
  },
) {
  const runtime = normalizeDegapRuntimeState(degap);
  const labels = resolveDegapLabels(i18n);
  const trackPrefs = resolveTrackPrefs(runtime.trackView || trackView);
  const shouldShowSettings = runtime.panelOpen || !runtime.settingsPanelDismissed;
  const entries = normalizeDegapFinalPathEntries(finalPathEntry, finalPathEntries);
  const isAllMode = entries.length > 1;
  const renderGraphEntry = (entry) => `
    <div class="degap-graph-wrap" data-degap-graph data-final-path-target-chr-name="${escapeAttr(entry.chrName)}">
      ${renderFinalPathGraph({
        escapeAttr,
        escapeHtml,
        finalPathEntry: entry.finalPathEntry,
        trackControls: trackPrefs,
        trackViewportPx,
        primaryDatasetName,
        previewSegmentOrder: entry.graphPreviewSegmentOrder,
        targetChrName: entry.chrName,
        allGraphLabel: isAllMode ? entry.label : "",
        compact: "degap",
      })}
      ${!isAllMode || normalizeString(runtime.menu?.chrName) === entry.chrName
        ? renderDegapContextMenu({ menu: runtime.menu, escapeAttr, escapeHtml, labels })
        : ""}
    </div>
  `;
  const graph = isAllMode
    ? `<div class="final-path-all-card-stack" data-final-path-all-stack="true">${entries.map((entry) => `
        <section class="final-path-all-card is-degap" data-final-path-all-card="${escapeAttr(entry.chrName)}" data-final-path-target-chr-name="${escapeAttr(entry.chrName)}">
          ${renderGraphEntry(entry)}
        </section>
      `).join("")}</div>`
    : renderGraphEntry(entries[0] || { chrName: normalizeString(finalPathEntry?.chrName), label: "", finalPathEntry });
  return `
    <section class="degap-panel" data-degap-panel>
      ${shouldShowSettings ? renderGlobalSettingsModal({ degap: runtime, escapeAttr, escapeHtml, labels }) : ""}
      ${renderDegapToast({ runtime, shouldShowSettings, escapeHtml })}
      <div class="degap-panel-body">
        ${graph}
        <section class="degap-jobs-panel" data-degap-jobs-panel>
          <div class="degap-jobs-head">
            <strong>${escapeHtml(labels.jobsTitle)}</strong>
            <button type="button" class="degap-settings-button" data-degap-settings-open aria-label="${escapeAttr(labels.settingsTitle)}" title="${escapeAttr(labels.settingsTitle)}">⚙</button>
          </div>
          ${renderJobList({ degap: runtime, finalPathEntry, finalPathEntries: entries, escapeAttr, escapeHtml, labels })}
        </section>
      </div>
    </section>
  `;
}
