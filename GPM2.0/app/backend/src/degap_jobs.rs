use std::collections::HashSet;
use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

use crate::db::open_workspace_db;

mod manual_refinement;
mod server_runtime;
pub(crate) use manual_refinement::{load_project_paths, write_project_paths, canonicalize_entry, update_length, witness};

pub use manual_refinement::{
    ManualExportSummary, ManualRefinementAction, ManualRefinementExportReceipt, ManualRefinementImport, ManualRefinementRequest,
    PatchOperation, ResultPatch, ResultRow, ResultStatus, ValidatedRefinementResults,
    export_manual_refinement, import_manual_refinement_results, list_manual_refinement_exports, list_manual_refinement_results,
    switch_manual_refinement_locus, undo_manual_refinement_locus,
    validate_manual_refinement_results,
};

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct DegapJobExportSettings {
    pub degap_path: String,
    pub hifi_reads: Vec<String>,
    pub ont_reads: Vec<String>,
    pub gpm_server_path: String,
    pub out_root: String,
    pub thread: i64,
    pub kmer_filter: bool,
    pub kmer_size: i64,
    pub kmer_num: i64,
    pub maximum_extension_round: Option<i64>,
    pub maximum_extension_length: Option<i64>,
    pub filter_depth_hifi: Option<f64>,
    pub filter_depth_ont: Option<f64>,
    pub remove: i64,
    pub edge: i64,
    pub motif: String,
    pub work: i64,
    pub tel_n: i64,
    pub tel_r: f64,
    pub tel_mm: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DegapJobSeedSegment {
    pub assembly_ctg_id: i64,
    pub start: i64,
    pub end: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DegapJobExportItem {
    pub job_type: String,
    pub job_id: String,
    pub chr_name: String,
    pub left_ctg: String,
    pub right_ctg: String,
    pub flag: String,
    pub out_path: String,
    pub left: Option<DegapJobSeedSegment>,
    pub right: Option<DegapJobSeedSegment>,
    pub endpoint_ctg: String,
    pub endpoint_end: String,
    pub endpoint: Option<DegapJobSeedSegment>,
    pub settings: Option<DegapJobExportSettings>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExportDegapJobsParams {
    pub output_dir: PathBuf,
    pub settings: DegapJobExportSettings,
    pub jobs: Vec<DegapJobExportItem>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DegapJobScriptSummary {
    pub job_id: String,
    pub script_path: PathBuf,
    pub out_path: String,
    pub seqleft_path: String,
    pub seqright_path: String,
    pub ctg_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportDegapJobsSummary {
    pub output_dir: PathBuf,
    pub manifest_path: PathBuf,
    pub prepare_script_path: PathBuf,
    pub scripts: Vec<DegapJobScriptSummary>,
}

const DEGAP_JOBS_MANIFEST_HEADER: &str = "job_id\tchr_name\tjob_type\tleft_ctg\tright_ctg\tflag\tendpoint_ctg\tendpoint_end\tscript_path\tout_path\tseqleft_path\tseqright_path\tctg_path\tprepare_script_path";

#[derive(Debug, Clone, PartialEq, Eq)]
struct DegapJobManifestRow {
    chr_name: String,
    script_path: String,
    line: String,
}

pub fn parse_degap_export_settings(value: &Value) -> Result<DegapJobExportSettings> {
    let object = value
        .as_object()
        .ok_or_else(|| anyhow!("settings must be an object"))?;
    Ok(DegapJobExportSettings {
        degap_path: string_from_object(object, "degapPath"),
        hifi_reads: string_list_from_object(object, "hifiReads"),
        ont_reads: string_list_from_object(object, "ontReads"),
        gpm_server_path: string_from_object(object, "gpmServerPath"),
        out_root: string_from_object(object, "outRoot"),
        thread: optional_i64_from_object(object, "thread")?.unwrap_or(20),
        kmer_filter: bool_from_object(object, "kmerFilter", true),
        kmer_size: optional_i64_from_object(object, "kmerSize")?.unwrap_or(41),
        kmer_num: optional_i64_from_object(object, "kmerNum")?.unwrap_or(20),
        maximum_extension_round: optional_i64_from_object(object, "maximumExtensionRound")?,
        maximum_extension_length: optional_i64_from_object(object, "maximumExtensionLength")?,
        filter_depth_hifi: optional_f64_from_object(object, "filterDepthHifi")?,
        filter_depth_ont: optional_f64_from_object(object, "filterDepthOnt")?,
        remove: optional_i64_from_object(object, "remove")?.unwrap_or(2),
        edge: optional_i64_from_object(object, "edge")?.unwrap_or(500),
        motif: {
            let motif = string_from_object(object, "motif");
            if motif.is_empty() {
                "TTAGGG".to_string()
            } else {
                motif
            }
        },
        work: optional_i64_from_object(object, "work")?.unwrap_or(1),
        tel_n: optional_i64_from_object(object, "telN")?.unwrap_or(100),
        tel_r: optional_f64_from_object(object, "telR")?.unwrap_or(0.6),
        tel_mm: optional_i64_from_object(object, "telMm")?.unwrap_or(0),
    })
}

pub fn parse_degap_export_jobs(value: &Value) -> Result<Vec<DegapJobExportItem>> {
    let jobs = value
        .as_array()
        .ok_or_else(|| anyhow!("jobs must be an array"))?;
    jobs.iter()
        .enumerate()
        .map(|(index, job)| {
            let object = job
                .as_object()
                .ok_or_else(|| anyhow!("jobs[{index}] must be an object"))?;
            Ok(DegapJobExportItem {
                job_type: {
                    let job_type = string_from_object(object, "jobType");
                    if job_type.is_empty() {
                        "gapfiller".to_string()
                    } else {
                        job_type
                    }
                },
                job_id: string_from_object(object, "jobId"),
                chr_name: string_from_object(object, "chrName"),
                left_ctg: string_from_object(object, "leftCtg"),
                right_ctg: string_from_object(object, "rightCtg"),
                flag: string_from_object(object, "flag"),
                out_path: string_from_object(object, "outPath"),
                left: match object.get("left") {
                    Some(value) if value.is_object() => {
                        Some(parse_degap_seed_segment(value, "left")?)
                    }
                    _ => None,
                },
                right: match object.get("right") {
                    Some(value) if value.is_object() => {
                        Some(parse_degap_seed_segment(value, "right")?)
                    }
                    _ => None,
                },
                endpoint_ctg: string_from_object(object, "endpointCtg"),
                endpoint_end: string_from_object(object, "endpointEnd"),
                endpoint: match object.get("endpoint") {
                    Some(value) if value.is_object() => {
                        Some(parse_degap_seed_segment(value, "endpoint")?)
                    }
                    _ => None,
                },
                settings: match object.get("settings") {
                    Some(value) if value.is_object() => Some(parse_degap_export_settings(value)?),
                    _ => None,
                },
            })
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SeedMemberPlan {
    dataset_name: String,
    source_length: i64,
    local_fasta_path: PathBuf,
    server_fasta_sha256: Option<String>,
    source_seq_name: String,
    server_fasta_path: String,
    source_start: i64,
    source_end: i64,
}

fn parse_degap_seed_segment(value: &Value, label: &str) -> Result<DegapJobSeedSegment> {
    let object = value
        .as_object()
        .ok_or_else(|| anyhow!("{label} seed must be an object"))?;
    Ok(DegapJobSeedSegment {
        assembly_ctg_id: object
            .get("assemblyCtgId")
            .ok_or_else(|| anyhow!("{label} seed missing assemblyCtgId"))
            .and_then(|value| value_to_i64(value, "assemblyCtgId"))?,
        start: object
            .get("start")
            .ok_or_else(|| anyhow!("{label} seed missing start"))
            .and_then(|value| value_to_i64(value, "start"))?,
        end: object
            .get("end")
            .ok_or_else(|| anyhow!("{label} seed missing end"))
            .and_then(|value| value_to_i64(value, "end"))?,
    })
}

fn optional_i64_from_object(object: &Map<String, Value>, key: &str) -> Result<Option<i64>> {
    let Some(value) = object.get(key) else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(None);
    }
    if let Some(text) = value.as_str()
        && is_optional_number_unset_text(text)
    {
        return Ok(None);
    }
    value_to_i64(value, key).map(Some)
}

fn optional_f64_from_object(object: &Map<String, Value>, key: &str) -> Result<Option<f64>> {
    let Some(value) = object.get(key) else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(None);
    }
    if let Some(number) = value.as_f64() {
        return Ok(Some(number));
    }
    if let Some(text) = value.as_str() {
        let trimmed = text.trim();
        if is_optional_number_unset_text(trimmed) {
            return Ok(None);
        }
        return trimmed
            .parse::<f64>()
            .map(Some)
            .with_context(|| format!("{key} is not a valid number"));
    }
    bail!("{key} is not a valid number");
}

fn is_optional_number_unset_text(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "" | "null" | "undefined" | "none" | "nan"
    )
}

fn value_to_i64(value: &Value, key: &str) -> Result<i64> {
    if let Some(number) = value.as_i64() {
        return Ok(number);
    }
    if let Some(text) = value.as_str() {
        return text
            .trim()
            .parse::<i64>()
            .with_context(|| format!("{key} is not a valid integer"));
    }
    bail!("{key} is not a valid integer");
}

fn string_list_from_object(object: &Map<String, Value>, key: &str) -> Vec<String> {
    match object.get(key) {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToString::to_string)
            .collect(),
        Some(Value::String(value)) => value
            .split(['\n', ',', ';'])
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToString::to_string)
            .collect(),
        _ => Vec::new(),
    }
}

fn string_from_object(object: &Map<String, Value>, key: &str) -> String {
    object
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string()
}

fn bool_from_object(object: &Map<String, Value>, key: &str, fallback: bool) -> bool {
    object.get(key).and_then(Value::as_bool).unwrap_or(fallback)
}

pub fn export_degap_jobs(
    project_db_path: &Path,
    workspace_root: &Path,
    project_id: i64,
    params: &ExportDegapJobsParams,
) -> Result<ExportDegapJobsSummary> {
    let conn = open_workspace_db(project_db_path)?;
    export_degap_jobs_with_connection(&conn, workspace_root, project_id, params)
}

fn export_degap_jobs_with_connection(
    conn: &Connection,
    workspace_root: &Path,
    project_id: i64,
    params: &ExportDegapJobsParams,
) -> Result<ExportDegapJobsSummary> {
    validate_project_exists(conn, project_id)?;
    validate_settings(&params.settings)?;
    if params.jobs.is_empty() {
        bail!("at least one DEGAP job is required");
    }
    fs::create_dir_all(&params.output_dir)
        .with_context(|| format!("failed to create {}", params.output_dir.display()))?;
    let scripts_dir = params.output_dir.join("degap_jobs");
    fs::create_dir_all(&scripts_dir)
        .with_context(|| format!("failed to create {}", scripts_dir.display()))?;
    let manifest_path = params.output_dir.join("jobs.tsv");
    let exported_chr_names: HashSet<String> = params
        .jobs
        .iter()
        .map(|job| job.chr_name.trim().to_string())
        .filter(|chr_name| !chr_name.is_empty())
        .collect();
    let existing_manifest_rows = read_existing_manifest_rows(&manifest_path)?;
    let mut stale_current_chr_script_paths = Vec::<String>::new();
    let mut manifest_rows = vec![DEGAP_JOBS_MANIFEST_HEADER.to_string()];
    for row in existing_manifest_rows {
        if exported_chr_names.contains(&row.chr_name) {
            stale_current_chr_script_paths.push(row.script_path);
        } else {
            manifest_rows.push(row.line);
        }
    }

    let prepare_script_path = params.output_dir.join("prepare_degap_shared.sh");
    fs::write(
        &prepare_script_path,
        build_shared_prepare_script(&params.settings),
    )
    .with_context(|| format!("failed to write {}", prepare_script_path.display()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&prepare_script_path)?.permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&prepare_script_path, permissions).with_context(|| {
            format!(
                "failed to mark {} executable",
                prepare_script_path.display()
            )
        })?;
    }

    let mut scripts = Vec::<DegapJobScriptSummary>::new();
    let mut current_script_paths = HashSet::<String>::new();
    for job in &params.jobs {
        let effective_settings = job.settings.as_ref().unwrap_or(&params.settings);
        validate_settings(effective_settings)?;
        validate_job(job, effective_settings)?;
        let safe_job_id = build_unique_script_file_stem(job, &current_script_paths);
        let script_path = scripts_dir.join(format!("{safe_job_id}.sh"));
        let script_manifest_path = format!("degap_jobs/{safe_job_id}.sh");
        current_script_paths.insert(script_manifest_path.clone());
        let job_type = normalize_job_type(&job.job_type);
        let mut seqleft_path = String::new();
        let mut seqright_path = String::new();
        let mut ctg_path = String::new();
        let (script, seed_plans) = if job_type == "telseeker_ctg" {
            let endpoint = job
                .endpoint
                .as_ref()
                .context("validated telseeker_ctg job missing endpoint")?;
            let endpoint_plan = load_seed_plan(
                conn,
                workspace_root,
                project_id,
                &effective_settings.gpm_server_path,
                endpoint,
            )
            .with_context(|| format!("failed to plan endpoint contig for {}", job.job_id))?;
            ctg_path = join_server_path(&job.out_path, "endpoint.ctg.fa");
            (
                build_telseeker_ctg_job_script(
                    job,
                    effective_settings,
                    &params.settings,
                    &endpoint_plan,
                    &ctg_path,
                ),
                json!({"endpoint": server_runtime::seed_plan(endpoint, &endpoint_plan)?}),
            )
        } else {
            let left = job
                .left
                .as_ref()
                .context("validated gapfiller job missing left seed")?;
            let right = job
                .right
                .as_ref()
                .context("validated gapfiller job missing right seed")?;
            let left_plan = load_seed_plan(
                conn,
                workspace_root,
                project_id,
                &effective_settings.gpm_server_path,
                left,
            )
            .with_context(|| format!("failed to plan left seed for {}", job.job_id))?;
            let right_plan = load_seed_plan(
                conn,
                workspace_root,
                project_id,
                &effective_settings.gpm_server_path,
                right,
            )
            .with_context(|| format!("failed to plan right seed for {}", job.job_id))?;
            seqleft_path = join_server_path(&job.out_path, "seqleft.fa");
            seqright_path = join_server_path(&job.out_path, "seqright.fa");
            (
                build_gapfiller_job_script(
                    job,
                    effective_settings,
                    &params.settings,
                    &left_plan,
                    &right_plan,
                    &seqleft_path,
                    &seqright_path,
                ),
                json!({"seqleft": server_runtime::seed_plan(left, &left_plan)?,
                      "seqright": server_runtime::seed_plan(right, &right_plan)?}),
            )
        };
        let receipt = build_degap_receipt(
            conn,
            workspace_root,
            project_id,
            job,
            effective_settings,
            seed_plans,
        )?;
        let receipt_path = scripts_dir.join(format!("{safe_job_id}.json"));
        let receipt_bytes = serde_json::to_vec_pretty(&receipt)?;
        fs::write(&receipt_path, &receipt_bytes)?;
        let receipt_dir = workspace_root.join("metadata/degap_exports");
        fs::create_dir_all(&receipt_dir)?;
        fs::write(
            receipt_dir.join(format!("{}.json", receipt["token"].as_str().unwrap())),
            &receipt_bytes,
        )?;
        let receipt_name = shell_quote(&format!("{safe_job_id}.json"));
        let begin = format!(
            "{}\nCGAT_RECIPE=\"$(cd -- \"$(dirname -- \"${{BASH_SOURCE[0]}}\")\" && pwd)/\"{}\npython3 -B \"$CGAT_RESULT_TOOL\" begin --recipe \"$CGAT_RECIPE\"\n",
            server_runtime::runtime_shell(&effective_settings.gpm_server_path),
            receipt_name
        );
        let script = script.replacen(
            "set -euo pipefail\n",
            &format!("set -euo pipefail\n{begin}"),
            1,
        );
        let seed = "python3 -B \"$CGAT_RESULT_TOOL\" seed --recipe \"$CGAT_RECIPE\"";
        let script = script.replacen(
            "# Step 3: run DEGAP",
            &format!("{seed}\n# Step 3: run DEGAP"),
            1,
        );
        let script = format!(
            "{script}\n# Record this run only after DEGAP exits successfully.\npython3 -B \"$CGAT_RESULT_TOOL\" record --recipe \"$CGAT_RECIPE\"\n"
        );
        fs::write(&script_path, script)
            .with_context(|| format!("failed to write {}", script_path.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(&script_path)?.permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(&script_path, permissions)
                .with_context(|| format!("failed to mark {} executable", script_path.display()))?;
        }
        manifest_rows.push(
            [
                job.job_id.as_str(),
                job.chr_name.as_str(),
                job_type.as_str(),
                job.left_ctg.as_str(),
                job.right_ctg.as_str(),
                job.flag.as_str(),
                job.endpoint_ctg.as_str(),
                job.endpoint_end.as_str(),
                script_manifest_path.as_str(),
                job.out_path.as_str(),
                seqleft_path.as_str(),
                seqright_path.as_str(),
                ctg_path.as_str(),
                "prepare_degap_shared.sh",
            ]
            .iter()
            .map(|value| value.replace(['\t', '\n', '\r'], " "))
            .collect::<Vec<_>>()
            .join("\t"),
        );
        scripts.push(DegapJobScriptSummary {
            job_id: job.job_id.clone(),
            script_path,
            out_path: job.out_path.clone(),
            seqleft_path,
            seqright_path,
            ctg_path,
        });
    }
    remove_stale_manifest_scripts(
        &params.output_dir,
        stale_current_chr_script_paths,
        &current_script_paths,
    )?;

    fs::write(&manifest_path, format!("{}\n", manifest_rows.join("\n")))
        .with_context(|| format!("failed to write {}", manifest_path.display()))?;

    for (name, action) in [
        ("run_degap_jobs.sh", "run"),
        ("collect_degap_results.sh", "collect"),
    ] {
        fs::write(
            params.output_dir.join(name),
            format!(
                "#!/usr/bin/env bash\nset -euo pipefail\n{}\nROOT=\"$(cd -- \"$(dirname -- \"${{BASH_SOURCE[0]}}\")\" && pwd)\"\nexec python3 -B \"$CGAT_RESULT_TOOL\" {action} --jobs \"$ROOT/jobs.tsv\"\n",
                server_runtime::runtime_shell(&params.settings.gpm_server_path)
            ),
        )?;
    }

    Ok(ExportDegapJobsSummary {
        output_dir: params.output_dir.clone(),
        manifest_path,
        prepare_script_path,
        scripts,
    })
}

fn read_existing_manifest_rows(manifest_path: &Path) -> Result<Vec<DegapJobManifestRow>> {
    if !manifest_path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(manifest_path)
        .with_context(|| format!("failed to read {}", manifest_path.display()))?;
    let mut lines = content.lines();
    let Some(header) = lines.next() else {
        return Ok(Vec::new());
    };
    let columns = header.split('\t').collect::<Vec<_>>();
    let Some(chr_name_index) = columns.iter().position(|column| *column == "chr_name") else {
        return Ok(Vec::new());
    };
    let Some(script_path_index) = columns.iter().position(|column| *column == "script_path") else {
        return Ok(Vec::new());
    };
    let mut rows = Vec::<DegapJobManifestRow>::new();
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let values = line.split('\t').collect::<Vec<_>>();
        let chr_name = values.get(chr_name_index).copied().unwrap_or("").trim();
        let script_path = values.get(script_path_index).copied().unwrap_or("").trim();
        if chr_name.is_empty() {
            continue;
        }
        rows.push(DegapJobManifestRow {
            chr_name: chr_name.to_string(),
            script_path: script_path.to_string(),
            line: line.to_string(),
        });
    }
    Ok(rows)
}

fn is_safe_manifest_relative_path(value: &str) -> bool {
    let path = Path::new(value);
    !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_) | Component::CurDir))
}

