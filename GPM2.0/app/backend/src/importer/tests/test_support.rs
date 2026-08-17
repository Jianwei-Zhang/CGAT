pub(super) use std::collections::BTreeMap;
pub(super) use std::io::Write;

pub(super) use rusqlite::{Connection, params};
pub(super) use serde_json::{Value, json};
pub(super) use sha2::{Digest, Sha256};
pub(super) use tempfile::tempdir;
pub(super) use zip::CompressionMethod;
pub(super) use zip::write::FileOptions;

pub(super) use super::super::*;
pub(super) use crate::workspace::looks_like_bundle_root;

pub(super) fn create_bundle_root(bundle_root: &Path) {
    fs::create_dir_all(bundle_root.join("metadata")).unwrap();
    fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
    fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
    fs::create_dir_all(bundle_root.join("data/reference/chrs")).unwrap();
    fs::create_dir_all(bundle_root.join("data/partitions/chr/r")).unwrap();
    fs::create_dir_all(bundle_root.join("runs")).unwrap();
    fs::write(
        bundle_root.join("metadata/reference.tsv"),
        "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/datasets.tsv"),
        "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\ttrue\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/package.tsv"),
        concat!(
            "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
            "fast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
        ),
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/chr_assignments.tsv"),
        "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds_a\td\t2\tr\t+\tref_alignment\t2\t100.000\t1\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/track_member_orders.tsv"),
        "target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds_a\tr\tds_a\td\t1\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/reference_chr_locator.tsv"),
        "reference_chr_name\tfasta_relpath\nr\tdata/reference/chrs/r.fa\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/source_seq_locator.tsv"),
        "dataset_name\tseq_name\tfasta_relpath\nds_a\td\tdata/partitions/chr/r/ds_a.fa\n",
    )
    .unwrap();
    fs::write(bundle_root.join("data/reference/ref.fa"), ">r\nAT\n").unwrap();
    fs::write(
        bundle_root.join("data/reference/ref.fa.fai"),
        "r\t2\t0\t2\t3\n",
    )
    .unwrap();
    fs::write(bundle_root.join("data/datasets/ds.fa"), ">d\nAT\n").unwrap();
    fs::write(
        bundle_root.join("data/datasets/ds.fa.fai"),
        "d\t2\t0\t2\t3\n",
    )
    .unwrap();
    fs::write(bundle_root.join("data/reference/chrs/r.fa"), ">r\nAT\n").unwrap();
    fs::write(
        bundle_root.join("data/partitions/chr/r/ds_a.fa"),
        ">d\nAT\n",
    )
    .unwrap();
    install_minimal_grt_contract(bundle_root);
}

pub(super) fn create_partitioned_fast_bundle_root(bundle_root: &Path, include_fasta_payload: bool) {
    fs::create_dir_all(bundle_root.join("metadata")).unwrap();
    fs::create_dir_all(bundle_root.join("data/reference")).unwrap();
    fs::create_dir_all(bundle_root.join("data/datasets")).unwrap();
    fs::create_dir_all(bundle_root.join("data/reference/chrs")).unwrap();
    fs::create_dir_all(bundle_root.join("data/partitions/chr/r")).unwrap();
    fs::create_dir_all(bundle_root.join("runs")).unwrap();
    fs::write(
        bundle_root.join("metadata/reference.tsv"),
        "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/datasets.tsv"),
        "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\ttrue\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/package.tsv"),
        concat!(
            "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n",
            "fast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
        ),
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/chr_assignments.tsv"),
        "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds_a\td\t4\tr\t+\tref_alignment\t4\t100.000\t1\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/track_member_orders.tsv"),
        "target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds_a\tr\tds_a\td\t1\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/reference_chr_locator.tsv"),
        "reference_chr_name\tfasta_relpath\nr\tdata/reference/chrs/r.fa\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("metadata/source_seq_locator.tsv"),
        "dataset_name\tseq_name\tfasta_relpath\nds_a\td\tdata/partitions/chr/r/ds_a.fa\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("data/reference/ref.fa.fai"),
        "r\t4\t0\t4\t5\n",
    )
    .unwrap();
    fs::write(
        bundle_root.join("data/datasets/ds.fa.fai"),
        "d\t4\t0\t4\t5\n",
    )
    .unwrap();
    if include_fasta_payload {
        fs::write(bundle_root.join("data/reference/chrs/r.fa"), ">r\nACGT\n").unwrap();
        fs::write(
            bundle_root.join("data/partitions/chr/r/ds_a.fa"),
            ">d\nACGT\n",
        )
        .unwrap();
        install_minimal_grt_contract(bundle_root);
    }
}

pub(super) fn add_second_chr_dataset_to_bundle_root(
    bundle_root: &Path,
    include_fasta_payload: bool,
) {
    append_text(
        &bundle_root.join("metadata/datasets.tsv"),
        "ds_b\tassembler_b\t\tdata/datasets/ds_b.fa\tdata/datasets/ds_b.fa.fai\ttrue\n",
    );
    append_text(
        &bundle_root.join("metadata/chr_assignments.tsv"),
        "ds_b\te\t4\tr\t+\tref_alignment\t4\t100.000\t1\n",
    );
    append_text(
        &bundle_root.join("metadata/track_member_orders.tsv"),
        "ds_b\tr\tds_b\te\t1\n",
    );
    append_text(
        &bundle_root.join("metadata/source_seq_locator.tsv"),
        "ds_b\te\tdata/partitions/chr/r/ds_b.fa\n",
    );
    fs::write(
        bundle_root.join("data/datasets/ds_b.fa.fai"),
        "e\t4\t0\t4\t5\n",
    )
    .unwrap();
    if include_fasta_payload {
        fs::write(
            bundle_root.join("data/partitions/chr/r/ds_b.fa"),
            ">e\nACGT\n",
        )
        .unwrap();
        install_minimal_grt_contract(bundle_root);
    }
}

