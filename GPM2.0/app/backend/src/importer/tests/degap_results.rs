use super::test_support::*;
use crate::importer::{import_degap_results_with_hooks, is_degap_results_package};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::io::Write;

fn receipt(workspace: &Path, db: &Path, project: i64, token: &str) -> Value {
    let conn = Connection::open(db).unwrap();
    if conn
        .query_row(
            "SELECT COUNT(*) FROM assembly_seq WHERE project_id=?1",
            [project],
            |r| r.get::<_, i64>(0),
        )
        .unwrap()
        == 0
    {
        crate::project_initializer::bootstrap_project_assembly(db, project).unwrap();
    }
    let id: i64 = conn
        .query_row(
            "SELECT id FROM assembly_ctg WHERE project_id=?1 ORDER BY id LIMIT 1",
            [project],
            |r| r.get(0),
        )
        .unwrap();
    conn.execute("INSERT INTO project_assembly_view_state(project_id, final_path_by_chr_json, updated_at) VALUES(?1, ?2, '1') ON CONFLICT(project_id) DO NOTHING", params![project, json!({"r":{"segments":[{"type":"ctg","assemblyCtgId":id,"start":1,"end":2}]}}).to_string()]).unwrap();
    let value = json!({"schema":"gpm.degap.export.v1", "token":token,
        "project_id":project, "job_id":"gap-r", "chr_name":"r", "target_chr":"r", "target_track":"ds_a",
        "segments":[{"id":id,"start":1,"end":4}],
        "final_path":crate::degap_jobs::degap_final_path_snapshot(&conn, project, "r").unwrap(),
        "sources":crate::degap_jobs::degap_seed_snapshot(&conn, project, &[id]).unwrap()});
    fs::create_dir_all(workspace.join("metadata/degap_exports")).unwrap();
    fs::write(
        workspace.join(format!("metadata/degap_exports/{token}.json")),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    value
}

fn result_zip(path: &Path, nested: &Path, receipts: &[Value], corrupt: bool) {
    result_zip_candidates(
        path,
        &vec![nested.to_path_buf(); receipts.len()],
        receipts,
        corrupt,
    );
}

fn result_zip_candidates(path: &Path, candidates: &[PathBuf], receipts: &[Value], corrupt: bool) {
    let mut zip = zip::ZipWriter::new(fs::File::create(path).unwrap());
    let options = zip::write::FileOptions::default();
    let results: Vec<_> = receipts
        .iter()
        .enumerate()
        .map(|(index, recipe)| {
            let source = format!(
                "DEGAP:{}:{}",
                recipe["token"].as_str().unwrap(),
                recipe["job_id"].as_str().unwrap()
            );
            let original = fs::read(&candidates[index]).unwrap();
            let mut input = zip::ZipArchive::new(std::io::Cursor::new(&original)).unwrap();
            let mut output = zip::ZipWriter::new(std::io::Cursor::new(Vec::new()));
            for entry in 0..input.len() {
                let mut file = input.by_index(entry).unwrap();
                let mut text = String::new();
                std::io::Read::read_to_string(&mut file, &mut text).unwrap();
                output.start_file(file.name(), options).unwrap();
                output
                    .write_all(text.replace("gapfiller", &source).as_bytes())
                    .unwrap();
            }
            let bytes = output.finish().unwrap().into_inner();
            let mut check = zip::ZipArchive::new(std::io::Cursor::new(&bytes)).unwrap();
            let mut manifest = String::new();
            std::io::Read::read_to_string(
                &mut check.by_name("add_ctg/manifest.tsv").unwrap(),
                &mut manifest,
            )
            .unwrap();
            let ctg_name = manifest
                .lines()
                .find_map(|line| line.strip_prefix("ctg_name\t"))
                .unwrap();
            let hash = format!("{:x}", Sha256::digest(&bytes));
            let name = format!("packages/{index}.zip");
            zip.start_file(&name, options).unwrap();
            zip.write_all(&bytes).unwrap();
            json!({"recipe":recipe,"ctg_name":ctg_name,"package":name,
            "sha256":if corrupt { "0".repeat(64) } else { hash.clone() }})
        })
        .collect();
    zip.start_file("degap_results.json", options).unwrap();
    zip.write_all(
        &serde_json::to_vec(&json!({"schema":"gpm.degap.results.v1","results":results})).unwrap(),
    )
    .unwrap();
    zip.finish().unwrap();
}

#[test]
fn degap_batch_import_associates_candidate_and_rejects_duplicates() {
    let temp = tempdir().unwrap();
    let (outcome, project) = import_workspace_with_project(temp.path());
    let token = "a".repeat(64);
    let receipt = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &token,
    );
    let nested = temp.path().join("candidate.zip");
    write_add_ctg_zip(&nested);
    let package = temp.path().join("results.zip");
    result_zip(&package, &nested, &[receipt], false);
    assert!(is_degap_results_package(&package).unwrap());
    assert!(!is_degap_results_package(&nested).unwrap());
    let (results, _) = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap();
    let final_path = crate::degap_jobs::degap_final_path_snapshot(
        &Connection::open(&outcome.project_db_path).unwrap(),
        project,
        "r",
    )
    .unwrap();
    assert_eq!(final_path.as_array().unwrap().len(), 1);
    assert_eq!(final_path[0]["end"], 2);
    assert_eq!(results.len(), 1);
    assert_eq!(results[0]["ctgName"], "gap_filled");
    assert!(
        outcome
            .workspace_root
            .join(format!("metadata/degap_imports/{token}.json"))
            .is_file()
    );
    let error = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap_err();
    assert!(
        error.to_string().contains("already been imported"),
        "{error:#}"
    );
}

