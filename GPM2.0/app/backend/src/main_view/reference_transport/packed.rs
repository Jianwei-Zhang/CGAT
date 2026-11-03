//! v2 retains every v1 field and row in order, but stores signed coordinate
//! deltas per PAF group as varints. The UI can retain this immutable payload
//! without constructing millions of hit objects on an unrelated Main render.
use std::collections::HashMap;

use serde::Serialize;

use super::super::ReferenceTrackMemberItem;
use super::HitGroup;

pub const ENCODING: &str = "reference-hits-v2";

#[derive(Debug, Serialize)]
pub struct PackedReferenceTracks {
    pub encoding: &'static str,
    pub items: Vec<PackedReferenceMember>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PackedReferenceMember {
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
    // Same immutable attributes and first-seen group order as compact v1.
    hit_groups: Vec<HitGroup>,
    hit_count: usize,
    // Per row: unsigned group index, then eight ZigZag varint deltas against
    // that group's previous row (zero for its first row). Original row order.
    // Fields: queryStart/End, refStart/End, matches, block, ctgStart/End.
    hit_data: String,
}

fn put_varint(mut value: u64, bytes: &mut Vec<u8>) {
    while value >= 128 {
        bytes.push((value as u8) | 128);
        value >>= 7;
    }
    bytes.push(value as u8);
}

fn put_delta(value: i64, previous: i64, bytes: &mut Vec<u8>) {
    if let Some(delta) = value.checked_sub(previous) {
        put_varint(((delta as u64) << 1) ^ ((delta >> 63) as u64), bytes);
    } else {
        // Only the two i64 extremes need this wider fallback. Ordinary genome
        // coordinates stay on the native u64 varint path.
        let delta = i128::from(value) - i128::from(previous);
        let mut zigzag = (delta.unsigned_abs() << 1) - u128::from(delta < 0);
        while zigzag >= 128 {
            bytes.push((zigzag as u8) | 128);
            zigzag >>= 7;
        }
        bytes.push(zigzag as u8);
    }
}

// Standard padded base64, kept local to this transport to avoid a new runtime
// dependency. The decoder uses the WebView's existing atob implementation.
fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut text = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let a = chunk[0] as usize;
        let b = chunk.get(1).copied().unwrap_or(0) as usize;
        let c = chunk.get(2).copied().unwrap_or(0) as usize;
        text.push(ALPHABET[a >> 2] as char);
        text.push(ALPHABET[((a & 3) << 4) | (b >> 4)] as char);
        text.push(if chunk.len() > 1 {
            ALPHABET[((b & 15) << 2) | (c >> 6)] as char
        } else {
            '='
        });
        text.push(if chunk.len() > 2 {
            ALPHABET[c & 63] as char
        } else {
            '='
        });
    }
    text
}

pub fn pack_reference_track_members(items: Vec<ReferenceTrackMemberItem>) -> PackedReferenceTracks {
    PackedReferenceTracks {
        encoding: ENCODING,
        items: items
            .into_iter()
            .map(|item| {
                let mut index = HashMap::new();
                let mut hit_groups = Vec::new();
                let mut previous: Vec<[i64; 8]> = Vec::new();
                let hit_count = item.hits.len();
                let mut bytes = Vec::with_capacity(hit_count.saturating_mul(9));
                for hit in item.hits {
                    let group = *index.entry(hit.hit_id).or_insert_with(|| {
                        let group = hit_groups.len();
                        hit_groups.push((
                            hit.hit_id,
                            hit.dataset_id,
                            hit.source_seq_id,
                            hit.strand.clone(),
                            hit.identity_pct,
                            hit.mapq,
                        ));
                        previous.push([0; 8]);
                        group
                    });
                    put_varint(group as u64, &mut bytes);
                    let row = [
                        hit.query_start,
                        hit.query_end,
                        hit.ref_start,
                        hit.ref_end,
                        hit.match_length,
                        hit.block_length,
                        hit.ctg_start,
                        hit.ctg_end,
                    ];
                    for (column, value) in row.iter().enumerate() {
                        put_delta(*value, previous[group][column], &mut bytes);
                    }
                    previous[group] = row;
                }
                PackedReferenceMember {
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
                    hit_count,
                    hit_data: base64(&bytes),
                }
            })
            .collect(),
    }
}

#[cfg(test)]
#[path = "packed/profile.rs"]
mod profile;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::main_view::ReferenceTrackHitItem;

    #[test]
    fn signed_deltas_handle_i64_extremes_without_wrapping() {
        for (value, previous) in [(i64::MIN, i64::MAX), (i64::MAX, i64::MIN), (0, -1), (-1, 0)] {
            let mut bytes = Vec::new();
            put_delta(value, previous, &mut bytes);
            let unsigned = bytes
                .iter()
                .enumerate()
                .fold(0u128, |n, (i, b)| n | (u128::from(b & 127) << (i * 7)));
            let signed = if unsigned & 1 == 1 {
                -((unsigned >> 1) as i128) - 1
            } else {
                (unsigned >> 1) as i128
            };
            assert_eq!(signed, i128::from(value) - i128::from(previous));
        }
    }

    #[test]
    fn standard_base64_vectors() {
        for (input, expected) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
            ("fooba", "Zm9vYmE="),
            ("foobar", "Zm9vYmFy"),
        ] {
            assert_eq!(base64(input.as_bytes()), expected);
        }
    }

    #[test]
    fn packed_rows_match_shared_cross_language_fixture() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/testdata/reference_transport_v2.json"
        )))
        .unwrap();
        let items = fixture["legacy"]["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| {
                let groups = item["hitGroups"].as_array().unwrap();
                ReferenceTrackMemberItem {
                    source_kind: item["sourceKind"].as_str().unwrap().into(),
                    reference_chr_id: item["referenceChrId"].as_i64().unwrap(),
                    reference_chr_name: item["referenceChrName"].as_str().unwrap().into(),
                    segment_order: item["segmentOrder"].as_i64().unwrap(),
                    segment_start_bp: item["segmentStartBp"].as_i64().unwrap(),
                    segment_end_bp: item["segmentEndBp"].as_i64().unwrap(),
                    name: item["name"].as_str().unwrap().into(),
                    anchor_start: item["anchorStart"].as_i64().unwrap(),
                    total_length: item["totalLength"].as_i64().unwrap(),
                    ref_orient: item["refOrient"].as_str().unwrap().into(),
                    hits: item["hitRows"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(|row| {
                            let g = &groups[row[0].as_u64().unwrap() as usize];
                            ReferenceTrackHitItem {
                                hit_id: g[0].as_i64().unwrap(),
                                dataset_id: g[1].as_i64().unwrap(),
                                source_seq_id: g[2].as_i64().unwrap(),
                                strand: g[3].as_str().unwrap().into(),
                                identity_pct: g[4].as_f64().unwrap(),
                                mapq: g[5].as_i64().unwrap(),
                                query_start: row[1].as_i64().unwrap(),
                                query_end: row[2].as_i64().unwrap(),
                                ref_start: row[3].as_i64().unwrap(),
                                ref_end: row[4].as_i64().unwrap(),
                                match_length: row[5].as_i64().unwrap(),
                                block_length: row[6].as_i64().unwrap(),
                                ctg_start: row[7].as_i64().unwrap(),
                                ctg_end: row[8].as_i64().unwrap(),
                            }
                        })
                        .collect(),
                }
            })
            .collect();
        assert_eq!(
            serde_json::to_value(pack_reference_track_members(items)).unwrap(),
            fixture["packed"]
        );
    }
}
