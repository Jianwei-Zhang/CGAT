import { contigColorToken } from "./assembly/contig-colors.js";
import { projectIcon } from "./project-icons.js";
import { syncFinalPathStripGeometry } from "./assembly/final-path-visual-layout.js";
import { previewSemanticSignature, previewMutationStamp } from "../../services/preview-content-events.js";
import { getProjectPreviewCache, putProjectPreviewCache } from "../../services/workflow-api.js";
import { PREVIEW_MODEL_VERSION, previewSession, rememberPreviewEntry, previewLocalSignatures,
  pathSignatures, previewOverrideSignature, previewStateIsApplicable, compactPreviewInputs, previewPaletteKey,
  previewPathParents, affectedPreviewChromosomes, persistentPreviewPayload, isPreviewSnapshot,
  markPreviewDom, restoreProjectPreviewDom } from "./project-preview-cache.js";
import { getMessages } from "../i18n/index.js";
import { getGrtProjectView, getProjectAssemblyViewState, listChrViewCtgs,
  listPhasedChrTracks, listProjectChromosomes } from "../../services/workflow-api.js";
import { normalizeGrtProjectView } from "./assembly/grt-state.js";
import { canonicalizeFinalPathOverallLengths, normalizeFinalPathByChr,
  resolveFinalPathSegmentDisplayName } from "./assembly/final-path-state.js";
import { buildProjectPreviewModel, previewProjectKey, requestPreviewChromosome } from "./project-preview-state.js";

const requests = new WeakMap();
const BOUND = Symbol("projectPreviewBound");
const nodeModels = new WeakMap();
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
  return `<span class="project-preview-used" style="left:${percent(patch.start / length * 100)}%;width:${percent((patch.end - patch.start) / length * 100)}%;--source-color:${contigColorToken(patch.part.role, "stroke")}" title="${html(`${labels.used}: ${partTitle(patch.part, labels)}`)}"></span>`;
}

function renderContig(item, track, domain, labels) {
  // Adopted fragments share the path's visual floor. Never extrapolate that
  // scale to the entire source contig (a tiny donor can span megabases).
  const sourceStart = item.start + (item.alignment?.usedStart ?? 0);
  const sourceEnd = item.start + (item.alignment?.usedEnd ?? item.length);
  const visibleStart = domain ? Math.max(domain.start, sourceStart) : sourceStart;
  const visibleEnd = domain ? Math.min(domain.end, sourceEnd) : sourceEnd;
  if (visibleEnd <= visibleStart) return "";
  const clipped = domain ? visibleStart - item.start : 0;
  const visibleLength = visibleEnd - visibleStart;
  const start = domain ? (visibleStart - domain.start) / (domain.end - domain.start) * 100 : 0;
  const width = domain ? visibleLength / (domain.end - domain.start) * 100 : 100;
  const alignment = item.alignment;
  const attrs = alignment ? ` data-final-path-aligned-source="1" data-final-path-source-path="${html(alignment.pathName)}" data-final-path-source-index="${alignment.index}" data-final-path-source-offset="${alignment.offset}" data-final-path-used-start="${alignment.usedStart}" data-final-path-used-end="${alignment.usedEnd}" data-final-path-source-length="${item.length}"` : "";
  const title = alignment
    ? `${item.name} · ${labels.used}: ${partTitle(item.highlights[0].part, labels)} · ${number(alignment.usedEnd - alignment.usedStart)} bp`
    : `${item.name} · ${number(item.length)} bp`;
  return `<span class="project-preview-contig${item.highlights.length ? " is-adopted" : " is-context"}" ${attrs} style="left:${percent(start)}%;width:${percent(width)}%;top:${(item.lane || 0) * 20 + 2}px;background:${contigColorToken(track.role)};border-color:${contigColorToken(track.role, "stroke")};color:${contigColorToken(track.role, "text")}" title="${html(title)}">
    ${item.highlights.map(patch => renderHighlight({ ...patch, start: Math.max(0, patch.start - clipped), end: Math.min(visibleLength, patch.end - clipped) }, visibleLength, labels)).join("")}
    <span class="project-preview-contig-label" data-preview-source-fit-label="1">${html(item.name)}${(item.displayOrient || (item.reverse ? "-" : "+")) === "-" ? " (−)" : ""}</span>
  </span>`;
}

