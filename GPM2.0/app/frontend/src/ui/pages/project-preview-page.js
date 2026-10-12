import { projectIcon } from "./project-icons.js";
import { syncFinalPathStripGeometry } from "./assembly/final-path-visual-layout.js";
import { getMessages } from "../i18n/index.js";
import { getGrtProjectView, getProjectAssemblyViewState, listChrViewCtgs,
  listPhasedChrTracks, listProjectChromosomes } from "../../services/workflow-api.js";
import { normalizeGrtProjectView } from "./assembly/grt-state.js";
import { canonicalizeFinalPathOverallLengths, normalizeFinalPathByChr,
  resolveFinalPathSegmentDisplayName } from "./assembly/final-path-state.js";
import { buildProjectPreviewModel, previewProjectKey, requestPreviewChromosome } from "./project-preview-state.js";

const requests = new WeakMap();
const BOUND = Symbol("projectPreviewBound");
const html = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const number = value => Number(value).toLocaleString("en-US");
const bpLabel = value => value >= 1000000 ? `${(value / 1000000).toFixed(3)} Mb`
  : value >= 1000 ? `${(value / 1000).toFixed(1)} kb` : `${number(value)} bp`;
const percent = value => Math.max(0, Math.min(100, value)).toFixed(5);

function partTitle(part, labels) {
  if (part.gap) return `${labels.gap}: ${number(part.length)} bp`;
  const source = part.source;
  return source ? `${source.datasetName || labels.unknown} / ${source.contigName}: ${number(source.start)}–${number(source.end)} (${source.orient})`
    : resolveFinalPathSegmentDisplayName(part.segment);
}

function renderHighlight(patch, length, labels) {
  if (!(length > 0) || patch.end <= patch.start) return "";
  return `<span class="project-preview-used" style="left:${percent(patch.start / length * 100)}%;width:${percent((patch.end - patch.start) / length * 100)}%;--source-color:${patch.part.color}" title="${html(`${labels.used}: ${partTitle(patch.part, labels)}`)}"></span>`;
}

// Flatten dataset colors over white: overlapping source-context strips must
// not accumulate translucent fills and look like internal shadows.
function datasetTint(color, weight) {
  return "#" + color.slice(1).match(/../g).map(channel =>
    Math.round(parseInt(channel, 16) * weight + 255 * (1 - weight)).toString(16).padStart(2, "0")
  ).join("");
}

function renderContig(item, track, domain, labels) {
  const visibleStart = domain ? Math.max(domain.start, item.start) : 0;
  const visibleEnd = domain ? Math.min(domain.end, item.start + item.length) : item.length;
  if (visibleEnd <= visibleStart) return "";
  const clipped = domain ? visibleStart - item.start : 0;
  const visibleLength = visibleEnd - visibleStart;
  const start = domain ? (visibleStart - domain.start) / (domain.end - domain.start) * 100 : 0;
  const width = domain ? visibleLength / (domain.end - domain.start) * 100 : 100;
  const alignment = item.alignment;
  const attrs = alignment ? ` data-final-path-aligned-source="1" data-final-path-source-path="${html(alignment.pathName)}" data-final-path-source-index="${alignment.index}" data-final-path-source-offset="${alignment.offset}" data-final-path-used-start="${alignment.usedStart}" data-final-path-used-end="${alignment.usedEnd}" data-final-path-source-length="${item.length}"` : "";
  const title = `${item.name} · ${number(item.length)} bp`;
  return `<span class="project-preview-contig${item.highlights.length ? " is-adopted" : " is-context"}" ${attrs} style="left:${percent(start)}%;width:${percent(width)}%;top:${(item.lane || 0) * 20 + 2}px;background:${datasetTint(track.color, .33)};border-color:${datasetTint(track.color, .4)}" title="${html(title)}">
    ${item.highlights.map(patch => renderHighlight({ ...patch, start: Math.max(0, patch.start - clipped), end: Math.min(visibleLength, patch.end - clipped) }, visibleLength, labels)).join("")}
    <span class="project-preview-contig-label" data-preview-source-fit-label="1">${html(item.name)}${(item.displayOrient || (item.reverse ? "-" : "+")) === "-" ? " (−)" : ""}</span>
  </span>`;
}

function axis(label, start, end) {
  return `<span class="project-preview-row project-preview-axis"><span class="project-preview-track-label">${html(label)}</span>
    <span class="project-preview-axis-values"><span>${html(bpLabel(start))}</span><span>${html(bpLabel(end))}</span></span></span>`;
}

