//! Source-group delta reads for an already complete in-session Preview input.
//! Global IDs/order are always returned. Clients must reject an incomplete merge.
use super::{ChrViewCtgItem, list_chr_view_ctgs_with_source_scope};
use anyhow::{Result, ensure};
use rusqlite::{Connection, params};
use serde::Deserialize;
use std::{
    collections::{BTreeSet, HashSet},
    path::Path,
};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PreviewSourceScope {
    pub dirty_chr_names: Vec<String>,
    pub source_seq_ids: Vec<i64>,
    pub dataset_ids: Vec<i64>,
}
pub struct PreviewSourceDelta {
    pub items: Vec<ChrViewCtgItem>,
    pub source_seq_ids: Vec<i64>,
    pub ordered_ctg_ids: Vec<i64>,
    pub full: bool,
}
pub fn read_preview_source_delta(
    db: &Path,
    project_id: i64,
    scope: &PreviewSourceScope,
) -> Result<PreviewSourceDelta> {
    let conn = crate::db::open_workspace_db(db)?;
    let tx = conn.unchecked_transaction()?;
    let result = read_with_connection(&tx, project_id, scope)?;
    tx.commit()?;
    Ok(result)
}
fn read_with_connection(
    conn: &Connection,
    project_id: i64,
    scope: &PreviewSourceScope,
) -> Result<PreviewSourceDelta> {
    ensure!(
        !scope.dirty_chr_names.is_empty() && scope.dirty_chr_names.len() <= 4096,
        "invalid Preview dirty chromosome scope"
    );
    ensure!(
        scope.source_seq_ids.len() <= 100000 && scope.dataset_ids.len() <= 4096,
        "Preview source scope too large"
    );
    ensure!(
        scope
            .dirty_chr_names
            .iter()
            .all(|s| !s.is_empty() && s != "*")
            && scope.source_seq_ids.iter().all(|id| *id > 0)
            && scope.dataset_ids.iter().all(|id| *id > 0),
        "invalid Preview source scope"
    );
    let dirty = scope.dirty_chr_names.iter().collect::<HashSet<_>>();
    let datasets = scope.dataset_ids.iter().collect::<HashSet<_>>();
    let mut source_ids = scope
        .source_seq_ids
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    // Same project-wide ordering as the full source reader, including reverse fragments.
    let mut stmt=conn.prepare("SELECT c.id,s.source_seq_id,c.assigned_chr_name,ss.dataset_id FROM assembly_ctg c
  LEFT JOIN assembly_seq s ON s.id=c.assembly_seq_id LEFT JOIN source_seq ss ON ss.id=s.source_seq_id
  WHERE c.project_id=?1 ORDER BY CASE WHEN c.assigned_chr_name IS NULL OR c.assigned_chr_name='' THEN 1 ELSE 0 END,
  c.assigned_chr_name,c.chr_order,c.anchor_start,s.source_seq_id,CASE WHEN s.orient='-' THEN -s.source_end ELSE s.source_start END,c.id")?;
    let rows = stmt
        .query_map(params![project_id], |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, Option<i64>>(1)?,
                r.get::<_, Option<String>>(2)?,
                r.get::<_, Option<i64>>(3)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    for (_, source, chr, dataset) in &rows {
        if (chr.as_ref().is_some_and(|s| dirty.contains(s))
            || dataset.as_ref().is_some_and(|d| datasets.contains(d)))
            && let Some(id) = source
        {
            source_ids.insert(*id);
        }
    }
    // Broad dependency closures must not turn the optional delta into a more
    // expensive full read with restricted-source/co-assignment batching.
    let selected = rows
        .iter()
        .filter(|(_, source, _, _)| source.is_some_and(|id| source_ids.contains(&id)))
        .count();
    let full = selected.saturating_mul(4) >= rows.len().saturating_mul(3);
    let source_seq_ids = source_ids.into_iter().collect::<Vec<_>>();
    let items = list_chr_view_ctgs_with_source_scope(
        conn,
        project_id,
        None,
        None,
        false,
        if full { None } else { Some(&source_seq_ids) },
    )?;
    let ordered_ctg_ids = rows.iter().map(|r| r.0).collect();
    Ok(PreviewSourceDelta {
        items,
        source_seq_ids,
        ordered_ctg_ids,
        full,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn seed() -> Connection {
        let c = Connection::open_in_memory().unwrap();
        crate::source_fragments::tests::seed(&c, "AANAAA", "-");
        crate::source_fragments::split_new_source_instances(&c, 1, 0).unwrap();
        c.execute_batch("INSERT INTO reference_chr(id,reference_genome_id,chr_name,chr_order,length) VALUES(2,1,'Chr02',2,1000);
  INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) VALUES(2,1,'other',2,100);
  INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at) VALUES(100,1,2,'other','+',1,100,'0');
  INSERT INTO assembly_ctg(id,project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at) VALUES(100,1,100,'other','Chr02',2,0,'+','manual','0');").unwrap();
        c
    }
    fn scope() -> PreviewSourceScope {
        PreviewSourceScope {
            dirty_chr_names: vec!["Chr01".into()],
            source_seq_ids: vec![1],
            dataset_ids: vec![],
        }
    }
    fn full(c: &Connection) -> Vec<ChrViewCtgItem> {
        super::super::list_chr_view_ctgs_with_connection_options(c, 1, None, None, false).unwrap()
    }
    fn equivalent(c: &Connection, delta: &PreviewSourceDelta) {
        let all = full(c);
        assert_eq!(
            delta.ordered_ctg_ids,
            all.iter().map(|x| x.assembly_ctg_id).collect::<Vec<_>>()
        );
        for item in &delta.items {
            assert_eq!(
                Some(item),
                all.iter()
                    .find(|x| x.assembly_ctg_id == item.assembly_ctg_id)
            );
        }
    }
    #[test]
    fn source_closure_keeps_reverse_fragment_provenance_coassignment_and_unplaced_members() {
        let c = seed();
        c.execute_batch("UPDATE assembly_ctg SET assigned_chr_name='Chr02' WHERE assembly_seq_id=(SELECT MIN(id) FROM assembly_seq WHERE instance_key LIKE 'n-fragment:%');").unwrap();
        c.execute_batch("PRAGMA query_only=ON").unwrap();
        let d = read_with_connection(&c, 1, &scope()).unwrap();
        assert!(d.items.len() < full(&c).len());
        assert!(
            d.items
                .iter()
                .any(|x| x.assigned_chr_name.as_deref() == Some("Chr02"))
        );
        assert!(d.items.iter().all(|x| x.co_assigned_chr_names
            == if x.assigned_chr_name.as_deref() == Some("Chr01") {
                vec!["Chr02"]
            } else {
                vec!["Chr01"]
            }));
        equivalent(&c, &d);
    }
    #[test]
    fn old_source_closure_survives_deletion_and_dataset_scope_includes_renamed_unplaced_candidates()
    {
        let c = seed();
        c.execute_batch("DELETE FROM assembly_ctg WHERE assigned_chr_name='Chr01';")
            .unwrap();
        let mut request = scope();
        let d = read_with_connection(&c, 1, &request).unwrap();
        assert!(d.items.is_empty());
        assert!(d.source_seq_ids.contains(&1));
        equivalent(&c, &d);
        request.dataset_ids.push(1);
        let d = read_with_connection(&c, 1, &request).unwrap();
        assert_eq!(d.items.len(), 1);
        equivalent(&c, &d);
    }
    #[test]
    fn changed_source_groups_and_more_than_legacy_sqlite_bind_limit_preserve_full_order() {
        let c = seed();
        c.execute_batch("WITH RECURSIVE ids(n) AS(SELECT 3 UNION ALL SELECT n+1 FROM ids WHERE n<1302) INSERT INTO source_seq(id,dataset_id,seq_name,seq_order,length) SELECT n,1,'source'||n,n,100 FROM ids;
 INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at) SELECT id+1000,1,id,'ordinary'||id,'-',1,100,'0' FROM source_seq WHERE id>=3;
 INSERT INTO assembly_ctg(project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at) SELECT 1,id,'ctg'||id,'Chr01',1,id*10,'+','manual','0' FROM assembly_seq WHERE id>=1003;").unwrap();
        let mut request = scope();
        request.source_seq_ids = (1..=1302).collect();
        let d = read_with_connection(&c, 1, &request).unwrap();
        assert_eq!(d.items.len(), full(&c).len());
        equivalent(&c, &d);
    }
    #[test]
    fn invalid_scope_is_rejected_instead_of_silently_becoming_an_unbounded_query() {
        let c = seed();
        let mut request = scope();
        request.dirty_chr_names = vec!["*".into()];
        assert!(read_with_connection(&c, 1, &request).is_err());
        request = scope();
        request.source_seq_ids.push(-1);
        assert!(read_with_connection(&c, 1, &request).is_err());
    }
    #[test]
    #[ignore = "set GPM_PREVIEW_DELTA_READONLY_DB and GPM_PREVIEW_DELTA_PROFILE_OUTPUT"]
    fn profile_preview_source_delta_readonly() {
        use std::{
            collections::HashMap,
            fs::{self, OpenOptions},
            path::PathBuf,
            time::Instant,
        };
        let path = PathBuf::from(
            std::env::var("GPM_PREVIEW_DELTA_READONLY_DB").expect("read-only database"),
        );
        let output = PathBuf::from(
            std::env::var("GPM_PREVIEW_DELTA_PROFILE_OUTPUT").expect("private report path"),
        );
        assert!(
            !output
                .parent()
                .unwrap()
                .canonicalize()
                .unwrap()
                .starts_with(path.parent().unwrap().canonicalize().unwrap())
        );
        let before = fs::metadata(&path).unwrap();
        let conn =
            Connection::open_with_flags(&path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
        conn.execute_batch("PRAGMA query_only=ON; BEGIN;").unwrap();
        let mut samples = Vec::new();
        for chr in ["chr1", "chr7"] {
            for sample in 0..3 {
                let start = Instant::now();
                let original = full(&conn);
                let full_ms = start.elapsed().as_secs_f64() * 1000.0;
                let source_seq_ids = original
                    .iter()
                    .filter(|ctg| {
                        ctg.assigned_chr_name.as_deref() == Some(chr)
                            || ctg.co_assigned_chr_names.iter().any(|n| n == chr)
                    })
                    .filter_map(|ctg| ctg.origin_source_seq_id)
                    .collect::<BTreeSet<_>>()
                    .into_iter()
                    .collect();
                let scope = PreviewSourceScope {
                    dirty_chr_names: vec![chr.into()],
                    source_seq_ids,
                    dataset_ids: vec![1],
                };
                let start = Instant::now();
                let delta = read_with_connection(&conn, 1, &scope).unwrap();
                let delta_ms = start.elapsed().as_secs_f64() * 1000.0;
                let groups = delta.source_seq_ids.iter().copied().collect::<HashSet<_>>();
                let delta_count = delta.items.len();
                let mut merged = original
                    .iter()
                    .filter(|ctg| {
                        !ctg.origin_source_seq_id
                            .is_some_and(|id| groups.contains(&id))
                    })
                    .map(|ctg| (ctg.assembly_ctg_id, ctg.clone()))
                    .collect::<HashMap<_, _>>();
                for ctg in delta.items {
                    assert!(merged.insert(ctg.assembly_ctg_id, ctg).is_none());
                }
                let merged = delta
                    .ordered_ctg_ids
                    .iter()
                    .map(|id| merged.remove(id).unwrap())
                    .collect::<Vec<_>>();
                assert_eq!(merged, original);
                samples.push(serde_json::json!({"chr":chr,"sample":sample,"fullMs":full_ms,"deltaMs":delta_ms,"fullCtgs":original.len(),"deltaCtgs":delta_count,"orderedIds":delta.ordered_ctg_ids.len(),"allFieldsAndOrderIdentical":true,"originalSourceDatasetClosure":true}));
            }
        }
        conn.execute_batch("ROLLBACK;").unwrap();
        let after = fs::metadata(&path).unwrap();
        assert_eq!(before.len(), after.len());
        assert_eq!(before.modified().unwrap(), after.modified().unwrap());
        let report = serde_json::json!({"readonly":true,"databaseUnchanged":true,"scope":"Rust read-only source-group reads only; no IPC/render/cold-cache guarantee", "samples":samples});
        serde_json::to_writer_pretty(
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(output)
                .unwrap(),
            &report,
        )
        .unwrap();
        println!("{report}");
    }
}
