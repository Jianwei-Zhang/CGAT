//! Private Server path hints from an already validated refinement delivery.
//!
//! These describe the inputs the user supplied, not the files a particular
//! engine consumed. Never resolve them on the desktop or use them as proof that
//! a read file is available or unchanged on the execution host.
use super::*;

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RefinementReadInputs {
    pub hifi: Vec<RefinementReadSource>,
    pub ont: Vec<RefinementReadSource>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RefinementReadSource {
    pub path: String,
    pub sha256: Option<String>,
}

impl RefinementReadInputs {
    pub(super) fn from_recipe(recipe: &Value) -> Self {
        let fingerprints: HashMap<_, _> = recipe["reads"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|row| {
                let kind = row["technology"].as_str()?;
                let path = row["path"].as_str()?;
                let sha = row["sha256"].as_str().filter(|sha| {
                    sha.len() == 64
                        && sha
                            .bytes()
                            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
                });
                Some(((kind, path), sha))
            })
            .collect();
        let groups = |kind: &str| {
            let selection = &recipe["original_selection"];
            let original = ["selected", "unused"]
                .into_iter()
                .filter_map(|role| selection[role][kind].as_array());
            let paths = if selection.is_object() {
                original
                    .flatten()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
            } else {
                // DEGAP records original inputs directly, including inputs that
                // were not needed because the baseline has no remaining gaps.
                recipe["reads"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter(|row| row["technology"].as_str() == Some(kind))
                    .filter_map(|row| row["path"].as_str())
                    .collect()
            };
            let mut seen = HashSet::new();
            paths
                .into_iter()
                // Validate POSIX paths without calling Path::is_absolute on
                // the local platform (in particular a Windows App).
                .filter(|p| p.starts_with('/') && p.len() > 1 && !p.chars().any(char::is_control))
                .filter(|p| seen.insert(*p))
                .map(|p| RefinementReadSource {
                    path: p.into(),
                    sha256: fingerprints
                        .get(&(kind, p))
                        .copied()
                        .flatten()
                        .map(str::to_owned),
                })
                .collect::<Vec<_>>()
        };
        let mut hifi = groups("hifi");
        let mut ont = groups("ont");
        // Do not suggest a technology for ambiguous entries. Other usable
        // hints still survive even if optional metadata is incomplete.
        let ambiguous = hifi
            .iter()
            .filter(|h| ont.iter().any(|o| o.path == h.path))
            .map(|h| h.path.clone())
            .collect::<HashSet<_>>();
        hifi.retain(|row| !ambiguous.contains(&row.path));
        ont.retain(|row| !ambiguous.contains(&row.path));
        Self { hifi, ont }
    }

    pub(super) fn is_empty(&self) -> bool {
        self.hifi.is_empty() && self.ont.is_empty()
    }
}

/// Snapshot the validated package defaults into a newly initialized project.
/// Other projects in the same workspace must not inherit them by accident.
pub(super) fn bind_imported_inputs(conn: &Connection, project_id: i64) -> Result<()> {
    conn.execute(
        "INSERT INTO project_refinement_inputs (project_id, reads_json)
         SELECT ?1, reads_json FROM grt_refinement_inputs WHERE package_id=1",
        [project_id],
    )
    .context("failed to bind imported refinement read sources to project")?;
    Ok(())
}

/// Load origin hints only for the specified project. They are not desktop
/// paths or global settings, and absence is normal for projects without them.
pub fn load_project_refinement_read_inputs(
    project_db_path: &Path,
    project_id: i64,
) -> Result<RefinementReadInputs> {
    let conn = open_workspace_db(project_db_path)?;
    let value: Option<String> = conn
        .query_row(
            "SELECT reads_json FROM project_refinement_inputs WHERE project_id=?1",
            [project_id],
            |r| r.get(0),
        )
        .optional()?;
    match value {
        Some(value) => {
            serde_json::from_str(&value).context("invalid refinement read source storage")
        }
        None => Ok(RefinementReadInputs::default()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn uses_original_inputs_including_unused_instead_of_native_conversions() {
        let verified = "a".repeat(64);
        let reads = RefinementReadInputs::from_recipe(&json!({
            "original_selection": {
                "selected": {"hifi": ["/server/hifi.fastq.gz"], "ont": []},
                "unused": {"hifi": [], "ont": ["/server/ont.fastq.gz"]},
            },
            "conversions": {"hifi": {"fasta": "/tmp/converted.fa"}},
            "reads": [
                {"technology": "hifi", "path": "/server/hifi.fastq.gz", "sha256": verified},
                {"technology": "hifi", "path": "/tmp/converted.fa", "sha256": "b".repeat(64)},
            ],
        }));
        assert_eq!(
            reads,
            RefinementReadInputs {
                hifi: vec![RefinementReadSource {
                    path: "/server/hifi.fastq.gz".into(),
                    sha256: Some("a".repeat(64))
                }],
                ont: vec![RefinementReadSource {
                    path: "/server/ont.fastq.gz".into(),
                    sha256: None
                }],
            }
        );
    }

    #[test]
    fn supports_degap_without_selection_and_ignores_unusable_hints() {
        assert!(RefinementReadInputs::from_recipe(&Value::Null).is_empty());
        let reads = RefinementReadInputs::from_recipe(&json!({"reads": [
            {"technology": "hifi", "path": "/reads/both.fq"},
            {"technology": "ont", "path": "/reads/both.fq"},
            {"technology": "ont", "path": "/reads/unused.fq", "not_consumed": true},
            {"technology": "ont", "path": "/reads/unused.fq"},
            {"technology": "hifi", "path": "relative/reads.fq"},
            {"technology": "hifi", "path": "/bad\nline"},
            {"technology": "other", "path": "/reads/unknown.fq"},
        ]}));
        assert!(reads.hifi.is_empty());
        assert_eq!(
            reads.ont,
            vec![RefinementReadSource {
                path: "/reads/unused.fq".into(),
                sha256: None
            }]
        );
    }
}