fn remove_stale_manifest_scripts(
    output_dir: &Path,
    stale_script_paths: Vec<String>,
    current_script_paths: &HashSet<String>,
) -> Result<()> {
    for script_path in stale_script_paths {
        if script_path.is_empty()
            || current_script_paths.contains(&script_path)
            || !is_safe_manifest_relative_path(&script_path)
        {
            continue;
        }
        let full_path = output_dir.join(&script_path);
        match fs::remove_file(&full_path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(error).with_context(|| {
                    format!(
                        "failed to remove stale DEGAP job script {}",
                        full_path.display()
                    )
                });
            }
        }
    }
    Ok(())
}

fn validate_project_exists(conn: &Connection, project_id: i64) -> Result<()> {
    if project_id <= 0 {
        bail!("project_id must be > 0");
    }
    let exists: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM project WHERE id = ?1",
            params![project_id],
            |row| row.get(0),
        )
        .context("failed to validate project")?;
    if exists == 0 {
        bail!("project_id {} does not exist", project_id);
    }
    Ok(())
}

fn validate_settings(settings: &DegapJobExportSettings) -> Result<()> {
    if settings.gpm_server_path.trim().is_empty() {
        bail!("GPM_server PATH is required");
    }
    if settings.out_root.trim().is_empty() {
        bail!("Main DEGAP --out is required");
    }
    if settings.hifi_reads.is_empty() && settings.ont_reads.is_empty() {
        bail!("at least one of HiFi Reads PATH or ONT Reads PATH is required");
    }
    if settings.thread <= 0 {
        bail!("thread must be > 0");
    }
    if settings.kmer_size <= 0 {
        bail!("kmer_size must be > 0");
    }
    if settings.kmer_num <= 0 {
        bail!("kmer_num must be > 0");
    }
    if settings.remove <= 0 {
        bail!("remove must be > 0");
    }
    if settings.edge <= 0 {
        bail!("edge must be > 0");
    }
    if settings.motif.trim().is_empty()
        || !settings
            .motif
            .chars()
            .all(|ch| matches!(ch, 'A' | 'C' | 'G' | 'T'))
    {
        bail!("motif must contain uppercase A/C/G/T letters");
    }
    if settings.work <= 0 {
        bail!("work must be > 0");
    }
    if settings.tel_n <= 0 {
        bail!("tel_n must be > 0");
    }
    if settings.tel_r <= 0.0 || settings.tel_r > 1.0 {
        bail!("tel_r must be in the interval (0, 1]");
    }
    if settings.tel_mm != 0 && settings.tel_mm != 1 {
        bail!("tel_mm must be 0 or 1");
    }
    Ok(())
}

