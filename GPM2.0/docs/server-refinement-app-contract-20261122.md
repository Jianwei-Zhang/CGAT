# Refined App delivery contract

Date: 2026-11-22. Implemented serializer/validator and App reader; controlled sequence closure tested, public launcher integration remains pending.

## Version boundary

The existing `gpm_grt_app_precomputed_v2` workflow gains **package schema 5** and **App Final Path schema 4**. Existing packages 2/3/4 and their Final Path versions remain unchanged. An older App must reject schema 5 rather than importing only its LGZ baseline.

The Server's authoritative `cgat.refined-final-path` version 1 is copied byte-for-byte to `metadata/refinement/final_path.json`. The App projection at `metadata/grt_final_path.json` uses the same chromosomes, source intervals, strand, retained-parent links, patch/gap origins and coordinate lifts. Existing persisted `q4_length`/`q4_sha256` fields are storage-compatible names for the **refined** chromosome length/hash, not a choice of the old LGZ sequence. Its FASTA is `data/refinement/final.fa`.

`metadata/refinement/manifest.json` binds the tool/run, Server path hash, projected path, baseline, source identities, package mode and delivered file hashes. Full and light packages describe the same refined path. Full includes the needed source FASTAs and refined FASTA; light preserves indexes/locators and provenance but does not claim that sequence data are available.

## Source and display semantics

Original datasets/contig names are retained. Newly admitted bridge fragments remain a separate `cgat_refinement_<tool>_<run>` dataset; the whole refined chromosome must never become a replacement source dataset. Partial-fill Ns keep their `refinement_source` origin.

New bridge cards use `placement_mode=refinement`, not `normal` or a fabricated reference alignment. Their coordinate is explicitly a **display-context placement**, derived from an adjacent retained LGZ source card where available. It is not homology evidence or a newly measured reference alignment. No `chr_assignments.tsv` reference-hit row is invented for them. The App must materialize these cards and label their origin.

Old source-coordinate reference/pairwise alignments and annotations remain valid on the unchanged source sequences. Accepted local display evidence is retained only when its linked segment survives with compatible source/strand/interval identity; evidence attached to changed/split-out sequence is omitted and counted, not transferred blindly. New fragments have no inferred homology or annotation calls. The distinction is recorded in refinement metadata; a missing new annotation is not a negative biological finding.

The projected path is validated against its exact Server path. Full-package validation must reconstruct chromosome sequences from source intervals and verify the Server hashes. Final Path and FASTA disagreement is fatal. New App validation precedes database mutation; import creates an independent project and does not overwrite manual projects.

## Implementation/acceptance boundary

The package serializer, archive validator and App reader are implemented together. A fixture or filesystem commit test is not a production archive validator. Final acceptance still requires real-tool outputs, full/light import, source availability behavior, Server/App exported-sequence equality and regression coverage for old packages. No whole frontend build or browser run is needed during intermediate code edits.

## Implemented entrypoints and validation evidence

- `refinement_bundle.build_full()` uses the frozen LGZ contract and the content-bound admitted result, adds only actual patch records, and writes a full schema-5 payload. `build_light()` derives the same path with explicit sequence unavailability.
- `refinement_bundle_validate.validate_payload()` verifies the complete file inventory and the exact Server-to-App projection. Full mode reconstructs chromosome sequences from the referenced source intervals, including reverse orientation and residual N origins. It does not treat a matching copied final FASTA alone as proof.
- `refinement_delivery.build_delivery()` creates genuine ZIP or tar.gz full/light archives with a tool-specific independent project root. `validate_delivery()` safely opens both archives and validates their payloads; it is the real repository-owned validator passed by `refinement_batch.publish_batch()` to the three-area publication transaction.
- The Rust schema-5 reader validates all file hashes, the exact Server projection and indexed source reconstruction before importer database mutation. The existing project model stores the refined path, materializes contextual refinement cards, and uses the normal sequence exporter. It does not choose the LGZ file as an alternate final result.
- Refinement cards trace accepted segments by chromosome, source dataset and contig in the validated persisted path, including the `refinement_source` of residual N segments. This is separate from LGZ event and reference evidence; it does not fabricate either. New projects from a result with no accepted edits describe it as unchanged after refinement.

The controlled shared fixture contains partial `GTNNAC` admission over a genuinely validated, frozen LGZ scientific bundle. It preserves negative-strand original sources, retained/split lineage, unresolved gaps, and the bridge's residual N origin. It deliberately contains numbered locator values and differently wrapped partition FASTAs, so the test cannot pass by assuming every source uses the complete dataset's byte offsets. Frozen scientific selection/freeze receipts are not rewritten.

A source-local `.fai` is included for every delivered locator, in both full and light packages. Complete-dataset FAI lengths remain the catalog boundary, but source slices use the referenced partition's own offsets. Server physical numbering is projected to the portable App namespace; raw reads, unrelated accepted attempts and native work trees are not copied. The refined assembly writer wraps at 60 bases so readers do not allocate an entire chromosome just to read a FASTA line; chromosome sequence hashes and coordinates do not change.

Intermediate checks use only the dedicated serializer, archive/publication, Windows Rust refinement tests and selected pure frontend state tests. They prove controlled software contracts, not native-tool biological correctness, customer acceptance, all-tools benchmarking or browser behavior. The earlier serializer retained truthful `not_measured/not_scanned` patch cards. Current production orchestration now completes the separate accepted-source measurement phase before report/delivery, as specified in `server-refinement-source-evidence-contract-20261122.md`. Its optional `metadata/refinement/source_evidence.json` capability binds actual PAFs, frozen source annotations and source-to-final coordinate tables; Python and matching App validators must check those bindings, not only a status enum. Existing schema-5 packets without the capability keep their original unmeasured semantics. Real pinned/native and final App execution gates remain separate.


### Archive importer runtime files

The ZIP importer creates its own live `cache/import.log` before validating an archive. The App payload inventory excludes this exact runtime-owned path only; the archive builder does not ship it, and no source/evidence file is exempt. All other undeclared files, including an existing project database, still fail validation. The desktop's new-workspace reservation rejects repeated imports before touching an existing project's database. A dedicated full/light ZIP-import test checks both this progress-log boundary and preservation of a manually edited project note.
