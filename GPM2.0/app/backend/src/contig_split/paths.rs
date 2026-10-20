//! Re-express adopted intervals as immutable source locators. Never move DNA between paths.
use super::SplitSource;
use anyhow::{Context, Result, bail};
use rusqlite::{Connection, OptionalExtension};
use serde_json::{Value, json};

fn matches(segment: &Value, source: &SplitSource) -> bool {
    if segment.get("type").and_then(Value::as_str) == Some("gap") {
        return false;
    }
    let overlaps = segment
        .get("start")
        .and_then(Value::as_i64)
        .zip(segment.get("end").and_then(Value::as_i64))
        .is_some_and(|(a, b)| a.min(b) <= source.source_end && a.max(b) >= source.source_start);
    segment.get("assemblyCtgId").and_then(Value::as_i64) == Some(source.assembly_ctg_id)
        || (overlaps
            && segment.pointer("/source/dataset").and_then(Value::as_str)
                == Some(&source.dataset_name)
            && segment.pointer("/source/contig").and_then(Value::as_str)
                == Some(&source.contig_name))
}

pub(crate) fn count_path_references(
    conn: &Connection,
    project_id: i64,
    source: &SplitSource,
) -> Result<usize> {
    let text: Option<String> = conn
        .query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [project_id],
            |r| r.get(0),
        )
        .optional()?;
    let paths: Value = serde_json::from_str(text.as_deref().unwrap_or("{}"))?;
    Ok(paths
        .as_object()
        .into_iter()
        .flat_map(|o| o.values())
        .filter_map(|p| p.get("segments").and_then(Value::as_array))
        .flatten()
        .filter(|s| matches(s, source))
        .count())
}

pub(crate) fn rewrite_final_paths(
    paths: &mut Value,
    source: &SplitSource,
    cuts: &[i64],
    children: &[(i64, i64, i64)],
) -> Result<()> {
    let entries = paths
        .as_object_mut()
        .context("CTG_SPLIT_INVALID_PATH: paths must be an object")?;
    for entry in entries.values_mut() {
        let Some(segments) = entry.get_mut("segments").and_then(Value::as_array_mut) else {
            continue;
        };
        let mut rebuilt = Vec::new();
        for segment in segments.iter() {
            if !matches(segment, source) {
                rebuilt.push(segment.clone());
                continue;
            }
            let mut start = segment
                .get("start")
                .and_then(Value::as_i64)
                .context("CTG_SPLIT_INVALID_PATH: missing start")?;
            let mut end = segment
                .get("end")
                .and_then(Value::as_i64)
                .context("CTG_SPLIT_INVALID_PATH: missing end")?;
            let has_source = segment.pointer("/source/dataset").and_then(Value::as_str)
                == Some(&source.dataset_name)
                && segment.pointer("/source/contig").and_then(Value::as_str)
                    == Some(&source.contig_name);
            if !has_source {
                // Assembly Final Path coordinates are relative to the un-oriented source interval.
                if start < 1
                    || end < 1
                    || start > source.source_end - source.source_start + 1
                    || end > source.source_end - source.source_start + 1
                {
                    bail!("CTG_SPLIT_INVALID_PATH: adopted contig interval is out of bounds");
                }
                start += source.source_start - 1;
                end += source.source_start - 1;
            }
            if start < 1 || end < 1 || start > source.source_length || end > source.source_length {
                bail!("CTG_SPLIT_INVALID_PATH: source interval is out of bounds");
            }
            let reverse = start > end;
            let low = start.min(end);
            let high = start.max(end);
            let mut cursor = low;
            let mut intervals = Vec::new();
            for cut in cuts
                .iter()
                .copied()
                .filter(|k| *k >= low && *k < high)
                .chain([high])
            {
                intervals.push((cursor, cut));
                cursor = cut + 1;
            }
            if reverse {
                intervals.reverse();
            }
            for (index, (a, b)) in intervals.into_iter().enumerate() {
                let mut part = segment.clone();
                let child = children
                    .iter()
                    .find(|(_, x, y)| a >= *x && b <= *y)
                    .map(|r| r.0);
                let id = segment
                    .get("segmentId")
                    .and_then(Value::as_str)
                    .unwrap_or("source");
                part["segmentId"] = json!(format!(
                    "{id}:split:{}:{index}:{a}-{b}",
                    source.assembly_ctg_id
                ));
                part["assemblyCtgId"] = Value::Null;
                if let Some(child) = child {
                    part["splitFragmentCtgId"] = json!(child);
                } else if let Some(object) = part.as_object_mut() {
                    object.remove("splitFragmentCtgId");
                }
                part["splitFromAssemblyCtgId"] = json!(source.assembly_ctg_id);
                part["ctgName"] = json!(source.contig_name);
                part["originId"] = json!(source.contig_name);
                part["datasetName"] = json!(source.dataset_name);
                part["overallLen"] = json!(source.source_length);
                part["start"] = json!(if reverse { b } else { a });
                part["end"] = json!(if reverse { a } else { b });
                part["source"] = json!({"dataset":source.dataset_name,"contig":source.contig_name,"start":a,"end":b,"orientation":if reverse {"-"} else {"+"}});
                rebuilt.push(part);
            }
        }
        *segments = rebuilt;
    }
    Ok(())
}