fn normalize_job_type(value: &str) -> String {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "telseeker_ctg" => "telseeker_ctg".to_string(),
        _ => "gapfiller".to_string(),
    }
}

fn validate_seed_segment(job_id: &str, label: &str, segment: &DegapJobSeedSegment) -> Result<()> {
    if segment.assembly_ctg_id <= 0 {
        bail!("job {} {} assembly_ctg_id must be > 0", job_id, label);
    }
    if segment.start <= 0 || segment.end <= 0 {
        bail!("job {} {} range must be positive", job_id, label);
    }
    Ok(())
}

fn validate_job(job: &DegapJobExportItem, settings: &DegapJobExportSettings) -> Result<()> {
    if normalize_job_type(&job.job_type) == "gapfiller"
        && settings.degap_path.trim().is_empty()
        && settings.maximum_extension_round == Some(0)
    {
        bail!(
            "Bundled GapFiller requires MaximumExtensionRound >= 1, or leave it unset; zero-round TelSeeker is supported"
        );
    }
    if job.job_id.trim().is_empty() {
        bail!("job_id is required");
    }
    if job.chr_name.trim().is_empty() {
        bail!("job {} chr_name is required", job.job_id);
    }
    if job.out_path.trim().is_empty() {
        bail!("job {} out_path is required", job.job_id);
    }
    if normalize_job_type(&job.job_type) == "telseeker_ctg" {
        if settings.filter_depth_hifi.is_some() || settings.filter_depth_ont.is_some() {
            bail!(
                "job {} telseeker_ctg does not support depth filtering",
                job.job_id
            );
        }
        if job.endpoint_ctg.trim().is_empty() {
            bail!("job {} endpoint_ctg is required", job.job_id);
        }
        match job.endpoint_end.trim() {
            "L" | "R" => {}
            _ => bail!("job {} endpoint_end must be L or R", job.job_id),
        }
        validate_seed_segment(
            &job.job_id,
            "endpoint",
            job.endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("job {} endpoint is required", job.job_id))?,
        )?;
        return Ok(());
    }
    match job.flag.trim() {
        "left" | "right" => {}
        _ => bail!("job {} flag must be left or right", job.job_id),
    }
    validate_seed_segment(
        &job.job_id,
        "left",
        job.left
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("job {} left seed is required", job.job_id))?,
    )?;
    validate_seed_segment(
        &job.job_id,
        "right",
        job.right
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("job {} right seed is required", job.job_id))?,
    )?;
    Ok(())
}

fn load_seed_plan(
    conn: &Connection,
    workspace_root: &Path,
    project_id: i64,
    gpm_server_path: &str,
    segment: &DegapJobSeedSegment,
) -> Result<Vec<SeedMemberPlan>> {
    load_seed_plan_with_maps(conn, workspace_root, project_id, gpm_server_path, segment, &mut server_runtime::SourceMaps::default())
}

