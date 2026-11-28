//! A layout and its forward, full-length component records are planned together.
use super::*;
use std::io::BufWriter;
use tempfile::NamedTempFile;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Component {
    Source {
        id: i64,
        name: String,
        dataset: String,
    },
    Reference {
        id: i64,
        name: String,
        genome: String,
    },
    Auto {
        name: String,
        dataset: String,
        sha: String,
    },
    Patch(String),
}

// Reversible UTF-8 byte escaping; reserve __ as the field separator and :: for
// non-dataset namespaces. Names do not depend on which other paths are exported.
fn token(raw: &str) -> String {
    use std::fmt::Write as _;
    let bytes = raw.as_bytes();
    let mut out = String::new();
    for (i, &b) in bytes.iter().enumerate() {
        let safe_underscore = b == b'_'
            && i > 0
            && i + 1 < bytes.len()
            && bytes[i - 1] != b'_'
            && bytes[i + 1] != b'_';
        if b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-') || safe_underscore {
            out.push(char::from(b));
        } else {
            write!(out, ":{b:02X}").unwrap();
        }
    }
    out
}

impl Component {
    pub(super) fn id(&self, qualified: bool) -> String {
        match self {
            Self::Source { name, dataset, .. } if qualified => {
                format!("{}__{}", token(name), token(dataset))
            }
            Self::Reference { name, genome, .. } if qualified => {
                format!("{}__ref::{}", token(name), token(genome))
            }
            Self::Source { name, .. } | Self::Reference { name, .. } => name.clone(),
            Self::Auto { name, dataset, sha } if qualified => {
                format!("{}__auto::{}::{sha}", token(name), token(dataset))
            }
            Self::Auto { name, sha, .. } => format!("{name}@{sha}"),
            Self::Patch(sha) if qualified => format!("refine-{sha}__patch::sha256"),
            Self::Patch(sha) => format!("refine-{sha}"),
        }
    }
    pub(super) fn same_record(&self, other: &Self) -> bool {
        match (self, other) {
            // Two tool aliases may refer to exactly the same immutable FASTA record.
            (
                Self::Auto { sha, name, .. },
                Self::Auto {
                    sha: s, name: n, ..
                },
            ) => sha == s && name == n,
            _ => self == other,
        }
    }

    // The first word is the AGP key. Keep human-readable originals when a
    // field had to be escaped; JSON also prevents line breaks in a header.
    fn fasta_header(&self, id: &str) -> String {
        let (name, source) = match self {
            Self::Source { name, dataset, .. } | Self::Auto { name, dataset, .. } => {
                (name, dataset)
            }
            Self::Reference { name, genome, .. } => (name, genome),
            Self::Patch(_) => return id.into(),
        };
        if token(name) != *name || token(source) != *source {
            format!(
                "{id} origin={}",
                serde_json::json!({"id":name, "source":source})
            )
        } else {
            id.into()
        }
    }
}

// Both staged files are on the destination volume. Never replace an existing
// sibling implicitly; publish the AGP last, once its companion is complete.
pub fn export_final_path_agp_bundle(
    db: &Path,
    project: i64,
    params: &ExportProjectFinalPathFastaParams,
) -> Result<Vec<PathBuf>> {
    export_agp_files(db, project, params, true)
}

pub(super) fn export_agp_files(
    db: &Path,
    project: i64,
    params: &ExportProjectFinalPathFastaParams,
    with_components: bool,
) -> Result<Vec<PathBuf>> {
    let mut conn = open_workspace_db(db)?;
    let tx = conn.transaction()?;
    let (agp, components) = plan_final_path_agp(&tx, project, &params.records, with_components)?;
    let target = &params.output_path;
    let dir = target
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let companion = target.with_extension("components.fa");
    if target == &companion || target.try_exists()? || companion.try_exists()? {
        bail!(
            "AGP export destination already exists or overlaps its companion; choose a new name: {} / {}",
            target.display(),
            companion.display()
        );
    }
    fs::create_dir_all(dir)?;
    let mut layout = NamedTempFile::new_in(dir)?;
    layout.write_all(agp.as_bytes())?;
    if !with_components || components.is_empty() {
        // All-gap paths have no component records; do not fabricate an empty FASTA.
        tx.commit()?;
        layout.persist_noclobber(target)?;
        return Ok(vec![target.clone()]);
    }
    let mut fasta = NamedTempFile::new_in(dir)?;
    {
        let mut writer = BufWriter::new(fasta.as_file_mut());
        write_components(&tx, project, &components, &mut writer)?;
        writer.flush()?;
    }
    tx.commit()?;
    fasta.persist_noclobber(&companion)?;
    if let Err(e) = layout.persist_noclobber(target) {
        fs::remove_file(&companion).with_context(|| {
            format!(
                "AGP publish failed ({e}); could not remove {}",
                companion.display()
            )
        })?;
        return Err(e.into());
    }
    Ok(vec![target.clone(), companion])
}