pub(super) fn install_minimal_grt_contract(bundle_root: &Path) {
    let metadata_root = bundle_root.join("metadata");
    let grt_root = bundle_root.join("grt");
    fs::create_dir_all(grt_root.join("q")).unwrap();
    fs::create_dir_all(grt_root.join("donor")).unwrap();
    fs::create_dir_all(grt_root.join("checkpoints")).unwrap();
    fs::create_dir_all(grt_root.join("evidence/test")).unwrap();

    let references = read_reference_rows(bundle_root).unwrap();
    let reference = references.first().unwrap();
    let reference_fasta_path = bundle_root.join(&reference.fasta_relpath);
    if !reference_fasta_path.is_file() {
        let mut fasta = String::new();
        for row in parse_fai_rows(&bundle_root.join(&reference.fai_relpath)).unwrap() {
            let chr_path = bundle_root
                .join("data/reference/chrs")
                .join(format!("{}.fa", row.seq_name));
            let records = read_test_fasta(&chr_path);
            fasta.push_str(&format!(">{}\n{}\n", row.seq_name, records[&row.seq_name]));
        }
        fs::write(&reference_fasta_path, fasta).unwrap();
    }
    let datasets = read_dataset_rows(bundle_root).unwrap();
    let locators = read_source_seq_locator_rows(bundle_root).unwrap();
    let mut source_sequences = HashMap::<(String, String), String>::new();
    for locator in &locators {
        let records = read_test_fasta(&bundle_root.join(&locator.fasta_relpath));
        source_sequences.insert(
            (locator.dataset_name.clone(), locator.seq_name.clone()),
            records[&locator.seq_name].clone(),
        );
    }
    for dataset in &datasets {
        let fasta_path = bundle_root.join(&dataset.fasta_relpath);
        if !fasta_path.is_file() {
            let mut fasta = String::new();
            for locator in locators
                .iter()
                .filter(|row| row.dataset_name == dataset.name)
            {
                fasta.push_str(&format!(
                    ">{}\n{}\n",
                    locator.seq_name,
                    source_sequences[&(locator.dataset_name.clone(), locator.seq_name.clone())]
                ));
            }
            fs::write(fasta_path, fasta).unwrap();
        }
    }

    fs::write(
        metadata_root.join("package.tsv"),
        concat!(
            "workflow\tschema_version\tpackage_mode\tsequence_layout\tpreassigned_chr\tself_alignment_scope\tcross_alignment_scope\tchr_assignment_min_coverage_percent\tgrt_precompute_enabled\trecipe_locked\tfinal_path_schema_version\treads_qc_enabled\n",
            "gpm_grt_precomputed_v2\t2\tfast\tpartitioned\ttrue\tchr_partition\tchr_partition\t60\ttrue\ttrue\t1\tfalse\n",
        ),
    )
    .unwrap();

    let primary = datasets.first().unwrap().name.clone();
    let support = datasets
        .iter()
        .skip(1)
        .map(|dataset| dataset.name.clone())
        .collect::<Vec<_>>();
    fs::write(
        metadata_root.join("grt_recipe.tsv"),
        format!(
            "recipe_id\tprimary_dataset\tsupport_datasets_json\treads_qc_enabled\tdonor_set_id\ttel_donor_set_id\tq0_relpath\tfinal_q_relpath\nrecipe-test\t{}\t{}\tfalse\td0-test\tdtel-test\tgrt/q/q0.fa\tgrt/q/q4.fa\n",
            primary,
            serde_json::to_string(&support).unwrap()
        ),
    )
    .unwrap();

    let mut role_text = "dataset_name\tcontig_name\tq_eligible\tdonor_eligible\ttel_donor_eligible\tq_rejection_reason\tdonor_rejection_reason\ttel_rejection_reason\n".to_string();
    for locator in &locators {
        role_text.push_str(&format!(
            "{}\t{}\ttrue\ttrue\ttrue\t\t\t\n",
            locator.dataset_name, locator.seq_name
        ));
    }
    fs::write(metadata_root.join("grt_contig_roles.tsv"), role_text).unwrap();

    let assignments = read_imported_chr_assignment_rows(bundle_root).unwrap();
    let mut by_chr = HashMap::<String, Vec<&ImportedChrAssignmentRow>>::new();
    for assignment in &assignments {
        by_chr
            .entry(assignment.assigned_chr_name.clone())
            .or_default()
            .push(assignment);
    }
    for rows in by_chr.values_mut() {
        rows.sort_by(|left, right| {
            left.anchor_start
                .cmp(&right.anchor_start)
                .then_with(|| left.dataset_name.cmp(&right.dataset_name))
                .then_with(|| left.seq_name.cmp(&right.seq_name))
        });
    }

    let dataset_by_name = datasets
        .iter()
        .map(|dataset| (dataset.name.as_str(), dataset))
        .collect::<HashMap<_, _>>();
    let mut q_records = BTreeMap::<String, String>::new();
    let mut q_segments = "q_version\tchr\tsegment_id\tsegment_kind\tq_start\tq_end\tdataset_name\tcontig_name\tsource_start\tsource_end\torientation\tsource_card_key\tevidence_ids_json\n".to_string();
    let mut evidence = "evidence_id\tstage\tevidence_type\tstatus\tq_version\tq_source_sha256\tquery_artifact_relpath\tquery_sha256\tdonor_set_id\ttarget_artifact_relpath\ttarget_sha256\tsource_dataset\tsource_contig\tsource_start\tsource_end\torientation\ttarget_chr\ttarget_start\ttarget_end\ttool\ttool_version\tpreset\tparameters_json\traw_artifact_relpath\traw_artifact_sha256\tcoordinate_system\tprojection_status\n".to_string();
    let mut final_chromosomes = Vec::new();
    let reference_sha = test_sha256(&fs::read(&reference_fasta_path).unwrap());
    let mut evidence_index = 0_usize;
    for (chr_name, rows) in &by_chr {
        let mut q_sequence = String::new();
        let mut final_segments = Vec::new();
        let mut next_start = 1_i64;
        for assignment in rows {
            evidence_index += 1;
            let source_key = (assignment.dataset_name.clone(), assignment.seq_name.clone());
            let source_sequence = &source_sequences[&source_key];
            let projected_sequence = if assignment.source_orientation == "-" {
                test_reverse_complement(source_sequence)
            } else {
                source_sequence.clone()
            };
            let q_end = next_start + projected_sequence.len() as i64 - 1;
            let segment_id = format!("q0-seg-{evidence_index}");
            let evidence_id = format!("ev-q0-{evidence_index}");
            let source_card_key = format!(
                "{}:{}:{}:normal",
                assignment.dataset_name, assignment.seq_name, chr_name
            );
            q_segments.push_str(&format!(
                "q0\t{}\t{}\tsource\t{}\t{}\t{}\t{}\t1\t{}\t{}\t{}\t[\"{}\"]\n",
                chr_name,
                segment_id,
                next_start,
                q_end,
                assignment.dataset_name,
                assignment.seq_name,
                source_sequence.len(),
                assignment.source_orientation,
                source_card_key,
                evidence_id
            ));
            let raw_relpath = format!("grt/evidence/test/{evidence_id}.paf");
            fs::write(bundle_root.join(&raw_relpath), b"").unwrap();
            let dataset = dataset_by_name[assignment.dataset_name.as_str()];
            let query_sha =
                test_sha256(&fs::read(bundle_root.join(&dataset.fasta_relpath)).unwrap());
            evidence.push_str(&format!(
                "{}\tassignment\tpaf\tbackground\t\t\t{}\t{}\t\t{}\t{}\t{}\t{}\t1\t{}\t{}\t{}\t{}\t{}\tminimap2\ttest\tasm10\t{{}}\t{}\t{}\tpaf_0_based_half_open\tprojected\n",
                evidence_id,
                dataset.fasta_relpath,
                query_sha,
                reference.fasta_relpath,
                reference_sha,
                assignment.dataset_name,
                assignment.seq_name,
                source_sequence.len(),
                assignment.source_orientation,
                chr_name,
                assignment.anchor_start.max(1),
                assignment.anchor_start.max(1) + source_sequence.len() as i64 - 1,
                raw_relpath,
                test_sha256(b"")
            ));
            final_segments.push(json!({
                "segment_id": segment_id,
                "kind": "source",
                "length": source_sequence.len(),
                "orientation": assignment.source_orientation,
                "event_id": Value::Null,
                "source": {
                    "dataset": assignment.dataset_name,
                    "contig": assignment.seq_name,
                    "start": 1,
                    "end": source_sequence.len(),
                    "orientation": assignment.source_orientation
                },
                "evidence_ids": [evidence_id]
            }));
            q_sequence.push_str(&projected_sequence);
            next_start = q_end + 1;
        }
        q_records.insert(chr_name.clone(), q_sequence.clone());
        final_chromosomes.push(json!({
            "chr": chr_name,
            "q4_length": q_sequence.len(),
            "q4_sha256": test_sha256(q_sequence.as_bytes()),
            "segments": final_segments
        }));
    }
    let mut q_fasta = String::new();
    for (chr_name, sequence) in &q_records {
        q_fasta.push_str(&format!(">{}\n{}\n", chr_name, sequence));
    }
    for version in ["q0", "q0r1", "q0f", "q1", "q2", "q3", "q4"] {
        fs::write(grt_root.join(format!("q/{version}.fa")), &q_fasta).unwrap();
    }
    fs::write(metadata_root.join("grt_q_segments.tsv"), q_segments).unwrap();
    fs::write(metadata_root.join("grt_evidence_registry.tsv"), evidence).unwrap();

    fs::write(grt_root.join("donor/d0.fa"), b"").unwrap();
    fs::write(grt_root.join("donor/dtel.fa"), b"").unwrap();
    let member_header = "donor_set_id\tmember_id\tdataset_name\tcontig_name\tsource_start\tsource_end\torientation\tfasta_record_name\tsequence_sha256\n";
    fs::write(grt_root.join("donor/d0.manifest.tsv"), member_header).unwrap();
    fs::write(grt_root.join("donor/dtel.manifest.tsv"), member_header).unwrap();
    fs::write(metadata_root.join("grt_donor_members.tsv"), member_header).unwrap();
    fs::write(
        metadata_root.join("grt_donor_sets.tsv"),
        format!(
            "donor_set_id\tdonor_kind\tmanifest_relpath\tfasta_relpath\tfasta_sha256\tmember_count\nd0-test\tordinary\tgrt/donor/d0.manifest.tsv\tgrt/donor/d0.fa\t{}\t0\ndtel-test\ttelomere\tgrt/donor/dtel.manifest.tsv\tgrt/donor/dtel.fa\t{}\t0\n",
            test_sha256(b""),
            test_sha256(b"")
        ),
    )
    .unwrap();
    fs::write(metadata_root.join("grt_donor_usage.tsv"), "usage_id\tdonor_set_id\tmember_id\tsource_dataset\tsource_contig\tsource_start\tsource_end\tstage\tstatus\tevent_id\tfinal_path_segment_id\treason\n").unwrap();
    fs::write(metadata_root.join("grt_donor_fragments.tsv"), "donor_set_id\tmember_id\tfragment_id\tfasta_record_name\tfragment_start\tfragment_end\tfragment_length\tsequence_sha256\tleft_boundary\tright_boundary\n").unwrap();
    fs::write(metadata_root.join("grt_used_contigs.tsv"), "source_card_key\tdataset_name\tcontig_name\toriginal_assignment\ttarget_chr\tplacement_mode\tref_alignment_status\tanchor_start\torientation\tref_evidence_ids_json\taccepted_event_ids_json\tfinal_path_segment_ids_json\tpairwise_evidence_ids_json\n").unwrap();
    fs::write(metadata_root.join("grt_events.jsonl"), b"").unwrap();
    fs::write(
        metadata_root.join("grt_gap_attempts.tsv"),
        "attempt_id\tchr\tobject_id\tstage\tstatus\treason\tcandidate_count\taccepted_event_id\n",
    )
    .unwrap();
    let mut strategy_text = "chr\tstrategy\tstrategy_applied\tgap_count\tpatch_candidate_count\tvalidated_patch_count\taccepted_patch_count\tfallback_candidate_count\taccepted_fallback_count\treason\n".to_string();
    for chr_name in q_records.keys() {
        strategy_text.push_str(&format!(
            "{}\tno_gaps\tpatcher_result\t0\t0\t0\t0\t0\t0\tchromosome_has_no_gap_objects\n",
            chr_name
        ));
    }
    fs::write(
        metadata_root.join("grt_step2_strategies.tsv"),
        strategy_text,
    )
    .unwrap();
    fs::write(metadata_root.join("grt_step3_classifications.tsv"), "chr\tobject_id\tcandidate_id\terror_type\terror_subtype\terror_features_json\tconfidence\tconfidence_score\tgap_in_error_region\trepair_mode\trepair_reason\toutcome\tevent_id\tfragment_id\tdonor_reuse\tdonor_reuse_of\n").unwrap();

    let q_sha = test_sha256(q_fasta.as_bytes());
    let checkpoint = b"{}\n";
    let checkpoint_sha = test_sha256(checkpoint);
    let mut stage_text = "stage\tq_input_version\tq_input_sha256\tq_output_version\tq_output_sha256\tdonor_set_id\tstatus\tcheckpoint_relpath\tcheckpoint_sha256\n".to_string();
    for (stage, input, output, donor_set_id) in [
        ("donor_freeze", "q0", "q0", "d0-test"),
        ("step1_round1", "q0", "q0r1", "d0-test"),
        ("step1_filter", "q0r1", "q0f", "d0-test"),
        ("step1_round2", "q0f", "q1", "d0-test"),
        ("step2", "q1", "q2", "d0-test"),
        ("step3", "q2", "q3", "d0-test"),
        ("step4_telomere", "q3", "q4", "dtel-test"),
        ("finalize", "q4", "q4", ""),
    ] {
        let checkpoint_relpath = format!("grt/checkpoints/{stage}.json");
        fs::write(bundle_root.join(&checkpoint_relpath), checkpoint).unwrap();
        stage_text.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\tsuccess\t{}\t{}\n",
            stage, input, q_sha, output, q_sha, donor_set_id, checkpoint_relpath, checkpoint_sha
        ));
    }
    fs::write(metadata_root.join("grt_stage_status.tsv"), stage_text).unwrap();
    fs::write(
        metadata_root.join("grt_tool_versions.tsv"),
        "tool\tversion\texecutable\nminimap2\ttest\tminimap2\n",
    )
    .unwrap();
    fs::write(
        metadata_root.join("grt_final_path.json"),
        serde_json::to_vec_pretty(&json!({
            "workflow": "gpm_grt_precomputed_v2",
            "schema_version": "1",
            "q4_relpath": "grt/q/q4.fa",
            "chromosomes": final_chromosomes
        }))
        .unwrap(),
    )
    .unwrap();
}

