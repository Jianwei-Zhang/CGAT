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
  const coordinateValue = endpoint?.cutBp || endpoint?.sourcePosition;
  const coordinate = coordinateValue ? Number(coordinateValue).toLocaleString() : labels.coordinateUnavailable;
  const title = `${name} · ${source} · ${coordinate} bp`;
  return `<span class="subview-anchor-endpoint" title="${escapeAttr(title)}">
    <strong>${escapeHtml(name)}</strong><span>${escapeHtml(source)}</span><code>${escapeHtml(coordinate)} bp</code>
  </span>`;
}

export function renderSubviewAnchorList(objects, ui, labels, { escapeHtml, escapeAttr }) {
  const visible = filterSubviewAnchorObjects(objects, ui.query);
  const checked = new Set(ui.checkedObjectIds);
  const userObjects = visible.filter((object) => object.kind !== "grt");
  const grtObjects = visible.filter((object) => object.kind === "grt");
  const row = (object) => {
    const type = object.kind === "manual" && object.fromGrt
      ? labels.grtCopyType
      : object.kind === "manual"
        ? labels.manualType.replace("{direction}", labels[object.direction] || "")
          .replace("{offset}", object.offsetBp ? Number(object.offsetBp).toLocaleString() : "-")
        : object.kind === "grt"
          ? (object.connectionKind === "gap"
              ? labels.grtGapType.replace("{size}", Number(object.gapSizeBp || 0).toLocaleString())
              : labels.grtLinkType)
          : labels[`${object.edge}Edge`];
    const reason = object.reason ? labels[object.reason] : "";
    const select = object.canDelete
      ? `<input type="checkbox" data-subview-anchor-check="${escapeAttr(object.objectId)}"
          aria-label="${escapeAttr(labels.selectObject)}" ${checked.has(object.objectId) ? "checked" : ""}>`
      : `<span class="subview-anchor-readonly" title="${escapeAttr(labels.grtReadOnly)}" aria-label="${escapeAttr(labels.grtReadOnly)}">&#128274;</span>`;
    const action = object.kind === "grt"
      ? `<button type="button" class="button ghost tiny subview-anchor-copy-grt"
          data-subview-anchor-copy-grt="${escapeAttr(object.originId)}"
          aria-label="${escapeAttr(labels.copyGrt)}" title="${escapeAttr(reason || labels.copyGrt)}"
          ${object.canCopy ? "" : "disabled"}>${escapeHtml(labels.copy)}</button>`
      : `<button type="button" class="button ghost tiny subview-anchor-delete"
          data-subview-anchor-delete="${escapeAttr(object.objectId)}"
          aria-label="${escapeAttr(labels.deleteObject)}" title="${escapeAttr(labels.deleteObject)}">×</button>`;
    return `<div class="subview-anchor-object${object.kind === "grt" ? " is-readonly" : ""}${ui.focusedObjectId === object.objectId ? " is-focused" : ""}">
      ${select}
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
      ${action}
    </div>`;
  };
  const group = (title, entries, empty) => `<section class="subview-anchor-object-group">
    <h4>${escapeHtml(title)} <span>${entries.length}</span></h4>
    ${entries.map(row).join("") || `<p class="muted subview-tools-empty">${escapeHtml(empty)}</p>`}
  </section>`;
  const checkedCount = objects.filter(
    (object) => object.canDelete && checked.has(object.objectId),
  ).length;
  const groups = visible.length
    ? `${group(labels.userGroup, userObjects, labels.userEmpty)}${group(labels.grtGroup, grtObjects, labels.grtEmpty)}`
    : `<p class="muted subview-tools-empty">${escapeHtml(objects.length ? labels.noMatches : labels.empty)}</p>`;
  return `<section class="subview-anchor-manager" data-subview-anchor-manager="1">
    <div class="subview-anchor-manager-actions">
      <label class="subview-anchor-search"><span>${escapeHtml(labels.search)}</span>
        <input type="search" data-subview-anchor-search="1" value="${escapeAttr(ui.query)}"
          placeholder="${escapeAttr(labels.searchPlaceholder)}"></label>
      <button type="button" class="button ghost tiny" data-subview-anchor-delete-checked="1"
        ${checkedCount ? "" : "disabled"}>${escapeHtml(labels.deleteSelected.replace("{count}", checkedCount))}</button>
    </div>
    <div class="subview-anchor-object-list">
      ${groups}
    </div>
  </section>`;
}
