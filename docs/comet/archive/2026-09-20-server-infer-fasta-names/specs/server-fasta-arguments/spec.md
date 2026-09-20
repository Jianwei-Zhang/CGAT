# Server FASTA argument naming

## Accepted forms

`server/prepare.sh` accepts these reference forms:

- `--ref <reference_name> <reference_fasta_path>`
- `--ref <reference_fasta_path>`

It accepts these repeatable dataset forms:

- `--ds <dataset_name> <dataset_fasta_path>`
- `--ds <dataset_fasta_path>`

The generated `add_dataset.sh` accepts the same two dataset forms.

## Name inference

For a one-value form, the program derives the name from `basename(<fasta_path>)` using this order:

1. Remove one case-insensitive `.gz` suffix when present.
2. Remove one case-insensitive `.fa`, `.fasta`, or `.fna` suffix when present.
3. Replace each run of characters outside `A-Z`, `a-z`, `0-9`, dot, underscore, and hyphen with `_`.
4. Pass the result through the existing name validation.

Examples:

- `/data/rice.fa` becomes `rice`.
- `/data/rice.v1.fasta.gz` becomes `rice.v1`.
- `/data/primary assembly.fa` becomes `primary_assembly`.
- `/data/support-v1.fna` becomes `support-v1`.

## Compatibility and errors

- The existing explicit-name forms remain unchanged.
- A one-value form missing its FASTA path fails with a concise option-specific usage error.
- Existing readable-file validation applies to the selected FASTA path.
- Existing duplicate dataset-name detection applies after inference.
- Option order remains flexible, and repeated one-value and two-value `--ds` forms may be mixed.
- The first dataset remains primary and later datasets remain support datasets.

### Scenario: Infer reference and repeated dataset names during preparation

Given quoted readable FASTA paths whose basenames include supported suffixes and spaces, when the user runs `prepare.sh` with one-value `--ref` and repeated one-value `--ds` arguments, then the generated reference and dataset metadata use the deterministic inferred names and preserve dataset order.

### Scenario: Preserve explicitly named preparation arguments

Given valid explicit names and readable FASTA paths, when the user uses the existing `--ref <name> <fasta>` and `--ds <name> <fasta>` forms, then preparation records the explicit names exactly as before.

### Scenario: Mix explicit and inferred dataset names

Given multiple readable dataset FASTAs, when explicit and one-value `--ds` forms are mixed, then each dataset receives the requested or inferred name and the first dataset remains primary.

### Scenario: Reject duplicate inferred dataset names

Given two dataset paths that infer the same name, when preparation parses both, then it fails with the existing duplicate dataset name error before producing a valid workspace.

### Scenario: Infer a name for an incremental dataset

Given a completed generated Server workspace and a readable dataset FASTA, when the user runs `add_dataset.sh --ds <fasta>`, then the dataset name is inferred by the same rule, Server metadata is updated, and the add package uses that name.

### Scenario: Advertise both concise and explicit forms

Given a user reads command help or the English or Chinese Server instructions, then both accepted forms and the inference rule are described without hiding the backward-compatible explicit form.
