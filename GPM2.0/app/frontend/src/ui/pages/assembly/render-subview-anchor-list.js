import { filterSubviewAnchorObjects } from "./subview-anchor-objects.js";

function formatEndpointSource(endpoint, labels) {
  const roleKey = endpoint?.sourceRole === "support" && endpoint?.sourceKind === "mirror"
    ? "sourceMirror"
    : `source${String(endpoint?.sourceRole || "").replace(/^./, (character) => character.toUpperCase())}`;
  const role = labels[roleKey] || "";
  if (role) {
    return endpoint.sourceName
      ? labels.sourceWithName.replace("{role}", role).replace("{name}", endpoint.sourceName)
      : role;
  }
  return endpoint?.sourceLabel || endpoint?.sourceName || labels.sourceUnavailable;
}

function formatEndpoint(endpoint, labels, escapeHtml, escapeAttr) {
  const name = endpoint?.name || `${labels.contig} ${endpoint?.contigId || "?"}`;
  const source = formatEndpointSource(endpoint, labels);
  const coordinate = endpoint?.cutBp ? Number(endpoint.cutBp).toLocaleString() : labels.coordinateUnavailable;
  const title = `${name} · ${source} · ${coordinate} bp`;
  return `<span class="subview-anchor-endpoint" title="${escapeAttr(title)}">
    <strong>${escapeHtml(name)}</strong><span>${escapeHtml(source)}</span><code>${escapeHtml(coordinate)} bp</code>
  </span>`;
}

export function renderSubviewAnchorList(objects, ui, labels, { escapeHtml, escapeAttr }) {
  const visible = filterSubviewAnchorObjects(objects, ui.query);
  const checked = new Set(ui.checkedObjectIds);
  const rows = visible.map((object) => {
    const type = object.kind === "manual"
      ? labels.manualType.replace("{direction}", labels[object.direction] || "")
        .replace("{offset}", object.offsetBp ? Number(object.offsetBp).toLocaleString() : "-")
      : labels[`${object.edge}Edge`];
    const reason = object.reason ? labels[object.reason] : "";
    return `<div class="subview-anchor-object${ui.focusedObjectId === object.objectId ? " is-focused" : ""}">
      <input type="checkbox" data-subview-anchor-check="${escapeAttr(object.objectId)}"
        aria-label="${escapeAttr(labels.selectObject)}" ${checked.has(object.objectId) ? "checked" : ""}>
      <button type="button" class="subview-anchor-object-main"
        data-subview-anchor-list-row="${escapeAttr(object.objectId)}"
        aria-pressed="${ui.focusedObjectId === object.objectId}">
        <span class="subview-anchor-object-type">${escapeHtml(type)}</span>
        <span class="subview-anchor-endpoints">
          ${object.endpoints.map((endpoint) => formatEndpoint(endpoint, labels, escapeHtml, escapeAttr)).join("")
            || `<span class="muted">${escapeHtml(labels.endpointDetailsUnavailable)}</span>`}
        </span>
        ${reason ? `<span class="subview-anchor-object-reason">${escapeHtml(reason)}</span>` : ""}
      </button>
      <button type="button" class="button ghost tiny subview-anchor-delete"
        data-subview-anchor-delete="${escapeAttr(object.objectId)}"
        aria-label="${escapeAttr(labels.deleteObject)}" title="${escapeAttr(labels.deleteObject)}">×</button>
    </div>`;
  }).join("");
  return `<section class="subview-anchor-manager" data-subview-anchor-manager="1">
    <div class="subview-anchor-manager-actions">
      <label class="subview-anchor-search"><span>${escapeHtml(labels.search)}</span>
        <input type="search" data-subview-anchor-search="1" value="${escapeAttr(ui.query)}"
          placeholder="${escapeAttr(labels.searchPlaceholder)}"></label>
      <button type="button" class="button ghost tiny" data-subview-anchor-delete-checked="1"
        ${checked.size ? "" : "disabled"}>${escapeHtml(labels.deleteSelected.replace("{count}", checked.size))}</button>
    </div>
    <div class="subview-anchor-object-list">
      ${rows || `<p class="muted subview-tools-empty">${escapeHtml(objects.length ? labels.noMatches : labels.empty)}</p>`}
    </div>
  </section>`;
}