function axis(label, start, end) {
  return `<span class="project-preview-row project-preview-axis"><span class="project-preview-track-label">${html(label)}</span>
    <span class="project-preview-axis-values"><span>${html(bpLabel(start))}</span><span>${html(bpLabel(end))}</span></span></span>`;
}

function renderReference(card, labels) {
  const { domain } = card;
  const reference = card.reference || { start: 0, reverse: false };
  const refStart = Math.max(domain.start, reference.start), refEnd = Math.min(domain.end, reference.start + card.refLength);
  const refAlignment = reference.alignment;
  const refAttrs = refAlignment ? ` data-preview-reference-path="${html(refAlignment.pathName)}" data-preview-reference-index="${refAlignment.index}" data-preview-reference-offset="${refAlignment.offset}" data-preview-reference-length="${card.refLength}"` : "";
  const refPatches = card.refHighlights.map(patch => ({ ...patch,
    start: reference.reverse ? card.refLength - patch.end : patch.start,
    end: reference.reverse ? card.refLength - patch.start : patch.end }));
  return card.hasReference ? `<div class="project-preview-row"><span class="project-preview-track-label">Ref</span>
    <span class="project-preview-plot" style="height:18px"><span class="project-preview-reference"${refAttrs} style="left:${percent((refStart - domain.start) / (domain.end - domain.start) * 100)}%;width:${percent(Math.max(0, refEnd - refStart) / (domain.end - domain.start) * 100)}%" title="${html(`${labels.referenceHint}: ${card.chrName} · ${number(card.refLength)} bp`)}">
      ${refPatches.map(patch => {
        const start = Math.max(refStart, reference.start + patch.start);
        const end = Math.min(refEnd, reference.start + patch.end);
        const length = Math.max(1, refEnd - refStart);
        return `<span class="project-preview-used" data-preview-reference-highlight-start="${patch.start}" data-preview-reference-highlight-end="${patch.end}" style="left:${percent((start - refStart) / length * 100)}%;width:${percent(Math.max(0, end - start) / length * 100)}%;--source-color:${contigColorToken(patch.part.role, "stroke")}" title="${html(`${labels.used}: ${partTitle(patch.part, labels)}`)}"></span>`;
      }).join("")}
    </span></span></div>` : "";
}

