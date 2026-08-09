# Final Path Export Contracts

## Scenario: final path FASTA orientation

### 1. Scope / Trigger

- Trigger: final path FASTA export receives frontend `finalPathEntry.segments[]` payloads and resolves backend `assembly_ctg` / `assembly_seq` rows plus source FASTA records.
- This is a cross-layer contract: assembly page, subview, final path graph/table, and final path export must interpret orientation in one global coordinate system.

### 2. Signatures

- Tauri command: `export_final_path_fasta(workspaceRoot, projectId, chrName, finalPathEntry, outputPath)`.
- Tauri command: `export_project_final_path_fasta(workspaceRoot, projectId, finalPathByChr, outputPath)`.
- Backend enum:
  ```rust
  FinalPathExportSegment::Ctg {
      assembly_ctg_id: i64,
      start: i64,
      end: i64,
  }
  ```

### 3. Contracts

- `start` and `end` are 1-based closed coordinates on the original source-sequence orientation for the target ctg segment.
- `start <= end` means final path orient `+`: emit the source slice as-is.
- `start > end` means final path orient `-`: emit the reverse complement of the same source slice.
- `assembly_seq.orient`, `assembly_ctg.ref_orient`, main-view orient, subview local flips, and final path row orient are all expressed relative to the original source sequence. They are not nested relative orientations.
- Final path FASTA export must not build a current display-oriented ctg sequence and then apply final path row orientation again. That double interpretation can make `ctg(+)` and `ctg(-)` export the same sequence after a ctg was flipped.

### 4. Validation & Error Matrix

- Missing `finalPathEntry.segments` array -> command normalization error.
- Ctg segment missing `assemblyCtgId`, `start`, or `end` -> command normalization error.
- `start <= 0` or `end <= 0` -> backend export error.
- `max(start, end)` exceeds the source-oriented ctg length -> backend export error.
- Missing source sequence locator or source FASTA entry -> backend export error.

### 5. Good/Base/Bad Cases

- Good: source slice `ACGA`, final path `start=1,end=4` exports `ACGA`.
- Good: source slice `ACGA`, final path `start=4,end=1` exports `TCGT`.
- Base: a main-view ctg with orient `-` still follows the same final path rule; `start=1,end=4` exports the original source slice, and `start=4,end=1` exports its reverse complement.
- Bad: exporting from a display-oriented ctg sequence and then reversing again based on final path row direction.

### 6. Tests Required

- Backend exporter test must cover a ctg whose main-view orient is `-` and whose final path contains both `+` and `-` rows for the same `assembly_ctg_id`.
- Assert exact FASTA sequence text, not only row labels or TSV orient fields.
- Keep project-level final path FASTA export covered because it uses the same segment contract through `finalPathByChr`.

### 7. Wrong vs Correct

#### Wrong

```rust
let chunks = build_ctg_chunks(ctg, source_sequences)?;
let display_sequence = chunks_to_sequence(&chunks);
let slice = &display_sequence[(start_min - 1)..start_max];
```

This uses the current display/assembly orientation before interpreting final path direction.

#### Correct

```rust
let source_sequence = build_source_oriented_sequence(ctg, source_sequences)?;
let slice = &source_sequence[(start_min - 1)..start_max];
```

Then apply only the final path row direction: forward for `start <= end`, reverse complement for `start > end`.
