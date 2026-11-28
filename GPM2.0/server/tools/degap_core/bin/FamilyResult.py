"""Sequence/AGP/provenance publication for a completed family search."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from ExtensionFamilies import atomic_json, fingerprint, read_json
from FamilyOverlap import joined_sequence, read_sequence
from FamilyTools import content_hash
from ReportStyle import (
    badge_bi,
    badge_html,
    bi,
    esc,
    lang_switcher_html,
    lang_switcher_js,
    report_css,
    status_tone,
    summary_strip_html,
)

SCHEMA = "degap-family-result-v1"


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_result(directory):
    """Load only a complete, content-verified publication, never log heuristics."""
    directory = Path(directory)
    result = read_json(directory / "family-result.json")
    payload = {k: v for k, v in result.items() if k != "payload_sha256"}
    if result.get("schema") != SCHEMA or result.get("payload_sha256") != fingerprint(payload):
        raise ValueError("Invalid extension-family result manifest")
    if (result.get("status") == "closed") != (result.get("winner") is not None):
        raise ValueError("Family result closure state is inconsistent")
    for relative, digest in result["artifacts"].items():
        path = directory / relative
        if path.resolve().parent != directory.resolve() or not path.is_file() or content_hash(path) != digest:
            raise ValueError(f"Family result artifact changed: {path}")
    for required in (result["final_sequence"], "family-components.fa", "process.agp", "process.log", "process.summary", "family-report.html"):
        if required not in result["artifacts"]:
            raise ValueError(f"Family result is missing required artifact: {required}")
    return result


def publish_search(search, name=None, *, unclosed_families=None):
    """Export one joined sequence, or separate unclosed family sequences.

    AGP components are actual exported cumulative sequences, not invented reads
    or falsely attributed original contigs. Family/source provenance accompanies
    them in the manifest. Standard AGP coordinates are one-based inclusive.
    """
    if search.status == "running" or search.pending:
        raise ValueError("Cannot publish an incomplete family search")
    directory = search.directory
    exported = list(search.families) if unclosed_families is None else list(unclosed_families)
    if not exported or len(exported) != len(set(exported)) or any(key not in search.families for key in exported):
        raise ValueError("Invalid unclosed-family export selection")
    name = name or directory.name
    if not name or Path(name).name != name or any(c.isspace() for c in name):
        raise ValueError("Result name must be a single whitespace-free filename component")
    result_file = directory / "family-result.json"
    if result_file.exists():
        result = load_result(directory)
        if (result["search_contract"] != search.contract_id or result["status"] != search.status or
                result.get("unclosed_exports", list(search.families)) != exported):
            raise ValueError("Published result belongs to a different search")
        return result

    final_file = name + ".final.fa"
    result = {
        "schema": SCHEMA, "search_contract": search.contract_id,
        "status": search.status, "total_rounds": search.total_rounds,
        "total_extension_length": search.total_length,
        "final_sequence": final_file, "winner": asdict(search.winner) if search.winner else None,
        "gap_length": None, "junction": None,
        "connection_diagnostics": list(getattr(search, "checked_diagnostics", {}).values()), "families": [], "components": {}, "artifacts": {},
        "unclosed_exports": exported,
    }
    for family in search.families.values():
        result["families"].append({
            "key": family.key, "direction": family.direction, "attempts": family.attempts,
            "added_bases": family.added_bases, "stop_reason": family.stop_reason,
            "versions": [asdict(v) for v in family.versions],
        })
    result["anchor_retries"] = []
    result["anchor_backoff_requests"] = []
    for family in search.families.values():
        for attempt in range(1, family.attempts+1):
            receipt = directory/"attempts"/str(search.order[family.key])/str(attempt)/"result.json"
            if receipt.exists() and read_json(receipt).get("retry_reason"):
                following = receipt.parent.parent/str(attempt+1)/"result.json"
                executed = following.is_file()
                result["anchor_backoff_requests"].append({"family": family.key, "after_attempt": attempt,
                                                         "executed": executed, "backoff_bases": 2000})
                if executed:
                    result["anchor_retries"].append({"family": family.key, "attempt": attempt+1,
                                                     "after_attempt": attempt, "backoff_bases": 2000,
                                                     "reason": "terminal_anchor_backoff"})
    components = []
    agp = []

    def component(version):
        version.verify()
        key = f"family{search.order[version.family]}.v{version.number}"
        if key not in result["components"]:
            components.append(f">{key}\n{read_sequence(version.path)}\n")
            result["components"][key] = asdict(version)
        return key

    if search.winner:
        winner = search.winner
        left_family, right_family = search.families[winner.left_family], search.families[winner.right_family]
        left, right = left_family.versions[winner.left_version], right_family.versions[winner.right_version]
        sequence = joined_sequence(winner, left, right)
        final_text = f">{name}\n{sequence}\n"
        if (winner.evidence or {}).get("plan_path"):
            from JunctionRepair import load_plan
            plan = load_plan(winner.evidence)
            result["junction"] = plan["summary"]
            result["gap_length"] = plan["summary"]["gap_length"]
            position = 0
            for number, piece in enumerate(plan["pieces"], 1):
                key = f"junction.part{number}"
                full = read_sequence(piece["path"])
                components.append(f">{key}\n{full}\n")
                result["components"][key] = piece
                length = piece["end"]-piece["start"]
                agp.append(f"{name}\t{position+1}\t{position+length}\t{number}\tW\t{key}\t{piece['start']+1}\t{piece['end']}\t+")
                position += length
            if position != len(sequence):
                raise ValueError("Junction composition does not reconstruct output length")
        else:
            result["gap_length"] = len(sequence) - left_family.versions[0].length - right_family.versions[0].length
            left_id, right_id = component(left), component(right)
            agp.append(f"{name}\t1\t{winner.left_end}\t1\tW\t{left_id}\t1\t{winner.left_end}\t+")
            if right.length > winner.right_end:
                agp.append(f"{name}\t{winner.left_end + 1}\t{len(sequence)}\t2\tW\t{right_id}\t{winner.right_end + 1}\t{right.length}\t+")
    else:
        records = []
        for key in exported:
            family = search.families[key]
            version = family.current
            key = component(version)
            record_id = f"{name}.family{search.order[family.key]}.{search.status}"
            records.append(f">{record_id}\n{read_sequence(version.path)}\n")
            agp.append(f"{record_id}\t1\t{version.length}\t1\tW\t{key}\t1\t{version.length}\t+")
        final_text = "".join(records)

    summary = ["family\tdirection\tattempts\tversions\tadded_bases\tstop_reason"]
    for family in search.families.values():
        summary.append("\t".join(map(str, (family.key, family.direction, family.attempts,
                                           len(family.versions), family.added_bases, family.stop_reason or ""))))
    log = ["DEGAP extension-family search", f"Status: {search.status}",
           f"Total attempted rounds: {search.total_rounds}", f"totalExtensionLength: {search.total_length}"]
    if search.winner:
        log += ["GAP can be closed!", f"GAP Length: {result['gap_length']}",
                f"Selected families: {search.winner.left_family}/{search.winner.left_version} + "
                f"{search.winner.right_family}/{search.winner.right_version}"]
    else:
        log += ["Not a closed gap: exported family sequences remain separate."]
    for request in result["anchor_backoff_requests"]:
        if not request["executed"]:
            log.append(f"Anchor backoff requested for {request['family']} after attempt {request['after_attempt']}, but not executed before search ended; no extra round charged")
    for retry in result["anchor_retries"]:
        log.append(f"Anchor retry {retry['family']} attempt {retry['attempt']}: moved inward by up to {retry['backoff_bases']} bp; counted in the shared round budget")
    for diagnostic in result["connection_diagnostics"]:
        pair = f"{diagnostic.get('left_family')}/{diagnostic.get('left_version')} + {diagnostic.get('right_family')}/{diagnostic.get('right_version')}"
        stages = ", ".join(f"{x.get('stage')}:{x.get('reason')}" for x in diagnostic.get("stages", []))
        log.append(f"Connection check: {pair} | {diagnostic.get('status')} | {stages}")
    if result["junction"]:
        junction = result["junction"]
        log += [f"Junction mode: {junction['mode']}", f"Gap-only length: {junction['gap_length']} bp",
                f"Flank length delta: {junction['flank_length_delta']:+d} bp",
                f"Original overlap trim: {junction['overlap_trim']} bp"]
        for side, details in junction["flanks"].items():
            log.append(f"Flank {side}: {details['status']} | proposed={details['proposed_variants']} accepted={details['accepted_variants']} protected={details['protected_variants']}")
        for repair in junction["repairs"]:
            context = (f" (unresolved_context={repair['unresolved_context_reads']})"
                       if "unresolved_context_reads" in repair else "")
            log.append(f"Flank edit {repair['side']} [{repair['start0']},{repair['end0']}): {repair['status']} | {repair['reason']} | alt={repair.get('alt_reads',0)} ref={repair.get('ref_reads',0)} other={repair.get('other_reads',0)}{context}")
    log.append(f"Final EXtendFile: {directory / final_file}")
    outputs = {
        final_file: final_text, "family-components.fa": "".join(components),
        "process.agp": "\n".join(agp) + "\n", "process.log": "\n".join(log) + "\n",
        "process.summary": "\n".join(summary) + "\n",
    }
    if result["junction"]:
        junction = result["junction"]
        left0 = search.families[search.winner.left_family].versions[0].length
        right0 = search.families[search.winner.right_family].versions[0].length
        first = left0-junction["left_replace_bases"]
        last = len(sequence)-(right0-junction["right_replace_bases"])
        outputs["junction-integration.fa"] = f">{name}.junction\n{sequence[first:last]}\n"
        outputs["junction-evidence.json"] = json.dumps(plan, indent=2, sort_keys=True)+"\n"
        result["integration_sequence"] = "junction-integration.fa"
    outputs["connection-diagnostics.json"] = json.dumps(result["connection_diagnostics"], indent=2, sort_keys=True)+"\n"
    result["evidence_artifacts"] = {"Connection diagnostics / 连接诊断": "connection-diagnostics.json"}
    if result["junction"]:
        result["evidence_artifacts"]["Junction composition / 连接组成与修订证据"] = "junction-evidence.json"
    outputs["family-report.html"] = render_report(search, result)
    for relative, text in outputs.items():
        atomic_text(directory / relative, text)
        result["artifacts"][relative] = content_hash(directory / relative)
    result["payload_sha256"] = fingerprint(result)
    atomic_json(result_file, result)
    return result


_VISUAL_CSS = """
.fold-body > .jr-root { border: 0; margin: 0; }
.fold-body > .jr-root > .section-header { display: none; }
.fold-body > .jr-root > .section-body { padding: 4px 0 0; }
.viz-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-bottom: 10px; }
.viz-controls { display: inline-flex; align-items: center; gap: 4px; }
.viz-btn { font: inherit; font-size: 0.78rem; font-weight: 500; border: 1px solid var(--border-strong); background: var(--surface); color: var(--ink); border-radius: 4px; cursor: pointer; padding: 3px 9px; line-height: 1.35; }
.viz-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.viz-btn:disabled { opacity: 0.42; cursor: default; }
.viz-btn.is-play { background: var(--accent); border-color: var(--accent); color: #ffffff; }
.viz-btn.is-play:hover:not(:disabled) { background: var(--accent-hover); border-color: var(--accent-hover); color: #ffffff; }
.viz-btn.is-play .lbl-pause { display: none; }
.viz-btn.is-play[aria-pressed="true"] .lbl-play { display: none; }
.viz-btn.is-play[aria-pressed="true"] .lbl-pause { display: inline; }
.viz-pills { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.viz-pill { font: inherit; font-size: 0.75rem; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border-strong); background: var(--surface); color: var(--ink-secondary); cursor: pointer; line-height: 1.4; }
.viz-pill:hover { border-color: var(--accent); color: var(--ink); }
.viz-pill[aria-current="step"] { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.viz-view-toggle { display: inline-flex; margin-left: auto; background: var(--surface-muted); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 2px; gap: 2px; }
.viz-view-btn { font: inherit; font-size: 0.75rem; font-weight: 600; border: 0; background: transparent; color: var(--ink-muted); padding: 2px 9px; border-radius: 3px; cursor: pointer; }
.viz-view-btn:hover { color: var(--ink); }
.viz-view-btn[aria-pressed="true"] { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08); }
.viz-canvas { background: var(--surface-subtle); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; overflow-x: auto; }
.viz-svg { width: 100%; display: block; height: auto; }
.viz-svg text { font-family: var(--font-sans); font-size: 12px; fill: var(--ink-secondary); }
.viz-svg .v-lbl { font-size: 13px; font-weight: 600; fill: var(--ink); transition: fill 0.2s ease; }
.viz-svg .v-lbl.is-active { fill: var(--accent); }
.viz-svg .v-delta { font-size: 11px; font-weight: 600; fill: #ffffff; }
.viz-svg .v-muted { font-size: 10.5px; fill: var(--ink-muted); }
.viz-svg [data-from] { transition: opacity 0.28s ease; }
.viz-svg [data-from].is-hidden { opacity: 0; visibility: hidden; pointer-events: none; }
.viz-svg [data-from].is-new > rect { stroke: #0f172a; stroke-width: 1.5; }
.viz-svg [data-from].is-new > path { stroke-width: 1.8; }
.viz-caption { margin-top: 8px; font-size: 0.83rem; color: var(--ink-secondary); }
.viz-caption [hidden], [data-view-pane][hidden] { display: none !important; }
.viz-track-key { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-bottom: 3px; font-size: 0.79rem; font-variant-numeric: tabular-nums; color: var(--ink-secondary); }
.viz-track-key span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: -1px; margin-right: 5px; background: #2f5d8a; }
.viz-track-key .tk-r::before { background: #82571f; }
.viz-track-key .tk-f::before { background: #cbd5e1; }
.viz-track-key .tk-o::before { background: #2b7a57; }
.viz-note { margin: 6px 0 0; font-size: 0.77rem; color: var(--ink-muted); }
.viz-sub { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.viz-sub h3 { margin: 0 0 6px; font-size: 0.84rem; font-weight: 600; color: var(--ink); }
.viz-meta-line { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 6px; font-size: 0.79rem; color: var(--ink-secondary); font-variant-numeric: tabular-nums; }
.viz-meta-line b { color: var(--ink); font-weight: 600; }
.detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: start; }
.detail-grid > .section { margin-bottom: 14px; min-width: 0; }
.viz-matrix-wrap { overflow-x: auto; }
.viz-matrix { display: grid; width: max-content; gap: 3px; font: 0.77rem var(--font-mono); text-align: center; }
.viz-matrix span { padding: 3px 7px; border-radius: 3px; }
.viz-matrix .mh { color: var(--ink-muted); font-weight: 600; }
.viz-matrix .mc-win { color: var(--ok-ink); background: var(--ok-bg); border: 1px solid var(--ok-border); font-weight: 700; }
.viz-matrix .mc-ok { color: var(--accent); background: var(--accent-soft); border: 1px solid var(--accent-border); }
.viz-matrix .mc-rej { color: var(--warn-ink); background: var(--warn-bg); border: 1px solid var(--warn-border); }
.viz-matrix .mc-none { color: var(--ink-muted); background: var(--surface-muted); }
.viz-matrix .mc-unk { color: var(--ink-muted); border: 1px dashed var(--border-strong); }
@media (max-width: 820px) {
    .detail-grid { grid-template-columns: minmax(0, 1fr); gap: 0; }
}
@media (max-width: 700px) {
    .viz-svg .v-delta { display: none; }
    .viz-view-toggle { margin-left: 0; }
}
@media print {
    .viz-bar { display: none !important; }
}
"""

_PLAYER_JS = (
    "(function(){"
    "document.querySelectorAll('[data-viz-player]').forEach(function(root){"
    "var pills=Array.prototype.slice.call(root.querySelectorAll('[data-step]'));"
    "var max=pills.length?pills.length-1:0,cur=max,timer=null;"
    "var prev=root.querySelector('[data-viz-prev]'),next=root.querySelector('[data-viz-next]'),play=root.querySelector('[data-viz-play]');"
    "var segs=Array.prototype.slice.call(root.querySelectorAll('[data-from]'));"
    "var caps=Array.prototype.slice.call(root.querySelectorAll('[data-cap]'));"
    "var lbls=Array.prototype.slice.call(root.querySelectorAll('[data-side-lbl]'));"
    "var vbtns=Array.prototype.slice.call(root.querySelectorAll('[data-viz-view]'));"
    "var vpanes=Array.prototype.slice.call(root.querySelectorAll('[data-view-pane]'));"
    "function stop(){if(timer){clearInterval(timer);timer=null;}if(play)play.setAttribute('aria-pressed','false');}"
    "function setView(v){"
    "vpanes.forEach(function(p){p.hidden=p.getAttribute('data-view-pane')!==v;});"
    "vbtns.forEach(function(b){b.setAttribute('aria-pressed',b.getAttribute('data-viz-view')===v?'true':'false');});"
    "}"
    "function show(n){"
    "cur=Math.max(0,Math.min(max,n));"
    "segs.forEach(function(el){"
    "var from=Number(el.getAttribute('data-from'));"
    "var hide=from>cur;"
    "el.classList.toggle('is-hidden',hide);"
    "el.classList.toggle('is-new',!hide&&from===cur&&cur>0);"
    "if(hide){el.setAttribute('aria-hidden','true');}else{el.removeAttribute('aria-hidden');}"
    "});"
    "var activeSide='';"
    "caps.forEach(function(el){"
    "var on=Number(el.getAttribute('data-cap'))===cur;"
    "el.hidden=!on;"
    "if(on)activeSide=el.getAttribute('data-side')||'';"
    "});"
    "lbls.forEach(function(el){el.classList.toggle('is-active',Boolean(activeSide)&&el.getAttribute('data-side-lbl')===activeSide);});"
    "pills.forEach(function(p){p.setAttribute('aria-current',Number(p.getAttribute('data-step'))===cur?'step':'false');});"
    "if(prev)prev.disabled=cur<=0;"
    "if(next)next.disabled=cur>=max;"
    "}"
    "root.addEventListener('click',function(e){"
    "var t=e.target&&e.target.closest?e.target.closest('[data-step],[data-viz-prev],[data-viz-next],[data-viz-play],[data-viz-view]'):null;"
    "if(!t)return;"
    "if(t.hasAttribute('data-viz-view')){stop();setView(t.getAttribute('data-viz-view'));return;}"
    "if(vpanes.length)setView('zoom');"
    "if(t.hasAttribute('data-step')){stop();show(Number(t.getAttribute('data-step')));return;}"
    "if(t.hasAttribute('data-viz-prev')){stop();show(cur-1);return;}"
    "if(t.hasAttribute('data-viz-next')){stop();show(cur+1);return;}"
    "if(t.hasAttribute('data-viz-play')){"
    "if(timer){stop();return;}"
    "if(cur>=max)show(0);"
    "play.setAttribute('aria-pressed','true');"
    "timer=setInterval(function(){if(cur>=max){stop();return;}show(cur+1);},900);"
    "}"
    "});"
    "if(pills.length)show(max);"
    "});"
    "})();"
)


def _select_visual_pair(search, result):
    fams = search.families
    if "L" in fams and "R" in fams:
        return fams["L"], fams["R"]
    winner = result.get("winner")
    if isinstance(winner, dict):
        lf = fams.get(winner.get("left_family"))
        rf = fams.get(winner.get("right_family"))
        if lf is not None and rf is not None and lf.key != rf.key:
            return lf, rf
    rights = [f for f in fams.values() if f.direction == "rightward"]
    lefts = [f for f in fams.values() if f.direction == "leftward"]
    if len(rights) == 1 and len(lefts) == 1:
        return rights[0], lefts[0]
    return None, None


def _build_round_steps(l_fam, r_fam, result):
    """Reconstruct round-robin timeline steps from family versions, attempts and diagnostics."""
    winner = result.get("winner") if isinstance(result.get("winner"), dict) else None
    is_closed = winner is not None
    w_lv = winner.get("left_version") if is_closed else None
    w_rv = winner.get("right_version") if is_closed else None

    diag_map = {}
    for item in (result.get("connection_diagnostics") or []):
        if not isinstance(item, dict):
            continue
        if item.get("left_family") == l_fam.key and item.get("right_family") == r_fam.key:
            lv, rv = item.get("left_version"), item.get("right_version")
            if isinstance(lv, int) and isinstance(rv, int):
                diag_map[(lv, rv)] = item

    backoff_attempts = {l_fam.key: set(), r_fam.key: set()}
    for item in (result.get("anchor_retries") or []):
        if isinstance(item, dict) and item.get("family") in backoff_attempts and isinstance(item.get("attempt"), int):
            backoff_attempts[item["family"]].add(item["attempt"])

    def _pair_note(lv, rv, side=None):
        if side is None:
            pairs = [(0, 0)]
        elif side == "L":
            pairs = [(lv, j) for j in range(rv + 1)]
        else:
            pairs = [(i, rv) for i in range(lv + 1)]
        bits = []
        for i, j in pairs:
            if is_closed and i == w_lv and j == w_rv:
                bits.append(f"{l_fam.key}/v{i} × {r_fam.key}/v{j}: Winner ★")
                continue
            d = diag_map.get((i, j))
            if d:
                bits.append(f'{l_fam.key}/v{i} × {r_fam.key}/v{j}: {d.get("reason") or d.get("status") or "checked"}')
        return "; ".join(bits)

    steps = [{
        "step": 0,
        "side": None,
        "lv": 0,
        "rv": 0,
        "delta": 0,
        "pill_en": "v0" + (" · Closed" if is_closed and w_lv == 0 and w_rv == 0 else ""),
        "pill_zh": "初始 v0" + (" · 闭合" if is_closed and w_lv == 0 and w_rv == 0 else ""),
        "title_en": f"Initial · {l_fam.key}/v0 × {r_fam.key}/v0" + (" · Closed" if is_closed and w_lv == 0 and w_rv == 0 else ""),
        "title_zh": f"初始状态 · {l_fam.key}/v0 × {r_fam.key}/v0" + (" · 直接闭合" if is_closed and w_lv == 0 and w_rv == 0 else ""),
        "note": _pair_note(0, 0, None),
        "closes": bool(is_closed and w_lv == 0 and w_rv == 0),
    }]

    l_max_v = len(l_fam.versions) - 1
    r_max_v = len(r_fam.versions) - 1
    l_done = r_done = 0
    lv = rv = 0
    turn = "L"
    step_no = 0
    closed_seen = bool(steps[0]["closes"])
    total_target = int(l_fam.attempts or 0) + int(r_fam.attempts or 0)

    while (l_done < (l_fam.attempts or 0) or r_done < (r_fam.attempts or 0)) and step_no < max(total_target, 1) + 2:
        if turn == "L" and l_done >= (l_fam.attempts or 0):
            turn = "R"
        elif turn == "R" and r_done >= (r_fam.attempts or 0):
            turn = "L"
        step_no += 1
        if turn == "L":
            l_done += 1
            rem_after = (l_fam.attempts or 0) - l_done
            grew = lv < l_max_v and not (l_done in backoff_attempts[l_fam.key] and rem_after >= (l_max_v - lv))
            if grew:
                prev_len = l_fam.versions[lv].length
                lv += 1
                delta = l_fam.versions[lv].length - prev_len
                closes = bool(is_closed and not closed_seen and isinstance(w_lv, int) and isinstance(w_rv, int) and lv >= w_lv and rv >= w_rv)
                closed_seen = closed_seen or closes
                pill_en = f"{l_fam.key}→v{lv}" + (" · Closed" if closes else "")
                pill_zh = f"{l_fam.key}→v{lv}" + (" · 闭合" if closes else "")
                title_en = f"Round {step_no} · {l_fam.key}/v{lv} · +{delta:,} bp → {l_fam.versions[lv].length:,} bp" + (" · Closed" if closes else "")
                title_zh = f"第 {step_no} 轮 · {l_fam.key}/v{lv} · +{delta:,} bp → {l_fam.versions[lv].length:,} bp" + (" · 闭合" if closes else "")
                note = _pair_note(lv, rv, "L")
            else:
                delta = 0
                closes = False
                stop = l_fam.stop_reason if l_done == l_fam.attempts and l_fam.stop_reason else ""
                pill_en = f"{l_fam.key} #{l_done}"
                pill_zh = f"{l_fam.key} #{l_done}"
                title_en = f"Round {step_no} · {l_fam.key} · +0 bp" + (f" · {stop}" if stop else "")
                title_zh = f"第 {step_no} 轮 · {l_fam.key} · +0 bp" + (f" · {stop}" if stop else "")
                note = ""
            steps.append({
                "step": step_no, "side": "L", "lv": lv, "rv": rv, "delta": delta,
                "grew": grew, "pill_en": pill_en, "pill_zh": pill_zh,
                "title_en": title_en, "title_zh": title_zh, "note": note, "closes": closes,
            })
            turn = "R"
        else:
            r_done += 1
            rem_after = (r_fam.attempts or 0) - r_done
            grew = rv < r_max_v and not (r_done in backoff_attempts[r_fam.key] and rem_after >= (r_max_v - rv))
            if grew:
                prev_len = r_fam.versions[rv].length
                rv += 1
                delta = r_fam.versions[rv].length - prev_len
                closes = bool(is_closed and not closed_seen and isinstance(w_lv, int) and isinstance(w_rv, int) and lv >= w_lv and rv >= w_rv)
                closed_seen = closed_seen or closes
                pill_en = f"{r_fam.key}→v{rv}" + (" · Closed" if closes else "")
                pill_zh = f"{r_fam.key}→v{rv}" + (" · 闭合" if closes else "")
                title_en = f"Round {step_no} · {r_fam.key}/v{rv} · +{delta:,} bp → {r_fam.versions[rv].length:,} bp" + (" · Closed" if closes else "")
                title_zh = f"第 {step_no} 轮 · {r_fam.key}/v{rv} · +{delta:,} bp → {r_fam.versions[rv].length:,} bp" + (" · 闭合" if closes else "")
                note = _pair_note(lv, rv, "R")
            else:
                delta = 0
                closes = False
                stop = r_fam.stop_reason if r_done == r_fam.attempts and r_fam.stop_reason else ""
                pill_en = f"{r_fam.key} #{r_done}"
                pill_zh = f"{r_fam.key} #{r_done}"
                title_en = f"Round {step_no} · {r_fam.key} · +0 bp" + (f" · {stop}" if stop else "")
                title_zh = f"第 {step_no} 轮 · {r_fam.key} · +0 bp" + (f" · {stop}" if stop else "")
                note = ""
            steps.append({
                "step": step_no, "side": "R", "lv": lv, "rv": rv, "delta": delta,
                "grew": grew, "pill_en": pill_en, "pill_zh": pill_zh,
                "title_en": title_en, "title_zh": title_zh, "note": note, "closes": closes,
            })
            turn = "L"

    if is_closed and not any(s["closes"] for s in steps):
        steps[-1]["closes"] = True
        steps[-1]["pill_en"] += " · Closed"
        steps[-1]["pill_zh"] += " · 闭合"
    if not is_closed and len(steps) > 1:
        steps[-1]["pill_en"] += " · Unclosed"
        steps[-1]["pill_zh"] += " · 未闭合"
    return steps, diag_map


def _fmt_kb(val):
    if abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f} Mb"
    if abs(val) >= 1_000:
        return f"{val / 1_000:.1f} kb"
    return f"{int(val)} bp"


def _render_process_visual(search, result):
    """Render intuitive interactive bidirectional extension & alignment visuals.

    Returns (process_section_html, matrix_section_html) so the caller can place
    the compact Pair Checks Matrix beside the 2-row Families table on wide screens.
    """
    l_fam, r_fam = _select_visual_pair(search, result)
    if l_fam is None or r_fam is None or not l_fam.versions or not r_fam.versions:
        return "", ""

    winner = result.get("winner") if isinstance(result.get("winner"), dict) else None
    is_closed = winner is not None
    steps, diag_map = _build_round_steps(l_fam, r_fam, result)

    # Map each version increment (1..max) to the step number where it first appeared
    l_ver_step = {}
    r_ver_step = {}
    close_step = steps[-1]["step"]
    for st in steps:
        if st.get("side") == "L" and st.get("grew"):
            l_ver_step.setdefault(st["lv"], st["step"])
        elif st.get("side") == "R" and st.get("grew"):
            r_ver_step.setdefault(st["rv"], st["step"])
        if st.get("closes"):
            close_step = st["step"]

    # Build zoomed terminal extension SVG (800 x 136) with top coordinate ruler
    x0, plot_w = 60.0, 714.0
    ly, ry, bh = 36.0, 96.0, 18.0
    l0 = l_fam.versions[0].length
    r0 = r_fam.versions[0].length
    l_last = l_fam.versions[-1].length
    r_last = r_fam.versions[-1].length

    svg = [
        '<svg class="viz-svg" viewBox="0 0 800 136" role="img" aria-label="Bidirectional extension process">',
        '<defs><pattern id="dg-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="7" stroke="#b58546" stroke-width="2" stroke-opacity="0.5"/></pattern></defs>',
        f'<text x="8" y="{ly + 13:.0f}" class="v-lbl" data-side-lbl="L">{esc(l_fam.key)} →</text>',
        f'<text x="8" y="{ry + 13:.0f}" class="v-lbl" data-side-lbl="R">{esc(r_fam.key)} ←</text>',
    ]

    if is_closed:
        w_lv = int(winner.get("left_version", len(l_fam.versions) - 1))
        w_rv = int(winner.get("right_version", len(r_fam.versions) - 1))
        l_win = l_fam.versions[min(w_lv, len(l_fam.versions) - 1)].length
        r_win = r_fam.versions[min(w_rv, len(r_fam.versions) - 1)].length
        ov = int(winner.get("overlap") or 0)
        ls = winner.get("left_start")
        le = winner.get("left_end")
        rs = winner.get("right_start")
        re_ = winner.get("right_end")
        if all(isinstance(v, int) for v in (ls, le, rs, re_)) and le > ls and re_ > rs:
            r_tip_x = ls - rs
            ov_lo, ov_hi = ls, le
            r_ov_lo, r_ov_hi = r_tip_x + rs, r_tip_x + re_
        else:
            ov_eff = max(1, min(ov, l_win, r_win))
            ov_lo, ov_hi = l_win - ov_eff, l_win
            r_tip_x = ov_lo
            r_ov_lo, r_ov_hi = ov_lo, ov_hi
        r0_start_x = r_tip_x + (r_win - r0)
        r_min_x = r0_start_x - (r_last - r0)
        active_lo = min(l0, r_min_x, ov_lo)
        active_hi = max(l_last, r0_start_x, ov_hi)
        span = max(1000, active_hi - active_lo)
        pad = max(800, int(0.22 * span))
        win_lo = max(min(0, r_min_x, ov_lo), active_lo - pad)
        win_hi = min(max(l_last, r0_start_x + r0), active_hi + pad)
        if win_hi <= win_lo:
            win_hi = win_lo + 1000
        def px(coord):
            return x0 + plot_w * (coord - win_lo) / (win_hi - win_lo)

        # Top 1px coordinate scale ruler (L-anchored frame)
        mid_coord = (win_lo + win_hi) / 2.0
        svg.append(
            f'<line x1="{x0:.1f}" y1="18" x2="{x0 + plot_w:.1f}" y2="18" stroke="#cbd5e1" stroke-width="1"/>'
            f'<line x1="{x0:.1f}" y1="15" x2="{x0:.1f}" y2="21" stroke="#94a3b8" stroke-width="1"/>'
            f'<line x1="{x0 + plot_w / 2:.1f}" y1="15" x2="{x0 + plot_w / 2:.1f}" y2="21" stroke="#94a3b8" stroke-width="1"/>'
            f'<line x1="{x0 + plot_w:.1f}" y1="15" x2="{x0 + plot_w:.1f}" y2="21" stroke="#94a3b8" stroke-width="1"/>'
            f'<text x="{x0:.1f}" y="12" class="v-muted">{esc(_fmt_kb(win_lo))}</text>'
            f'<text x="{x0 + plot_w / 2:.1f}" y="12" text-anchor="middle" class="v-muted">{esc(_fmt_kb(mid_coord))}</text>'
            f'<text x="{x0 + plot_w:.1f}" y="12" text-anchor="end" class="v-muted">{esc(_fmt_kb(win_hi))}</text>'
        )

        # Original flank stubs + '//' crop marks when flanks extend beyond zoom window
        lf_x1, lf_x2 = px(max(win_lo, 0)), px(min(win_hi, l0))
        if lf_x2 > lf_x1:
            svg.append(f'<rect x="{lf_x1:.2f}" y="{ly:.0f}" width="{lf_x2 - lf_x1:.2f}" height="{bh:.0f}" rx="2" fill="#cbd5e1"><title>{esc(l_fam.key)} original flank ({l0:,} bp)</title></rect>')
            if win_lo > 0 and (lf_x2 - lf_x1) >= 14:
                svg.append(f'<path d="M{lf_x1 + 5:.1f},{ly + bh + 1:.0f} l4,-{bh + 2:.0f} M{lf_x1 + 9:.1f},{ly + bh + 1:.0f} l4,-{bh + 2:.0f}" stroke="#ffffff" stroke-width="1.5"/>')
        rf_x1, rf_x2 = px(max(win_lo, r0_start_x)), px(min(win_hi, r0_start_x + r0))
        if rf_x2 > rf_x1:
            svg.append(f'<rect x="{rf_x1:.2f}" y="{ry:.0f}" width="{rf_x2 - rf_x1:.2f}" height="{bh:.0f}" rx="2" fill="#cbd5e1"><title>{esc(r_fam.key)} original flank ({r0:,} bp)</title></rect>')
            if win_hi < r0_start_x + r0 and (rf_x2 - rf_x1) >= 14:
                svg.append(f'<path d="M{rf_x2 - 11:.1f},{ry + bh + 1:.0f} l4,-{bh + 2:.0f} M{rf_x2 - 7:.1f},{ry + bh + 1:.0f} l4,-{bh + 2:.0f}" stroke="#ffffff" stroke-width="1.5"/>')

        # L extension segments (growing rightward from l0)
        for v_idx in range(1, len(l_fam.versions)):
            s_len = l_fam.versions[v_idx - 1].length
            e_len = l_fam.versions[v_idx].length
            delta = e_len - s_len
            sx, ex = px(s_len), px(e_len)
            w_px = max(2.0, ex - sx)
            s_from = l_ver_step.get(v_idx, 1)
            lbl = f'<text x="{sx + w_px / 2:.2f}" y="{ly + 13:.0f}" text-anchor="middle" class="v-delta">+{delta:,} bp</text>' if w_px >= 66 else ""
            svg.append(
                f'<g data-from="{s_from}"><rect x="{sx:.2f}" y="{ly:.0f}" width="{w_px:.2f}" height="{bh:.0f}" fill="#2f5d8a">'
                f'<title>{esc(l_fam.key)}/v{v_idx} · +{delta:,} bp ({e_len:,} bp)</title></rect>'
                f'<path d="M{sx:.2f},{ly:.0f} v{bh:.0f}" stroke="#ffffff" stroke-width="1"/>{lbl}</g>'
            )

        # R extension segments (growing leftward from r0_start_x)
        for v_idx in range(1, len(r_fam.versions)):
            prev_add = r_fam.versions[v_idx - 1].length - r0
            cur_add = r_fam.versions[v_idx].length - r0
            delta = cur_add - prev_add
            ex = px(r0_start_x - prev_add)
            sx = px(r0_start_x - cur_add)
            w_px = max(2.0, ex - sx)
            s_from = r_ver_step.get(v_idx, 1)
            lbl = f'<text x="{sx + w_px / 2:.2f}" y="{ry + 13:.0f}" text-anchor="middle" class="v-delta">+{delta:,} bp</text>' if w_px >= 66 else ""
            svg.append(
                f'<g data-from="{s_from}"><rect x="{sx:.2f}" y="{ry:.0f}" width="{w_px:.2f}" height="{bh:.0f}" fill="#82571f">'
                f'<title>{esc(r_fam.key)}/v{v_idx} · +{delta:,} bp ({r_fam.versions[v_idx].length:,} bp)</title></rect>'
                f'<path d="M{ex:.2f},{ry:.0f} v{bh:.0f}" stroke="#ffffff" stroke-width="1"/>{lbl}</g>'
            )

        # Winning overlap bridge
        bx1, bx2 = px(ov_lo), px(ov_hi)
        rx1, rx2 = px(r_ov_lo), px(r_ov_hi)
        mid_y = (ly + bh + ry) / 2.0
        svg.append(
            f'<g data-from="{close_step}"><path fill="#2b7a57" fill-opacity="0.24" stroke="#2b7a57" stroke-width="1.2" '
            f'd="M{bx1:.2f},{ly + bh:.0f} H{bx2:.2f} C{bx2:.2f},{mid_y:.1f} {rx2:.2f},{mid_y:.1f} {rx2:.2f},{ry:.0f} '
            f'H{rx1:.2f} C{rx1:.2f},{mid_y:.1f} {bx1:.2f},{mid_y:.1f} {bx1:.2f},{ly + bh:.0f} Z">'
            f'<title>Overlap: {ov:,} bp ({winner.get("identity")}%)</title></path></g>'
        )
    else:
        l_add = max(0, l_last - l0)
        r_add = max(0, r_last - r0)
        stub_w = 82.0
        gap_w = 112.0
        ext_budget = plot_w - 2 * stub_w - gap_w
        scale_ref = max(20000, l_add + r_add)
        l_ext_w = max(4.0, ext_budget * (l_add / scale_ref)) if l_add else 0.0
        r_ext_w = max(4.0, ext_budget * (r_add / scale_ref)) if r_add else 0.0
        if l_ext_w + r_ext_w > ext_budget:
            shrink = ext_budget / (l_ext_w + r_ext_w)
            l_ext_w *= shrink
            r_ext_w *= shrink

        l_start = x0
        r_end = x0 + plot_w
        # Subtle scale reference on top right
        svg.append(
            f'<text x="{r_end:.1f}" y="14" text-anchor="end" class="v-muted t-en">Extension scale ref: {esc(_fmt_kb(scale_ref))}</text>'
            f'<text x="{r_end:.1f}" y="14" text-anchor="end" class="v-muted t-zh">延伸比例参考：{esc(_fmt_kb(scale_ref))}</text>'
        )
        # Flank stubs with '//' crop marks
        svg.append(
            f'<rect x="{l_start:.2f}" y="{ly:.0f}" width="{stub_w:.2f}" height="{bh:.0f}" rx="2" fill="#cbd5e1"><title>{esc(l_fam.key)} original flank ({l0:,} bp)</title></rect>'
            f'<path d="M{l_start + 7:.1f},{ly + bh + 1:.0f} l4,-{bh + 2:.0f} M{l_start + 11:.1f},{ly + bh + 1:.0f} l4,-{bh + 2:.0f}" stroke="#ffffff" stroke-width="1.5"/>'
        )
        svg.append(
            f'<rect x="{r_end - stub_w:.2f}" y="{ry:.0f}" width="{stub_w:.2f}" height="{bh:.0f}" rx="2" fill="#cbd5e1"><title>{esc(r_fam.key)} original flank ({r0:,} bp)</title></rect>'
            f'<path d="M{r_end - 13:.1f},{ry + bh + 1:.0f} l4,-{bh + 2:.0f} M{r_end - 9:.1f},{ry + bh + 1:.0f} l4,-{bh + 2:.0f}" stroke="#ffffff" stroke-width="1.5"/>'
        )

        # L increments
        cur_x = l_start + stub_w
        for v_idx in range(1, len(l_fam.versions)):
            delta = l_fam.versions[v_idx].length - l_fam.versions[v_idx - 1].length
            w_px = max(3.0, l_ext_w * delta / max(1, l_add))
            s_from = l_ver_step.get(v_idx, 1)
            lbl = f'<text x="{cur_x + w_px / 2:.2f}" y="{ly + 13:.0f}" text-anchor="middle" class="v-delta">+{delta:,} bp</text>' if w_px >= 66 else ""
            svg.append(
                f'<g data-from="{s_from}"><rect x="{cur_x:.2f}" y="{ly:.0f}" width="{w_px:.2f}" height="{bh:.0f}" fill="#2f5d8a">'
                f'<title>{esc(l_fam.key)}/v{v_idx} · +{delta:,} bp</title></rect>'
                f'<path d="M{cur_x:.2f},{ly:.0f} v{bh:.0f}" stroke="#ffffff" stroke-width="1"/>{lbl}</g>'
            )
            cur_x += w_px
        if 0 < l_add and l_ext_w < 66:
            svg.append(f'<text x="{cur_x + 5:.2f}" y="{ly + 13:.0f}" class="v-muted" data-from="{l_ver_step.get(1, 1)}">+{l_add:,} bp</text>')

        # Unclosed hatched gap indicator
        gap_x = cur_x + 6.0
        gap_draw_w = max(44.0, (r_end - stub_w - r_ext_w) - gap_x - 6.0)
        svg.append(
            f'<rect x="{gap_x:.2f}" y="{ly + bh + 6:.0f}" width="{gap_draw_w:.2f}" height="{ry - (ly + bh) - 12:.0f}" rx="3" fill="url(#dg-hatch)" stroke="#b58546" stroke-dasharray="3 3">'
            f'<title>Unclosed interval (span unknown)</title></rect>'
            f'<text x="{gap_x + gap_draw_w / 2:.2f}" y="{ly - 8:.0f}" text-anchor="middle" class="v-muted t-en">Unclosed · span unknown</text>'
            f'<text x="{gap_x + gap_draw_w / 2:.2f}" y="{ly - 8:.0f}" text-anchor="middle" class="v-muted t-zh">未闭合 · 间距未知</text>'
        )

        # R increments (leftward)
        cur_rx = r_end - stub_w
        for v_idx in range(1, len(r_fam.versions)):
            delta = r_fam.versions[v_idx].length - r_fam.versions[v_idx - 1].length
            w_px = max(3.0, r_ext_w * delta / max(1, r_add))
            sx = cur_rx - w_px
            s_from = r_ver_step.get(v_idx, 1)
            lbl = f'<text x="{sx + w_px / 2:.2f}" y="{ry + 13:.0f}" text-anchor="middle" class="v-delta">+{delta:,} bp</text>' if w_px >= 66 else ""
            svg.append(
                f'<g data-from="{s_from}"><rect x="{sx:.2f}" y="{ry:.0f}" width="{w_px:.2f}" height="{bh:.0f}" fill="#82571f">'
                f'<title>{esc(r_fam.key)}/v{v_idx} · +{delta:,} bp</title></rect>'
                f'<path d="M{cur_rx:.2f},{ry:.0f} v{bh:.0f}" stroke="#ffffff" stroke-width="1"/>{lbl}</g>'
            )
            cur_rx = sx
        if 0 < r_add and r_ext_w < 66:
            svg.append(f'<text x="{cur_rx - 5:.2f}" y="{ry + 13:.0f}" text-anchor="end" class="v-muted" data-from="{r_ver_step.get(1, 1)}">+{r_add:,} bp</text>')

    svg.append("</svg>")

    # Pills & step captions
    last_step = steps[-1]["step"]
    pills_html = "".join(
        f'<button type="button" class="viz-pill" data-step="{st["step"]}" aria-current="{"step" if st["step"] == last_step else "false"}">'
        f'{bi(st["pill_en"], st["pill_zh"])}</button>'
        for st in steps
    )
    caps_html = []
    for st in steps:
        hidden = "" if st["step"] == last_step else " hidden"
        ll = l_fam.versions[st["lv"]].length
        rl = r_fam.versions[st["rv"]].length
        note_div = f'<div class="muted" style="font-size:0.78rem;margin-top:2px;">{esc(st["note"])}</div>' if st["note"] else ""
        ov_key = f'<span class="tk-o">{bi("Overlap", "重叠区")}</span>' if is_closed and st["step"] >= close_step else ""
        caps_html.append(
            f'<div data-cap="{st["step"]}" data-side="{esc(st.get("side") or "")}"{hidden}>'
            f'<div class="viz-track-key"><span>{esc(l_fam.key)}/v{st["lv"]} · {ll:,} bp</span>'
            f'<span class="tk-r">{esc(r_fam.key)}/v{st["rv"]} · {rl:,} bp</span>'
            f'<span class="tk-f">{bi("Original flanks", "原始侧翼")}</span>{ov_key}</div>'
            f'<strong>{bi(st["title_en"], st["title_zh"])}</strong>{note_div}</div>'
        )

    # Full-length synteny view pane (merged into same canvas via Zoom | Full toggle, avoiding duplicate stacked diagrams)
    full_pane_html = ""
    view_toggle_html = ""
    if is_closed and all(isinstance(winner.get(k), int) for k in ("left_start", "left_end", "right_start", "right_end")):
        w_lv = int(winner.get("left_version", len(l_fam.versions) - 1))
        w_rv = int(winner.get("right_version", len(r_fam.versions) - 1))
        l_win = l_fam.versions[min(w_lv, len(l_fam.versions) - 1)].length
        r_win = r_fam.versions[min(w_rv, len(r_fam.versions) - 1)].length
        max_seq = max(1, l_win, r_win)
        sx0, sw = 76.0, 698.0
        scale = sw / max_seq
        ls, le, rs, re_ = winner["left_start"], winner["left_end"], winner["right_start"], winner["right_end"]
        l_w, r_w = l_win * scale, r_win * scale
        l_flank_w = min(l0, l_win) * scale
        r_ext_w = max(0, r_win - r0) * scale
        lx1, lx2 = sx0 + ls * scale, sx0 + le * scale
        rx1, rx2 = sx0 + rs * scale, sx0 + re_ * scale
        syn_svg = (
            '<svg class="viz-svg" viewBox="0 0 800 116" role="img" aria-label="Winning pair synteny">'
            f'<path fill="#2b7a57" fill-opacity="0.22" stroke="#2b7a57" stroke-width="1" '
            f'd="M{lx1:.2f},36 H{lx2:.2f} C{lx2:.2f},58 {rx2:.2f},58 {rx2:.2f},80 H{rx1:.2f} C{rx1:.2f},58 {lx1:.2f},58 {lx1:.2f},36 Z"/>'
            f'<text x="8" y="33" class="v-lbl">{esc(l_fam.key)}/v{w_lv}</text>'
            f'<rect x="{sx0:.2f}" y="22" width="{l_w:.2f}" height="14" rx="2" fill="#cbd5e1"/>'
            + (f'<rect x="{sx0 + l_flank_w:.2f}" y="22" width="{max(1.0, l_w - l_flank_w):.2f}" height="14" fill="#2f5d8a"/>' if l_win > l0 else "")
            + f'<rect x="{lx1:.2f}" y="27" width="{max(2.0, lx2 - lx1):.2f}" height="4" fill="#2b7a57"/>'
            f'<text x="{sx0:.2f}" y="16" class="v-muted">0</text>'
            f'<text x="{sx0 + l_w:.2f}" y="16" text-anchor="end" class="v-muted">{l_win:,} bp</text>'
            f'<text x="8" y="91" class="v-lbl">{esc(r_fam.key)}/v{w_rv}</text>'
            f'<rect x="{sx0:.2f}" y="80" width="{r_w:.2f}" height="14" rx="2" fill="#cbd5e1"/>'
            + (f'<rect x="{sx0:.2f}" y="80" width="{max(1.0, r_ext_w):.2f}" height="14" fill="#82571f"/>' if r_win > r0 else "")
            + f'<rect x="{rx1:.2f}" y="85" width="{max(2.0, rx2 - rx1):.2f}" height="4" fill="#2b7a57"/>'
            f'<text x="{sx0:.2f}" y="109" class="v-muted">0</text>'
            f'<text x="{sx0 + r_w:.2f}" y="109" text-anchor="end" class="v-muted">{r_win:,} bp</text>'
            '</svg>'
        )
        stage_tag = ((winner.get("evidence") or {}).get("stage") or "")
        stage_bit = f'<span>{bi("Stage", "阶段")}: <b>{esc(stage_tag)}</b></span>' if stage_tag else ""
        full_pane_html = (
            '<div data-view-pane="full" hidden>'
            f'<div class="viz-canvas">{syn_svg}</div>'
            f'<div class="viz-meta-line"><span><b>{winner.get("overlap", 0):,} bp</b> {bi("overlap", "重叠")}</span>'
            f'<span><b>{esc(winner.get("identity"))}%</b> {bi("identity", "一致性")}</span>'
            f'<span><b>{winner.get("overhang", 0):,} bp</b> {bi("overhang", "悬垂")}</span>'
            f'{stage_bit}'
            f'<span class="muted mono">{esc(l_fam.key)} [{ls:,}, {le:,}) ↔ {esc(r_fam.key)} [{rs:,}, {re_:,})</span></div>'
            '</div>'
        )
        view_toggle_html = (
            '<div class="viz-view-toggle" role="group" aria-label="View mode">'
            f'<button type="button" class="viz-view-btn" data-viz-view="zoom" aria-pressed="true">{bi("Terminal zoom", "末端放大")}</button>'
            f'<button type="button" class="viz-view-btn" data-viz-view="full" aria-pressed="false">{bi("Full alignment", "全长比对")}</button>'
            '</div>'
        )

    # Conditional Junction Composition bar: only render when there are terminal edits or overlap trimming
    junction_bar_html = ""
    junction = result.get("junction") if isinstance(result.get("junction"), dict) else None
    repairs_list = [r for r in (junction.get("repairs") or []) if isinstance(r, dict)] if junction else []
    ov_trim = int(junction.get("overlap_trim") or 0) if junction else 0
    if junction and isinstance(junction.get("gap_length"), int) and (repairs_list or ov_trim > 0):
        g_len = junction["gap_length"]
        fill_pos = max(0, g_len)
        total_comp = max(1, l0 + fill_pos + r0)
        jx0, jw = 14.0, 772.0
        lw_px = jw * l0 / total_comp
        fw_px = max(3.0, jw * fill_pos / total_comp) if fill_pos > 0 else 0.0
        rw_px = max(2.0, jw - lw_px - fw_px)
        pins = []
        for rep in repairs_list[:60]:
            pos = rep.get("start0") if isinstance(rep.get("start0"), int) else rep.get("start")
            if not isinstance(pos, int):
                continue
            st_r = str(rep.get("status") or "").lower()
            col = "#2b7a57" if st_r == "accepted" else ("#b45309" if st_r == "retained" else "#64748b")
            py = 56 if st_r == "retained" else 48
            if rep.get("side") == "L":
                px_pin = jx0 + lw_px * max(0.0, min(1.0, pos / max(1, l0)))
            else:
                px_pin = jx0 + lw_px + fw_px + rw_px * max(0.0, min(1.0, pos / max(1, r0)))
            pins.append(
                f'<g><title>{esc(rep.get("side"))} [{pos:,}) · {esc(st_r)}</title>'
                f'<line x1="{px_pin:.2f}" y1="36" x2="{px_pin:.2f}" y2="{py}" stroke="{col}" stroke-width="1"/>'
                f'<circle cx="{px_pin:.2f}" cy="{py}" r="2.4" fill="{col}"/></g>'
            )
        j_svg = (
            '<svg class="viz-svg" viewBox="0 0 800 62" role="img" aria-label="Final junction composition">'
            f'<rect x="{jx0:.2f}" y="20" width="{lw_px:.2f}" height="16" rx="2" fill="#2f5d8a"><title>Left flank ({l0:,} bp)</title></rect>'
            + (f'<rect x="{jx0 + lw_px:.2f}" y="20" width="{fw_px:.2f}" height="16" fill="#2b7a57"><title>Gap-only fill ({g_len:,} bp)</title></rect>' if fw_px else "")
            + f'<rect x="{jx0 + lw_px + fw_px:.2f}" y="20" width="{rw_px:.2f}" height="16" rx="2" fill="#82571f"><title>Right flank ({r0:,} bp)</title></rect>'
            f'<line x1="{jx0 + lw_px:.2f}" y1="15" x2="{jx0 + lw_px:.2f}" y2="41" stroke="#2b7a57" stroke-width="1.2"/>'
            + "".join(pins) + '</svg>'
        )
        trim_bit = f'<span>{bi("Overlap trim", "重叠裁剪")}: <b>{ov_trim:,} bp</b></span>' if ov_trim else ""
        delta_j = junction.get("flank_length_delta")
        delta_bit = f'<span>{bi("Flank delta", "末端变化")}: <b>{delta_j:+,} bp</b></span>' if isinstance(delta_j, int) and delta_j != 0 else ""
        edit_bit = f'<span>{bi("Terminal edits", "末端提议")}: <b>{len(repairs_list):,}</b></span>' if repairs_list else ""
        junction_bar_html = (
            '<div class="viz-sub">'
            f'<h3>{bi("Final Junction Composition", "最终拼接与末端位点")}</h3>'
            f'<div class="viz-canvas">{j_svg}</div>'
            f'<div class="viz-meta-line">{edit_bit}{trim_bit}{delta_bit}'
            f'<span class="muted">{bi("Pins: green accepted · slate protected · amber retained", "标记：绿采用 · 灰保护 · 橙保留")}</span></div>'
            '</div>'
        )

    # Compact L x R Pair Checks Matrix (returned as its own side-by-side section for .detail-grid)
    matrix_section_html = ""
    if diag_map or is_closed:
        n_r = len(r_fam.versions)
        cells = [f'<span class="mh">{esc(l_fam.key)}×{esc(r_fam.key)}</span>'] + [f'<span class="mh">v{j}</span>' for j in range(n_r)]
        for i in range(len(l_fam.versions)):
            cells.append(f'<span class="mh">v{i}</span>')
            for j in range(n_r):
                d = diag_map.get((i, j))
                if is_closed and i == winner.get("left_version") and j == winner.get("right_version"):
                    tip = f"{l_fam.key}/v{i} × {r_fam.key}/v{j}: Winner"
                    cells.append(f'<span class="mc-win" title="{esc(tip)}">★</span>')
                elif d:
                    st_d = str(d.get("status") or "").lower()
                    rsn = str(d.get("reason") or st_d)
                    tip = f"{l_fam.key}/v{i} × {r_fam.key}/v{j}: {rsn}"
                    if st_d == "eligible":
                        cells.append(f'<span class="mc-ok" title="{esc(tip)}">✓</span>')
                    elif "no_align" in rsn.lower():
                        cells.append(f'<span class="mc-none" title="{esc(tip)}">–</span>')
                    else:
                        cells.append(f'<span class="mc-rej" title="{esc(tip)}">×</span>')
                else:
                    cells.append(f'<span class="mc-unk" title="{esc(l_fam.key)}/v{i} × {esc(r_fam.key)}/v{j}">·</span>')
        matrix_section_html = (
            '<section class="section">'
            f'<div class="section-header"><h2>{bi("Pair Checks", "配对矩阵")}</h2></div>'
            '<div class="section-body">'
            f'<div class="viz-matrix-wrap"><div class="viz-matrix" style="grid-template-columns:auto repeat({n_r},minmax(34px,1fr))">{"".join(cells)}</div></div>'
            f'<p class="viz-note">{bi("★ win · ✓ ok · × rej · – none · · skip", "★ 胜出 · ✓ 合格 · × 否决 · – 无比对 · · 未检")}</p>'
            '</div></section>'
        )

    playback_html = (
        '<div class="viz-controls">'
        f'<button type="button" class="viz-btn is-play" data-viz-play aria-pressed="false">'
        f'<span class="lbl-play">{bi("▶ Play", "▶ 播放")}</span>'
        f'<span class="lbl-pause">{bi("⏸ Pause", "⏸ 暂停")}</span></button>'
        '<button type="button" class="viz-btn" data-viz-prev aria-label="Previous step">←</button>'
        '<button type="button" class="viz-btn" data-viz-next disabled aria-label="Next step">→</button>'
        '</div>'
        f'<div class="viz-pills">{pills_html}</div>'
    ) if len(steps) > 1 else ""
    toolbar_html = f'<div class="viz-bar">{playback_html}{view_toggle_html}</div>' if (playback_html or view_toggle_html) else ""

    process_section_html = (
        '<section class="section">'
        f'<div class="section-header"><h2>{bi("Extension Process", "双向延伸过程")}</h2></div>'
        '<div class="section-body" data-viz-player>'
        f'{toolbar_html}'
        '<div data-view-pane="zoom">'
        f'<div class="viz-canvas">{"".join(svg)}</div>'
        f'<div class="viz-caption" aria-live="polite">{"".join(caps_html)}</div>'
        '</div>'
        f'{full_pane_html}'
        f'{junction_bar_html}'
        '</div></section>'
    )
    return process_section_html, matrix_section_html


def render_report(search, result):
    """Portable evidence tables for both chains; no single-direction attribution."""
    is_closed = search.status == "closed"
    tone = "ok" if is_closed else status_tone(search.status)
    if tone == "info":
        tone = "warn"
    state_badge = (
        badge_bi("Closed", "已闭合", tone)
        if is_closed
        else badge_bi(f"Unclosed ({search.status})", f"未闭合 ({search.status})", tone)
    )

    rows = []
    histories = []
    for family in search.families.values():
        stop_reason = family.stop_reason or "—"
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(family.key)}</td>'
            f'<td>{esc(family.direction)}</td>'
            f'<td class="num">{esc(family.attempts)}</td>'
            f'<td class="num">{len(family.versions)}</td>'
            f'<td class="num">{family.added_bases:,} bp</td>'
            f'<td>{esc(stop_reason)}</td>'
            "</tr>"
        )
        for version in family.versions:
            histories.append(
                "<tr>"
                f'<td class="mono">{esc(family.key)}</td>'
                f'<td class="num">v{esc(version.number)}</td>'
                f'<td class="num">{version.length:,} bp</td>'
                f'<td><span class="hash hash-short" title="{esc(version.sha256)}">{esc(version.sha256)}</span></td>'
                "</tr>"
            )

    comparisons = []
    candidate_count = 0
    for candidates in search.checked.values():
        for candidate in candidates:
            candidate_count += 1
            selected = candidate == result["winner"]
            row_class = ' class="row-selected"' if selected else ""
            selection_badge = (
                badge_bi("Selected", "已采用", "ok")
                if selected
                else badge_bi("Not selected", "未采用", "muted")
            )
            comparisons.append(
                f"<tr{row_class}>"
                f'<td class="mono">{esc(candidate["left_family"])}/{esc(candidate["left_version"])}</td>'
                f'<td class="mono">{esc(candidate["right_family"])}/{esc(candidate["right_version"])}</td>'
                f'<td class="num">{esc(candidate["identity"])}</td>'
                f'<td class="num">{esc(candidate["overlap"])}</td>'
                f'<td class="num">{esc(candidate["overhang"])}</td>'
                f'<td>{selection_badge}</td>'
                "</tr>"
            )

    if not rows:
        rows.append(f'<tr><td colspan="6" class="empty-state">{bi("No extension families recorded", "暂无延伸家族记录")}</td></tr>')
    if not histories:
        histories.append(f'<tr><td colspan="4" class="empty-state">{bi("No sequence versions recorded", "暂无序列版本记录")}</td></tr>')

    winner = result.get("winner")
    gap_length = result.get("gap_length")
    strip_items = []
    if gap_length is not None:
        strip_items.append((bi("Gap length", "填补长度"), f"{gap_length:,} bp", "accent", ""))
    strip_items.extend([
        (bi("Attempts", "轮数"), f"{search.total_rounds:,}", "", ""),
        (bi("Added", "延伸"), f"{search.total_length:,} bp", "", ""),
    ])
    if len(search.families) != 2:
        strip_items.append((bi("Families", "家族"), str(len(search.families)), "", ""))
    if winner:
        win_pair = f'{winner["left_family"]}/{winner["left_version"]} + {winner["right_family"]}/{winner["right_version"]}'
        id_note = f'{winner["identity"]}%' if winner.get("identity") is not None else ""
        strip_items.append((bi("Winner", "胜出"), win_pair, "ok", id_note))
    elif candidate_count > 0:
        strip_items.append((bi("Eligible", "合格连接"), str(candidate_count), "", ""))

    process_visual_html, matrix_section_html = _render_process_visual(search, result)

    from JunctionReport import render_junction_report
    junction_html = render_junction_report(result)
    junction_drawer = ""
    if junction_html:
        junction_drawer = (
            '<details class="fold">'
            f'<summary><span class="fold-title">{bi("Junction & Connection Diagnostics", "连接边界与诊断")}</span></summary>'
            f'<div class="fold-body">{junction_html}</div>'
            '</details>'
        )

    connections_drawer = ""
    if candidate_count > 1 or (candidate_count > 0 and not winner):
        connections_table = (
            '<div class="table-scroll">'
            '<table>'
            '<thead><tr>'
            f'<th>{bi("Left", "左侧")}</th>'
            f'<th>{bi("Right", "右侧")}</th>'
            f'<th>{bi("Identity %", "一致性")}</th>'
            f'<th>{bi("Overlap", "重叠")}</th>'
            f'<th>{bi("Overhang", "悬垂")}</th>'
            f'<th>{bi("Status", "状态")}</th>'
            '</tr></thead>'
            f'<tbody>{"".join(comparisons)}</tbody>'
            '</table>'
            '</div>'
        )
        connections_drawer = (
            '<details class="fold">'
            f'<summary><span class="fold-title">{bi("Eligible Connections", "合格连接")} <span class="muted num">({candidate_count})</span></span></summary>'
            f'<div class="fold-body">{connections_table}</div>'
            '</details>'
        )

    families_section = (
        '<section class="section">'
        f'<div class="section-header"><h2>{bi("Families", "延伸家族")}</h2></div>'
        '<div class="section-body">'
        '<div class="table-scroll">'
        '<table>'
        '<thead><tr>'
        f'<th>{bi("Family", "家族")}</th>'
        f'<th>{bi("Direction", "方向")}</th>'
        f'<th>{bi("Attempts", "轮数")}</th>'
        f'<th>{bi("Versions", "版本")}</th>'
        f'<th>{bi("Added", "延伸")}</th>'
        f'<th>{bi("Stop reason", "停止原因")}</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div>'
        '</div>'
        '</section>'
    )
    summary_row_html = (
        f'<div class="detail-grid">{families_section}{matrix_section_html}</div>'
        if matrix_section_html else families_section
    )

    css = report_css(_VISUAL_CSS)
    final_href = esc(result["final_sequence"])
    title_label = esc(result["final_sequence"].removesuffix(".final.fa")) if isinstance(result.get("final_sequence"), str) else "DEGAP"

    return f'''<!doctype html>
<html lang="en" data-lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_label} · DEGAP</title>
<style>
{css}
</style>
</head>
<body>
<main class="report-shell">
  <header class="report-header">
    <div class="header-top">
      <div class="header-info">
        <div class="report-eyebrow">DEGAP · {bi("Bidirectional Family Extension", "双向家族延伸")}</div>
        <h1>{title_label}</h1>
      </div>
      <div class="header-actions">{state_badge}{lang_switcher_html("en")}</div>
    </div>
    {summary_strip_html(strip_items)}
  </header>

  {process_visual_html}

  {summary_row_html}

  <div class="fold-panel">
    {junction_drawer}
    {connections_drawer}
    <details class="fold">
      <summary><span class="fold-title">{bi("Sequence History & SHA-256", "序列版本与校验值")} <span class="muted num">({len(histories)})</span></span></summary>
      <div class="fold-body">
        <div class="table-scroll scroll">
          <table>
            <thead>
              <tr>
                <th>{bi("Family", "家族")}</th>
                <th>{bi("Version", "版本")}</th>
                <th>{bi("Length", "长度")}</th>
                <th>SHA-256</th>
              </tr>
            </thead>
            <tbody>{''.join(histories)}</tbody>
          </table>
        </div>
      </div>
    </details>
    <details class="fold">
      <summary><span class="fold-title">{bi("Files & Provenance", "输出与溯源文件")}</span></summary>
      <div class="fold-body">
        <nav aria-label="Downloadable artifacts">
          <ul class="artifact-list">
            <li><a class="artifact-link" href="{final_href}">FASTA ({final_href})</a></li>
            <li><a class="artifact-link" href="process.agp">AGP</a></li>
            <li><a class="artifact-link" href="family-components.fa">{bi("AGP components", "组成序列")}</a></li>
            <li><a class="artifact-link" href="family-result.json">{bi("Result provenance", "结果溯源")}</a></li>
            <li><a class="artifact-link" href="families.json">{bi("Checkpoint & history", "历史与断点")}</a></li>
          </ul>
        </nav>
      </div>
    </details>
  </div>
</main>
<script>{lang_switcher_js()}{_PLAYER_JS}</script>
</body>
</html>'''



def render_family_report_from_data(result, families=None, junction_evidence=None, connection_diagnostics=None):
    """Render a detached L/R report from decoded JSON; never open paths in the data.

    `families` is the optional families.json checkpoint, used for all eligible
    comparisons. With no checkpoint, only the winner is known individually.
    This function never overwrites the digest-bound published report.
    """
    from FamilyReport import render
    checkpoint = families or {}
    if checkpoint.get("contract_id") and checkpoint["contract_id"] != result.get("search_contract"):
        raise ValueError("Checkpoint belongs to a different family search")
    if any(key in checkpoint and checkpoint[key] != result.get(key) for key in ("status", "winner")):
        raise ValueError("Checkpoint does not match the published outcome")
    if "families" in checkpoint:
        def history(records):
            return {f["key"]: (f["attempts"], [(v["number"], v["length"], v["sha256"]) for v in f["versions"]])
                    for f in records}
        if history(checkpoint["families"]) != history(result["families"]):
            raise ValueError("Checkpoint does not match the published version history")
    data = dict(result)
    if junction_evidence is not None:
        summary = junction_evidence["summary"]
        if "junction" in data and data["junction"] != summary:
            raise ValueError("Conflicting junction evidence")
        data["junction"] = summary
    if connection_diagnostics is not None:
        if data.get("connection_diagnostics") is not None and data["connection_diagnostics"] != connection_diagnostics:
            raise ValueError("Conflicting connection diagnostics")
        data["connection_diagnostics"] = connection_diagnostics
    return render(data, checkpoint.get("checked"))