pub(super) fn read_test_fasta(path: &Path) -> BTreeMap<String, String> {
    let mut records = BTreeMap::new();
    let mut current = String::new();
    for line in fs::read_to_string(path).unwrap().lines() {
        if let Some(header) = line.strip_prefix('>') {
            current = header.split_whitespace().next().unwrap().to_string();
            records.entry(current.clone()).or_insert_with(String::new);
        } else if !line.trim().is_empty() {
            records.get_mut(&current).unwrap().push_str(line.trim());
        }
    }
    records
}

pub(super) fn test_sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(super) fn test_reverse_complement(sequence: &str) -> String {
    sequence
        .chars()
        .rev()
        .map(|base| match base.to_ascii_uppercase() {
            'A' => 'T',
            'C' => 'G',
            'G' => 'C',
            'T' => 'A',
            other => other,
        })
        .collect()
}

pub(super) fn append_text(path: &Path, text: &str) {
    use std::io::Write;

    let mut file = fs::OpenOptions::new().append(true).open(path).unwrap();
    file.write_all(text.as_bytes()).unwrap();
}

#[derive(Debug, Clone)]
pub(super) struct AddZipOptions {
    pub(super) package_type: String,
    pub(super) dataset_name: String,
    pub(super) reference_name: String,
    pub(super) sequence_layout: String,
    pub(super) chr_assignment_min_coverage_percent: String,
    pub(super) alignment_engine: String,
    pub(super) minimap_preset: String,
    pub(super) blastn_task: String,
    pub(super) blastn_evalue: String,
    pub(super) blastn_dust: String,
    pub(super) winnowmap_preset: String,
    pub(super) winnowmap_kmer: String,
    pub(super) winnowmap_repeat_fraction: String,
    pub(super) skip_self: bool,
    pub(super) self_alignment_available: bool,
    pub(super) include_ref_paf: bool,
    pub(super) include_self_paf: bool,
    pub(super) include_pairwise_paf: bool,
    pub(super) dataset_fasta_relpath: String,
    pub(super) dataset_fai_relpath: String,
    pub(super) locator_fasta_relpath: String,
    pub(super) locator_seq_name: Option<String>,
    pub(super) tel_enabled: bool,
    pub(super) cen_enabled: bool,
    pub(super) include_tel_payload: bool,
    pub(super) include_cen_payload: bool,
    pub(super) include_extra_payload_file: bool,
    pub(super) include_track_member_orders: bool,
}

