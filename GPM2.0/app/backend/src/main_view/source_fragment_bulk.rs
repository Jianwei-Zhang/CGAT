//! Bounded batched provenance reads. Preserve the scalar reader's source/gap
//! semantics without one prepare/query roundtrip per displayed contig.
use super::{ChrViewCtgItem, SourceFragment};
use anyhow::Result;
use rusqlite::{Connection, params_from_iter};
use std::collections::HashMap;

pub(super) fn populate_source_fragments(
    conn: &Connection,
    project_id: i64,
    ctgs: &mut [ChrViewCtgItem],
) -> Result<()> {
    let mut rows = Vec::new();
    for chunk in ctgs.chunks(400) {
        let mut bind = vec![project_id];
        bind.extend(chunk.iter().map(|ctg| ctg.assembly_ctg_id));
        let sql=format!("SELECT c.id,s.source_seq_id,s.instance_key,s.source_start,s.source_end,ss.length
            FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id JOIN source_seq ss ON ss.id=s.source_seq_id
            WHERE c.project_id=? AND c.id IN ({})
            AND (s.instance_key LIKE 'n-fragment:%' OR s.instance_key LIKE 'manual-fragment:%')",vec!["?";chunk.len()].join(","));
        let mut stmt = conn.prepare(&sql)?;
        rows.extend(
            stmt.query_map(params_from_iter(bind), |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, i64>(3)?,
                    r.get::<_, i64>(4)?,
                    r.get::<_, i64>(5)?,
                ))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?,
        );
    }
    let mut sources = rows.iter().map(|row| row.1).collect::<Vec<_>>();
    sources.sort_unstable();
    sources.dedup();
    let mut gaps: HashMap<i64, Vec<(i64, i64)>> = HashMap::new();
    for chunk in sources.chunks(400) {
        let sql = format!(
            "SELECT source_seq_id,start_bp,end_bp FROM source_seq_n_region WHERE source_seq_id IN ({}) ORDER BY source_seq_id,start_bp,end_bp",
            vec!["?"; chunk.len()].join(",")
        );
        let mut stmt = conn.prepare(&sql)?;
        for row in stmt.query_map(params_from_iter(chunk), |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, i64>(2)?,
            ))
        })? {
            let (source, start, end) = row?;
            gaps.entry(source).or_default().push((start, end));
        }
    }
    let mut fragments = HashMap::new();
    for (ctg, source, key, start, end, length) in rows {
        let source_gaps = gaps.get(&source).map(Vec::as_slice).unwrap_or(&[]);
        fragments.insert(
            ctg,
            SourceFragment {
                source_seq_id: source,
                group_key: key
                    .rsplit_once(':')
                    .map(|(group, _)| group)
                    .unwrap_or(&key)
                    .into(),
                source_start: start,
                source_end: end,
                source_length: length,
                gap_before_bp: source_gaps
                    .iter()
                    .find(|(_, right)| *right == start - 1)
                    .map(|(l, r)| r - l + 1)
                    .unwrap_or(0),
                gap_after_bp: source_gaps
                    .iter()
                    .find(|(left, _)| *left == end + 1)
                    .map(|(l, r)| r - l + 1)
                    .unwrap_or(0),
            },
        );
    }
    for ctg in ctgs {
        ctg.source_fragment = fragments.remove(&ctg.assembly_ctg_id);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn batched_fragments_match_scalar_reader_for_normal_manual_split_and_reverse_sources() {
        for orient in ["+", "-"] {
            let conn = Connection::open_in_memory().unwrap();
            crate::source_fragments::tests::seed(
                &conn,
                "NAANANN AAN".replace(' ', "").as_str(),
                orient,
            );
            crate::source_fragments::split_new_source_instances(&conn, 1, 0).unwrap();
            // Include a non-fragment and a manual instance alongside automatic splits.
            conn.execute_batch("INSERT INTO assembly_seq(project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at) VALUES(1,1,'manual-fragment:source:cut:99','+',2,3,'0');
                INSERT INTO assembly_ctg(project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at)
                VALUES(1,last_insert_rowid(),'manual','Chr01',10,0,'+','manual','0');
                INSERT INTO assembly_seq(project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at) VALUES(1,1,'ordinary','+',1,10,'0');
                INSERT INTO assembly_ctg(project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at)
                VALUES(1,last_insert_rowid(),'ordinary','Chr01',11,0,'+','manual','0');").unwrap();
            let ctgs = super::super::list_chr_view_ctgs_with_connection_options(
                &conn, 1, None, None, false,
            )
            .unwrap();
            for ctg in ctgs {
                assert_eq!(
                    ctg.source_fragment,
                    super::super::load_source_fragment(&conn, ctg.assembly_ctg_id).unwrap()
                );
            }
        }
    }
    #[test]
    fn bounded_batches_keep_more_than_sqlite_legacy_parameter_limit() {
        let conn = Connection::open_in_memory().unwrap();
        crate::source_fragments::tests::seed(&conn, "AANA", "+");
        conn.execute_batch("WITH RECURSIVE ids(n) AS (SELECT 2 UNION ALL SELECT n+1 FROM ids WHERE n<1300)
            INSERT INTO assembly_seq(id,project_id,source_seq_id,instance_key,orient,source_start,source_end,created_at)
            SELECT n,1,1,'manual-fragment:group:'||n,'+',1,2,'0' FROM ids;
            INSERT INTO assembly_ctg(project_id,assembly_seq_id,name,assigned_chr_name,chr_order,anchor_start,ref_orient,placement_mode,created_at)
            SELECT 1,id,'ctg'||id,'Chr01',id,id*5,'+','manual','0' FROM assembly_seq WHERE id>1;").unwrap();
        let ctgs = super::super::list_chr_view_ctgs_with_connection_options(
            &conn,
            1,
            Some("Chr01"),
            None,
            false,
        )
        .unwrap();
        assert_eq!(ctgs.len(), 1300);
        for ctg in ctgs {
            assert_eq!(
                ctg.source_fragment,
                super::super::load_source_fragment(&conn, ctg.assembly_ctg_id).unwrap()
            );
        }
    }
}
