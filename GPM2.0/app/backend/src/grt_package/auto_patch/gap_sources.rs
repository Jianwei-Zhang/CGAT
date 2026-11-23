//! Working-path sources are scoped to one project and one immutable native FASTA, not a tool name.
use super::*;

pub(super) fn alias(dataset: &str, sha: &str) -> String {
    format!("@cgat.auto:{sha}:{dataset}")
}

pub(crate) fn lookup_auto_source(
    conn: &Connection,
    project: i64,
    ds: &str,
    name: &str,
) -> Result<Option<(String, String, i64)>> {
    if !ds.starts_with("@cgat.auto:") {
        return Ok(None);
    }
    let row: Option<(String,String,i64)>=conn.query_row("SELECT dataset,fasta_sha256,length FROM project_auto_source WHERE project_id=?1 AND alias=?2 AND contig=?3",params![project,ds,name],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).optional()?;
    if let Some((native, sha, len)) = &row {
        if !is_hash(sha) || *len <= 0 || alias(native, sha) != ds {
            bail!("incorrect automatic source binding");
        }
    }
    Ok(row)
}

// Light retains the same path and source identity without pretending to have sequences.
// A cumulative patch adds the missing object to this same store, never changing the path.
pub(crate) fn load_auto_records(conn: &Connection, sha: &str) -> Result<BTreeMap<String, String>> {
    if !is_hash(sha) {
        bail!("invalid automatic source object identity");
    }
    let id:i64=conn.query_row("SELECT rowid FROM project_auto_version_object WHERE sha256=?1",[sha],|r|r.get(0)).context("automatic sequence is unavailable; import the matching automatic patch or Full package")?;
    let blob = conn.blob_open(
        DatabaseName::Main,
        "project_auto_version_object",
        "content",
        id,
        true,
    )?;
    if blob.len() as u64 > MAX_OBJECT {
        bail!("oversize automatic source object");
    }
    let mut input = std::io::BufReader::new(blob);
    let mut digest = Sha256::new();
    std::io::copy(&mut input, &mut digest)?;
    if format!("{:x}", digest.finalize()) != sha {
        bail!("automatic source object changed");
    }
    use std::io::Seek;
    input.rewind()?;
    read_fasta_records(&mut input, "adopted automatic source", false, &mut || false)
}

/// Light and Full must make the same decisions. The per-source N table is in both
/// packages; tie it to the sourced path and, when present, to the actual FASTA records.
pub(super) struct GapRuns {
    ranges: HashMap<(String, String), Vec<(usize, usize)>>,
    native: HashMap<(String, String), String>,
}
impl GapRuns {
    pub(super) fn load(view: &Path, m: &Value) -> Result<Self> {
        let mut ranges = HashMap::<_, Vec<_>>::new();
        let mut native = HashMap::new();
        for s in m["sources"]
            .as_array()
            .context("missing automatic sources")?
        {
            if s["origin"] != "lgz" {
                native.insert(
                    (
                        s["fasta_sha256"]
                            .as_str()
                            .context("missing accepted FASTA")?
                            .into(),
                        s["contig"]
                            .as_str()
                            .context("missing accepted contig")?
                            .into(),
                    ),
                    s["dataset"]
                        .as_str()
                        .context("missing accepted dataset")?
                        .into(),
                );
            }
        }
        for row in read_tsv(
            view,
            "metadata/source_seq_n_regions.tsv",
            SOURCE_N_REGIONS_HEADER,
            0,
            None,
        )?
        .rows
        {
            let lo = field(&row, "start_bp")?.parse::<usize>()?;
            let hi = field(&row, "end_bp")?.parse::<usize>()?;
            if lo == 0 || hi < lo || hi - lo + 1 != field(&row, "length_bp")?.parse::<usize>()? {
                bail!("invalid N range in automatic source");
            }
            ranges
                .entry((
                    field(&row, "dataset_name")?.to_owned(),
                    field(&row, "seq_name")?.to_owned(),
                ))
                .or_default()
                .push((lo, hi));
        }
        for list in ranges.values_mut() {
            list.sort_unstable();
            if list.windows(2).any(|p| p[0].1 >= p[1].0) {
                bail!("overlapping automatic source N ranges");
            }
        }
        let path = json_at(&view.join("metadata/refinement/final_path.json"))?;
        for chr in path["chromosomes"]
            .as_array()
            .context("missing automatic chromosomes")?
        {
            for r in chr["segments"]
                .as_array()
                .context("missing automatic segments")?
            {
                if !r["refinement_edit_id"].is_string() {
                    continue;
                }
                let gap = r["kind"] == "gap";
                let src = &r[if gap { "refinement_source" } else { "source" }];
                let ds = src["dataset"]
                    .as_str()
                    .context("missing replacement dataset")?;
                let name = src["contig"]
                    .as_str()
                    .context("missing replacement contig")?;
                let a = usize::try_from(
                    src["start"]
                        .as_u64()
                        .context("missing replacement interval")?,
                )?;
                let b = usize::try_from(
                    src["end"]
                        .as_u64()
                        .context("missing replacement interval")?,
                )?;
                let list = ranges
                    .get(&(ds.to_owned(), name.to_owned()))
                    .map(Vec::as_slice)
                    .unwrap_or_default();
                let run = list.get(list.partition_point(|&(_, end)| end < a));
                if (gap && !run.is_some_and(|&(x, y)| x <= a && b <= y))
                    || (!gap && run.is_some_and(|&(x, _)| x <= b))
                {
                    bail!("replacement segment disagrees with its N evidence");
                }
            }
        }
        Ok(Self { ranges, native })
    }
    pub(super) fn verify(&self, sha: &str, name: &str, seq: &str) -> Result<()> {
        let ds = self
            .native
            .get(&(sha.to_owned(), name.to_owned()))
            .context("unbound automatic sequence")?;
        let ranges = self
            .ranges
            .get(&(ds.clone(), name.to_owned()))
            .map(Vec::as_slice)
            .unwrap_or_default();
        let mut next = ranges.iter();
        let mut start = None;
        for (i, b) in seq.bytes().chain(std::iter::once(b'.')).enumerate() {
            if b == b'N' {
                start.get_or_insert(i + 1);
            } else if let Some(lo) = start.take() {
                if next.next() != Some(&(lo, i)) {
                    bail!("actual automatic sequence differs from N evidence");
                }
            }
        }
        if next.next().is_some() {
            bail!("automatic source N evidence exceeds sequence");
        }
        Ok(())
    }
}