impl Default for AddZipOptions {
    fn default() -> Self {
        Self {
            package_type: "add_dataset".to_string(),
            dataset_name: "ds4".to_string(),
            reference_name: "ref_a".to_string(),
            sequence_layout: "partitioned".to_string(),
            chr_assignment_min_coverage_percent: "60".to_string(),
            alignment_engine: "minimap2".to_string(),
            minimap_preset: "asm10".to_string(),
            blastn_task: "blastn".to_string(),
            blastn_evalue: "1e-10".to_string(),
            blastn_dust: "no".to_string(),
            winnowmap_preset: "asm20".to_string(),
            winnowmap_kmer: "19".to_string(),
            winnowmap_repeat_fraction: "0.9998".to_string(),
            skip_self: false,
            self_alignment_available: true,
            include_ref_paf: true,
            include_self_paf: true,
            include_pairwise_paf: true,
            dataset_fasta_relpath: "data/datasets/ds4.fa".to_string(),
            dataset_fai_relpath: "data/datasets/ds4.fa.fai".to_string(),
            locator_fasta_relpath: "data/partitions/chr/r/ds4.fa".to_string(),
            locator_seq_name: None,
            tel_enabled: false,
            cen_enabled: false,
            include_tel_payload: false,
            include_cen_payload: false,
            include_extra_payload_file: false,
            include_track_member_orders: true,
        }
    }
}