#[test]
fn degap_batch_rolls_back_first_candidate_when_second_fails() {
    let temp = tempdir().unwrap();
    let (outcome, project) = import_workspace_with_project(temp.path());
    let first = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"a".repeat(64),
    );
    let second = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"b".repeat(64),
    );
    let before = count_rows(&outcome.project_db_path, "source_seq");
    let nested = temp.path().join("candidate.zip");
    write_add_ctg_zip(&nested);
    let package = temp.path().join("results.zip");
    result_zip(&package, &nested, &[first, second], false);
    // Both envelopes pass provenance; the second repeats a ctg and fails after
    // the first has actually changed files, database and association metadata.
    assert!(
        import_degap_results_with_hooks(
            &package,
            &outcome.workspace_root,
            project,
            &mut |_| {},
            &mut || false
        )
        .is_err()
    );
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), before);
    assert!(
        !outcome
            .workspace_root
            .join("data/derived_ctgs/gap_filled.fa")
            .exists()
    );
    assert!(
        !outcome
            .workspace_root
            .join(format!("metadata/degap_imports/{}.json", "a".repeat(64)))
            .exists()
    );
}

#[test]
fn degap_batch_rejects_checksum_foreign_workspace_and_changed_source_before_mutation() {
    let temp = tempdir().unwrap();
    let (outcome, project) = import_workspace_with_project(temp.path());
    let token = "c".repeat(64);
    let saved = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &token,
    );
    let before = count_rows(&outcome.project_db_path, "source_seq");
    let nested = temp.path().join("candidate.zip");
    write_add_ctg_zip(&nested);
    let package = temp.path().join("results.zip");
    result_zip(&package, &nested, std::slice::from_ref(&saved), true);
    let import = || {
        import_degap_results_with_hooks(
            &package,
            &outcome.workspace_root,
            project,
            &mut |_| {},
            &mut || false,
        )
    };
    assert!(import().unwrap_err().to_string().contains("checksum"));
    result_zip(&package, &nested, std::slice::from_ref(&saved), false);
    Connection::open(&outcome.project_db_path)
        .unwrap()
        .execute(
            "UPDATE assembly_seq SET source_end=source_end-1 WHERE project_id=?1",
            [project],
        )
        .unwrap();
    assert!(
        import()
            .unwrap_err()
            .to_string()
            .contains("source objects changed")
    );
    fs::remove_file(
        outcome
            .workspace_root
            .join(format!("metadata/degap_exports/{token}.json")),
    )
    .unwrap();
    assert!(
        import()
            .unwrap_err()
            .to_string()
            .contains("not exported from this workspace")
    );
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), before);
}

