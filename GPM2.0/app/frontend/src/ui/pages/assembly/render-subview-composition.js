import {
  filterSubviewCompositionCandidates,
  resolveSubviewCompositionCandidate,
} from "./subview-composition-candidates.js";
import { normalizeSubviewComposition } from "./subview-composition-state.js";
import {
  formatTrackCtgOrientationLabel,
  resolveTrackCtgEffectiveOrientation,
} from "./track-label-geometry.js";

function sourceLabel(source, labels) {
  const role = labels.sources?.[source?.role] || source?.role || labels.unknownSource;
  const detail = source?.datasetName || source?.hap || "";
  return detail ? `${role} · ${detail}` : role;
}

function displayLabel(member) {
  return formatTrackCtgOrientationLabel(
    member?.label,
    resolveTrackCtgEffectiveOrientation(member?.baseOrientation, member?.flipped),
  );
}

function renderMember(member, focusedEntityKey, isUnavailable, labels, escapeHtml, escapeAttr) {
  const opposite = member.lane === "top" ? "bottom" : "top";
  const focused = member.entityKey === focusedEntityKey;
  const label = displayLabel(member);
  return `<li class="subview-composition-member${focused ? " is-composition-focused" : ""}" draggable="true"
      data-subview-composition-member="${escapeAttr(member.entityKey)}"
      data-subview-composition-lane="${member.lane}" tabindex="0" aria-pressed="${focused ? "true" : "false"}">
    <button type="button" class="subview-composition-member-main"
      data-subview-composition-focus="${escapeAttr(member.entityKey)}" title="${escapeAttr(label)}">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(sourceLabel(member.source, labels))}</span>
      ${isUnavailable ? `<span class="inline-error">${escapeHtml(labels.sourceUnavailable)}</span>` : ""}
      <code>${Math.round(member.xBp).toLocaleString()} bp${member.flipped ? ` · ${escapeHtml(labels.flipped)}` : ""}</code>
    </button>
    <button type="button" class="button ghost tiny" data-subview-composition-move="${escapeAttr(member.entityKey)}"
      data-subview-composition-target-lane="${opposite}" title="${escapeAttr(labels.moveTo[opposite])}">⇅</button>
    <button type="button" class="button ghost tiny danger" data-subview-composition-remove="${escapeAttr(member.entityKey)}"
      title="${escapeAttr(labels.remove)}">×</button>
  </li>`;
}

function renderLane(
  composition,
  lane,
  focusedEntityKey,
  candidates,
  candidatesLoaded,
  labels,
  escapeHtml,
  escapeAttr,
) {
  const members = composition.members.filter((member) => member.lane === lane)
    .sort((left, right) => left.order - right.order || left.entityKey.localeCompare(right.entityKey));
  return `<section class="subview-composition-lane" data-subview-composition-drop-lane="${lane}">
    <header><strong>${escapeHtml(labels.lanes[lane])} (${members.length})</strong>
      <button type="button" class="button secondary tiny" data-subview-composition-add="${lane}">＋${escapeHtml(labels.add)}</button></header>
    ${members.length
      ? `<ul>${members.map((member) => renderMember(
        member,
        focusedEntityKey,
        candidatesLoaded && !resolveSubviewCompositionCandidate(candidates, member),
        labels,
        escapeHtml,
        escapeAttr,
      )).join("")}</ul>`
      : `<p class="muted">${escapeHtml(labels.emptyLane)}</p>`}
  </section>`;
}

function renderPicker(candidates, composition, ui, labels, escapeHtml, escapeAttr) {
  const filtered = filterSubviewCompositionCandidates(candidates, {
    query: ui.query,
    source: ui.source,
  });
  const membersByKey = new Map(composition.members.map((member) => [member.entityKey, member]));
  return `<section class="subview-composition-picker" data-subview-composition-picker="1">
    <header><button type="button" class="button ghost tiny" data-subview-composition-back="1">← ${escapeHtml(labels.back)}</button>
      <strong>${escapeHtml(labels.addTo[ui.targetLane])}</strong></header>
    <div class="subview-composition-picker-filters">
      <input type="search" data-subview-composition-search="1" value="${escapeAttr(ui.query)}"
        placeholder="${escapeAttr(labels.searchPlaceholder)}" aria-label="${escapeAttr(labels.search)}">
      <select data-subview-composition-source="1" aria-label="${escapeAttr(labels.sourceFilter)}">
        ${["all", "primary", "support", "phased", "ref"].map((source) => `<option value="${source}"
          ${ui.source === source ? "selected" : ""}>${escapeHtml(source === "all" ? labels.allSources : labels.sources[source])}</option>`).join("")}
      </select>
    </div>
    ${ui.loading ? `<p class="muted">${escapeHtml(labels.loading)}</p>` : ""}
    ${ui.error ? `<p class="inline-error">${escapeHtml(ui.error)}
      <button type="button" class="button ghost tiny" data-subview-composition-retry="1">${escapeHtml(labels.retry)}</button></p>` : ""}
    <ul class="subview-composition-candidate-list">
      ${filtered.map((candidate) => {
        const existing = membersByKey.get(candidate.entityKey);
        const displayedCandidate = existing || candidate;
        const moveNote = existing && existing.lane !== ui.targetLane
          ? labels.willMove[existing.lane]
          : existing ? labels.alreadyAdded : "";
        const checked = ui.checkedKeys.includes(candidate.candidateKey);
        const label = displayLabel(displayedCandidate);
        return `<li><label>
          <input type="checkbox" data-subview-composition-candidate="${escapeAttr(candidate.candidateKey)}"
            ${checked ? "checked" : ""}>
          <span><strong title="${escapeAttr(label)}">${escapeHtml(label)}</strong>
            <small>${escapeHtml(sourceLabel(candidate.source, labels))}${moveNote ? ` · ${escapeHtml(moveNote)}` : ""}</small></span>
        </label></li>`;
      }).join("") || (ui.loading ? "" : `<li class="muted">${escapeHtml(labels.noMatches)}</li>`)}
    </ul>
    <button type="button" class="button primary" data-subview-composition-confirm-add="1"
      ${ui.checkedKeys.length ? "" : "disabled"}>${escapeHtml(labels.addSelected.replace("{count}", ui.checkedKeys.length))}</button>
  </section>`;
}

export function renderSubviewCompositionPanel({
  composition,
  candidates,
  candidatesLoaded = false,
  ui,
  labels,
}, {
  escapeHtml,
  escapeAttr,
}) {
  const normalized = normalizeSubviewComposition(composition);
  if (ui.view === "picker") {
    return renderPicker(candidates, normalized, ui, labels, escapeHtml, escapeAttr);
  }
  return `<section class="subview-composition-manager" data-subview-composition-manager="1">
    ${renderLane(normalized, "top", ui.focusedEntityKey, candidates, candidatesLoaded,
      labels, escapeHtml, escapeAttr)}
    ${renderLane(normalized, "bottom", ui.focusedEntityKey, candidates, candidatesLoaded,
      labels, escapeHtml, escapeAttr)}
    <button type="button" class="button secondary" data-subview-composition-compact="1">${escapeHtml(labels.compact)}</button>
  </section>`;
}
