const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

// Only remove decoration supplied by the compact-label templates. Names are
// escaped as text, and the role gets its own non-shrinking flex item.
export function renderTrackIdentity(label, role) {
  const marker = { primary: "P", support: "A", ref: "R" }[role];
  let name = String(label ?? "");
  if (marker && role !== "ref") {
    const suffix = ` [${marker}]`;
    if (name.endsWith(suffix)) name = name.slice(0, -suffix.length);
    else if (name === `[${marker}]`) name = "";
  }
  return `<span class="assembly-track-label-name">${escape(name)}</span>`
    + (marker ? `<span class="assembly-track-role-marker" aria-hidden="true">[${marker}]</span>` : "");
}