type Records = BTreeMap<String, Vec<(String, i64)>>;
fn emit(out: &mut impl Write, targets: &[(String, i64)], sequence: &[u8]) -> Result<()> {
    if !sequence
        .iter()
        .all(|b| b"ACGTRYSWKMBDHVN".contains(&b.to_ascii_uppercase()))
    {
        bail!("invalid nucleotide in component {}", targets[0].0);
    }
    for (id, length) in targets {
        if sequence.len() as i64 != *length {
            bail!("component {id} length differs from project metadata");
        }
        writeln!(out, ">{id}")?;
        for line in sequence.chunks(FASTA_WRAP_WIDTH) {
            out.write_all(line)?;
            out.write_all(b"\n")?;
        }
    }
    Ok(())
}

fn write_components(
    conn: &Connection,
    project: i64,
    plan: &AgpComponentInventory,
    out: &mut impl Write,
) -> Result<()> {
    let mut disk: BTreeMap<PathBuf, Records> = BTreeMap::new();
    let mut automatic: BTreeMap<&str, Records> = BTreeMap::new();
    for (id, (component, length)) in plan {
        let record = (component.fasta_header(id), *length);
        match component {
            Component::Source {
                id: source, name, ..
            }
            | Component::Reference {
                id: source, name, ..
            } => {
                let sql = match component {
                    Component::Source { .. } => {
                        "SELECT fasta_path FROM source_seq_locator WHERE source_seq_id=?1"
                    }
                    _ => "SELECT fasta_path FROM reference_chr_locator WHERE reference_chr_id=?1",
                };
                let path: String = conn
                    .query_row(sql, [source], |r| r.get(0))
                    .with_context(|| format!("missing FASTA locator for {id}"))?;
                disk.entry(path.into())
                    .or_default()
                    .entry(name.clone())
                    .or_default()
                    .push(record);
            }
            Component::Auto { sha, name, .. } => automatic
                .entry(sha)
                .or_default()
                .entry(name.clone())
                .or_default()
                .push(record),
            Component::Patch(sha) => {
                let seq: Vec<u8> = conn.query_row("SELECT sequence FROM project_refinement_patch WHERE project_id=?1 AND sha256=?2", params![project,sha], |r| r.get(0))?;
                if format!("{:x}", Sha256::digest(&seq)) != *sha {
                    bail!("refinement patch content changed: {id}");
                }
                emit(out, &[record], &seq)?;
            }
        }
    }
    for (sha, records) in automatic {
        let object = crate::grt_package::load_auto_records(conn, sha)?;
        for (name, targets) in records {
            emit(
                out,
                &targets,
                object
                    .get(&name)
                    .context("missing automatic FASTA record")?
                    .as_bytes(),
            )?;
        }
    }
    for (path, records) in disk {
        write_disk_records(&path, records, out)
            .with_context(|| format!("reading components from {}", path.display()))?;
    }
    Ok(())
}

// Bound peak memory to one disk record. Read the index once per source file;
// absent/stale entries fall back to one sequential scan, not one scan per contig.
fn write_disk_records(path: &Path, mut records: Records, out: &mut impl Write) -> Result<()> {
    let mut file = File::open(path)?;
    let mut index_path = path.as_os_str().to_owned();
    index_path.push(".fai");
    if let Ok(text) = fs::read_to_string(index_path) {
        let index = parse_fai_index(&text);
        for name in records.keys().cloned().collect::<Vec<_>>() {
            if let Some(entry) = index.get(&name)
                && let Some(seq) = read_indexed_record(&mut file, path, &name, entry)?
            {
                emit(out, &records[&name], seq.as_bytes())?;
                records.remove(&name);
            }
        }
    }
    if records.is_empty() {
        return Ok(());
    }
    file.rewind()?;
    let mut active: Option<Vec<(String, i64)>> = None;
    let mut sequence = Vec::new();
    for line in BufReader::new(file).lines() {
        let line = line?;
        if let Some(header) = line.strip_prefix('>') {
            if let Some(targets) = active.take() {
                emit(out, &targets, &sequence)?;
                sequence.clear();
            }
            if records.is_empty() {
                break;
            }
            active = records.remove(header.split_whitespace().next().unwrap_or(""));
        } else if active.is_some() {
            sequence.extend_from_slice(line.trim().as_bytes());
        }
    }
    if let Some(targets) = active {
        emit(out, &targets, &sequence)?;
    }
    if let Some((name, _)) = records.first_key_value() {
        bail!("missing component record {name}");
    }
    Ok(())
}