fn load_seed_plan_with_maps(
    conn: &Connection,
    workspace_root: &Path,
    project_id: i64,
    gpm_server_path: &str,
    segment: &DegapJobSeedSegment,
    maps: &mut server_runtime::SourceMaps,
) -> Result<Vec<SeedMemberPlan>> {
    let mut stmt = conn.prepare(
        "SELECT ss.seq_name, s.source_start, s.source_end, s.hidden, ssl.fasta_path, d.name, ss.length
         FROM assembly_ctg c
         JOIN assembly_seq s ON s.id = c.assembly_seq_id
         JOIN source_seq ss ON ss.id = s.source_seq_id
         JOIN dataset d ON d.id = ss.dataset_id
         LEFT JOIN source_seq_locator ssl ON ssl.source_seq_id = ss.id
         WHERE c.project_id = ?1
           AND c.id = ?2
         ORDER BY c.id",
    )?;
    let rows = stmt
        .query_map(params![project_id, segment.assembly_ctg_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)? > 0,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, i64>(6)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if rows.is_empty() {
        bail!("assembly_ctg_id {} not found", segment.assembly_ctg_id);
    }
    let mut plans = Vec::<SeedMemberPlan>::new();
    for (
        source_seq_name,
        source_start,
        source_end,
        hidden,
        local_fasta_path,
        dataset_name,
        source_length,
    ) in rows
    {
        if hidden {
            continue;
        }
        let local_fasta_path = local_fasta_path.ok_or_else(|| {
            anyhow::anyhow!(
                "missing source sequence locator for assembly_ctg_id {}",
                segment.assembly_ctg_id
            )
        })?;
        let relpath = server_relative_locator_path(workspace_root, Path::new(&local_fasta_path))?;
        let server_fasta_sha256 = maps.bind(
            workspace_root,
            Path::new(&local_fasta_path),
            &dataset_name,
            &source_seq_name,
            source_length,
        )?;
        plans.push(SeedMemberPlan {
            dataset_name,
            source_length,
            local_fasta_path: PathBuf::from(local_fasta_path),
            server_fasta_sha256,
            source_seq_name,
            source_start,
            source_end,
            server_fasta_path: join_server_path(gpm_server_path, &relpath),
        });
    }
    if plans.is_empty() {
        bail!(
            "assembly_ctg_id {} has no visible sequence members",
            segment.assembly_ctg_id
        );
    }
    Ok(plans)
}

fn server_relative_locator_path(workspace_root: &Path, local_fasta_path: &Path) -> Result<String> {
    let rel = local_fasta_path
        .strip_prefix(workspace_root)
        .with_context(|| {
            format!(
                "source locator {} is not under workspace root {}",
                local_fasta_path.display(),
                workspace_root.display()
            )
        })?;
    Ok(rel.to_string_lossy().replace('\\', "/"))
}

fn join_server_path(root: &str, rel: &str) -> String {
    let normalized_root = root.trim().trim_end_matches('/');
    let normalized_rel = rel.trim().trim_start_matches('/');
    if normalized_root.is_empty() {
        return normalized_rel.to_string();
    }
    if normalized_rel.is_empty() {
        return normalized_root.to_string();
    }
    format!("{normalized_root}/{normalized_rel}")
}

fn sanitize_job_id(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    let trimmed = sanitized.trim_matches('_');
    if trimmed.is_empty() {
        "degap_job".to_string()
    } else {
        trimmed.to_string()
    }
}

fn sanitize_job_part(value: &str, fallback: &str) -> String {
    if value.trim().is_empty() {
        sanitize_job_id(fallback)
    } else {
        sanitize_job_id(value)
    }
}

fn build_script_file_stem(job: &DegapJobExportItem) -> String {
    let chr_name = sanitize_job_part(&job.chr_name, "chr");
    let job_type = normalize_job_type(&job.job_type);
    if job_type == "telseeker_ctg" {
        let side = if job.endpoint_end.trim().eq_ignore_ascii_case("R") {
            "right"
        } else {
            "left"
        };
        return format!(
            "{}_telseeker_ctg_{}_{}",
            chr_name,
            side,
            sanitize_job_part(&job.endpoint_ctg, &job.job_id)
        );
    }
    let side = if job.flag.trim().eq_ignore_ascii_case("right") {
        "right"
    } else {
        "left"
    };
    format!(
        "{}_gapfiller_{}_{}_to_{}",
        chr_name,
        side,
        sanitize_job_part(&job.left_ctg, "left_ctg"),
        sanitize_job_part(&job.right_ctg, "right_ctg")
    )
}

fn build_unique_script_file_stem(
    job: &DegapJobExportItem,
    current_script_paths: &HashSet<String>,
) -> String {
    let base_stem = build_script_file_stem(job);
    let base_path = format!("degap_jobs/{base_stem}.sh");
    if !current_script_paths.contains(&base_path) {
        return base_stem;
    }
    let job_stem = format!("{}_{}", base_stem, sanitize_job_id(&job.job_id));
    let job_path = format!("degap_jobs/{job_stem}.sh");
    if !current_script_paths.contains(&job_path) {
        return job_stem;
    }
    let mut suffix = 2;
    loop {
        let candidate = format!("{job_stem}_{suffix}");
        let candidate_path = format!("degap_jobs/{candidate}.sh");
        if !current_script_paths.contains(&candidate_path) {
            return candidate;
        }
        suffix += 1;
    }
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn shell_array(values: &[String]) -> String {
    values
        .iter()
        .map(|value| shell_quote(value))
        .collect::<Vec<_>>()
        .join(" ")
}

fn python_string(value: &str) -> String {
    format!("{:?}", value)
}

fn python_string_list(values: &[String]) -> String {
    format!(
        "[{}]",
        values
            .iter()
            .map(|value| python_string(value))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn shared_prepare_out(settings: &DegapJobExportSettings) -> String {
    join_server_path(&settings.out_root, "shared_prepare")
}

fn can_use_shared_reads(
    settings: &DegapJobExportSettings,
    shared_settings: &DegapJobExportSettings,
) -> bool {
    settings.hifi_reads == shared_settings.hifi_reads
        && settings.ont_reads == shared_settings.ont_reads
        && settings.degap_path == shared_settings.degap_path
        && settings.gpm_server_path == shared_settings.gpm_server_path
}

fn family_shared_layout(settings: &DegapJobExportSettings) -> &'static str {
    if settings.degap_path.trim().is_empty() {
        r#"if [ -f "$CGAT_RUNTIME/degap_core/bin/PreparedReads.py" ]; then
  CGAT_FAMILY_SHARED=1
  SHARED_OUT="$SHARED_OUT.family-v1"
fi"#
    } else {
        ""
    }
}

fn build_shared_prepare_script(settings: &DegapJobExportSettings) -> String {
    let shared_out = shared_prepare_out(settings);
    let hifi_count = settings.hifi_reads.len();
    let ont_count = settings.ont_reads.len();
    let runtime = if settings.degap_path.trim().is_empty() {
        server_runtime::runtime_shell(&settings.gpm_server_path)
    } else {
        String::new()
    };
    format!(
        r#"#!/usr/bin/env bash
set -euo pipefail

# DEGAP shared prepare script.
# Run this once before running any exported degap_jobs/*.sh script.
# Output: {shared_out}

SHARED_OUT={quoted_shared_out}
HIFI_READS=({hifi_reads})
ONT_READS=({ont_reads})
{runtime}
CGAT_FAMILY_SHARED=0
{family_layout}
mkdir -p "$SHARED_OUT/processed_reads"

python3 - "$SHARED_OUT" <<'PY'
from pathlib import Path
import json
import sys

shared_out = Path(sys.argv[1])
manifest = shared_out / "cache_manifest.json"
requested = {{
    "hifi": {hifi_reads_py},
    "ont": {ont_reads_py},
    "schema": "gpm_next.degap.shared_prepare.v1",
}}
if manifest.exists():
    existing = json.loads(manifest.read_text(encoding="utf-8"))
    for key in ("hifi", "ont", "schema"):
        if existing.get(key) != requested.get(key):
            print(f"[error] shared_prepare cache mismatch for {{key}}", file=sys.stderr)
            print(f"        existing: {{existing.get(key)}}", file=sys.stderr)
            print(f"        requested: {{requested.get(key)}}", file=sys.stderr)
            sys.exit(1)
else:
    manifest.write_text(json.dumps(requested, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

prepare_reads() {{
  local label="$1"
  local fasta="$2"
  shift 2
  local reads=("$@")
  if [ "${{#reads[@]}}" -eq 0 ]; then
    return 0
  fi
  if [ ! -s "$fasta" ]; then
    echo "[prepare] $label reads -> $fasta"
    seqkit fq2fa -o "$fasta" "${{reads[@]}}"
  else
    echo "[skip] existing $label FASTA: $fasta"
  fi
}}

prepare_index() {{
  local label="$1"
  local fasta="$2"
  local index="$3"
  if [ ! -s "$fasta" ]; then
    return 0
  fi
  if [ ! -s "$index" ]; then
    echo "[prepare] $label index -> $index"
    python3 - "$index" "$fasta" <<'PY'
import sys
from Bio import SeqIO
SeqIO.index_db(sys.argv[1], sys.argv[2], "fasta")
PY
  else
    echo "[skip] existing $label index: $index"
  fi
}}

prepare_split() {{
  local label="$1"
  local fasta="$2"
  local part_dir="$3"
  if [ ! -s "$fasta" ]; then
    return 0
  fi
  mkdir -p "$part_dir"
  if [ -n "$(find "$part_dir" -maxdepth 1 -type f -name '*.fa*' -print -quit)" ]; then
    echo "[skip] existing $label split dir: $part_dir"
  else
    echo "[prepare] $label split -> $part_dir"
    seqkit split "$fasta" -O "$part_dir" --force --by-size 100000 --two-pass -w 0
  fi
}}

if [ "$CGAT_FAMILY_SHARED" -eq 1 ]; then
  read_args=()
  if [ {hifi_count} -gt 0 ]; then read_args+=(--hifi "${{HIFI_READS[@]}}"); fi
  if [ {ont_count} -gt 0 ]; then read_args+=(--ont "${{ONT_READS[@]}}"); fi
  python3 -B "$CGAT_DEGAP_TOOL" prepare-shared-reads --out "$SHARED_OUT" "${{read_args[@]}}"
fi

if [ {hifi_count} -gt 0 ]; then
  if [ "$CGAT_FAMILY_SHARED" -eq 0 ]; then
    prepare_reads "HiFi" "$SHARED_OUT/processed_reads/hifi_reads.fa" "${{HIFI_READS[@]}}"
  fi
  prepare_index "HiFi" "$SHARED_OUT/processed_reads/hifi_reads.fa" "$SHARED_OUT/hifi_reads.idx"
  prepare_split "HiFi" "$SHARED_OUT/processed_reads/hifi_reads.fa" "$SHARED_OUT/hifi_reads_part"
fi

if [ {ont_count} -gt 0 ]; then
  if [ "$CGAT_FAMILY_SHARED" -eq 0 ]; then
    prepare_reads "ONT" "$SHARED_OUT/processed_reads/ont_reads.fa" "${{ONT_READS[@]}}"
  fi
  prepare_index "ONT" "$SHARED_OUT/processed_reads/ont_reads.fa" "$SHARED_OUT/ont_reads.idx"
  prepare_split "ONT" "$SHARED_OUT/processed_reads/ont_reads.fa" "$SHARED_OUT/ont_reads_part"
fi

echo "[done] DEGAP shared prepare outputs are ready in $SHARED_OUT"
"#,
        shared_out = shared_out,
        quoted_shared_out = shell_quote(&shared_out),
        hifi_reads = shell_array(&settings.hifi_reads),
        ont_reads = shell_array(&settings.ont_reads),
        hifi_count = hifi_count,
        ont_count = ont_count,
        runtime = runtime,
        family_layout = family_shared_layout(settings),
        hifi_reads_py = python_string_list(&settings.hifi_reads),
        ont_reads_py = python_string_list(&settings.ont_reads),
    )
}

fn build_shared_link_block(
    out_path: &str,
    settings: &DegapJobExportSettings,
    shared_settings: &DegapJobExportSettings,
    include_index_and_split: bool,
) -> String {
    if !can_use_shared_reads(settings, shared_settings) {
        return r#"echo "[shared] per-job reads or runtime differ from global settings; this job will build its own read cache"
"#
        .to_string();
    }
    let mut artifacts = vec!["processed_reads".to_string()];
    if include_index_and_split {
        if !settings.hifi_reads.is_empty() {
            artifacts.push("hifi_reads.idx".to_string());
            artifacts.push("hifi_reads_part".to_string());
        }
        if !settings.ont_reads.is_empty() {
            artifacts.push("ont_reads.idx".to_string());
            artifacts.push("ont_reads_part".to_string());
        }
    }
    let artifact_lines = artifacts
        .iter()
        .map(|artifact| format!("link_shared_artifact {}", shell_quote(artifact)))
        .collect::<Vec<_>>()
        .join("\n");
    let shared_out = shared_prepare_out(shared_settings);
    format!(
        r#"SHARED_OUT={quoted_shared_out}
JOB_OUT={quoted_out}
CGAT_FAMILY_SHARED=0
{family_layout}

if [ ! -d "$SHARED_OUT" ]; then
  echo "[error] Missing DEGAP shared prepare output: $SHARED_OUT" >&2
  echo "        Run prepare_degap_shared.sh before this job." >&2
  exit 1
fi

link_shared_artifact() {{
  local name="$1"
  local source="$SHARED_OUT/$name"
  local target="$JOB_OUT/$name"
  if [ ! -e "$source" ]; then
    echo "[error] Missing shared artifact: $source" >&2
    echo "        Run prepare_degap_shared.sh before this job." >&2
    exit 1
  fi
  if [ -L "$target" ]; then
    if [ "$(readlink "$target")" = "$source" ]; then
      echo "[shared] $target already links to $source"
      return 0
    fi
    if [ "$CGAT_FAMILY_SHARED" -eq 1 ]; then
      echo "[error] Old or different DEGAP read cache in $JOB_OUT; choose a new job output directory." >&2
      exit 1
    fi
    rm "$target"
  elif [ -e "$target" ]; then
    if [ "$CGAT_FAMILY_SHARED" -eq 1 ]; then
      echo "[error] Job-local DEGAP read artifacts in $JOB_OUT cannot be mixed with the new shared cache; choose a new job output directory." >&2
      exit 1
    fi
    echo "[shared] keeping existing job-local artifact: $target"
    return 0
  fi
  ln -s "$source" "$target"
  echo "[shared] linked $target -> $source"
}}

{artifact_lines}
"#,
        quoted_shared_out = shell_quote(&shared_out),
        quoted_out = shell_quote(out_path),
        family_layout = family_shared_layout(settings),
        artifact_lines = artifact_lines,
    )
}

fn build_prepare_block(
    label: &str,
    segment: &DegapJobSeedSegment,
    members: &[SeedMemberPlan],
    output_path: &str,
) -> String {
    let orient = if segment.start <= segment.end {
        "+"
    } else {
        "-"
    };
    format!(
        "# segment_start = {}\n# segment_end = {}\n# orient = \"{}\"; source_members = {}\necho {}\npython3 -B \"$CGAT_SOURCE_TOOL\" --recipe \"$CGAT_RECIPE\" --label {}\n",
        segment.start,
        segment.end,
        orient,
        members.len(),
        shell_quote(&format!("[prepare] {label} seed -> {output_path}")),
        shell_quote(label)
    )
}

/// Identity of the original source objects, independent of display names alone.
pub(crate) fn degap_seed_snapshot(
    conn: &Connection,
    project_id: i64,
    ids: &[i64],
) -> Result<Value> {
    let mut sources = Vec::new();
    for id in ids {
        let source = conn.query_row(
            "SELECT c.id, c.name, c.assigned_chr_name, s.source_seq_id, s.source_start,
                    s.source_end, s.orient, s.hidden, ss.seq_name, ss.length, d.name
             FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id
             JOIN source_seq ss ON ss.id=s.source_seq_id JOIN dataset d ON d.id=ss.dataset_id
             WHERE c.project_id=?1 AND c.id=?2",
            params![project_id, id],
            |row| {
                Ok(json!({
                    "id": row.get::<_, i64>(0)?, "name": row.get::<_, String>(1)?,
                    "chr": row.get::<_, Option<String>>(2)?, "source_id": row.get::<_, i64>(3)?,
                    "start": row.get::<_, i64>(4)?, "end": row.get::<_, i64>(5)?,
                    "orient": row.get::<_, String>(6)?, "hidden": row.get::<_, i64>(7)?,
                    "sequence": row.get::<_, String>(8)?, "length": row.get::<_, i64>(9)?,
                    "dataset": row.get::<_, String>(10)?
                }))
            },
        )?;
        sources.push(source);
    }
    Ok(json!(sources))
}

pub(crate) fn degap_final_path_snapshot(
    conn: &Connection,
    project_id: i64,
    chr: &str,
) -> Result<Value> {
    let raw = conn
        .query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=?1",
            [project_id],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    let paths: Value = serde_json::from_str(raw.as_deref().unwrap_or("{}"))?;
    Ok(paths
        .get(chr)
        .and_then(|entry| entry.get("segments"))
        .cloned()
        .unwrap_or(Value::Null))
}

fn build_degap_receipt(
    conn: &Connection,
    workspace_root: &Path,
    project_id: i64,
    job: &DegapJobExportItem,
    settings: &DegapJobExportSettings,
    seed_plans: Value,
) -> Result<Value> {
    let segments: Vec<_> = [&job.left, &job.right, &job.endpoint]
        .into_iter()
        .flatten()
        .map(|s| json!({"id": s.assembly_ctg_id, "start": s.start, "end": s.end}))
        .collect();
    let ids: Vec<_> = segments.iter().map(|s| s["id"].as_i64().unwrap()).collect();
    let snapshot = degap_seed_snapshot(conn, project_id, &ids)?;
    let primary: String = conn.query_row(
        "SELECT d.name FROM project p JOIN dataset d ON d.id=p.primary_dataset_id WHERE p.id=?1",
        [project_id],
        |r| r.get(0),
    )?;
    let placed_track: Option<String> = conn.query_row(
        "SELECT d.name FROM derived_ctg_track_member t JOIN dataset d ON d.id=t.target_dataset_id
         JOIN assembly_seq s ON s.source_seq_id=t.source_seq_id
         JOIN assembly_ctg c ON c.assembly_seq_id=s.id
         WHERE c.id=?1 AND t.project_id=?2 AND t.target_chr_name=?3",
        params![ids[0], project_id, job.chr_name], |row| row.get(0),
    ).optional()?;
    let mode: String = conn.query_row(
        "SELECT placement_mode FROM assembly_ctg WHERE id=?1 AND project_id=?2",
        params![ids[0], project_id],
        |row| row.get(0),
    )?;
    let source_dataset = snapshot[0]["dataset"]
        .as_str()
        .context("missing seed source dataset")?;
    let (target_track, track_basis) = if let Some(track) = placed_track {
        (track, "existing_derived_placement")
    } else if mode == "refinement"
        || source_dataset == "derived_ctg"
        || source_dataset.starts_with("cgat_refinement_")
    {
        (primary, "project_primary_context_not_homology")
    } else {
        (source_dataset.to_string(), "original_dataset_track")
    };
    let target_chr = snapshot[0]["chr"]
        .as_str()
        .filter(|name| !name.is_empty())
        .unwrap_or(&job.chr_name);
    let mut receipt = json!({"schema": "gpm.degap.export.v1", "project_id": project_id,
        "job_id": job.job_id, "chr_name": job.chr_name, "job_type": normalize_job_type(&job.job_type),
        "target_chr": target_chr, "target_track": target_track, "target_track_basis": track_basis,
        "seed_plans": seed_plans, "endpoint_end": job.endpoint_end,
        "server_root": settings.gpm_server_path, "out_path": job.out_path,
        "segments": segments, "sources": snapshot, "settings": settings,
        "final_path": degap_final_path_snapshot(conn, project_id, &job.chr_name)?});
    let mut digest = Sha256::new();
    digest.update(serde_json::to_vec(&receipt)?);
    digest.update(workspace_root.as_os_str().to_string_lossy().as_bytes());
    digest.update(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos()
            .to_le_bytes(),
    );
    receipt["token"] = json!(format!("{:x}", digest.finalize()));
    Ok(receipt)
}

fn resolve_degap_entrypoint(settings: &DegapJobExportSettings) -> String {
    if settings.degap_path.trim().is_empty() {
        "\"$CGAT_DEGAP_TOOL\"".to_string()
    } else {
        shell_quote(&settings.degap_path)
    }
}

fn build_gapfiller_job_script(
    job: &DegapJobExportItem,
    settings: &DegapJobExportSettings,
    shared_settings: &DegapJobExportSettings,
    left_plan: &[SeedMemberPlan],
    right_plan: &[SeedMemberPlan],
    seqleft_path: &str,
    seqright_path: &str,
) -> String {
    let left = job.left.as_ref().expect("validated gapfiller left seed");
    let right = job.right.as_ref().expect("validated gapfiller right seed");
    let source_comments = left_plan
        .iter()
        .map(|member| format!("# left_source_fasta: {}", member.server_fasta_path))
        .chain(
            right_plan
                .iter()
                .map(|member| format!("# right_source_fasta: {}", member.server_fasta_path)),
        )
        .collect::<Vec<_>>()
        .join("\n");
    let mut command = vec![
        "python".to_string(),
        resolve_degap_entrypoint(settings),
        "--mode".to_string(),
        "gapfiller".to_string(),
        "--seqleft".to_string(),
        shell_quote(seqleft_path),
        "--seqright".to_string(),
        shell_quote(seqright_path),
        "--out".to_string(),
        shell_quote(&job.out_path),
        "--flag".to_string(),
        shell_quote(&job.flag),
    ];
    if !settings.hifi_reads.is_empty() {
        command.push("--hifi".to_string());
        for read in &settings.hifi_reads {
            command.push(shell_quote(read));
        }
    }
    if !settings.ont_reads.is_empty() {
        command.push("--ont".to_string());
        for read in &settings.ont_reads {
            command.push(shell_quote(read));
        }
    }
    command.extend(["-t".to_string(), shell_quote(&settings.thread.to_string())]);
    command.extend([
        "--remove".to_string(),
        shell_quote(&settings.remove.to_string()),
    ]);
    command.extend([
        "--edge".to_string(),
        shell_quote(&settings.edge.to_string()),
    ]);
    if settings.kmer_filter {
        command.push("--kmer_filter".to_string());
        command.extend([
            "--kmer_size".to_string(),
            shell_quote(&settings.kmer_size.to_string()),
        ]);
        command.extend([
            "--kmer_num".to_string(),
            shell_quote(&settings.kmer_num.to_string()),
        ]);
    }
    if let Some(value) = settings.maximum_extension_round {
        command.extend([
            "--MaximumExtensionRound".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    if let Some(value) = settings.maximum_extension_length {
        command.extend([
            "--MaximumExtensionLength".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    if let Some(value) = settings.filter_depth_hifi {
        command.extend([
            "--filterDepthHifi".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    if let Some(value) = settings.filter_depth_ont {
        command.extend([
            "--filterDepthOnt".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    let use_shared_index_and_split =
        settings.filter_depth_hifi.is_none() && settings.filter_depth_ont.is_none();
    let shared_link_block = build_shared_link_block(
        &job.out_path,
        settings,
        shared_settings,
        use_shared_index_and_split,
    );
    format!(
        r#"#!/usr/bin/env bash
set -euo pipefail

# DEGAP gapfiller job: {job_id}
# left_ctg: {left_ctg}
# right_ctg: {right_ctg}
# flag: {flag}
# out: {out_path}
{source_comments}

mkdir -p {quoted_out}

# Step 1: link shared DEGAP read cache prepared by prepare_degap_shared.sh
{shared_link_block}

# Step 2: prepare seqleft.fa and seqright.fa
{left_prepare}
{right_prepare}

# Step 3: run DEGAP gapfiller
echo "[run] DEGAP gapfiller {job_id}"
{command}
"#,
        job_id = job.job_id,
        left_ctg = job.left_ctg,
        right_ctg = job.right_ctg,
        flag = job.flag,
        out_path = job.out_path,
        source_comments = source_comments,
        quoted_out = shell_quote(&job.out_path),
        shared_link_block = shared_link_block,
        left_prepare = build_prepare_block("seqleft", left, left_plan, seqleft_path),
        right_prepare = build_prepare_block("seqright", right, right_plan, seqright_path),
        command = command.join(" "),
    )
}

fn build_telseeker_ctg_job_script(
    job: &DegapJobExportItem,
    settings: &DegapJobExportSettings,
    shared_settings: &DegapJobExportSettings,
    endpoint_plan: &[SeedMemberPlan],
    ctg_path: &str,
) -> String {
    let endpoint = job
        .endpoint
        .as_ref()
        .expect("validated telseeker_ctg endpoint");
    let source_comments = endpoint_plan
        .iter()
        .map(|member| format!("# endpoint_source_fasta: {}", member.server_fasta_path))
        .collect::<Vec<_>>()
        .join("\n");
    let mut command = vec![
        "python".to_string(),
        resolve_degap_entrypoint(settings),
        "--mode".to_string(),
        "telseeker_ctg".to_string(),
        "--ctg".to_string(),
        shell_quote(ctg_path),
        shell_quote(&job.endpoint_end),
        "--motif".to_string(),
        shell_quote(&settings.motif),
        "--out".to_string(),
        shell_quote(&job.out_path),
    ];
    if !settings.hifi_reads.is_empty() {
        command.push("--hifi".to_string());
        for read in &settings.hifi_reads {
            command.push(shell_quote(read));
        }
    }
    if !settings.ont_reads.is_empty() {
        command.push("--ont".to_string());
        for read in &settings.ont_reads {
            command.push(shell_quote(read));
        }
    }
    command.extend(["-t".to_string(), shell_quote(&settings.thread.to_string())]);
    command.extend([
        "--work".to_string(),
        shell_quote(&settings.work.to_string()),
    ]);
    command.extend([
        "--edge".to_string(),
        shell_quote(&settings.edge.to_string()),
    ]);
    if settings.kmer_filter {
        command.push("--kmer_filter".to_string());
        command.extend([
            "--kmer_size".to_string(),
            shell_quote(&settings.kmer_size.to_string()),
        ]);
        command.extend([
            "--kmer_num".to_string(),
            shell_quote(&settings.kmer_num.to_string()),
        ]);
    }
    if let Some(value) = settings.maximum_extension_round {
        command.extend([
            "--MaximumExtensionRound".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    if let Some(value) = settings.maximum_extension_length {
        command.extend([
            "--MaximumExtensionLength".to_string(),
            shell_quote(&value.to_string()),
        ]);
    }
    command.extend([
        "--tel-n".to_string(),
        shell_quote(&settings.tel_n.to_string()),
    ]);
    command.extend([
        "--tel-r".to_string(),
        shell_quote(&settings.tel_r.to_string()),
    ]);
    command.extend([
        "--tel-mm".to_string(),
        shell_quote(&settings.tel_mm.to_string()),
    ]);
    let shared_link_block = build_shared_link_block(&job.out_path, settings, shared_settings, true);
    format!(
        r#"#!/usr/bin/env bash
set -euo pipefail

# DEGAP telseeker-ctg job: {job_id}
# endpoint_ctg: {endpoint_ctg}
# endpoint_end: {endpoint_end}
# out: {out_path}
{source_comments}

mkdir -p {quoted_out}

# Step 1: link shared DEGAP read cache prepared by prepare_degap_shared.sh
{shared_link_block}

# Step 2: prepare endpoint.ctg.fa
{endpoint_prepare}

# Step 3: run DEGAP telseeker_ctg
echo "[run] DEGAP telseeker_ctg {job_id}"
{command}
"#,
        job_id = job.job_id,
        endpoint_ctg = job.endpoint_ctg,
        endpoint_end = job.endpoint_end,
        out_path = job.out_path,
        source_comments = source_comments,
        quoted_out = shell_quote(&job.out_path),
        shared_link_block = shared_link_block,
        endpoint_prepare = build_prepare_block("endpoint", endpoint, endpoint_plan, ctg_path),
        command = command.join(" "),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::params;
    use serde_json::json;
    use tempfile::tempdir;

    fn test_settings() -> DegapJobExportSettings {
        DegapJobExportSettings {
            degap_path: "/opt/DEGAP/bin/DEGAP.py".to_string(),
            hifi_reads: vec!["/reads/hifi.fq.gz".to_string()],
            ont_reads: Vec::new(),
            gpm_server_path: "/srv/gpm_server".to_string(),
            out_root: "/srv/degap".to_string(),
            thread: 20,
            kmer_filter: true,
            kmer_size: 41,
            kmer_num: 20,
            maximum_extension_round: Some(30),
            maximum_extension_length: None,
            filter_depth_hifi: None,
            filter_depth_ont: None,
            remove: 2,
            edge: 500,
            motif: "TTAGGG".to_string(),
            work: 1,
            tel_n: 100,
            tel_r: 0.6,
            tel_mm: 0,
        }
    }

    fn test_gap_job(job_id: &str, chr_name: &str, out_path: &str) -> DegapJobExportItem {
        DegapJobExportItem {
            job_type: "gapfiller".to_string(),
            job_id: job_id.to_string(),
            chr_name: chr_name.to_string(),
            left_ctg: "CtgA".to_string(),
            right_ctg: "CtgB".to_string(),
            flag: "left".to_string(),
            out_path: out_path.to_string(),
            left: Some(DegapJobSeedSegment {
                assembly_ctg_id: 301,
                start: 8,
                end: 5,
            }),
            right: Some(DegapJobSeedSegment {
                assembly_ctg_id: 302,
                start: 1,
                end: 4,
            }),
            endpoint_ctg: String::new(),
            endpoint_end: String::new(),
            endpoint: None,
            settings: None,
        }
    }

    #[test]
    #[ignore = "requires the controlled exported/collected bridge fixture"]
    fn manual_source_bridge_import_preserves_the_edited_final_path() -> Result<()> {
        let value = std::env::var("CGAT_MANUAL_EXPORT_FIXTURE_ROOT")?;
        let fixture = PathBuf::from(value);
        assert_eq!(
            fs::read_to_string(fixture.join(".owned-fixture"))?,
            "cgat.manual-source-bridge.v1\n"
        );
        let client = fixture.join("client");
        let before = fs::read_to_string(fixture.join("manual-path-before.json"))?;
        let (results, _) = crate::importer::import_degap_results_with_hooks(
            &client.join("exports/degap/degap_results.zip"),
            &client,
            1,
            &mut |_| {},
            &mut || false,
        )?;
        assert_eq!(results.len(), 1);
        let conn = open_workspace_db(&client.join("project.sqlite"))?;
        let after: String = conn.query_row(
            "SELECT final_path_by_chr_json FROM project_assembly_view_state WHERE project_id=1",
            [],
            |row| row.get(0),
        )?;
        assert_eq!(after, before);
        let count: i64 =
            conn.query_row("SELECT COUNT(*) FROM derived_ctg", [], |row| row.get(0))?;
        assert_eq!(count, 1);
        let (path, name): (String, String) = conn.query_row("SELECT l.fasta_path,s.seq_name FROM source_seq_locator l JOIN source_seq s ON s.id=l.source_seq_id JOIN derived_ctg d ON d.source_seq_id=s.id", [], |row| Ok((row.get(0)?, row.get(1)?)))?;
        let seq = crate::exporter::load_fasta_source_interval(Path::new(&path), &name, 1, 10)?;
        assert_eq!(seq, "AACCGTTTTT");
        Ok(())
    }

    #[test]
    fn bundled_shared_reads_use_a_separate_cache_for_family_runtime() {
        let mut bundled = test_settings();
        let legacy_custom = bundled.clone();
        bundled.degap_path.clear();
        let prepare = build_shared_prepare_script(&bundled);
        assert!(prepare.contains("$SHARED_OUT.family-v1"));
        assert!(prepare.contains("prepare-shared-reads --out"));
        let links = build_shared_link_block("/srv/job", &bundled, &bundled, true);
        assert!(links.contains("$SHARED_OUT.family-v1"));
        assert!(links.contains("cannot be mixed with the new shared cache"));
        assert!(!build_shared_prepare_script(&legacy_custom).contains("$SHARED_OUT.family-v1"));
        assert!(!can_use_shared_reads(&bundled, &legacy_custom));
    }

    #[test]
    fn bundled_degap_path_is_default_and_custom_paths_remain_supported() -> Result<()> {
        let mut settings = parse_degap_export_settings(&json!({
            "gpmServerPath": "/srv/project with spaces",
            "outRoot": "/srv/out", "hifiReads": ["/reads/hifi.fa"]
        }))?;
        validate_settings(&settings)?;
        assert_eq!(resolve_degap_entrypoint(&settings), "\"$CGAT_DEGAP_TOOL\"");
        settings.degap_path = "/custom/DEGAP.py".to_string();
        assert_eq!(resolve_degap_entrypoint(&settings), "'/custom/DEGAP.py'");
        Ok(())
    }

    #[test]
    fn parse_degap_export_settings_treats_null_and_empty_optional_numbers_as_unset() -> Result<()> {
        let settings = parse_degap_export_settings(&json!({
            "degapPath": "/opt/DEGAP/bin/DEGAP.py",
            "hifiReads": ["/reads/hifi.fq.gz"],
            "gpmServerPath": "/srv/gpm_server",
            "outRoot": "/srv/degap",
            "maximumExtensionRound": "30",
            "maximumExtensionLength": null,
            "filterDepthHifi": "",
            "filterDepthOnt": null
        }))?;

        assert_eq!(settings.maximum_extension_round, Some(30));
        assert_eq!(settings.maximum_extension_length, None);
        assert_eq!(settings.filter_depth_hifi, None);
        assert_eq!(settings.filter_depth_ont, None);
        Ok(())
    }

    #[test]
    fn parse_degap_export_settings_treats_string_unset_optional_numbers_as_unset() -> Result<()> {
        let settings = parse_degap_export_settings(&json!({
            "degapPath": "/opt/DEGAP/bin/DEGAP.py",
            "hifiReads": ["/reads/hifi.fq.gz"],
            "gpmServerPath": "/srv/gpm_server",
            "outRoot": "/srv/degap",
            "maximumExtensionLength": "null",
            "filterDepthHifi": "undefined",
            "filterDepthOnt": "NaN"
        }))?;

        assert_eq!(settings.maximum_extension_length, None);
        assert_eq!(settings.filter_depth_hifi, None);
        assert_eq!(settings.filter_depth_ont, None);
        assert!(
            parse_degap_export_settings(&json!({
                "degapPath": "/opt/DEGAP/bin/DEGAP.py",
                "hifiReads": ["/reads/hifi.fq.gz"],
                "gpmServerPath": "/srv/gpm_server",
                "outRoot": "/srv/degap",
                "maximumExtensionLength": "abc"
            }))
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn export_degap_jobs_writes_manifest_and_reverse_oriented_seed_script() -> Result<()> {
        let temp = tempdir()?;
        let workspace_root = temp.path().join("workspace");
        fs::create_dir_all(workspace_root.join("data/partitions/chr/Chr01"))?;
        let fasta_path = workspace_root.join("data/partitions/chr/Chr01/ds.fa");
        fs::write(&fasta_path, ">tigA\nAACCGGTT\n>tigB\nTTTTCCCC\n")?;
        let db_path = workspace_root.join("project.sqlite");
        fs::create_dir_all(&workspace_root)?;
        let conn = open_workspace_db(&db_path)?;
        conn.execute(
            "INSERT INTO reference_genome (id, name, species_name, assembly_label, fasta_path, fai_path)
             VALUES (1, 'ref', 'species', 'asm', '', '')",
            [],
        )?;
        conn.execute(
            "INSERT INTO dataset (id, name, assembler, assembler_version, fasta_path, fai_path)
             VALUES (1, 'ds', 'asm', NULL, '', '')",
            [],
        )?;
        conn.execute(
            "INSERT INTO project (id, name, version, reference_genome_id, primary_dataset_id, auto_check_new_seq, description, created_at, note)
             VALUES (1, 'p1', 1, 1, 1, 0, NULL, '1', NULL)",
            [],
        )?;
        conn.execute(
            "INSERT INTO source_seq (id, dataset_id, seq_name, seq_order, length)
             VALUES (101, 1, 'tigA', 1, 8), (102, 1, 'tigB', 2, 8)",
            [],
        )?;
        conn.execute(
            "INSERT INTO source_seq_locator (source_seq_id, fasta_path)
             VALUES (101, ?1), (102, ?1)",
            params![fasta_path.to_string_lossy()],
        )?;
        conn.execute(
            "INSERT INTO assembly_seq (id, project_id, source_seq_id, orient, source_start, source_end, left_end_type, right_end_type, hidden, created_at, note)
             VALUES (201, 1, 101, '+', 1, 8, 'normal', 'normal', 0, '1', NULL),
                    (202, 1, 102, '+', 1, 8, 'normal', 'normal', 0, '1', NULL)",
            [],
        )?;
        conn.execute(
            "INSERT INTO assembly_ctg (id, project_id, assembly_seq_id, name, assigned_chr_name, chr_order, anchor_start, ref_orient, placement_mode, created_at, note)
             VALUES (301, 1, 201, 'CtgA', 'Chr01', 1, 1, '+', 'manual', '1', NULL),
                    (302, 1, 202, 'CtgB', 'Chr01', 2, 20, '+', 'manual', '1', NULL)",
            [],
        )?;

        let output_dir = workspace_root.join("exports/degap");
        let summary = export_degap_jobs_with_connection(
            &conn,
            &workspace_root,
            1,
            &ExportDegapJobsParams {
                output_dir: output_dir.clone(),
                settings: test_settings(),
                jobs: vec![
                    DegapJobExportItem {
                        job_type: "gapfiller".to_string(),
                        job_id: "CtgA_vs_CtgB_Left-job".to_string(),
                        chr_name: "Chr01".to_string(),
                        left_ctg: "CtgA".to_string(),
                        right_ctg: "CtgB".to_string(),
                        flag: "left".to_string(),
                        out_path: "/srv/degap/CtgA_vs_CtgB_left".to_string(),
                        left: Some(DegapJobSeedSegment {
                            assembly_ctg_id: 301,
                            start: 8,
                            end: 5,
                        }),
                        right: Some(DegapJobSeedSegment {
                            assembly_ctg_id: 302,
                            start: 1,
                            end: 4,
                        }),
                        endpoint_ctg: String::new(),
                        endpoint_end: String::new(),
                        endpoint: None,
                        settings: None,
                    },
                    DegapJobExportItem {
                        job_type: "telseeker_ctg".to_string(),
                        job_id: "telseeker_ctg_right_CtgB".to_string(),
                        chr_name: "Chr01".to_string(),
                        left_ctg: String::new(),
                        right_ctg: String::new(),
                        flag: String::new(),
                        out_path: "/srv/degap/telseeker_ctg_right_CtgB".to_string(),
                        left: None,
                        right: None,
                        endpoint_ctg: "CtgB".to_string(),
                        endpoint_end: "R".to_string(),
                        endpoint: Some(DegapJobSeedSegment {
                            assembly_ctg_id: 302,
                            start: 1,
                            end: 8,
                        }),
                        settings: None,
                    },
                ],
            },
        )?;

        assert_eq!(summary.manifest_path, output_dir.join("jobs.tsv"));
        assert_eq!(
            summary.prepare_script_path,
            output_dir.join("prepare_degap_shared.sh")
        );
        let prepare_script = fs::read_to_string(&summary.prepare_script_path)?;
        assert!(
            prepare_script
                .contains("Run this once before running any exported degap_jobs/*.sh script.")
        );
        assert!(prepare_script.contains("SHARED_OUT='/srv/degap/shared_prepare'"));
        let manifest = fs::read_to_string(&summary.manifest_path)?;
        assert!(manifest.contains("CtgA_vs_CtgB_Left-job"));
        assert!(manifest.contains("job_id\tchr_name\tjob_type"));
        assert!(manifest.contains("CtgA_vs_CtgB_Left-job\tChr01\tgapfiller"));
        assert!(manifest.contains("degap_jobs/Chr01_gapfiller_left_CtgA_to_CtgB.sh"));
        assert!(manifest.contains("degap_jobs/Chr01_telseeker_ctg_right_CtgB.sh"));
        assert_eq!(
            summary.scripts[0]
                .script_path
                .file_name()
                .and_then(|name| name.to_str()),
            Some("Chr01_gapfiller_left_CtgA_to_CtgB.sh")
        );
        assert_eq!(
            summary.scripts[1]
                .script_path
                .file_name()
                .and_then(|name| name.to_str()),
            Some("Chr01_telseeker_ctg_right_CtgB.sh")
        );
        let script = fs::read_to_string(&summary.scripts[0].script_path)?;
        assert!(script.contains("/srv/gpm_server/data/partitions/chr/Chr01/ds.fa"));
        assert!(script.contains("Run prepare_degap_shared.sh before this job."));
        assert!(script.contains("link_shared_artifact 'hifi_reads_part'"));
        assert!(script.contains("segment_start = 8"));
        assert!(script.contains("orient = \"-\""));
        assert!(script.contains("--MaximumExtensionRound '30'"));
        assert!(script.contains("--kmer_filter"));
        let telseeker_script = fs::read_to_string(&summary.scripts[1].script_path)?;
        assert!(telseeker_script.contains("# DEGAP telseeker-ctg job: telseeker_ctg_right_CtgB"));
        assert!(telseeker_script.contains("--mode telseeker_ctg"));
        assert!(
            telseeker_script
                .contains("--ctg '/srv/degap/telseeker_ctg_right_CtgB/endpoint.ctg.fa' 'R'")
        );
        assert!(telseeker_script.contains("--motif 'TTAGGG'"));
        assert!(telseeker_script.contains("link_shared_artifact 'hifi_reads_part'"));
        assert!(!telseeker_script.contains("--filterDepthHifi"));
        assert_eq!(
            summary.scripts[1].ctg_path,
            "/srv/degap/telseeker_ctg_right_CtgB/endpoint.ctg.fa"
        );

        let chr01_old_script = summary.scripts[0].script_path.clone();
        let chr01_old_telseeker_script = summary.scripts[1].script_path.clone();
        let chr02_summary = export_degap_jobs_with_connection(
            &conn,
            &workspace_root,
            1,
            &ExportDegapJobsParams {
                output_dir: output_dir.clone(),
                settings: test_settings(),
                jobs: vec![test_gap_job(
                    "Chr02_gap_left",
                    "Chr02",
                    "/srv/degap/Chr02_gap_left",
                )],
            },
        )?;
        assert_eq!(chr02_summary.scripts.len(), 1);
        let merged_manifest = fs::read_to_string(output_dir.join("jobs.tsv"))?;
        assert!(merged_manifest.contains("CtgA_vs_CtgB_Left-job\tChr01\tgapfiller"));
        assert!(merged_manifest.contains("telseeker_ctg_right_CtgB\tChr01\ttelseeker_ctg"));
        assert!(merged_manifest.contains("Chr02_gap_left\tChr02\tgapfiller"));
        assert!(chr01_old_script.exists());
        assert!(chr02_summary.scripts[0].script_path.exists());
        assert_eq!(
            chr02_summary.scripts[0]
                .script_path
                .file_name()
                .and_then(|name| name.to_str()),
            Some("Chr02_gapfiller_left_CtgA_to_CtgB.sh")
        );

        let chr02_script = chr02_summary.scripts[0].script_path.clone();
        let chr01_replace_summary = export_degap_jobs_with_connection(
            &conn,
            &workspace_root,
            1,
            &ExportDegapJobsParams {
                output_dir: output_dir.clone(),
                settings: test_settings(),
                jobs: vec![test_gap_job(
                    "Chr01_replacement_left",
                    "Chr01",
                    "/srv/degap/Chr01_replacement_left",
                )],
            },
        )?;
        let replaced_manifest = fs::read_to_string(output_dir.join("jobs.tsv"))?;
        assert!(replaced_manifest.contains("Chr01_replacement_left\tChr01\tgapfiller"));
        assert!(replaced_manifest.contains("Chr02_gap_left\tChr02\tgapfiller"));
        assert!(!replaced_manifest.contains("CtgA_vs_CtgB_Left-job\tChr01"));
        assert!(!replaced_manifest.contains("telseeker_ctg_right_CtgB\tChr01"));
        assert!(chr01_old_script.exists());
        assert!(!chr01_old_telseeker_script.exists());
        assert!(chr02_script.exists());
        assert!(chr01_replace_summary.scripts[0].script_path.exists());
        if let Ok(value) = std::env::var("CGAT_MANUAL_EXPORT_FIXTURE_ROOT") {
            let fixture = PathBuf::from(value);
            assert_eq!(
                fs::read_to_string(fixture.join(".owned-fixture"))?,
                "cgat.manual-source-bridge.v1\n"
            );
            let client = fixture.join("client");
            fs::create_dir(&client)?;
            fs::create_dir_all(client.join("data/partitions/chr/Chr01"))?;
            fs::copy(&fasta_path, client.join("data/partitions/chr/Chr01/ds.fa"))?;
            conn.query_row("PRAGMA wal_checkpoint(TRUNCATE)", [], |row| {
                row.get::<_, i64>(0)
            })?;
            fs::copy(&db_path, client.join("project.sqlite"))?;
            let bridge = open_workspace_db(&client.join("project.sqlite"))?;
            bridge.execute(
                "UPDATE source_seq_locator SET fasta_path=?1",
                [client
                    .join("data/partitions/chr/Chr01/ds.fa")
                    .to_string_lossy()
                    .to_string()],
            )?;
            bridge.execute("INSERT OR IGNORE INTO project_dataset(project_id,dataset_id,dataset_role,display_order) VALUES(1,1,'primary',0)", [])?;
            bridge.execute("INSERT OR IGNORE INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(1,1,'Chr01',1,8)", [])?;
            for (source, order) in [(101_i64, 1_i64), (102, 2)] {
                bridge.execute("INSERT OR IGNORE INTO imported_chr_assignment(source_seq_id,reference_chr_id,source_orientation,orientation_source,support_bp,support_percent,anchor_start) VALUES(?1,1,'+','ref_alignment',8,100,1)", [source])?;
                bridge.execute("INSERT OR IGNORE INTO imported_track_member_order(target_dataset_id,reference_chr_id,source_seq_id,member_order) VALUES(1,1,?1,?2)", params![source, order])?;
            }
            bridge.execute(
                "INSERT OR IGNORE INTO workspace_package_metadata(id) VALUES(1)",
                [],
            )?;
            let edited = json!({"Chr01": {"segments": [{"type":"ctg","assemblyCtgId":301,"name":"CtgA","start":2,"end":7},
                                                       {"type":"gap","size":13,"id":"keep-manual-gap"}]}}).to_string();
            bridge.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,updated_at) VALUES(1,?1,'1') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json", [&edited])?;
            fs::write(fixture.join("manual-path-before.json"), &edited)?;
            let server = std::env::var("CGAT_MANUAL_EXPORT_SERVER_ROOT")?;
            let mut settings = test_settings();
            settings.gpm_server_path = server.clone();
            settings.out_root = format!("{server}/manual-jobs");
            settings.degap_path = format!("{server}/controlled_degap.py");
            settings.hifi_reads = vec![format!("{server}/controlled_reads.fa")];
            let output = client.join("exports/degap");
            let summary = export_degap_jobs_with_connection(
                &bridge,
                &client,
                1,
                &ExportDegapJobsParams {
                    output_dir: output.clone(),
                    settings: settings.clone(),
                    jobs: vec![test_gap_job(
                        "bridge-gap",
                        "Chr01",
                        &format!("{server}/manual-jobs/gap"),
                    )],
                },
            )?;
            fs::write(
                fixture.join("exported.json"),
                serde_json::to_vec_pretty(&json!({"script": summary.scripts[0].script_path,
                "out": format!("{server}/manual-jobs/gap"), "export_dir": output, "server": server}))?,
            )?;
        }
        Ok(())
    }
}