#[test]
fn degap_batch_detects_changed_final_path_and_cancellation_rolls_back() {
    use std::cell::Cell;
    let temp = tempdir().unwrap();
    let (outcome, project) = import_workspace_with_project(temp.path());
    let saved = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"d".repeat(64),
    );
    let before = count_rows(&outcome.project_db_path, "source_seq");
    let nested = temp.path().join("candidate.zip");
    write_add_ctg_zip(&nested);
    let package = temp.path().join("results.zip");
    result_zip(&package, &nested, std::slice::from_ref(&saved), false);
    let cancelled = Cell::new(false);
    let result = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |step| {
            if step.stage == "sync_add_ctg_catalog" {
                cancelled.set(true);
            }
        },
        &mut || cancelled.get(),
    );
    assert!(result.unwrap_err().to_string().contains("cancel"));
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), before);
    assert!(
        !outcome
            .workspace_root
            .join("data/derived_ctgs/gap_filled.fa")
            .exists()
    );
    Connection::open(&outcome.project_db_path).unwrap().execute("UPDATE project_assembly_view_state SET final_path_by_chr_json='{}' WHERE project_id=?1", [project]).unwrap();
    let error = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap_err();
    assert!(
        error.to_string().contains("Final Path changed"),
        "{error:#}"
    );
}

#[test]
fn degap_later_collection_imports_only_new_candidates_and_rejects_changed_history() {
    let temp = tempdir().unwrap();
    let (outcome, project) = import_workspace_with_project(temp.path());
    let first = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"a".repeat(64),
    );
    let second = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"b".repeat(64),
    );
    let nested = temp.path().join("first.zip");
    write_add_ctg_zip(&nested);
    let next = temp.path().join("second.zip");
    let mut input = zip::ZipArchive::new(fs::File::open(&nested).unwrap()).unwrap();
    let mut output = zip::ZipWriter::new(fs::File::create(&next).unwrap());
    for index in 0..input.len() {
        let mut file = input.by_index(index).unwrap();
        let name = file.name().replace("gap_filled", "gap_second");
        let mut text = String::new();
        std::io::Read::read_to_string(&mut file, &mut text).unwrap();
        output
            .start_file(name, zip::write::FileOptions::default())
            .unwrap();
        let mut text = text.replace("gap_filled", "gap_second");
        if file.name() == "gpm_server/metadata/track_member_orders.tsv" {
            // The real collector stages the existing Server candidates too.
            text = text.replace(
                "ds_a\tr\tds_a\td\t2\n",
                "ds_a\tr\tderived_ctg\tgap_filled\t2\nds_a\tr\tds_a\td\t3\n",
            );
        }
        output.write_all(text.as_bytes()).unwrap();
    }
    output.finish().unwrap();
    let package = temp.path().join("results.zip");
    result_zip(&package, &nested, std::slice::from_ref(&first), false);
    import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap();
    let before = count_rows(&outcome.project_db_path, "source_seq");
    let third = receipt(
        &outcome.workspace_root,
        &outcome.project_db_path,
        project,
        &"c".repeat(64),
    );
    // The old candidate must survive rollback if a later new candidate fails.
    result_zip_candidates(
        &package,
        &[nested.clone(), next.clone(), next.clone()],
        &[first.clone(), second.clone(), third],
        false,
    );
    assert!(
        import_degap_results_with_hooks(
            &package,
            &outcome.workspace_root,
            project,
            &mut |_| {},
            &mut || false
        )
        .is_err()
    );
    assert_eq!(count_rows(&outcome.project_db_path, "source_seq"), before);
    assert!(
        outcome
            .workspace_root
            .join("data/derived_ctgs/gap_filled.fa")
            .is_file()
    );
    assert!(
        !outcome
            .workspace_root
            .join("data/derived_ctgs/gap_second.fa")
            .exists()
    );
    assert!(
        !outcome
            .workspace_root
            .join(format!("metadata/degap_imports/{}.json", "b".repeat(64)))
            .exists()
    );
    result_zip_candidates(&package, &[nested, next], &[first, second], false);
    let (results, _) = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap();
    assert_eq!(results.len(), 1);
    assert_eq!(results[0]["ctgName"], "gap_second");
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq"),
        before + 1
    );
    let ledger = outcome
        .workspace_root
        .join(format!("metadata/degap_imports/{}.json", "a".repeat(64)));
    let mut saved: Value = serde_json::from_slice(&fs::read(&ledger).unwrap()).unwrap();
    saved["delivery"]["sha256"] = json!("0".repeat(64));
    fs::write(ledger, serde_json::to_vec(&saved).unwrap()).unwrap();
    let error = import_degap_results_with_hooks(
        &package,
        &outcome.workspace_root,
        project,
        &mut |_| {},
        &mut || false,
    )
    .unwrap_err();
    assert!(
        error.to_string().contains("previously imported"),
        "{error:#}"
    );
    assert_eq!(
        count_rows(&outcome.project_db_path, "source_seq"),
        before + 1
    );
}
