//! Extract independently usable closed Gap edits from the admitted Server paths and receipts.
//! A per-tool closure count is NOT authorization to splice an entire tool assembly.
use super::working_version::{admitted, bound_json};
use super::*;
use serde_json::json;

pub(super) const PRIORITY: [&str; 4] = ["degap", "lrgapcloser", "tgsgapcloser", "quartet"];
#[derive(Clone)]
pub(super) struct Candidate {
    pub tool: String,
    pub manifest: String,
    pub gap: String,
    pub chr: String,
    pub edit: String,
    pub start: i64,
    pub end: i64,
    pub gap_start: i64,
    pub gap_end: i64,
    pub replacement: Option<Value>,
    pub native_source: Option<(String, String, String, i64)>,
}
fn text<'a>(o: &'a Value, k: &str) -> Result<&'a str> {
    o[k].as_str()
        .filter(|v| !v.is_empty())
        .with_context(|| format!("missing automatic {k}"))
}
fn arr<'a>(o: &'a Value, k: &str) -> Result<&'a Vec<Value>> {
    o[k].as_array()
        .with_context(|| format!("missing automatic {k}"))
}
fn number(o: &Value, k: &str) -> Result<i64> {
    o[k].as_i64()
        .filter(|v| *v >= 0)
        .with_context(|| format!("invalid automatic {k}"))
}
fn unique<'a>(rows: &'a [Value], key: &str) -> Result<HashMap<&'a str, &'a Value>> {
    let mut out = HashMap::new();
    for r in rows {
        if out.insert(text(r, key)?, r).is_some() {
            bail!("duplicate automatic {key}");
        }
    }
    Ok(out)
}
pub(super) fn collect(
    conn: &Connection,
    project: i64,
    tool: &str,
    v: &Version,
    review: &mut super::gap_adoption::Review,
) -> Result<Vec<Candidate>> {
    let (_, m) = admitted(conn, project, tool, &v.light_manifest)?;
    let get = |name: &str, field: &str| -> Result<Value> {
        let h = text(&m["files"], name)?;
        if m[field] != h {
            bail!("automatic evidence binding differs from inventory");
        }
        bound_json(conn, h, MAX_OBJECT)
    };
    let path = get(
        "metadata/refinement/final_path.json",
        "server_final_path_sha256",
    )?;
    let proof = get("metadata/refinement/provenance.json", "provenance_sha256")?;
    if path["tool"] != tool
        || path["baseline"] != m["baseline"]
        || proof["run_id"] != v.run_id
        || proof["tool"] != tool
        || proof["baseline"] != m["baseline"]
    {
        bail!("different automatic origins in admitted evidence");
    }
    let originals = unique(arr(&path, "original_gaps")?, "gap_id")?;
    let edits = unique(arr(&path, "edits")?, "edit_id")?;
    let mut segments = HashMap::new();
    let mut lifts = HashMap::new();
    for c in arr(&path, "chromosomes")? {
        let mut previous = (0, 0);
        for lift in arr(c, "coordinate_lift")? {
            let a = number(lift, "baseline_start")?;
            let b = number(lift, "baseline_end")?;
            let x = number(lift, "output_start")?;
            let y = number(lift, "output_end")?;
            if (a, x) != previous || b <= a || y < x {
                bail!("discontinuous automatic coordinate lift");
            }
            match lift["kind"].as_str() {
                Some("retained") if b - a == y - x => (),
                Some("replacement") => {
                    if lifts
                        .insert(text(lift, "edit_id")?, (text(c, "chr")?, a, b, x, y))
                        .is_some()
                    {
                        bail!("duplicate automatic lift");
                    }
                }
                _ => bail!("invalid automatic coordinate lift"),
            }
            previous = (b, y);
        }
        if c["length"] != previous.1 {
            bail!("automatic coordinate lift does not cover its chromosome");
        }
        for s in arr(c, "segments")? {
            if segments
                .insert(text(s, "segment_id")?, (text(c, "chr")?, s))
                .is_some()
            {
                bail!("ambiguous automatic segment");
            }
        }
    }
    let mut sources = HashMap::new();
    for row in arr(&m, "sources")? {
        if sources
            .insert((text(row, "dataset")?, text(row, "contig")?), row)
            .is_some()
        {
            bail!("ambiguous automatic source");
        }
    }
    let mut result = Vec::new();
    for row in arr(&proof, "gap_outcomes")? {
        if row["status"] != "closed" {
            continue;
        }
        let gid = text(row, "gap_id")?;
        let chr = text(row, "chromosome")?;
        review.insert(
            (tool.to_owned(), v.light_manifest.clone(), gid.to_owned()),
            (chr.to_owned(), "joint_or_unmapped"),
        );
        let original = originals.get(gid).context("unknown closed gap")?;
        let (gs, ge) = (number(row, "start")?, number(row, "end")?);
        if gs >= ge
            || original["chromosome"] != chr
            || original["start"] != gs
            || original["end"] != ge
        {
            bail!("inconsistent original Gap interval");
        }
        // Joint edits belong to the tool result, not to any one Gap in this project.
        let [id] = arr(row, "edit_ids")?.as_slice() else {
            continue;
        };
        let eid = id.as_str().context("invalid edit id")?;
        let e = edits.get(eid).context("closed Gap lacks admitted edit")?;
        if e["gap_ids"] != json!([gid]) || e["chromosome"] != chr || e["tool"] != tool {
            continue;
        }
        let (a, b) = (number(e, "start")?, number(e, "end")?);
        if a > gs || b < ge {
            continue;
        }
        let out_start = number(e, "output_start")?;
        let out_end = number(e, "output_end")?;
        if lifts.get(eid) != Some(&(chr, a, b, out_start, out_end)) {
            bail!("automatic selection differs from its admitted coordinate lift");
        }
        let ids = arr(e, "replacement_segment_ids")?;
        let (replacement, native_source) = if e["replacement"].is_null() {
            if !ids.is_empty() || out_start != out_end {
                bail!("invalid zero-length bridge");
            }
            (None, None)
        } else {
            let [id] = ids.as_slice() else { continue };
            let sid = id.as_str().context("invalid bridge id")?;
            let (out_chr, s) = segments
                .get(sid)
                .context("missing admitted bridge segment")?;
            let src = &e["replacement"];
            if *out_chr != chr
                || s["kind"] != "patch"
                || s["source"] != *src
                || s["refinement_edit_id"] != eid
                || s["original_gap_ids"] != e["gap_ids"]
                || s["output_start"] != out_start
                || s["output_end"] != out_end
            {
                bail!("automatic bridge differs from admitted edit");
            }
            let (ds, name) = (text(src, "dataset")?, text(src, "contig")?);
            let desc = sources.get(&(ds, name)).context("unknown bridge source")?;
            let sha = text(desc, "fasta_sha256")?;
            let len = number(desc, "length")?;
            let (lo, hi) = (number(src, "start")?, number(src, "end")?);
            if !is_hash(sha)
                || lo < 1
                || hi < lo
                || hi > len
                || s["length"] != hi - lo + 1
                || out_end - out_start != hi - lo + 1
                || !matches!(src["orientation"].as_str(), Some("+" | "-"))
            {
                bail!("invalid automatic source slice");
            }
            let (ds_alias, origin) = if desc["origin"] == format!("refinement:{tool}")
                && v.accepted_sequence_objects.iter().any(|h| h == sha)
            {
                (
                    gap_sources::alias(ds, sha),
                    Some((ds.into(), name.into(), sha.into(), len)),
                )
            } else if desc["origin"] == "lgz" {
                (ds.to_owned(), None)
            } else {
                bail!("foreign automatic source");
            };
            let (start, end) = if src["orientation"] == "-" {
                (hi, lo)
            } else {
                (lo, hi)
            };
            (
                Some(
                    json!({"type":"ctg","serverBaseline":true,"segmentId":sid,"ctgName":name,"originId":name,"overallLen":len,"start":start,"end":end,"datasetName":ds,"grtKind":"patch","source":{"dataset":ds_alias,"contig":name,"start":lo,"end":hi,"orientation":src["orientation"]},"refinement":{"mode":"automatic","tool":tool,"batchSha256":v.light_manifest,"editId":eid,"originalGapIds":[gid],"source":src}}),
                ),
                origin,
            )
        };
        result.push(Candidate {
            tool: tool.into(),
            manifest: v.light_manifest.clone(),
            gap: gid.into(),
            chr: chr.into(),
            edit: eid.into(),
            start: a,
            end: b,
            gap_start: gs,
            gap_end: ge,
            replacement,
            native_source,
        });
    }
    Ok(result)
}
