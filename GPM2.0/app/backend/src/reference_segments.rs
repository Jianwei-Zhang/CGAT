use anyhow::{Result, bail};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReferenceGapInterval {
    pub start_bp: i64,
    pub end_bp: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReferenceSegment {
    pub reference_chr_name: String,
    pub segment_order: i64,
    pub start_bp: i64,
    pub end_bp: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SplitReferenceBlock {
    pub query_start_bp: i64,
    pub query_end_bp: i64,
    pub ref_start_bp: i64,
    pub ref_end_bp: i64,
}

pub fn detect_reference_segments(
    reference_chr_name: &str,
    sequence: &str,
    min_gap_run_bp: usize,
) -> Vec<ReferenceSegment> {
    let seq_len = sequence.len() as i64;
    if seq_len <= 0 {
        return Vec::new();
    }

    let gaps = detect_reference_gap_intervals(sequence, min_gap_run_bp);
    let mut segments = Vec::new();
    let mut next_start = 1_i64;

    for gap in gaps {
        if next_start < gap.start_bp {
            segments.push(ReferenceSegment {
                reference_chr_name: reference_chr_name.to_string(),
                segment_order: segments.len() as i64 + 1,
                start_bp: next_start,
                end_bp: gap.start_bp - 1,
            });
        }
        next_start = gap.end_bp + 1;
    }

    if next_start <= seq_len {
        segments.push(ReferenceSegment {
            reference_chr_name: reference_chr_name.to_string(),
            segment_order: segments.len() as i64 + 1,
            start_bp: next_start,
            end_bp: seq_len,
        });
    }

    segments
}

pub fn detect_reference_gap_intervals(
    sequence: &str,
    min_gap_run_bp: usize,
) -> Vec<ReferenceGapInterval> {
    collect_reference_gap_intervals(sequence, min_gap_run_bp)
}

pub fn split_paf_hit_by_reference_gaps(
    query_start_bp: i64,
    query_end_bp: i64,
    ref_start_bp: i64,
    ref_end_bp: i64,
    strand: &str,
    cg_tag: &str,
    gaps: &[ReferenceGapInterval],
) -> Result<Vec<SplitReferenceBlock>> {
    if query_start_bp < 1 || query_end_bp < query_start_bp {
        bail!("invalid query range {}..{}", query_start_bp, query_end_bp);
    }
    if ref_start_bp < 1 || ref_end_bp < ref_start_bp {
        bail!("invalid reference range {}..{}", ref_start_bp, ref_end_bp);
    }
    if strand != "+" && strand != "-" {
        bail!("unsupported strand {}", strand);
    }

    let ops = parse_cg_ops(cg_tag)?;
    let expected_query_span = query_end_bp - query_start_bp + 1;
    let expected_ref_span = ref_end_bp - ref_start_bp + 1;
    let actual_query_span: i64 = ops
        .iter()
        .filter(|(_, op)| consumes_query(*op))
        .map(|(len, _)| *len)
        .sum();
    let actual_ref_span: i64 = ops
        .iter()
        .filter(|(_, op)| consumes_ref(*op))
        .map(|(len, _)| *len)
        .sum();

    if actual_query_span != expected_query_span {
        bail!(
            "cg tag query span {} does not match paf query span {}",
            actual_query_span,
            expected_query_span
        );
    }
    if actual_ref_span != expected_ref_span {
        bail!(
            "cg tag reference span {} does not match paf reference span {}",
            actual_ref_span,
            expected_ref_span
        );
    }

    let normalized_gaps = normalize_reference_gaps(gaps);
    let mut gap_index = 0_usize;
    let mut query_cursor = if strand == "+" {
        query_start_bp
    } else {
        query_end_bp
    };
    let mut ref_cursor = ref_start_bp;
    let mut blocks = Vec::new();

    for (len, op) in ops {
        match op {
            'M' | '=' | 'X' => {
                let mut remaining = len;
                while remaining > 0 {
                    while gap_index < normalized_gaps.len()
                        && normalized_gaps[gap_index].end_bp < ref_cursor
                    {
                        gap_index += 1;
                    }

                    let next_gap = normalized_gaps.get(gap_index);
                    if let Some(gap) = next_gap {
                        if gap.start_bp <= ref_cursor {
                            let overlap = (gap.end_bp - ref_cursor + 1).min(remaining);
                            advance_query_cursor(&mut query_cursor, overlap, strand);
                            ref_cursor += overlap;
                            remaining -= overlap;
                            continue;
                        }

                        let before_gap = (gap.start_bp - ref_cursor).min(remaining);
                        if before_gap > 0 {
                            push_reference_block(
                                &mut blocks,
                                &mut query_cursor,
                                &mut ref_cursor,
                                before_gap,
                                strand,
                            )?;
                            remaining -= before_gap;
                            continue;
                        }
                    }

                    push_reference_block(
                        &mut blocks,
                        &mut query_cursor,
                        &mut ref_cursor,
                        remaining,
                        strand,
                    )?;
                    remaining = 0;
                }
            }
            'I' => advance_query_cursor(&mut query_cursor, len, strand),
            'D' | 'N' => ref_cursor += len,
            _ => bail!("unsupported cg operation {}", op),
        }
    }

    let expected_query_cursor = if strand == "+" {
        query_end_bp + 1
    } else {
        query_start_bp - 1
    };
    let expected_ref_cursor = ref_end_bp + 1;
    if query_cursor != expected_query_cursor {
        bail!(
            "query cursor ended at {}, expected {}",
            query_cursor,
            expected_query_cursor
        );
    }
    if ref_cursor != expected_ref_cursor {
        bail!(
            "reference cursor ended at {}, expected {}",
            ref_cursor,
            expected_ref_cursor
        );
    }

    Ok(blocks)
}

pub fn map_paf_query_interval_to_ref_span(
    query_start_bp: i64,
    query_end_bp: i64,
    ref_start_bp: i64,
    ref_end_bp: i64,
    strand: &str,
    cg_tag: &str,
    interval_start_bp: i64,
    interval_end_bp: i64,
) -> Result<Option<SplitReferenceBlock>> {
    if query_start_bp < 1 || query_end_bp < query_start_bp {
        bail!("invalid query range {}..{}", query_start_bp, query_end_bp);
    }
    if ref_start_bp < 1 || ref_end_bp < ref_start_bp {
        bail!("invalid reference range {}..{}", ref_start_bp, ref_end_bp);
    }
    if strand != "+" && strand != "-" {
        bail!("unsupported strand {}", strand);
    }
    if interval_start_bp < query_start_bp
        || interval_end_bp > query_end_bp
        || interval_end_bp < interval_start_bp
    {
        bail!(
            "query interval {}..{} is outside hit query range {}..{}",
            interval_start_bp,
            interval_end_bp,
            query_start_bp,
            query_end_bp
        );
    }

    let ops = parse_cg_ops(cg_tag)?;
    let expected_query_span = query_end_bp - query_start_bp + 1;
    let expected_ref_span = ref_end_bp - ref_start_bp + 1;
    let actual_query_span: i64 = ops
        .iter()
        .filter(|(_, op)| consumes_query(*op))
        .map(|(len, _)| *len)
        .sum();
    let actual_ref_span: i64 = ops
        .iter()
        .filter(|(_, op)| consumes_ref(*op))
        .map(|(len, _)| *len)
        .sum();

    if actual_query_span != expected_query_span {
        bail!(
            "cg tag query span {} does not match paf query span {}",
            actual_query_span,
            expected_query_span
        );
    }
    if actual_ref_span != expected_ref_span {
        bail!(
            "cg tag reference span {} does not match paf reference span {}",
            actual_ref_span,
            expected_ref_span
        );
    }

    let mut query_cursor = if strand == "+" {
        query_start_bp
    } else {
        query_end_bp
    };
    let mut ref_cursor = ref_start_bp;
    let mut ref_start = None::<i64>;
    let mut ref_end = None::<i64>;

    for (len, op) in ops {
        match op {
            'M' | '=' | 'X' => {
                let (op_query_start, op_query_end) = if strand == "+" {
                    (query_cursor, query_cursor + len - 1)
                } else {
                    (query_cursor - len + 1, query_cursor)
                };
                let overlap_start = op_query_start.max(interval_start_bp);
                let overlap_end = op_query_end.min(interval_end_bp);
                if overlap_start <= overlap_end {
                    let (mapped_ref_start, mapped_ref_end) = if strand == "+" {
                        (
                            ref_cursor + (overlap_start - op_query_start),
                            ref_cursor + (overlap_end - op_query_start),
                        )
                    } else {
                        (
                            ref_cursor + (op_query_end - overlap_end),
                            ref_cursor + (op_query_end - overlap_start),
                        )
                    };
                    ref_start = Some(
                        ref_start.map_or(mapped_ref_start, |value| value.min(mapped_ref_start)),
                    );
                    ref_end =
                        Some(ref_end.map_or(mapped_ref_end, |value| value.max(mapped_ref_end)));
                }
                advance_query_cursor(&mut query_cursor, len, strand);
                ref_cursor += len;
            }
            'I' => advance_query_cursor(&mut query_cursor, len, strand),
            'D' | 'N' => {
                let include_deletion = if strand == "+" {
                    query_cursor > interval_start_bp && query_cursor <= interval_end_bp
                } else {
                    query_cursor >= interval_start_bp && query_cursor < interval_end_bp
                };
                if include_deletion {
                    ref_start = Some(ref_start.map_or(ref_cursor, |value| value.min(ref_cursor)));
                    ref_end = Some(ref_end.map_or(ref_cursor + len - 1, |value| {
                        value.max(ref_cursor + len - 1)
                    }));
                }
                ref_cursor += len;
            }
            _ => bail!("unsupported cg operation {}", op),
        }
    }

    let expected_query_cursor = if strand == "+" {
        query_end_bp + 1
    } else {
        query_start_bp - 1
    };
    let expected_ref_cursor = ref_end_bp + 1;
    if query_cursor != expected_query_cursor {
        bail!(
            "query cursor ended at {}, expected {}",
            query_cursor,
            expected_query_cursor
        );
    }
    if ref_cursor != expected_ref_cursor {
        bail!(
            "reference cursor ended at {}, expected {}",
            ref_cursor,
            expected_ref_cursor
        );
    }

    Ok(ref_start
        .zip(ref_end)
        .map(|(ref_start_bp, ref_end_bp)| SplitReferenceBlock {
            query_start_bp: interval_start_bp,
            query_end_bp: interval_end_bp,
            ref_start_bp,
            ref_end_bp,
        }))
}

fn collect_reference_gap_intervals(
    sequence: &str,
    min_gap_run_bp: usize,
) -> Vec<ReferenceGapInterval> {
    let threshold = min_gap_run_bp.max(1);
    let bytes = sequence.as_bytes();
    let mut gaps = Vec::new();
    let mut index = 0_usize;

    while index < bytes.len() {
        if !is_gap_base(bytes[index]) {
            index += 1;
            continue;
        }

        let run_start = index;
        while index < bytes.len() && is_gap_base(bytes[index]) {
            index += 1;
        }

        if index - run_start >= threshold {
            gaps.push(ReferenceGapInterval {
                start_bp: run_start as i64 + 1,
                end_bp: index as i64,
            });
        }
    }

    gaps
}

fn normalize_reference_gaps(gaps: &[ReferenceGapInterval]) -> Vec<ReferenceGapInterval> {
    let mut normalized: Vec<ReferenceGapInterval> = gaps
        .iter()
        .filter(|gap| gap.start_bp >= 1 && gap.end_bp >= gap.start_bp)
        .cloned()
        .collect();
    normalized.sort_by_key(|gap| (gap.start_bp, gap.end_bp));

    let mut merged: Vec<ReferenceGapInterval> = Vec::new();
    for gap in normalized {
        if let Some(last) = merged.last_mut()
            && gap.start_bp <= last.end_bp + 1
        {
            last.end_bp = last.end_bp.max(gap.end_bp);
            continue;
        }
        merged.push(gap);
    }
    merged
}

fn parse_cg_ops(cg_tag: &str) -> Result<Vec<(i64, char)>> {
    let raw = cg_tag.strip_prefix("cg:Z:").unwrap_or(cg_tag);
    if raw.is_empty() {
        bail!("cg tag is empty");
    }

    let mut ops = Vec::new();
    let mut current_len = 0_i64;
    for ch in raw.chars() {
        if let Some(digit) = ch.to_digit(10) {
            current_len = current_len
                .checked_mul(10)
                .and_then(|value| value.checked_add(i64::from(digit)))
                .ok_or_else(|| anyhow::anyhow!("cg length overflow"))?;
            continue;
        }

        if current_len <= 0 {
            bail!("cg tag is missing a length before operation {}", ch);
        }

        match ch {
            'M' | '=' | 'X' | 'I' | 'D' | 'N' => ops.push((current_len, ch)),
            _ => bail!("unsupported cg operation {}", ch),
        }
        current_len = 0;
    }

    if current_len != 0 {
        bail!("cg tag ends with a bare length");
    }

    Ok(ops)
}

fn consumes_query(op: char) -> bool {
    matches!(op, 'M' | '=' | 'X' | 'I')
}

fn consumes_ref(op: char) -> bool {
    matches!(op, 'M' | '=' | 'X' | 'D' | 'N')
}

fn is_gap_base(base: u8) -> bool {
    matches!(base, b'N' | b'n')
}

fn advance_query_cursor(query_cursor: &mut i64, length: i64, strand: &str) {
    if strand == "+" {
        *query_cursor += length;
    } else {
        *query_cursor -= length;
    }
}

fn push_reference_block(
    blocks: &mut Vec<SplitReferenceBlock>,
    query_cursor: &mut i64,
    ref_cursor: &mut i64,
    length: i64,
    strand: &str,
) -> Result<()> {
    if length <= 0 {
        return Ok(());
    }

    let (query_start_bp, query_end_bp) = if strand == "+" {
        (*query_cursor, *query_cursor + length - 1)
    } else {
        (*query_cursor - length + 1, *query_cursor)
    };
    let block = SplitReferenceBlock {
        query_start_bp,
        query_end_bp,
        ref_start_bp: *ref_cursor,
        ref_end_bp: *ref_cursor + length - 1,
    };

    if block.query_start_bp < 1
        || block.query_end_bp < block.query_start_bp
        || block.ref_start_bp < 1
        || block.ref_end_bp < block.ref_start_bp
    {
        bail!("invalid split block {:?}", block);
    }

    if let Some(last) = blocks.last_mut() {
        if can_merge_split_blocks(last, &block, strand) {
            if strand == "+" {
                last.query_end_bp = block.query_end_bp;
            } else {
                last.query_start_bp = block.query_start_bp;
            }
            last.ref_end_bp = block.ref_end_bp;
        } else {
            blocks.push(block);
        }
    } else {
        blocks.push(block);
    }

    advance_query_cursor(query_cursor, length, strand);
    *ref_cursor += length;
    Ok(())
}

fn can_merge_split_blocks(
    previous: &SplitReferenceBlock,
    next: &SplitReferenceBlock,
    strand: &str,
) -> bool {
    if previous.ref_end_bp + 1 != next.ref_start_bp {
        return false;
    }

    if strand == "+" {
        previous.query_end_bp + 1 == next.query_start_bp
    } else {
        next.query_end_bp + 1 == previous.query_start_bp
    }
}

#[cfg(test)]
mod tests {
    use super::{
        ReferenceGapInterval, detect_reference_segments, map_paf_query_interval_to_ref_span,
        split_paf_hit_by_reference_gaps,
    };

    #[test]
    fn detect_reference_segments_splits_only_on_runs_of_100_or_more_ns() {
        let seq = format!(
            "{}{}{}{}{}",
            "A".repeat(50),
            "N".repeat(99),
            "C".repeat(40),
            "N".repeat(100),
            "G".repeat(60),
        );
        let segments = detect_reference_segments("Chr01", &seq, 100);
        assert_eq!(segments.len(), 2);
        assert_eq!((segments[0].start_bp, segments[0].end_bp), (1, 189));
        assert_eq!((segments[1].start_bp, segments[1].end_bp), (290, 349));
    }

    #[test]
    fn split_cg_alignment_breaks_a_cross_gap_hit_into_two_reference_blocks() {
        let gaps = vec![ReferenceGapInterval {
            start_bp: 5001,
            end_bp: 5100,
        }];
        let blocks =
            split_paf_hit_by_reference_gaps(1, 10_000, 1, 10_100, "+", "5000M100D5000M", &gaps)
                .expect("split blocks");
        assert_eq!(blocks.len(), 2);
        assert_eq!((blocks[0].ref_start_bp, blocks[0].ref_end_bp), (1, 5000));
        assert_eq!(
            (blocks[1].ref_start_bp, blocks[1].ref_end_bp),
            (5101, 10100)
        );
    }

    #[test]
    fn split_cg_alignment_preserves_reverse_strand_query_coordinates() {
        let gaps = vec![ReferenceGapInterval {
            start_bp: 5001,
            end_bp: 5100,
        }];
        let blocks =
            split_paf_hit_by_reference_gaps(1, 10_000, 1, 10_100, "-", "5000M100D5000M", &gaps)
                .expect("split blocks");
        assert_eq!(blocks.len(), 2);
        assert_eq!(
            (blocks[0].query_start_bp, blocks[0].query_end_bp),
            (5001, 10_000)
        );
        assert_eq!(
            (blocks[1].query_start_bp, blocks[1].query_end_bp),
            (1, 5000)
        );
        assert_eq!((blocks[0].ref_start_bp, blocks[0].ref_end_bp), (1, 5000));
        assert_eq!(
            (blocks[1].ref_start_bp, blocks[1].ref_end_bp),
            (5101, 10100)
        );
    }

    #[test]
    fn maps_query_interval_to_ref_span_with_insertion_and_deletion_offsets() {
        let block =
            map_paf_query_interval_to_ref_span(10, 40, 100, 129, "+", "10M3I5M2D13M", 10, 24)
                .unwrap()
                .unwrap();
        assert_eq!((block.query_start_bp, block.query_end_bp), (10, 24));
        assert_eq!((block.ref_start_bp, block.ref_end_bp), (100, 111));

        let block =
            map_paf_query_interval_to_ref_span(10, 40, 100, 129, "+", "10M3I5M2D13M", 31, 40)
                .unwrap()
                .unwrap();
        assert_eq!((block.query_start_bp, block.query_end_bp), (31, 40));
        assert_eq!((block.ref_start_bp, block.ref_end_bp), (120, 129));
    }
}