function renderCard(card, labels) {
  const { domain } = card;
  const ref = card.hasReference ? `<div class="project-preview-row"><span class="project-preview-track-label">Ref</span>
    <span class="project-preview-plot" style="height:18px"><span class="project-preview-reference" style="left:${percent(-domain.start / (domain.end - domain.start) * 100)}%;width:${percent(card.refLength / (domain.end - domain.start) * 100)}%" title="${html(`${labels.referenceHint}: ${card.chrName} · ${number(card.refLength)} bp`)}">
      ${card.refHighlights.map(patch => renderHighlight(patch, card.refLength, labels)).join("")}
    </span></span></div>` : "";
  const rows = card.tracks.map(track => `<div class="project-preview-row"><span class="project-preview-track-label" title="${html(track.name || labels.unknown)}"><span class="project-preview-dataset-dot" style="background:${track.color}"></span>${html(track.name || labels.unknown)}</span>
    <div class="project-preview-source-plots">
      ${track.positioned.length ? `<span class="project-preview-plot" style="height:${track.laneCount * 20 + 4}px">${track.positioned.slice().sort((a, b) => Number(Boolean(a.alignment)) - Number(Boolean(b.alignment))).map(item => renderContig(item, track, domain, labels)).join("")}</span>` : ""}
      ${!track.positioned.length ? `<span class="project-preview-empty-track">—</span>` : ""}
    </div></div>`).join("");
  const paths = card.paths.map(path => path.parts.length ? `<div class="project-preview-path">
    <div class="project-preview-row"><span class="project-preview-track-label project-preview-final-label" title="${html(path.name)}">Final Path${path.name !== card.chrName ? `<small>${html(path.name)}</small>` : ""}</span>
      <span class="project-preview-plot project-preview-final-plot${path.parts.some(part => part.gap) ? " has-gaps" : ""}" data-final-path-strip="1" data-final-path-name="${html(path.name)}" data-final-path-domain="${domain.end}" style="height:${path.parts.some(part => part.gap) ? 40 : 24}px">${path.parts.map((part, index) => `<span class="project-preview-final-part${part.gap ? " is-gap" : ""}" data-final-path-segment="1" data-final-path-kind="${part.gap ? "gap" : "ctg"}" data-final-path-length="${part.length}" style="left:${percent(part.start / domain.end * 100)}%;width:${percent(part.length / domain.end * 100)}%;background:${part.gap ? "#dbd2bd" : `${part.color}70`}" title="${html(`${partTitle(part, labels)} · ${number(part.length)} bp`)}"><span data-final-path-fit-label>${html(part.gap ? labels.gap : resolveFinalPathSegmentDisplayName(part.segment))}${!part.gap && (part.source?.orient === "-" || part.segment.orient === "-") ? " (−)" : ""}</span></span>${part.gap ? `<span class="project-preview-gap-label" data-final-path-gap-label="${index}" style="left:clamp(14px, ${percent((part.start + part.length / 2) / domain.end * 100)}%, calc(100% - 14px));" title="${html(partTitle(part, labels))}">${html(labels.gap)}</span>` : ""}`).join("")}</span>
    </div></div>` : `<div class="project-preview-row"><span class="project-preview-track-label project-preview-final-label">Final Path${path.name !== card.chrName ? `<small>${html(path.name)}</small>` : ""}</span><span class="project-preview-empty-track">${html(labels.noPath)}</span></div>`).join("");
  const pathSummary = card.paths.filter(path => path.parts.length).map(path => bpLabel(path.length)).join(" / ");
  const summary = [card.hasReference ? `Ref ${bpLabel(card.refLength)}` : "", pathSummary ? `Final Path ${pathSummary}` : ""].filter(Boolean).join(" · ");
  return `<article class="project-preview-card" data-preview-chr="${html(card.chrName)}" aria-label="${html(card.chrName)}">
    <button type="button" class="project-preview-card-header" aria-label="${html(`${card.chrName} · ${labels.open}`)}"><span class="project-preview-chr-name">${html(card.chrName)}</span><span class="project-preview-card-summary">${html(summary)}</span><span class="project-preview-open">${html(labels.open)} →</span></button>
    ${axis(labels.compositionAxis, domain.start, domain.end)}
    ${ref}${rows}
    <div class="project-preview-paths">${paths || `<span class="project-preview-empty-track">${html(labels.noPath)}</span>`}</div>
    ${card.unresolvedCount ? `<span class="project-preview-warning">${html(labels.unresolved)} (${card.unresolvedCount})</span>` : ""}
  </article>`;
}

export function renderProjectPreviewPage(state) {
  const labels = getMessages(state, "projectPreview"), key = previewProjectKey(state);
  const preview = state.projectPreview?.key === key ? state.projectPreview : {};
  const content = !key ? `<p class="muted">${html(labels.noProject)}</p>`
    : preview.error ? `<p class="error-text" role="alert">${html(preview.error)}</p><button type="button" class="button" data-preview-refresh>${html(labels.retry)}</button>`
    : preview.loading || !preview.loaded ? `<p class="muted" role="status">${html(labels.loading)}</p>`
    : preview.cards?.length ? `<div class="project-preview-cards">${preview.cards.map(card => renderCard(card, labels)).join("")}</div>`
    : `<p class="muted">${html(labels.empty)}</p>`;
  return `<section class="project-preview-page"><header class="project-preview-heading"><h2>${html(labels.title)}</h2><span class="project-preview-subtitle" title="${html(labels.subtitle)}">${html(labels.subtitle)}</span>
    <details class="project-preview-legend"><summary aria-label="${html(labels.legend)}" title="${html(labels.legend)}">i</summary><div class="project-preview-hint">${html(labels.hint)}</div></details>
    <button type="button" class="button project-preview-refresh" data-preview-refresh title="${html(labels.refresh)}" aria-label="${html(labels.refresh)}" ${!key || preview.loading ? "disabled" : ""}>${projectIcon("refresh")}</button></header>
    ${content}</section>`;
}

export async function loadProjectPreviewData(host, store, deps = {}) {
  const state = store.getState(), key = previewProjectKey(state);
  if (!key) return false;
  const request = {};
  requests.set(store, request);
  const isCurrent = () => requests.get(store) === request && previewProjectKey(store.getState()) === key
    && store.getState().activeRoute === "projectPreview";
  const rerender = () => { if (isCurrent()) { host.innerHTML = renderProjectPreviewPage(store.getState()); syncFinalPathStripGeometry(host); } };
  store.setState({ projectPreview: { key, loading: true, loaded: false, error: "" } });
  rerender();
  const args = { workspaceRoot: state.session.workspacePath, projectId: state.session.projectId };
  try {
    const [chromosomes, ctgResult, view, rawGrt] = await Promise.all([
      (deps.listProjectChromosomes || listProjectChromosomes)(args),
      (deps.listChrViewCtgs || listChrViewCtgs)({ ...args, chrName: null }),
      (deps.getProjectAssemblyViewState || getProjectAssemblyViewState)(args),
      (deps.getGrtProjectView || getGrtProjectView)(args),
    ]);
    if (!isCurrent()) return false;
    const project = state.initializer?.existingProjects?.find(item => Number(item.projectId) === Number(args.projectId)) || {};
    const phasedChrTracksByChr = {};
    if (project.phasedAssemblyEnabled) {
      for (const chr of chromosomes.items || []) {
        if (!isCurrent()) return false;
        const result = await (deps.listPhasedChrTracks || listPhasedChrTracks)({ ...args, parentChrName: chr.chrName });
        phasedChrTracksByChr[chr.chrName] = result.tracks || [];
      }
    }
    if (!isCurrent()) return false;
    const baseline = normalizeGrtProjectView(rawGrt).baselineFinalPathByChr;
    // In-memory edits win over persisted paths, including explicit empty paths.
    const finalPathByChr = canonicalizeFinalPathOverallLengths({ ...baseline,
      ...normalizeFinalPathByChr(view?.finalPathByChr),
      ...normalizeFinalPathByChr(store.getState().assembly?.finalPathByChr),
    }, baseline);
    const cards = buildProjectPreviewModel({ chromosomes: chromosomes.items || [],
      referenceGenomeId: chromosomes.referenceGenomeId, ctgs: ctgResult.items || [],
      datasets: state.initializer?.datasets || [], project, finalPathByChr, phasedChrTracksByChr });
    store.setState({ projectPreview: { key, loading: false, loaded: true, error: "",
      chromosomes: chromosomes.items || [], cards } });
    rerender();
    return true;
  } catch (error) {
    if (!isCurrent()) return false;
    store.setState({ projectPreview: { key, loading: false, loaded: false,
      error: String(error?.message || error) } });
    rerender();
    return false;
  }
}

export function bindProjectPreviewPage(host, store, deps = {}) {
  const binding = host[BOUND] || {};
  binding.store = store; binding.deps = deps;
  if (!host[BOUND]) {
    host.addEventListener("click", event => {
      if (binding.store.getState().activeRoute !== "projectPreview") return;
      const card = event.target?.closest?.("[data-preview-chr]");
      if (card && host.contains(card)) {
        requestPreviewChromosome(binding.store, card.dataset.previewChr);
        return;
      }
      const refresh = event.target?.closest?.("[data-preview-refresh]");
      if (refresh && host.contains(refresh)) void loadProjectPreviewData(host, binding.store, binding.deps);
    });
    const win = host.ownerDocument?.defaultView;
    const Observer = win?.ResizeObserver;
    if (Observer) {
      binding.resize = new Observer(() => {
        if (binding.store.getState().activeRoute === "projectPreview") syncFinalPathStripGeometry(host);
      });
      binding.resize.observe(host);
    } else {
      win?.addEventListener?.("resize", () => {
        if (binding.store.getState().activeRoute === "projectPreview") syncFinalPathStripGeometry(host);
      });
    }
    host[BOUND] = binding;
  }
  void loadProjectPreviewData(host, store, deps);
}
