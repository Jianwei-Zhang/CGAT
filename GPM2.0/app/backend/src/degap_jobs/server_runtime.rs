use super::*;

pub(super) fn runtime_shell(server: &str) -> String {
    format!(
        r#"CGAT_RUNTIME="$(python3 -B - {server} <<'PY'
from pathlib import Path
import json
import sys
root = Path(sys.argv[1])
if not root.is_absolute():
    raise SystemExit("GPM Server root must be an absolute Server path")
root = root.resolve()
marker = root / ".runtime/workspace.json"
if marker.is_symlink() or marker.parent.is_symlink():
    raise SystemExit("Invalid Server workspace marker")
area = ".prepare_lib"
if marker.exists():
    declaration = json.loads(marker.read_text(encoding="utf-8"))
    area = ".lib" if declaration.get("prepared_runtime") == ".lib" else ".runtime/prepared"
tools = root / area / "tools"
if tools.is_symlink() or tools.parent.is_symlink():
    raise SystemExit("Server runtime must not traverse a symlink")
for name in ("workspace_layout.py", "degap_results.py", "server_source_identity.py"):
    if not (tools / name).is_file():
        raise SystemExit("Matching Server runtime is missing: " + str(tools / name) + "; update tools/runtime without re-preparing the workspace")
sys.path.insert(0, str(tools))
from workspace_layout import WorkspaceLayout
layout = WorkspaceLayout.detect(root)
if layout.path(".prepare_lib/tools") != tools:
    raise SystemExit("Server runtime does not match the declared workspace layout")
print(tools)
PY
)"
CGAT_RESULT_TOOL="$CGAT_RUNTIME/degap_results.py"
CGAT_SOURCE_TOOL="$CGAT_RUNTIME/server_source_identity.py"
CGAT_DEGAP_TOOL="$CGAT_RUNTIME/degap.py"
"#,
        server = shell_quote(server)
    )
}

// Per-operation index. A whole-project task can address thousands of members in the
// same immutable import; never rescan or deserialize the entire map per segment.
#[derive(Default)]
pub(super) struct SourceMaps {
    maps: std::collections::HashMap<
        PathBuf,
        std::collections::HashMap<(String, String), Option<(i64, String)>>,
    >,
}

impl SourceMaps {
    pub(super) fn bind(
        &mut self,
        workspace: &Path,
        fasta: &Path,
        dataset: &str,
        contig: &str,
        length: i64,
    ) -> Result<Option<String>> {
        for parent in fasta
            .ancestors()
            .skip(1)
            .take_while(|p| p.starts_with(workspace))
        {
            let path = parent.join("metadata/server_sources.json");
            if !path.try_exists()? {
                continue;
            }
            if !self.maps.contains_key(&path) {
                let value: Value = serde_json::from_slice(&fs::read(&path)?)?;
                if value["schema"] != "cgat.server-source-identities"
                    || value["schema_version"] != 1
                {
                    bail!("unsupported Server source identities: {}", path.display());
                }
                let mut index = std::collections::HashMap::new();
                for row in value["sources"]
                    .as_array()
                    .context("missing Server source identities")?
                {
                    let (Some(ds), Some(name)) = (row["dataset"].as_str(), row["contig"].as_str())
                    else {
                        continue;
                    };
                    let binding = row["length"]
                        .as_i64()
                        .zip(row["fasta_sha256"].as_str().map(str::to_owned));
                    index
                        .entry((ds.to_owned(), name.to_owned()))
                        .and_modify(|old| *old = None)
                        .or_insert(binding);
                }
                self.maps.insert(path.clone(), index);
            }
            let Some(binding) = self.maps[&path].get(&(dataset.into(), contig.into())) else {
                return Ok(None);
            };
            let (size, sha) = binding
                .as_ref()
                .context("ambiguous or malformed Server source binding")?;
            if *size != length
                || sha.len() != 64
                || !sha
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                bail!("stale or invalid Server source identity for {dataset}:{contig}");
            }
            return Ok(Some(sha.clone()));
        }
        Ok(None)
    }
}

#[cfg(test)]
pub(super) fn bind_member(
    workspace: &Path,
    fasta: &Path,
    dataset: &str,
    contig: &str,
    length: i64,
) -> Result<Option<String>> {
    SourceMaps::default().bind(workspace, fasta, dataset, contig, length)
}

