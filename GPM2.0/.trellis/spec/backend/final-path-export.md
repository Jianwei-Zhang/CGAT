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

## Scenario: server final path TSV to FASTA

### 1. Scope / Trigger

- Trigger: `server/export_final_path_fasta.sh` or a generated
  `gpm_server/export_final_path_fasta.sh` consumes a TSV exported by the
  desktop App.
- The shell exporter accepts both the single-chromosome table and the project
  table. Users must not need to remove the header or first column manually.

### 2. Input Contracts

- Single-chromosome TSV header (9 columns):
  `#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end`.
- Project TSV header (10 columns):
  `Chr\t#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end`.
- Header matching is exact after tolerating a final CR from CRLF input.
- Every data row must contain exactly the same number of tab-separated fields
  as its recognized header. Empty fields must not shift later fields.
- Existing coordinate, orientation, source-resolution, and `--ds` contracts
  apply independently to every row.

### 3. Output Contracts

- A single-chromosome TSV emits one FASTA record. Its record name is derived
  from the output filename, preserving the existing behavior.
- A project TSV emits one FASTA record per distinct `Chr` value, in first-seen
  chromosome order. Rows for each chromosome are concatenated in input order.
- Every FASTA record ends with a newline; adjacent records must never merge.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|-----------|-------------------|
| Header is neither the exact 9-column nor exact 10-column contract | Fail before reading data rows and report the unsupported header. |
| A row width differs from its recognized header | Fail with the line number and expected/actual column counts. |
| Project row has an empty `Chr` | Fail rather than emitting an unnamed record. |
| Any row violates the existing coordinate/orientation/source contract | Fail without publishing a partial final output. |

### 5. Tests Required

- Keep a single-chromosome TSV regression for backward compatibility.
- Add a project TSV regression with at least two chromosome values and assert
  the exact multi-record FASTA text.
- Cover an unsupported header and an inconsistent-width project row.
- Run the shell regression with GNU Bash 4.2 because generated Server helpers
  support that baseline.