pub(super) fn import_workspace_with_project(root: &Path) -> (ImportOutcome, i64) {
    let bundle_root = root.join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    write_prepare_options(&bundle_root, "asm10", false);
    let (outcome, _progress) = import_from_extracted_bundle(&bundle_root).unwrap();
    let project_id = insert_existing_project(&outcome.project_db_path);
    (outcome, project_id)
}

pub(super) fn write_prepare_options(bundle_root: &Path, minimap_preset: &str, skip_self: bool) {
    fs::write(
        bundle_root.join("metadata/prepare_options.tsv"),
        format!(
            concat!(
                "key\tvalue\n",
                "chr_assignment_min_coverage_percent\t60\n",
                "alignment_engine\tminimap2\n",
                "minimap_preset\t{}\n",
                "blastn_task\tblastn\n",
                "blastn_evalue\t1e-10\n",
                "blastn_dust\tno\n",
                "winnowmap_preset\tasm20\n",
                "winnowmap_kmer\t19\n",
                "winnowmap_repeat_fraction\t0.9998\n",
                "threads\t10\n",
                "skip_self\t{}\n",
                "self_alignment_scope\t{}\n",
                "tel_enabled\tfalse\n",
                "cen_enabled\tfalse\n",
                "cen_min_len\t10000\n",
                "cen_min_identity\t80\n",
            ),
            minimap_preset,
            if skip_self { "true" } else { "false" },
            if skip_self { "none" } else { "chr_partition" }
        ),
    )
    .unwrap();
}

pub(super) fn insert_existing_project(project_db_path: &Path) -> i64 {
    let conn = Connection::open(project_db_path).unwrap();
    let reference_id: i64 = conn
        .query_row(
            "SELECT id FROM reference_genome WHERE name = 'ref_a'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let primary_dataset_id: i64 = conn
        .query_row("SELECT id FROM dataset WHERE name = 'ds_a'", [], |row| {
            row.get(0)
        })
        .unwrap();
    conn.execute(
        "INSERT INTO project (
            name, version, reference_genome_id, primary_dataset_id,
            chr_assignment_min_coverage_percent, created_at
         ) VALUES ('existing', 1, ?1, ?2, 60, 'now')",
        params![reference_id, primary_dataset_id],
    )
    .unwrap();
    let project_id = conn.last_insert_rowid();
    conn.execute(
        "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
         VALUES (?1, ?2, 'primary', 1)",
        params![project_id, primary_dataset_id],
    )
    .unwrap();
    project_id
}

pub(super) fn insert_support_project_dataset(
    project_db_path: &Path,
    project_id: i64,
    dataset_name: &str,
    display_order: i64,
) {
    let conn = Connection::open(project_db_path).unwrap();
    let dataset_id: i64 = conn
        .query_row(
            "SELECT id FROM dataset WHERE name = ?1",
            params![dataset_name],
            |row| row.get(0),
        )
        .unwrap();
    conn.execute(
        "INSERT INTO project_dataset (project_id, dataset_id, dataset_role, display_order)
         VALUES (?1, ?2, 'support', ?3)",
        params![project_id, dataset_id, display_order],
    )
    .unwrap();
}

pub(super) fn query_pairwise_run_ids_for_dataset_names(
    conn: &Connection,
    dataset_names: &[&str],
) -> Vec<i64> {
    let placeholders = dataset_names
        .iter()
        .map(|_| "?")
        .collect::<Vec<_>>()
        .join(",");
    let sql = format!(
        "SELECT DISTINCT r.id
         FROM pairwise_alignment_run r
         JOIN dataset q ON q.id = r.query_dataset_id
         JOIN dataset t ON t.id = r.target_dataset_id
         WHERE q.name IN ({placeholders}) OR t.name IN ({placeholders})
         ORDER BY r.id"
    );
    let params = dataset_names
        .iter()
        .chain(dataset_names.iter())
        .map(|value| rusqlite::types::Value::Text((*value).to_string()))
        .collect::<Vec<_>>();
    let mut stmt = conn.prepare(&sql).unwrap();
    stmt.query_map(rusqlite::params_from_iter(params), |row| row.get(0))
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
}

pub(super) fn query_project_assembly_rows(
    conn: &Connection,
    project_id: i64,
) -> Vec<(String, String, Option<String>)> {
    let mut stmt = conn
        .prepare(
            "SELECT c.name, s.orient, c.ref_orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             WHERE c.project_id = ?1
             ORDER BY c.id",
        )
        .unwrap();
    stmt.query_map(params![project_id], |row| {
        Ok((row.get(0)?, row.get(1)?, row.get(2)?))
    })
    .unwrap()
    .collect::<std::result::Result<Vec<_>, _>>()
    .unwrap()
}

pub(super) fn query_project_assembly_rows_excluding_dataset(
    conn: &Connection,
    project_id: i64,
    dataset_id: i64,
) -> Vec<(String, String, Option<String>)> {
    let mut stmt = conn
        .prepare(
            "SELECT c.name, s.orient, c.ref_orient
             FROM assembly_ctg c
             JOIN assembly_seq s ON s.id = c.assembly_seq_id
             JOIN source_seq ss ON ss.id = s.source_seq_id
             WHERE c.project_id = ?1 AND ss.dataset_id != ?2
             ORDER BY c.id",
        )
        .unwrap();
    stmt.query_map(params![project_id, dataset_id], |row| {
        Ok((row.get(0)?, row.get(1)?, row.get(2)?))
    })
    .unwrap()
    .collect::<std::result::Result<Vec<_>, _>>()
    .unwrap()
}

pub(super) fn write_add_ctg_zip(zip_path: &Path) {
    write_add_ctg_zip_with_order(zip_path, true);
}

