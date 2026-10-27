# B3 Naming Audit

Date: 2026-10-28. Scope: Job 5, acceptance A15-A18. This is Builder evidence, not the complete change's final verification.

## Coverage and method

- Reviewed both locales in all five central catalogues: Assembly, Importer, Workspace, Shell and Project Preview.
- Reviewed inline copy owners for Projects, Project Export, dataset details, settings, updates, generic dialogs, cross-chromosome alignments, anchor/manual split dialogs, Main split menus, Local fragment menus and view navigation.
- The structured inventory contains 1,238 current message paths per locale across 17 copy owners (2,476 literals). Against the pre-B3 snapshot, 472 existing literals changed and 22 message paths per locale were added. No existing message path or interpolation placeholder was removed/renamed.
- Also inspected the direct consumers and hardcoded render fallbacks: Final Path headings/tables/logs, Main/Local tooltips, context-menu destinations, detail filters/sorting, radio options, and destructive-action tooltips. Role decisions follow actual use, not a property named `title` or an HTML heading level alone.
- All changes are explicit source copy or local display-caption selection. There is no runtime title-casing of user data and no new global text-transform rule.

## Semantic casing

| Role | Examples | Rule |
| --- | --- | --- |
| Major surface or dialog heading | Main View; Primary Dataset Members; Auxiliary Contig Length Rules; App Settings; Cross-Chromosome Alignments | Title Case |
| Minor heading / field label | Auxiliary dataset; Auxiliary contig length (bp); Alignment length (bp); Source contig length; Path start | Sentence case |
| Button / context-menu action | Create project; Hide selected contigs; Cross-chromosome alignments…; Top track | Sentence case; keep named surfaces such as Final Path and Local View |
| System option value | Follow System; Follow Interface; Not Configured; Top Track; Extracted Directory; Auxiliary Contig Usage | Title Case |
| User-supplied option value | Dataset names and chromosome names, including original version suffixes | Verbatim, not recased |
| Unit / acronym / proper filename | bp, kb, Mb, ID, GRT, FASTA, DEGAP, HiFi, ONT, gpm_server, project.sqlite, tar.gz | Canonical spelling preserved |

The first-phased-track GRT notice also uses Title Case for its primary heading and sentence case for its explanatory body. A dialog heading is not reused as an executable menu label. Cross-chromosome alignment actions have their own sentence-case caption. The Local View destination submenu executes actions (`Top track`), whereas the actual lane values use `Top Track`. Projects' delete-failed tooltip uses action copy, not its confirmation-dialog title. Extracted-source radio text and its input-field label have separate captions. Detail-filter type options have separate Title Case display labels; their internal values remain `support` and `other_chr_primary`.

## Terminology and visible fields

| Context | English | Chinese |
| --- | --- | --- |
| Auxiliary selector | Auxiliary dataset | 辅助数据集 |
| Auxiliary length control | Auxiliary contig length (bp) | 辅助组装 Contig 长度 (bp) |
| Primary members | Primary Dataset Members | 主数据集成员 |
| Marker toggles | Telomere markers; Centromere markers | Existing full Chinese marker names |
| Source identity / table field | Origin ID | 来源 ID |
| Cumulative Final Path positions | Path start; Path end | 路径起点；路径终点 |
| Detail length | Length (bp) | 长度 (bp) |
| Cross-path usage | Used by chromosomes | 使用染色体 |

- Removed exposed `ds`, `ctg`, `len`, `chr`, `ref` and `seq` shorthand from catalogue captions/prose where these were human-facing terms.
- Final Path and Project Export detail tables now use localized captions rather than rendering `origin_id`, `length_bp` or `used_by_chr` as visible schema names.
- Length sorting keeps `length_bp` as its dispatch key; the visible caption is localized and the direction is an arrow with a full localized accessible description.
- Main/Local native tooltips use full Start/Length captions and explicit bp units; Final Path tooltip captions distinguish adopted length from source length.
- The generated Final Path card heading changes only its fixed `path` suffix to `Final Path`; the project/chromosome prefix is unchanged.

## Protected boundaries and deliberate exceptions

- Internal property names, API fields, operation IDs, enum values, data attributes, filter/sort keys and database contents are not renamed. Examples: `supportDatasetId`, `assemblyCtgId`, `chr`, `length_bp`, `source_start`, `add_ctg` and `import_add_ctg_package` retain their protocol meaning.
- Legacy backend-error recognition still accepts old `support ds`, `ctg` and related messages. These parser patterns are inputs, not displayed captions.
- Existing TSV schemas retain `Ctg`, `overall_len`, `Ctg_start`, `Chr_start` and related wire headers byte-for-byte. Export/log data, filenames, coordinates, field ordering and user strings are not presentation aliases.
- Numeric values and canonical units are not title-cased. Lowercase `steps` remains a unit fragment; ordinary prose is not converted wholesale into a heading.
- Raw user names, identifiers, paths and caller-provided confirmation-message data remain verbatim. The regressions include mixed-case `ds`/`ctg`/`LEN` names and chromosome version suffixes.
- Project Export's route/title rename and the new Project Information / Path Overview / Project Preview sections remain B5 work; this audit does not claim the page migration is complete.

## Verification

- Added 11 naming-contract cases covering all five catalogues' bilingual key/placeholder parity, exposed shorthand, distinct semantic casing, original user names/IDs, the two unchanged TSV headers, and actual English/Chinese detail/log rendering with stable filter/sort attributes and row values.
- Updated existing literal presentation expectations without changing their interaction, coordinate, persistence, deletion or export assertions. Raw protocol stimuli and the caller-supplied confirmation-message regression remain unchanged.
- Windows-host full frontend suite: 2,060/2,060 passed, zero skipped/cancelled, at this Builder checkpoint. Final batch build/review evidence is recorded in `brief.md` after it is available.
- No browser/native-window acceptance is inferred from this textual/source evidence. The complete change's Windows/macOS menu, tooltip, flicker and resize gates remain separate.
