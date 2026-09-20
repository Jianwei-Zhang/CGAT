# Outcome

Make GPM Server FASTA arguments easier to enter by allowing reference and dataset names to be omitted while preserving every existing explicitly named command.

# Scope

- Support both `--ref <name> <fasta>` and `--ref <fasta>` in `server/prepare.sh`.
- Support both `--ds <name> <fasta>` and repeatable `--ds <fasta>` in `server/prepare.sh`.
- Support both `--ds <name> <fasta>` and `--ds <fasta>` in generated `add_dataset.sh`.
- Infer an omitted name from the FASTA basename, remove a case-insensitive `.gz` suffix and one case-insensitive `.fa`, `.fasta`, or `.fna` suffix, and replace characters outside the existing name alphabet with `_`.
- Update command help plus the English and Chinese server usage documentation.
- Add regression coverage for inferred names and retain coverage for explicit names.

# Non-goals

- Do not remove or change the meaning of the existing two-value forms.
- Do not infer names for `--ctg`, `--reads`, `--cen`, or unrelated options.
- Do not redesign the Server CLI or implement the deferred Conda package.
- Do not change FASTA contents, metadata schemas, dataset ordering, or primary/support dataset semantics.

# Acceptance examples

The complete acceptance scenarios are defined in `specs/server-fasta-arguments/spec.md`.

# Constraints and invariants

- Explicit names remain authoritative and continue through the existing `validate_name` path unchanged.
- Inference must occur before existing name validation and duplicate-dataset checks.
- The first `--ds` remains the primary dataset regardless of whether its name is explicit or inferred.
- An inferred duplicate dataset name must fail with the existing duplicate-name error.
- Paths containing spaces remain a single argument when shell-quoted; the inferred name replaces unsupported basename characters with `_`.
- Generated incremental scripts use the same shared inference helper as initial preparation.

# Decisions

- Preserve backward compatibility by distinguishing the one-value form when the token after the FASTA path is another option or the argument ends there.
- Strip only recognized FASTA and gzip suffixes; preserve other dots, hyphens, underscores, letters, and numbers in the basename.
- Apply the convenience rule to incremental `add_dataset.sh` as well as initial `prepare.sh` so dataset addition is consistent across the Server lifecycle.

# Open questions

None. The inference and compatibility rules are fully specified for this change.

# Verification expectations

- Run shell syntax checks for every changed shell script.
- Run `tests/gpm_server/prepare_metadata_test.sh` with inferred reference and repeated dataset names.
- Run `tests/gpm_server/add_dataset_test.sh` with the generated short `--ds <fasta>` form.
- Confirm existing explicitly named forms continue to pass their current regression coverage.
- Run `git diff --check` and an independent read-only review before Verify.
