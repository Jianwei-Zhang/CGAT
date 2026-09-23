//! Lossless IPC encoding: share PAF hit attributes across its CIGAR fragments.
use std::collections::HashMap;

use serde::Serialize;

use super::ReferenceTrackMemberItem;

type HitGroup = (i64, i64, i64, String, f64, i64);
type HitRow = (usize, i64, i64, i64, i64, i64, i64, i64, i64);

#[derive(Debug, Serialize)]
pub struct CompactReferenceTracks {
    pub encoding: &'static str,
    pub items: Vec<CompactReferenceMember>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompactReferenceMember {
    source_kind: String,
    reference_chr_id: i64,
    reference_chr_name: String,
    segment_order: i64,
    segment_start_bp: i64,
    segment_end_bp: i64,
    name: String,
    anchor_start: i64,
    total_length: i64,
    ref_orient: String,
    // [hit_id, dataset_id, source_seq_id, strand, identity_pct, mapq]
    hit_groups: Vec<HitGroup>,
    // [group, query_start, query_end, ref_start, ref_end, matches, block, ctg_start, ctg_end]
    hit_rows: Vec<HitRow>,
}

pub fn compact_reference_track_members(
    items: Vec<ReferenceTrackMemberItem>,
) -> CompactReferenceTracks {
    CompactReferenceTracks {
        encoding: "reference-hits-v1",
        items: items
            .into_iter()
            .map(|item| {
                let mut group_index = HashMap::new();
                let mut hit_groups = Vec::new();
                let mut hit_rows = Vec::with_capacity(item.hits.len());
                for hit in item.hits {
                    // A database hit ID owns these immutable attributes; rows keep
                    // their original order even when fragments from hits interleave.
                    let index = *group_index.entry(hit.hit_id).or_insert_with(|| {
                        let index = hit_groups.len();
                        hit_groups.push((
                            hit.hit_id,
                            hit.dataset_id,
                            hit.source_seq_id,
                            hit.strand,
                            hit.identity_pct,
                            hit.mapq,
                        ));
                        index
                    });
                    hit_rows.push((
                        index,
                        hit.query_start,
                        hit.query_end,
                        hit.ref_start,
                        hit.ref_end,
                        hit.match_length,
                        hit.block_length,
                        hit.ctg_start,
                        hit.ctg_end,
                    ));
                }
                CompactReferenceMember {
                    source_kind: item.source_kind,
                    reference_chr_id: item.reference_chr_id,
                    reference_chr_name: item.reference_chr_name,
                    segment_order: item.segment_order,
                    segment_start_bp: item.segment_start_bp,
                    segment_end_bp: item.segment_end_bp,
                    name: item.name,
                    anchor_start: item.anchor_start,
                    total_length: item.total_length,
                    ref_orient: item.ref_orient,
                    hit_groups,
                    hit_rows,
                }
            })
            .collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::main_view::ReferenceTrackHitItem;

    #[test]
    fn compact_hits_keep_interleaved_order_and_exact_coordinates() {
        let a = ReferenceTrackHitItem {
            hit_id: 1,
            dataset_id: 2,
            source_seq_id: 40,
            strand: "-".into(),
            identity_pct: 98.44,
            mapq: 60,
            query_start: 901,
            query_end: 910,
            ref_start: 1001,
            ref_end: 1010,
            match_length: 9,
            block_length: 10,
            ctg_start: 1,
            ctg_end: 10,
        };
        let b = ReferenceTrackHitItem {
            hit_id: 2,
            strand: "+".into(),
            mapq: 0,
            ..a.clone()
        };
        let c = ReferenceTrackHitItem {
            query_start: 881,
            query_end: 900,
            ref_start: 1011,
            ref_end: 1030,
            match_length: 19,
            block_length: 20,
            ctg_start: 11,
            ctg_end: 30,
            ..a.clone()
        };
        let item = ReferenceTrackMemberItem {
            source_kind: "ref_segment".into(),
            reference_chr_id: 6,
            reference_chr_name: "chr06".into(),
            segment_order: 2,
            segment_start_bp: 1001,
            segment_end_bp: 5000,
            name: "ref_chr06".into(),
            anchor_start: 1001,
            total_length: 4000,
            ref_orient: "+".into(),
            hits: vec![a, b, c],
        };
        let empty = ReferenceTrackMemberItem {
            hits: vec![],
            ..item.clone()
        };
        let result = compact_reference_track_members(vec![item, empty]);
        assert_eq!(result.items[0].hit_groups.len(), 2);
        assert_eq!(
            result.items[0].hit_groups[0],
            (1, 2, 40, "-".into(), 98.44, 60)
        );
        assert_eq!(
            result.items[0].hit_rows,
            vec![
                (0, 901, 910, 1001, 1010, 9, 10, 1, 10),
                (1, 901, 910, 1001, 1010, 9, 10, 1, 10),
                (0, 881, 900, 1011, 1030, 19, 20, 11, 30),
            ]
        );
        assert!(result.items[1].hit_rows.is_empty());
        let value = serde_json::to_value(result).unwrap();
        assert_eq!(value["encoding"], "reference-hits-v1");
        assert_eq!(value["items"][0]["segmentStartBp"], 1001);
        assert!(value["items"][0].get("hits").is_none());
    }
}