function renderCard(card, labels) {
  const { domain } = card;
  const ref = renderReference(card, labels);
  const rows = card.tracks.map(track => `<div class="project-preview-row"><span class="project-preview-track-label" title="${html(track.name || labels.unknown)}"><span class="project-preview-dataset-dot" style="background:${contigColorToken(track.role, "stroke")}"></span>${html(track.name || labels.unknown)}</span>
    <div class="project-preview-source-plots">
      ${track.positioned.length ? `<span class="project-preview-plot" style="height:${track.laneCount * 20}px">${track.positioned.slice().sort((a, b) => Number(Boolean(a.alignment)) - Number(Boolean(b.alignment))).map(item => renderContig(item, track, domain, labels)).join("")}</span>` : ""}
      ${!track.positioned.length ? `<span class="project-preview-empty-track">—</span>` : ""}
    </div></div>`).join("");
  const paths = card.paths.map(path => path.parts.length ? `<div class="project-preview-path">
    <div class="project-preview-row"><span class="project-preview-track-label project-preview-final-label" title="${html(path.name)}">Final Path${path.name !== card.chrName ? `<small>${html(path.name)}</small>` : ""}</span>
      <span class="project-preview-plot project-preview-final-plot" data-final-path-strip="1" data-final-path-name="${html(path.name)}" data-final-path-domain="${domain.end}" style="height:20px">${path.parts.map(part => `<span class="project-preview-final-part${part.gap ? " is-gap" : ""}" data-final-path-segment="1" data-final-path-kind="${part.gap ? "gap" : "ctg"}" data-final-path-length="${part.length}" style="left:${percent(part.start / domain.end * 100)}%;width:${percent(part.length / domain.end * 100)}%;background:${part.gap ? "var(--gap-marker-fill, #ffffff)" : contigColorToken(part.role)};border-color:${part.gap ? "var(--border-strong)" : contigColorToken(part.role, "stroke")};color:${part.gap ? "var(--gap-marker-text, #1b1b1b)" : contigColorToken(part.role, "text")}" title="${html(`${partTitle(part, labels)} · ${number(part.length)} bp`)}"><span data-final-path-fit-label>${html(part.gap ? "" : resolveFinalPathSegmentDisplayName(part.segment))}${!part.gap && (part.source?.orient === "-" || part.segment.orient === "-") ? " (−)" : ""}</span></span>`).join("")}</span>
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
    : !preview.loaded || (preview.localSignature !== undefined && !previewStateIsApplicable(state)) ? `<p class="muted" role="status">${html(labels.loading)}</p>`
    : preview.cards?.length ? `<div class="project-preview-cards">${preview.cards.map(card => renderCard(card, labels)).join("")}</div>`
    : `<p class="muted">${html(labels.empty)}</p>`;
  return `<section class="project-preview-page" data-preview-project="${html(key)}" data-preview-locale="${html(state.locale)}" aria-busy="${Boolean(preview.loading)}"><header class="project-preview-heading"><h2>${html(labels.title)}</h2><span class="project-preview-subtitle" title="${html(labels.subtitle)}">${html(labels.subtitle)}</span>
    <details class="project-preview-legend"><summary aria-label="${html(labels.legend)}" title="${html(labels.legend)}">i</summary><div class="project-preview-hint">${html(labels.hint)}</div></details>
    <button type="button" class="button project-preview-refresh" data-preview-refresh title="${html(labels.refresh)}" aria-label="${html(labels.refresh)}" ${!key || preview.loading ? "disabled" : ""}>${projectIcon("refresh")}</button></header>
    ${content}</section>`;
}

function updatePreviewDom(host, state) {
  const preview = state.projectPreview, page = host.querySelector?.(".project-preview-page");
  const container = page?.querySelector?.(".project-preview-cards");
  if (container && preview?.loaded && preview.cards.length && page.dataset.previewProject === preview.key
    && page.dataset.previewLocale === state.locale && !preview.error && previewStateIsApplicable(state)) {
    const existing = new Map([...container.querySelectorAll("[data-preview-chr]")].map(node => [node.dataset.previewChr, node]));
    const nodes = preview.cards.map(card => {
      let node = existing.get(card.chrName);
      if (nodeModels.get(node) !== card) {
        const wrapper = host.ownerDocument.createElement("div");
        wrapper.innerHTML = renderCard(card, getMessages(state, "projectPreview"));
        node = wrapper.firstElementChild;
        nodeModels.set(node, card);
      }
      return node;
    });
    const wanted = new Set(nodes);
    for (const node of [...container.children]) if (!wanted.has(node)) node.remove();
    nodes.forEach((node, index) => {
      const current = container.children[index];
      if (current !== node) container.insertBefore(node, current || null);
    });
  } else {
    host.innerHTML = renderProjectPreviewPage(state);
    for (const node of host.querySelectorAll?.("[data-preview-chr]") || []) {
      const card = preview?.cards?.find(card => card.chrName === node.dataset.previewChr);
      if (card) nodeModels.set(node, card);
    }
  }
  const currentPage = host.querySelector?.(".project-preview-page");
  currentPage?.setAttribute?.("aria-busy", String(Boolean(preview?.loading)));
  const refresh = host.querySelector?.("[data-preview-refresh]");
  if (refresh) refresh.disabled = Boolean(preview?.loading);
  syncFinalPathStripGeometry(host);
  markPreviewDom(host, state);
}

function buildCards(inputs, paths, previous, affected, build) {
  const selected = affected ? inputs.chromosomes.filter(chr => affected.has(chr.chrName)) : inputs.chromosomes;
  const replacements = new Map(build({ ...inputs, chromosomes: selected, finalPathByChr: paths }).map(card => [card.chrName, card]));
  const old = new Map((previous || []).map(card => [card.chrName, card]));
  return inputs.chromosomes.slice().sort((a, b) => Number(a.chrOrder || 0) - Number(b.chrOrder || 0)
    || a.chrName.localeCompare(b.chrName, undefined, { numeric: true }))
    .map(chr => replacements.get(chr.chrName) || old.get(chr.chrName)).filter(Boolean);
}

async function readPreviewSources(state, args, metadata, deps) {
  const [chromosomes, ctgResult, view, rawGrt] = await Promise.all([
    (deps.listProjectChromosomes || listProjectChromosomes)(args),
    (deps.listChrViewCtgs || listChrViewCtgs)({ ...args, chrName: null, previewOnly: true }),
    (deps.getProjectAssemblyViewState || getProjectAssemblyViewState)(args),
    (deps.getGrtProjectView || getGrtProjectView)(args),
  ]);
  const project = metadata?.sourceMetadata?.project
    || state.initializer?.existingProjects?.find(item => Number(item.projectId) === Number(args.projectId)) || {};
  const phasedChrTracksByChr = {};
  if (project.phasedAssemblyEnabled) {
    const pending = (chromosomes.items || []).slice();
    // Bounded concurrency rather than a serial roundtrip for every chromosome.
    await Promise.all(Array.from({ length: Math.min(3, pending.length) }, async () => {
      while (pending.length) {
        const chr = pending.shift();
        const result = await (deps.listPhasedChrTracks || listPhasedChrTracks)({ ...args, parentChrName: chr.chrName });
        phasedChrTracksByChr[chr.chrName] = (result.tracks || []).map(track => ({ label: track.label }));
      }
    }));
  }
  const baseline = normalizeGrtProjectView(rawGrt).baselineFinalPathByChr;
  const savedPaths = canonicalizeFinalPathOverallLengths({ ...baseline, ...normalizeFinalPathByChr(view?.finalPathByChr) }, baseline);
  return compactPreviewInputs({ chromosomes: chromosomes.items || [], referenceGenomeId: chromosomes.referenceGenomeId,
    ctgs: ctgResult.items || [], datasets: metadata?.sourceMetadata?.datasets || state.initializer?.datasets || [],
    project, phasedChrTracksByChr, baseline, savedPaths });
}

export function loadProjectPreviewData(host, store, deps = {}, options = {}) {
  const initial = store.getState(), key = previewProjectKey(initial);
  if (!key) return Promise.resolve(false);
  const session = previewSession(store);
  const pending = session.pending.get(key);
  if (!options.force && pending?.host === host && pending.mutationStamp === previewMutationStamp({
    workspaceRoot: initial.session.workspacePath, projectId: initial.session.projectId,
  }) && pending.localSignature === previewSemanticSignature(previewLocalSignatures(initial))) return pending.promise;
  const token = {}; requests.set(store, token);
  const isCurrent = () => requests.get(store) === token && previewProjectKey(store.getState()) === key
    && (options.background || store.getState().activeRoute === "projectPreview")
    && (options.shouldContinue?.() ?? true);
  const args = { workspaceRoot: initial.session.workspacePath, projectId: initial.session.projectId };
  const getCache = deps.getProjectPreviewCache || getProjectPreviewCache;
  const putCache = deps.putProjectPreviewCache || putProjectPreviewCache;
  const build = deps.buildProjectPreviewModel || buildProjectPreviewModel;
  const readMetadata = async entry => {
    try {
      const metadata = await getCache({ ...args, modelVersion: PREVIEW_MODEL_VERSION,
        expectedIdentity: entry?.identity || null, sinceRevision: entry?.revision ?? null });
      return metadata?.trackingVersion >= 3 ? metadata : { available: false };
    }
    catch { return { available: false }; }
  };
  const apply = entry => {
    if (!isCurrent()) return false;
    rememberPreviewEntry(store, key, entry);
    store.setState({ projectPreview: { key, loading: false, loaded: true, error: "",
      modelVersion: PREVIEW_MODEL_VERSION, identity: entry.identity, revision: entry.revision,
      chromosomes: entry.payload.chromosomes, cards: entry.cards,
      savedPathSignatures: entry.payload.savedPathSignatures,
      localSignature: entry.localSignature, mutationStamp: entry.mutationStamp, cacheSource: entry.cacheSource } });
    // No paint/await between restoring the old foundation and replacing the
    // changed cards; unaffected node identities (and keyboard focus) survive.
    if (!isCurrent()) return false;
    if (host) {
      restoreProjectPreviewDom(host, store.getState(), { allowModelMismatch: true });
      updatePreviewDom(host, store.getState());
    }
    return true;
  };
  const run = async () => {
    try {
      for (let attempt = 0; attempt < 3; attempt++) {
        const cached = session.entries.get(key);
        const previous = cached?.payload?.modelVersion === PREVIEW_MODEL_VERSION ? cached : null;
        const stamp = previewMutationStamp(args);
        const metadata = await readMetadata(previous);
        if (!isCurrent()) return false;
        if (stamp !== previewMutationStamp(args)) continue;
        const sameIdentity = metadata.available && previous?.identity === metadata.identity;
        const sameRevision = sameIdentity && metadata.memoryValid && previous.revision === metadata.revision;
        const local = previewLocalSignatures(store.getState());
        const localSignature = previewOverrideSignature(local, previous?.payload?.savedPathSignatures || metadata.snapshot?.savedPathSignatures);
        if (!options.force && sameRevision && previous.localSignature === localSignature) {
          return apply({ ...previous, mutationStamp: stamp, cacheSource: "memory" });
        }
        const supplied = isPreviewSnapshot(metadata.snapshot) ? metadata.snapshot : null;
        let payload = sameRevision ? previous.payload : supplied;
        let savedCards = sameRevision ? previous.savedCards : supplied?.cards;
        if (!sameRevision && sameIdentity && metadata.valid && supplied) {
          const oldCompact = new Map(previous.payload.cards.map(card => [card.chrName, card]));
          const oldModels = new Map(previous.savedCards.map(card => [card.chrName, card]));
          savedCards = supplied.cards.map(card => previewSemanticSignature(oldCompact.get(card.chrName)) === previewSemanticSignature(card)
            ? oldModels.get(card.chrName) || card : card);
        }
        let inputs = sameRevision ? previous.inputs : null;
        const savedIsCurrent = !options.force && (sameRevision || (metadata.valid && supplied));
        const overlayNames = payload ? Object.keys(local).filter(name => local[name] !== payload.savedPathSignatures[name]) : [];
        if (savedIsCurrent && !overlayNames.length) {
          return apply({ identity: metadata.identity, revision: metadata.revision, payload, savedCards,
            inputs, sourceMetadata: metadata.sourceMetadata || previous?.sourceMetadata,
            cards: savedCards, localSignature: previewOverrideSignature(local, payload.savedPathSignatures), mutationStamp: stamp,
            incrementalSafe: sameRevision ? previous.incrementalSafe : true, cacheSource: sameRevision ? "memory" : "project" });
        }
        let stored = sameRevision ? previous.incrementalSafe : Boolean(savedIsCurrent);
        if (!savedIsCurrent || !inputs) {
          const visible = store.getState().projectPreview;
          store.setState({ projectPreview: { ...(visible?.key === key ? visible : { loaded: false }), key, loading: true, error: "" } });
          const refresh = host?.querySelector?.("[data-preview-refresh]");
          if (refresh) refresh.disabled = true;
          host?.querySelector?.(".project-preview-page")?.setAttribute?.("aria-busy", "true");
          inputs = await readPreviewSources(store.getState(), args,
            { ...metadata, sourceMetadata: metadata.sourceMetadata || (sameRevision ? previous?.sourceMetadata : null) }, deps);
          if (!isCurrent()) return false;
          const after = metadata.available ? await readMetadata({ identity: metadata.identity, revision: metadata.revision }) : null;
          if (!isCurrent()) return false;
          if (stamp !== previewMutationStamp(args) || (after?.available
            && (!after.memoryValid || after.identity !== metadata.identity || after.revision !== metadata.revision))) continue;
          // An unavailable validity check does not authorize publishing a cache.
          const publishable = metadata.available && after?.available;
          const palette = previewPaletteKey(inputs, inputs.savedPaths);
          const baseCards = sameIdentity && previous ? previous.savedCards : supplied?.cards;
          let affected = !options.force && baseCards && (previous?.incrementalSafe || !previous)
            ? affectedPreviewChromosomes(metadata.dirtyChrNames, baseCards, payload?.pathParents) : null;
          if (!payload || palette !== payload.paletteKey) affected = null;
          if (savedIsCurrent && previewSemanticSignature(pathSignatures(inputs.savedPaths)) === previewSemanticSignature(payload.savedPathSignatures)) {
            // Sources were fetched solely to overlay a session-only edit.
            savedCards = savedCards || payload.cards;
          } else {
            savedCards = buildCards(inputs, inputs.savedPaths, baseCards, affected, build);
          }
          const retained = Object.fromEntries((payload?.dependencies || []).filter(dependency =>
            baseCards?.find(card => card.chrName === dependency.chrName) === savedCards.find(card => card.chrName === dependency.chrName))
            .map(dependency => [dependency.chrName, dependency.ctgIds]));
          payload = persistentPreviewPayload(inputs, inputs.savedPaths, savedCards, retained);
          stored = false;
          if (publishable) {
            try {
              const result = await putCache({ ...args, modelVersion: PREVIEW_MODEL_VERSION,
                expectedIdentity: metadata.identity, expectedRevision: metadata.revision, payload });
              if (result?.superseded) continue;
              stored = Boolean(result?.stored);
            } catch { /* Derived-cache write failure must not hide a valid fresh view. */ }
          }
          if (!isCurrent()) return false;
          if (stamp !== previewMutationStamp(args)) continue;
        }
        const latestLocal = previewLocalSignatures(store.getState());
        const overlay = Object.keys(latestLocal).filter(name => latestLocal[name] !== payload.savedPathSignatures[name]);
        let cards = savedCards;
        if (overlay.length) {
          const paths = canonicalizeFinalPathOverallLengths({ ...inputs.savedPaths,
            ...normalizeFinalPathByChr(store.getState().assembly?.finalPathByChr) }, inputs.baseline);
          const affected = previewPaletteKey(inputs, paths) === payload.paletteKey
            ? affectedPreviewChromosomes(overlay, savedCards, previewPathParents(inputs)) : null;
          cards = buildCards(inputs, paths, savedCards, affected, build);
        }
        return apply({ identity: metadata.available ? metadata.identity : null,
          revision: metadata.available ? metadata.revision : null, payload, savedCards, inputs, cards,
          sourceMetadata: metadata.sourceMetadata || (sameRevision ? previous?.sourceMetadata : null),
          localSignature: previewOverrideSignature(latestLocal, payload.savedPathSignatures), mutationStamp: stamp,
          // Unsaved adopted sources may add dependencies not present on disk.
          incrementalSafe: stored && !overlay.length, cacheSource: "rebuilt" });
      }
      throw new Error(initial.locale === "en" ? "Project content changed during Preview loading; retry." : "项目内容在预览加载期间发生变化，请重试。");
    } catch (error) {
      if (!isCurrent()) return false;
      store.setState({ projectPreview: { key, loading: false, loaded: false, error: String(error?.message || error) } });
      if (host) updatePreviewDom(host, store.getState());
      return false;
    }
  };
  const promise = run().finally(() => { if (session.pending.get(key)?.promise === promise) session.pending.delete(key); });
  session.pending.set(key, { promise, host, mutationStamp: previewMutationStamp(args),
    localSignature: previewSemanticSignature(previewLocalSignatures(initial)) });
  return promise;
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
      if (refresh && host.contains(refresh)) void loadProjectPreviewData(host, binding.store, binding.deps, { force: true });
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
  if (previewStateIsApplicable(store.getState())) {
    for (const node of host.querySelectorAll?.("[data-preview-chr]") || []) {
      const card = store.getState().projectPreview.cards.find(card => card.chrName === node.dataset.previewChr);
      if (card && !nodeModels.has(node)) nodeModels.set(node, card);
    }
    markPreviewDom(host, store.getState());
    syncFinalPathStripGeometry(host);
  }
  void loadProjectPreviewData(host, store, deps);
}