pub(super) fn seed_plan(
    segment: &DegapJobSeedSegment,
    members: &[SeedMemberPlan],
) -> Result<Value> {
    let low = segment.start.min(segment.end);
    let high = segment.start.max(segment.end);
    if low <= 0 {
        bail!("invalid seed interval");
    }
    let mut offset = 0;
    let mut selected = Vec::new();
    for member in members {
        let size = member.source_end - member.source_start + 1;
        let start = low.max(offset + 1);
        let end = high.min(offset + size);
        if start <= end {
            let a = member.source_start + start - offset - 1;
            let b = member.source_start + end - offset - 1;
            let interval_hash = if member.local_fasta_path.is_file() {
                let sequence = crate::exporter::load_fasta_source_interval(
                    &member.local_fasta_path,
                    &member.source_seq_name,
                    a,
                    b,
                )?;
                Some(format!("{:x}", Sha256::digest(sequence.as_bytes())))
            } else {
                None
            };
            selected.push(json!({"dataset": member.dataset_name, "name": member.source_seq_name,
                                "length": member.source_length, "start": a, "end": b,
                                "fasta_sha256": member.server_fasta_sha256, "interval_sha256": interval_hash}));
        }
        offset += size;
    }
    if high > offset || selected.is_empty() {
        bail!("seed interval exceeds its real source members");
    }
    let size = high - low + 1;
    Ok(
        json!({"members": selected, "start": if segment.start <= segment.end {1} else {size},
              "end": if segment.start <= segment.end {size} else {1}}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn light_source_map_binds_without_local_fasta_and_incremental_sources_can_use_intervals()
    -> Result<()> {
        let root = tempdir()?;
        fs::create_dir(root.path().join("metadata"))?;
        fs::write(
            root.path().join("metadata/server_sources.json"),
            serde_json::to_vec(&json!({
                "schema": "cgat.server-source-identities", "schema_version": 1,
                "sources": [{"dataset": "ds", "contig": "u", "length": 15, "fasta_sha256": "a".repeat(64)}]
            }))?,
        )?;
        let fasta = root.path().join("data/source.fa");
        assert_eq!(
            bind_member(root.path(), &fasta, "ds", "u", 15)?,
            Some("a".repeat(64))
        );
        assert!(bind_member(root.path(), &fasta, "ds", "u", 14).is_err());
        assert_eq!(
            bind_member(root.path(), &fasta, "derived_ctg", "new", 10)?,
            None
        );
        Ok(())
    }

    #[test]
    fn clipped_reverse_plan_reads_only_the_consumed_original_source_interval() -> Result<()> {
        let root = tempdir()?;
        let fasta = root.path().join("source.fa");
        fs::write(&fasta, ">u desc\nRYSW\nKMBD\nHVNA\nCGT\n")?;
        fs::write(root.path().join("source.fa.fai"), "u\t15\t8\t4\t5\n")?;
        let members = vec![SeedMemberPlan {
            dataset_name: "ds".into(),
            source_seq_name: "u".into(),
            source_length: 15,
            source_start: 2,
            source_end: 13,
            server_fasta_path: "/portable/hint.fa".into(),
            server_fasta_sha256: Some("b".repeat(64)),
            local_fasta_path: fasta.clone(),
        }];
        let plan = seed_plan(
            &DegapJobSeedSegment {
                assembly_ctg_id: 1,
                start: 8,
                end: 5,
            },
            &members,
        )?;
        assert_eq!(plan["start"], 4);
        assert_eq!(plan["end"], 1);
        assert_eq!(plan["members"][0]["start"], 6);
        assert_eq!(plan["members"][0]["end"], 9);
        assert_eq!(
            plan["members"][0]["interval_sha256"],
            format!("{:x}", Sha256::digest(b"MBDH"))
        );
        fs::write(root.path().join("source.fa.fai"), "u\t15\t0\t4\t5\n")?;
        assert_eq!(
            crate::exporter::load_fasta_source_interval(&fasta, "u", 6, 9)?,
            "MBDH"
        );
        Ok(())
    }
}