pub(super) fn write_add_ctg_zip_with_order(zip_path: &Path, include_track_member_orders: bool) {
    let file = File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);

    zip.start_file("add_ctg/manifest.tsv", options).unwrap();
    zip.write_all(
        concat!(
            "package_type\tadd_ctg\n",
            "ctg_name\tgap_filled\n",
            "derived_dataset\tderived_ctg\n",
            "target_chr\tr\n",
            "target_track\tds_a\n",
            "source\tgapfiller\n",
            "reference_name\tref_a\n",
            "alignment_engine\tminimap2\n",
            "minimap_preset\tasm10\n",
            "blastn_task\tblastn\n",
            "blastn_evalue\t1e-10\n",
            "blastn_dust\tno\n",
            "winnowmap_preset\tasm20\n",
            "winnowmap_kmer\t19\n",
            "winnowmap_repeat_fraction\t0.9998\n",
            "skip_self\tfalse\n",
            "self_alignment_scope\tchr_partition\n",
            "cross_alignment_scope\tchr_partition\n",
            "sequence_layout\tpartitioned\n",
            "preassigned_chr\ttrue\n",
            "contains_fasta\ttrue\n",
            "created_at\t1\n",
        )
        .as_bytes(),
    )
    .unwrap();

    zip.start_file("gpm_server/metadata/datasets.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n\
derived_ctg\tderived_ctg\t\tdata/datasets/derived_ctg.fa\tdata/datasets/derived_ctg.fa.fai\ttrue\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/derived_ctgs.tsv", options)
        .unwrap();
    zip.write_all(
        b"derived_dataset\tctg_name\tsource\tsource_fasta_name\tsource_fasta_sha256\tcreated_at\n\
derived_ctg\tgap_filled\tgapfiller\tfinal.fa\tsha\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/track_members.tsv", options)
        .unwrap();
    zip.write_all(
        b"member_dataset\tmember_ctg\ttarget_chr\ttarget_track\tmember_role\tcreated_at\n\
derived_ctg\tgap_filled\tr\tds_a\tderived\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\n\
derived_ctg\tgap_filled\t4\tr\t+\tref_alignment\t4\t100.000\t2\n",
    )
    .unwrap();
    if include_track_member_orders {
        zip.start_file("gpm_server/metadata/track_member_orders.tsv", options)
            .unwrap();
        zip.write_all(
            b"target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\n\
ds_a\tr\tderived_ctg\tgap_filled\t1\n\
ds_a\tr\tds_a\td\t2\n",
        )
        .unwrap();
    }
    zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tfasta_relpath\n\
derived_ctg\tgap_filled\tdata/derived_ctgs/gap_filled.fa\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/source_seq_n_regions.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\n\
derived_ctg\tgap_filled\t2\t2\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/data/derived_ctgs/gap_filled.fa", options)
        .unwrap();
    zip.write_all(b">gap_filled\nANCG\n").unwrap();
    zip.start_file("gpm_server/data/derived_ctgs/gap_filled.fa.fai", options)
        .unwrap();
    zip.write_all(b"gap_filled\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/datasets/derived_ctg.fa", options)
        .unwrap();
    zip.write_all(b">gap_filled\nANCG\n").unwrap();
    zip.start_file("gpm_server/data/datasets/derived_ctg.fa.fai", options)
        .unwrap();
    zip.write_all(b"gap_filled\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/runs/chr_r/datasets/derived_ctg.fa", options)
        .unwrap();
    zip.write_all(b">gap_filled\nANCG\n").unwrap();
    zip.start_file(
        "gpm_server/runs/add_ctg/gap_filled_vs_ref/result.paf",
        options,
    )
    .unwrap();
    zip.write_all(b"gap_filled\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n")
        .unwrap();
    zip.start_file(
        "gpm_server/runs/chr_r/add_ctg/ds_a_vs_gap_filled/result.paf",
        options,
    )
    .unwrap();
    zip.write_all(b"gap_filled\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n")
        .unwrap();
    zip.start_file(
        "gpm_server/runs/chr_r/add_ctg/ds_b_vs_gap_filled/result.paf",
        options,
    )
    .unwrap();
    zip.write_all(b"gap_filled\t4\t0\t4\t+\te\t4\t0\t4\t4\t4\t60\n")
        .unwrap();
    zip.finish().unwrap();
}

