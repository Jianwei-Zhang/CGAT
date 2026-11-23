//! Write one editable path, not one workspace per tool. The caller holds a SQLite write transaction.
use super::gap_candidates::{Candidate, PRIORITY};
use super::*;
use crate::degap_jobs::{
    canonicalize_entry, load_project_paths, update_length, witness, write_project_paths,
};
use serde_json::json;

pub(super) type Review = BTreeMap<(String, String, String), (String, &'static str)>;
fn note(review: &mut Review, c: &Candidate, reason: &'static str) {
    review.insert(
        (c.tool.clone(), c.manifest.clone(), c.gap.clone()),
        (c.chr.clone(), reason),
    );
}
fn save_review(conn: &Transaction<'_>, project: i64, review: Review) -> Result<()> {
    let mut stmt=conn.prepare("INSERT INTO project_auto_gap_review(project_id,tool,light_manifest,gap_id,chr,disposition) VALUES(?1,?2,?3,?4,?5,?6)
        ON CONFLICT(project_id,tool,light_manifest,gap_id) DO UPDATE SET disposition=excluded.disposition WHERE project_auto_gap_review.disposition!='adopted'")?;
    for ((tool, key, gid), (chr, why)) in review {
        stmt.execute(params![project, tool, key, gid, chr, why])?;
    }
    Ok(())
}

struct Geometry<'a> {
    rows: &'a [Value],
    offsets: Vec<i64>,
    ids: HashMap<&'a str, Option<usize>>,
}
impl<'a> Geometry<'a> {
    fn new(rows: &'a [Value]) -> Option<Self> {
        let mut offsets = vec![0i64];
        let mut ids = HashMap::new();
        for (i, r) in rows.iter().enumerate() {
            let id = r["segmentId"].as_str()?;
            ids.entry(id)
                .and_modify(|old| *old = None)
                .or_insert(Some(i));
            let n = if r["type"] == "gap" {
                r["gapSizeBp"].as_i64()?
            } else {
                let (a, b) = (r["start"].as_i64()?, r["end"].as_i64()?);
                if a < 1 || b < 1 {
                    return None;
                }
                a.max(b) - a.min(b) + 1
            };
            if n < 1 {
                return None;
            }
            offsets.push(offsets.last()?.checked_add(n)?);
        }
        Some(Self { rows, offsets, ids })
    }
    fn index(&self, pos: i64) -> Option<usize> {
        if pos < 0 || pos >= *self.offsets.last()? {
            return None;
        }
        Some(self.offsets.partition_point(|&o| o <= pos) - 1)
    }
}
fn bounds(
    c: &Candidate,
    base: &Geometry,
    now: &Geometry,
    protected: &HashSet<String>,
) -> Option<(i64, i64)> {
    let (i, j) = (base.index(c.start)?, base.index(c.end.checked_sub(1)?)?);
    let (g, h) = (
        base.index(c.gap_start)?,
        base.index(c.gap_end.checked_sub(1)?)?,
    );
    if base.offsets[g] != c.gap_start || base.offsets[h + 1] != c.gap_end {
        return None;
    }
    if !(g..=h).all(|n| {
        base.rows[n]["type"] == "gap"
            && !protected.contains(base.rows[n]["segmentId"].as_str().unwrap_or(""))
    }) {
        return None;
    }
    // A single-gap edit cannot delete a second explicit Gap even if corrupt metadata omitted it.
    if (i..=j).any(|n| !(g..=h).contains(&n) && base.rows[n]["type"] == "gap") {
        return None;
    }
    // Bind the consumed interval plus one original base on either side. A new insertion
    // inside that span must block application; a trim outside it need not block a distant gap.
    let left = c.start.saturating_sub(1).max(0);
    let right = c.end.saturating_add(1).min(*base.offsets.last()?);
    let mut previous = None;
    let mut first = None;
    for k in base.index(left)?..=base.index(right - 1)? {
        let old = &base.rows[k];
        let id = old["segmentId"].as_str()?;
        let j = now.ids.get(id).copied().flatten()?;
        let actual = &now.rows[j];
        let lo = left.max(base.offsets[k]) - base.offsets[k];
        let hi = right.min(base.offsets[k + 1]) - base.offsets[k];
        let mut w = witness(old).ok()?;
        let mut current = witness(actual).ok()?;
        let mut delta = 0;
        if w["kind"] == "ctg" && current["kind"] == "ctg" {
            let (a, b) = (w["start"].as_i64()?, w["end"].as_i64()?);
            let (x, y) = (current["start"].as_i64()?, current["end"].as_i64()?);
            if (a > b) != (x > y) {
                return None;
            }
            for key in ["start", "end"] {
                w.as_object_mut()?.remove(key);
                current.as_object_mut()?.remove(key);
            }
            delta = if a > b { x - a } else { a - x };
        }
        if w != current {
            return None;
        }
        let a = lo.checked_add(delta)?;
        let b = hi.checked_add(delta)?;
        if a < 0 || b > now.offsets[j + 1] - now.offsets[j] {
            return None;
        }
        let (a, b) = (now.offsets[j] + a, now.offsets[j] + b);
        if previous.is_some_and(|v| v != a) {
            return None;
        }
        first.get_or_insert(a);
        previous = Some(b);
    }
    let a = first?.checked_add(c.start - left)?;
    let b = a.checked_add(c.end - c.start)?;
    if c.start == 0 && a != 0 || c.end == *base.offsets.last()? && b != *now.offsets.last()? {
        return None;
    }
    Some((a, b))
}
fn section(r: &Value, lo: i64, hi: i64, n: i64) -> Result<Value> {
    if lo == 0 && hi == n {
        return Ok(r.clone());
    }
    if lo < 0 || lo >= hi || hi > n {
        bail!("invalid retained automatic interval");
    }
    let mut row = r.clone();
    if r["type"] == "gap" {
        row["gapSizeBp"] = json!(hi - lo);
    } else {
        let start = r["start"].as_i64().context("missing source start")?;
        let end = r["end"].as_i64().context("missing source end")?;
        let (a, b) = if start <= end {
            (start + lo, start + (hi - 1))
        } else {
            (start - lo, start - (hi - 1))
        };
        row["start"] = json!(a);
        row["end"] = json!(b);
        if row["source"].is_object() {
            row["source"]["start"] = json!(a.min(b));
            row["source"]["end"] = json!(a.max(b));
        }
    }
    if row.get("length").is_some() {
        row["length"] = json!(hi - lo);
    }
    Ok(row)
}
fn retain(rows: &mut Vec<Value>, g: &Geometry, lo: i64, hi: i64) -> Result<()> {
    if hi == lo {
        return Ok(());
    }
    let i = g.index(lo).context("invalid retained start")?;
    let j = g.index(hi - 1).context("invalid retained end")?;
    for k in i..=j {
        let a = g.offsets[k];
        let b = g.offsets[k + 1];
        rows.push(section(&g.rows[k], lo.max(a) - a, hi.min(b) - a, b - a)?);
    }
    Ok(())
}

pub(in crate::grt_package) fn adopt(
    conn: &Transaction<'_>,
    project: i64,
    versions: &BTreeMap<String, Version>,
) -> Result<usize> {
    if versions.is_empty() {
        return Ok(0);
    }
    // All subsequent writes, including this ledger, roll back together. A duplicate import
    // may hydrate previously missing FASTAs but must not replay a decision after an undo.
    let key = sha256_bytes(&serde_json::to_vec(versions)?);
    if conn.execute("INSERT INTO project_auto_gap_plan(project_id,plan_sha256) VALUES(?1,?2) ON CONFLICT DO NOTHING",params![project,key])?==0 {return Ok(0);}
    // A standalone, old single-tool project is already based on an independently admitted path.
    // Never splice original-LGZ coordinates into that assembly.
    let raw: String = conn.query_row(
        "SELECT final_path_json FROM grt_package WHERE id=1",
        [],
        |r| r.get(0),
    )?;
    if serde_json::from_str::<Value>(&raw)?["tool"].is_string() {
        return Ok(0);
    }
    let mut review = Review::new();
    let mut groups = BTreeMap::<String, BTreeMap<String, Vec<Candidate>>>::new();
    for tool in PRIORITY {
        if let Some(v) = versions.get(tool) {
            for c in gap_candidates::collect(conn, project, tool, v, &mut review)? {
                note(&mut review, &c, "path_changed_or_protected");
                groups
                    .entry(c.chr.clone())
                    .or_default()
                    .entry(c.gap.clone())
                    .or_default()
                    .push(c);
            }
        }
    }
    if groups.is_empty() {
        save_review(conn, project, review)?;
        return Ok(0);
    }
    let mut baselines = load_grt_final_path_for_project_with_connection(conn, project)?;
    let mut paths = load_project_paths(conn, project)?;
    let mut done = 0;
    let mut q = conn.prepare("SELECT gap_id FROM project_auto_gap_adoption WHERE project_id=?1")?;
    let prior = q
        .query_map([project], |r| r.get::<_, String>(0))?
        .collect::<rusqlite::Result<HashSet<_>>>()?;
    // A manual decision (including an explicit undo) owns its locus.
    let mut q=conn.prepare("SELECT json_extract(state_json,'$.locus.target') FROM project_refinement_adoption WHERE project_id=?1 AND json_extract(state_json,'$.locus.kind')='gap'")?;
    let protected = q
        .query_map([project], |r| r.get::<_, String>(0))?
        .collect::<rusqlite::Result<HashSet<_>>>()?;
    let phased =
        crate::phased_assembly::list_project_phased_chr_tracks_with_connection(conn, project)?
            .into_iter()
            .map(|t| t.parent_chr_name)
            .collect::<HashSet<_>>();
    for (chr, gaps) in groups {
        if phased.contains(&chr) {
            continue;
        }
        let Some(base) = baselines.remove(&chr) else {
            bail!("automatic version chromosome absent from LGZ baseline");
        };
        let original = canonicalize_entry(&chr, base)?;
        let base = Geometry::new(
            original["segments"]
                .as_array()
                .context("invalid LGZ path")?,
        )
        .context("invalid LGZ geometry")?;
        let mut entry = if let Some(saved) = paths.get(&chr) {
            if saved["mode"].as_str().is_some_and(|s| s != "segments") {
                continue;
            }
            let Ok(e) = canonicalize_entry(&chr, saved.clone()) else {
                continue;
            };
            e
        } else {
            original.clone()
        };
        let Some(now) = entry["segments"].as_array().and_then(|s| Geometry::new(s)) else {
            continue;
        };
        let mut edits = Vec::new();
        for (id, list) in gaps {
            let chr_sha = original["q4_sha256"]
                .as_str()
                .filter(|s| is_hash(s))
                .context("missing original chromosome digest")?;
            for c in &list {
                let bytes = q0_provenance::canonical(&(&chr, chr_sha, c.gap_start, c.gap_end))?;
                if c.gap != format!("gap-{}", &sha256_bytes(bytes.as_bytes())[..24]) {
                    bail!("automatic Gap does not belong to this LGZ chromosome");
                }
            }
            if prior.contains(&id) {
                for c in &list {
                    note(&mut review, c, "already_filled");
                }
                continue;
            }
            let mut chosen = None;
            for c in list {
                if let Some((a, b)) = bounds(&c, &base, &now, &protected) {
                    if chosen.is_none() {
                        chosen = Some((a, b, c));
                    } else {
                        note(&mut review, &c, "lower_priority");
                    }
                }
            }
            if let Some(selection) = chosen {
                edits.push(selection);
            }
        }
        edits.sort_by_key(|(a, b, _)| (*a, *b));
        // Keep BOTH sides of a conflict unchanged, rather than making coordinate order a fifth priority.
        let mut high = 0;
        let mut bad = vec![false; edits.len()];
        for i in 0..edits.len() {
            if i > 0 && edits[i].0 < high {
                bad[i] = true;
                bad[i - 1] = true;
            }
            high = high.max(edits[i].1);
        }
        let mut rows = Vec::new();
        let mut cursor = 0;
        let mut batch = Vec::new();
        for (i, (a, b, c)) in edits.into_iter().enumerate() {
            if bad[i] {
                note(&mut review, &c, "overlapping_edits");
                continue;
            }
            retain(&mut rows, &now, cursor, a)?;
            if let Some(r) = &c.replacement {
                rows.push(r.clone());
            }
            cursor = b;
            batch.push(c);
        }
        if batch.is_empty() {
            continue;
        }
        retain(&mut rows, &now, cursor, *now.offsets.last().unwrap())?;
        let mut ids = HashSet::new();
        if rows.is_empty() || rows.iter().any(|r| !ids.insert(r["segmentId"].as_str())) {
            continue;
        }
        for c in batch {
            note(&mut review, &c, "adopted");
            if let Some((ds, name, sha, len)) = &c.native_source {
                let alias = gap_sources::alias(ds, sha);
                if conn.query_row("SELECT EXISTS(SELECT 1 FROM project_dataset pd JOIN dataset d ON d.id=pd.dataset_id WHERE pd.project_id=?1 AND d.name=?2)",params![project,alias],|r|r.get::<_,bool>(0))?{bail!("automatic source collides with a real project dataset");}
                conn.execute("INSERT INTO project_auto_source(project_id,alias,contig,dataset,length,fasta_sha256) VALUES(?1,?2,?3,?4,?5,?6) ON CONFLICT DO NOTHING",params![project,alias,name,ds,len,sha])?;
                if gap_sources::lookup_auto_source(conn, project, &alias, name)?
                    != Some((ds.clone(), sha.clone(), *len))
                {
                    bail!("conflicting automatic source binding");
                }
            }
            let evidence = json!({"chr":chr,"gap":[c.gap_start,c.gap_end],"removed":[c.start,c.end],"replacement":c.replacement});
            conn.execute("INSERT INTO project_auto_gap_adoption(project_id,gap_id,tool,light_manifest,edit_id,evidence_json) VALUES(?1,?2,?3,?4,?5,?6)",params![project,c.gap,c.tool,c.manifest,c.edit,evidence.to_string()])?;
            done += 1;
        }
        for row in &mut rows {
            if let Some(o) = row.as_object_mut() {
                o.remove("output_start");
                o.remove("output_end");
            }
        }
        for key in [
            "q4_sha256",
            "q4_length",
            "length",
            "sha256",
            "coordinate_lift",
            "display_evidence",
        ] {
            entry
                .as_object_mut()
                .context("invalid editable chromosome")?
                .remove(key);
        }
        entry["segments"] = Value::Array(rows);
        update_length(&mut entry)?;
        paths.insert(chr, entry);
    }
    if done > 0 {
        write_project_paths(conn, project, &paths)?;
    }
    save_review(conn, project, review)?;
    Ok(done)
}
