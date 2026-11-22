"""Sequence/AGP/provenance publication for a completed family search."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from ExtensionFamilies import atomic_json, fingerprint, read_json
from FamilyOverlap import joined_sequence, read_sequence
from FamilyTools import content_hash
from ReportStyle import badge_html, esc, report_css, status_tone

SCHEMA = "degap-family-result-v1"


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
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


def render_report(search, result):
    """Portable evidence tables for both chains; no single-direction attribution."""
    is_closed = search.status == "closed"
    tone = "ok" if is_closed else status_tone(search.status)
    if tone == "info":
        tone = "warn"
    state_label = ("Closed / 已闭合"
                   if is_closed else f"Unclosed / 未闭合 ({search.status})")

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
            f'<td class="num">{esc(family.added_bases)} bp</td>'
            f'<td>{esc(stop_reason)}</td>'
            "</tr>"
        )
        for version in family.versions:
            histories.append(
                "<tr>"
                f'<td class="mono">{esc(family.key)}</td>'
                f'<td class="num">v{esc(version.number)}</td>'
                f'<td class="num">{esc(version.length)} bp</td>'
                f'<td class="hash">{esc(version.sha256)}</td>'
                "</tr>"
            )

    comparisons = []
    candidate_count = 0
    for candidates in search.checked.values():
        for candidate in candidates:
            candidate_count += 1
            selected = candidate == result["winner"]
            row_class = ' class="row-selected"' if selected else ""
            selection_badge = (badge_html("Selected / 已采用", "ok")
                               if selected else badge_html("Not selected / 未采用", "muted"))
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
        rows.append('<tr><td colspan="6" class="empty-state">No extension families recorded / 暂无延伸家族记录</td></tr>')
    if not comparisons:
        comparisons.append('<tr><td colspan="6" class="empty-state">No eligible connections recorded / 暂无合格连接记录</td></tr>')
    if not histories:
        histories.append('<tr><td colspan="4" class="empty-state">No sequence versions recorded / 暂无序列版本记录</td></tr>')

    winner = result.get("winner")
    gap_length = result.get("gap_length")
    metrics = [
        ("Attempts / 总尝试轮数", str(search.total_rounds), "", ""),
        ("Added bases / 总延伸长度", f"{search.total_length} bp", "", ""),
        ("Families / 延伸家族", str(len(search.families)), "", ""),
        ("Eligible pairs / 合格连接", str(candidate_count), "ok" if winner else "",
         f'{winner["left_family"]}/{winner["left_version"]} + {winner["right_family"]}/{winner["right_version"]}' if winner else ""),
    ]
    if gap_length is not None:
        metrics.append(("Gap length / 填补长度", f"{gap_length} bp", "accent", ""))

    metric_cards = []
    for label, value, value_tone, note in metrics:
        tone_class = f" {value_tone}" if value_tone else ""
        note_html = f'<div class="metric-note mono">{esc(note)}</div>' if note else ""
        metric_cards.append(
            f'<div class="metric-card">'
            f'<div class="metric-label">{esc(label)}</div>'
            f'<div class="metric-value{tone_class}">{esc(value)}</div>'
            f'{note_html}'
            f'</div>'
        )

    from JunctionReport import render_junction_report
    junction_html = render_junction_report(result)
    notice_class = "notice notice-ok" if is_closed else "notice notice-warn"
    css = report_css()
    final_href = esc(result["final_sequence"])

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DEGAP family extension / 双向家族延伸</title>
<style>
{css}
</style>
</head>
<body>
<main class="report-shell">
  <header class="report-header">
    <div class="header-top">
      <div class="header-info">
        <div class="report-eyebrow">DEGAP · Bidirectional Family Extension</div>
        <h1>DEGAP family extension <span class="bilingual-zh">/ 双向家族延伸</span></h1>
      </div>
      <div>{badge_html(state_label, tone)}</div>
    </div>
  </header>

  {junction_html}
  <section class="metrics-grid" aria-label="Summary metrics">
    {''.join(metric_cards)}
  </section>

  <div class="{notice_class}" role="note">
    <p>Only a closed result joins both families. Unclosed sequences are exported separately.</p>
    <p>只有闭合结果才连接两侧；未闭合时各家族序列分别导出。</p>
  </div>

  <nav class="artifact-bar" aria-label="Downloadable artifacts">
    <div class="artifact-bar-title">Artifacts and Provenance <span class="bilingual-zh">/ 输出与溯源文件</span></div>
    <ul class="artifact-list">
      <li><a class="artifact-link" href="{final_href}">FASTA ({final_href})</a></li>
      <li><a class="artifact-link" href="process.agp">AGP</a></li>
      <li><a class="artifact-link" href="family-components.fa">AGP components / 组成序列</a></li>
      <li><a class="artifact-link" href="family-result.json">Result provenance / 结果溯源</a></li>
      <li><a class="artifact-link" href="families.json">History and checkpoint / 历史与断点</a></li>
    </ul>
  </nav>

  <section class="section">
    <div class="section-header"><h2>Families <span class="bilingual-zh">/ 延伸家族</span></h2></div>
    <div class="section-body">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Family / 家族</th>
              <th>Direction / 方向</th>
              <th>Attempts / 轮数</th>
              <th>Versions / 版本数</th>
              <th>Added bases / 延伸长度</th>
              <th>Stop reason / 停止原因</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-header"><h2>Eligible connections <span class="bilingual-zh">/ 合格连接</span></h2></div>
    <div class="section-body">
      <p class="section-note">Rank: identity, overlap length, endpoint overhang, fixed version order.<br>
      依次按一致性、重叠长度、端点未对齐长度和固定版本顺序选优；只采用一个结果。</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Left version / 左侧版本</th>
              <th>Right version / 右侧版本</th>
              <th>Identity % / 一致性</th>
              <th>Overlap / 重叠</th>
              <th>Overhang / 悬垂</th>
              <th>Selection / 采用状态</th>
            </tr>
          </thead>
          <tbody>{''.join(comparisons)}</tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-header"><h2>Sequence history <span class="bilingual-zh">/ 序列历史</span></h2></div>
    <div class="section-body">
      <div class="table-scroll scroll">
        <table>
          <thead>
            <tr>
              <th>Family / 家族</th>
              <th>Version / 版本</th>
              <th>Length / 长度</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>{''.join(histories)}</tbody>
        </table>
      </div>
    </div>
  </section>

  <footer class="report-footer">
    <p>Read mappings, local assemblies and their receipts remain under <code>attempts/</code> for inspection.</p>
    <p>reads 比对、局部组装及其记录保存在 <code>attempts/</code> 中，供复核。</p>
  </footer>
</main>
</body>
</html>'''