pub(super) fn write_add_dataset_zip(zip_path: &Path, options: AddZipOptions) {
    let file = File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    let zip_options = FileOptions::default().compression_method(CompressionMethod::Stored);
    let dataset_name = options.dataset_name.as_str();
    let seq_name = if dataset_name == "ds_a" { "d" } else { "x" };
    let locator_seq_name = options.locator_seq_name.as_deref().unwrap_or(seq_name);
    let dataset_fasta_relpath = options.dataset_fasta_relpath.replace("ds4", dataset_name);
    let dataset_fai_relpath = options.dataset_fai_relpath.replace("ds4", dataset_name);
    let locator_fasta_relpath = options.locator_fasta_relpath.replace("ds4", dataset_name);

    zip.start_file("add_package/manifest.tsv", zip_options)
        .unwrap();
    zip.write_all(
        format!(
            concat!(
                "package_type\t{}\n",
                "dataset_name\t{}\n",
                "reference_name\t{}\n",
                "sequence_layout\t{}\n",
                "preassigned_chr\ttrue\n",
                "chr_assignment_min_coverage_percent\t{}\n",
                "alignment_engine\t{}\n",
                "minimap_preset\t{}\n",
                "blastn_task\t{}\n",
                "blastn_evalue\t{}\n",
                "blastn_dust\t{}\n",
                "winnowmap_preset\t{}\n",
                "winnowmap_kmer\t{}\n",
                "winnowmap_repeat_fraction\t{}\n",
                "skip_self\t{}\n",
                "self_alignment_available\t{}\n",
                "tel_enabled\t{}\n",
                "cen_enabled\t{}\n",
            ),
            options.package_type,
            dataset_name,
            options.reference_name,
            options.sequence_layout,
            options.chr_assignment_min_coverage_percent,
            options.alignment_engine,
            options.minimap_preset,
            options.blastn_task,
            options.blastn_evalue,
            options.blastn_dust,
            options.winnowmap_preset,
            options.winnowmap_kmer,
            options.winnowmap_repeat_fraction,
            if options.skip_self { "true" } else { "false" },
            if options.self_alignment_available {
                "true"
            } else {
                "false"
            },
            if options.tel_enabled { "true" } else { "false" },
            if options.cen_enabled { "true" } else { "false" }
        )
        .as_bytes(),
    )
    .unwrap();

    zip.start_file("gpm_server/metadata/datasets.tsv", zip_options)
        .unwrap();
    zip.write_all(
        format!(
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n{dataset_name}\tassembler_4\t\t{dataset_fasta_relpath}\t{dataset_fai_relpath}\t{}\n",
            if options.self_alignment_available { "true" } else { "false" }
        )
        .as_bytes(),
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/chr_assignments.tsv", zip_options)
        .unwrap();
    zip.write_all(
        format!(
            "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\n{dataset_name}\t{seq_name}\t4\tr\t+\tref_alignment\t4\t100.000\t2\n"
        )
        .as_bytes(),
    )
    .unwrap();
    if options.include_track_member_orders {
        zip.start_file("gpm_server/metadata/track_member_orders.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\n{dataset_name}\tr\t{dataset_name}\t{seq_name}\t1\n"
            )
            .as_bytes(),
        )
        .unwrap();
    }
    zip.start_file("gpm_server/metadata/source_seq_locator.tsv", zip_options)
        .unwrap();
    zip.write_all(
        format!(
            "dataset_name\tseq_name\tfasta_relpath\n{dataset_name}\t{locator_seq_name}\t{locator_fasta_relpath}\n"
        )
        .as_bytes(),
    )
    .unwrap();
    zip.start_file(
        format!("gpm_server/data/datasets/{dataset_name}.fa"),
        zip_options,
    )
    .unwrap();
    zip.write_all(format!(">{seq_name}\nTGCA\n").as_bytes())
        .unwrap();
    zip.start_file(
        format!("gpm_server/data/datasets/{dataset_name}.fa.fai"),
        zip_options,
    )
    .unwrap();
    zip.write_all(format!("{seq_name}\t4\t0\t4\t5\n").as_bytes())
        .unwrap();
    zip.start_file(
        format!("gpm_server/data/partitions/chr/r/{dataset_name}.fa"),
        zip_options,
    )
    .unwrap();
    zip.write_all(format!(">{seq_name}\nTGCA\n").as_bytes())
        .unwrap();
    if options.include_ref_paf {
        zip.start_file(
            format!("gpm_server/runs/{dataset_name}_vs_ref/result.paf"),
            zip_options,
        )
        .unwrap();
        zip.write_all(format!("{seq_name}\t4\t0\t4\t+\tr\t4\t0\t4\t4\t4\t60\n").as_bytes())
            .unwrap();
    }
    if options.include_self_paf {
        zip.start_file(
            format!("gpm_server/runs/chr_r/{dataset_name}_vs_self/result.paf"),
            zip_options,
        )
        .unwrap();
        zip.write_all(
            format!("{seq_name}\t4\t0\t4\t+\t{seq_name}\t4\t0\t4\t4\t4\t60\n").as_bytes(),
        )
        .unwrap();
    }
    if options.include_pairwise_paf {
        zip.start_file(
            format!("gpm_server/runs/chr_r/ds_a_vs_{dataset_name}/result.paf"),
            zip_options,
        )
        .unwrap();
        zip.write_all(format!("{seq_name}\t4\t0\t4\t+\td\t4\t0\t4\t4\t4\t60\n").as_bytes())
            .unwrap();
    }
    if options.include_tel_payload {
        zip.start_file("gpm_server/tel/rules.tsv", zip_options)
            .unwrap();
        zip.write_all(
            b"rule_id\tmotif\tmin_repeat\treverse_complement\ntel_fwd\tTTAGGG\t2\tfalse\n",
        )
        .unwrap();
        zip.start_file("gpm_server/tel/chr_r/marks.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "rule_id\tdataset_name\tseq_name\tassigned_chr_name\tmotif\tmin_repeat\trepeat_count\tstart_bp\tend_bp\tstrand\ntel_fwd\t{dataset_name}\t{seq_name}\tr\tTTAGGG\t2\t2\t1\t12\t+\n"
            )
            .as_bytes(),
        )
        .unwrap();
    }
    if options.include_cen_payload {
        zip.start_file("gpm_server/cen/chr_r/marks.tsv", zip_options)
            .unwrap();
        zip.write_all(
            format!(
                "cen_id\tchr_name\tquery_name\tdataset_name\tctg_name\tctg_start\tctg_end\tstrand\talign_length\tidentity\tmapq\ncen1\tr\tcen_query\t{dataset_name}\t{seq_name}\t1\t4\t+\t4\t99.0\t60\n"
            )
            .as_bytes(),
        )
        .unwrap();
    }
    if options.include_extra_payload_file {
        zip.start_file("gpm_server/notes/evil.txt", zip_options)
            .unwrap();
        zip.write_all(b"unexpected").unwrap();
    }

    zip.finish().unwrap();
}

pub(super) fn write_bundle_zip(zip_path: &Path) {
    let file = File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);

    zip.add_directory("gpm_server/metadata/", options).unwrap();
    zip.add_directory("gpm_server/data/reference/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/datasets/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/reference/chrs/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
        .unwrap();
    zip.add_directory("gpm_server/runs/", options).unwrap();

    zip.start_file("gpm_server/metadata/reference.tsv", options)
        .unwrap();
    zip.write_all(
        b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/datasets.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/package.tsv", options)
        .unwrap();
    zip.write_all(
        b"package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t+\tref_alignment\t4\t100.000\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/track_member_orders.tsv", options)
        .unwrap();
    zip.write_all(
        b"target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds_a\tref\tds_a\tds\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
        .unwrap();
    zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
        .unwrap();
    zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
    )
    .unwrap();
    zip.start_file("gpm_server/data/reference/ref.fa", options)
        .unwrap();
    zip.write_all(b">ref\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
        .unwrap();
    zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/datasets/ds.fa", options)
        .unwrap();
    zip.write_all(b">ds\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
        .unwrap();
    zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/reference/chrs/ref.fa", options)
        .unwrap();
    zip.write_all(b">ref\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/partitions/chr/ref/ds_a.fa", options)
        .unwrap();
    zip.write_all(b">ds\nACGT\n").unwrap();
    zip.start_file("gpm_server/runs/.keep", options).unwrap();
    zip.write_all(b"").unwrap();

    zip.finish().unwrap();
    append_generated_grt_bundle(zip_path, true);
}

pub(super) fn write_bundle_zip_without_fasta(zip_path: &Path) {
    let file = File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);

    zip.add_directory("gpm_server/metadata/", options).unwrap();
    zip.add_directory("gpm_server/data/reference/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/datasets/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/reference/chrs/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
        .unwrap();
    zip.add_directory("gpm_server/runs/", options).unwrap();

    zip.start_file("gpm_server/metadata/reference.tsv", options)
        .unwrap();
    zip.write_all(
        b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/datasets.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/package.tsv", options)
        .unwrap();
    zip.write_all(
        b"package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\tchr_partition\tchr_partition\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t+\tref_alignment\t4\t100.000\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/track_member_orders.tsv", options)
        .unwrap();
    zip.write_all(
        b"target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds_a\tref\tds_a\tds\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
        .unwrap();
    zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
        .unwrap();
    zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
    )
    .unwrap();
    zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
        .unwrap();
    zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
        .unwrap();
    zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/runs/.keep", options).unwrap();
    zip.write_all(b"").unwrap();

    zip.finish().unwrap();
}

pub(super) fn write_bundle_zip_with_self_alignment_flag(zip_path: &Path, available: bool) {
    let file = File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);
    let availability = if available { "true" } else { "false" };
    let self_scope = if available { "chr_partition" } else { "none" };

    zip.add_directory("gpm_server/metadata/", options).unwrap();
    zip.add_directory("gpm_server/data/reference/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/datasets/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/reference/chrs/", options)
        .unwrap();
    zip.add_directory("gpm_server/data/partitions/chr/ref/", options)
        .unwrap();
    zip.add_directory("gpm_server/runs/", options).unwrap();

    zip.start_file("gpm_server/metadata/reference.tsv", options)
        .unwrap();
    zip.write_all(
        b"reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref_a\tunknown\tref_a\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/datasets.tsv", options)
        .unwrap();
    zip.write_all(
        format!(
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\t{}\n",
            availability
        )
        .as_bytes(),
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/package.tsv", options)
        .unwrap();
    zip.write_all(
        format!(
            "package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\nfast\tpartitioned\ttrue\t60\t{}\tchr_partition\n",
            self_scope
        )
        .as_bytes(),
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/chr_assignments.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds_a\tds\t4\tref\t+\tref_alignment\t4\t100.000\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/track_member_orders.tsv", options)
        .unwrap();
    zip.write_all(
        b"target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds_a\tref\tds_a\tds\t1\n",
    )
    .unwrap();
    zip.start_file("gpm_server/metadata/reference_chr_locator.tsv", options)
        .unwrap();
    zip.write_all(b"reference_chr_name\tfasta_relpath\nref\tdata/reference/chrs/ref.fa\n")
        .unwrap();
    zip.start_file("gpm_server/metadata/source_seq_locator.tsv", options)
        .unwrap();
    zip.write_all(
        b"dataset_name\tseq_name\tfasta_relpath\nds_a\tds\tdata/partitions/chr/ref/ds_a.fa\n",
    )
    .unwrap();
    zip.start_file("gpm_server/data/reference/ref.fa", options)
        .unwrap();
    zip.write_all(b">ref\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/reference/ref.fa.fai", options)
        .unwrap();
    zip.write_all(b"ref\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/datasets/ds.fa", options)
        .unwrap();
    zip.write_all(b">ds\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/datasets/ds.fa.fai", options)
        .unwrap();
    zip.write_all(b"ds\t4\t0\t4\t5\n").unwrap();
    zip.start_file("gpm_server/data/reference/chrs/ref.fa", options)
        .unwrap();
    zip.write_all(b">ref\nACGT\n").unwrap();
    zip.start_file("gpm_server/data/partitions/chr/ref/ds_a.fa", options)
        .unwrap();
    zip.write_all(b">ds\nACGT\n").unwrap();

    zip.finish().unwrap();
    append_generated_grt_bundle(zip_path, available);
}

pub(super) fn append_generated_grt_bundle(zip_path: &Path, self_alignment_available: bool) {
    let temp = tempdir().unwrap();
    let bundle_root = temp.path().join("gpm_server");
    create_partitioned_fast_bundle_root(&bundle_root, true);
    if !self_alignment_available {
        fs::write(
            bundle_root.join("metadata/datasets.tsv"),
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds_a\tassembler_a\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\tfalse\n",
        )
        .unwrap();
        install_minimal_grt_contract(&bundle_root);
        let package_path = bundle_root.join("metadata/package.tsv");
        let package = fs::read_to_string(&package_path).unwrap().replacen(
            "\tchr_partition\tchr_partition\t60\t",
            "\tnone\tchr_partition\t60\t",
            1,
        );
        fs::write(package_path, package).unwrap();
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(zip_path)
        .unwrap();
    let mut zip = zip::ZipWriter::new_append(file).unwrap();
    append_test_tree_to_zip(&mut zip, &bundle_root, Path::new("gpm_server"));
    zip.finish().unwrap();
}

pub(super) fn append_test_tree_to_zip(
    zip: &mut zip::ZipWriter<File>,
    source: &Path,
    archive_root: &Path,
) {
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let source_path = entry.path();
        let archive_path = archive_root.join(entry.file_name());
        if source_path.is_dir() {
            append_test_tree_to_zip(zip, &source_path, &archive_path);
        } else {
            zip.start_file(archive_path.to_string_lossy().replace('\\', "/"), options)
                .unwrap();
            zip.write_all(&fs::read(source_path).unwrap()).unwrap();
        }
    }
}

pub(super) fn count_rows(project_db_path: &Path, table: &str) -> i64 {
    let conn = Connection::open(project_db_path).unwrap();
    let sql = format!("SELECT COUNT(*) FROM {}", table);
    conn.query_row(&sql, [], |row| row.get(0)).unwrap()
}

pub(super) fn dataset_stats(project_db_path: &Path, name: &str) -> Option<(i64, i64)> {
    let conn = Connection::open(project_db_path).unwrap();
    conn.query_row(
        "SELECT contig_count, total_length_bp FROM dataset WHERE name = ?1",
        params![name],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )
    .ok()
}
