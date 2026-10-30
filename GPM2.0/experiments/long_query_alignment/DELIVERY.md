# Long-CIGAR recovery: branch delivery contract

## Scope and current status

This change is a separately packaged, locally validated **Linux x86_64 customer
validation candidate**, not an official Release replacement or a new generic
alignment algorithm. It covers the reported initial-reference `minimap2 -c -x
asm10` assertion on the pinned `2.31-r1302` binary. No installed minimap2 source,
binary, preset, default index partitioning, original record order or successful
native PAF bytes are changed. No query is skipped.

Customer logs already show independent reproduction on `ptg000008l` (411,848,600
bases) with the correct binary. Those logs do not expose the exact internal
CIGAR operation. The unavailable customer FASTA has **not** been repaired locally.
The package must therefore remain labelled `customer_validation_pending`; this
is not a promise of arbitrary polyploid/repetitive whole-query DP equivalence.

See [the dated validation record](VALIDATION_RECOVERY_20261030.md) for actual
receipts and limitations. The early public experimental PAF uses MAPQ 255 and
is **never** admitted to formal results.

## Customer operation — no configuration files

1. Extract the supplied, checksum-verified candidate into a **new installation
   directory**. Keep the original installation and existing output directory.
   The companion is precompiled and shipped with its licenses; no compiler,
   internet download, environment changes or manual FASTA splitting is needed.
2. Point `SERVER` to the extracted `GPM_Server`. Submit the **same existing
   `run.sh` arguments / sbatch script**, including the original output directory.
   Do not remove `-c`, force a different preset or supply an experiment command.
3. A supported old failed workspace is matched to an immutable, maintainer-bound
   source profile. Only unfinished initial-reference commands are adapted under
   the existing launch/task locks, with command/log backups. Completed valid
   reference checkpoints are reused. A customized/mixed/unsupported workspace
   is preserved and refused rather than guessed or silently regenerated.
4. Ordinary native success remains unchanged. Only the exact abort enters
   whole-record isolation. Each recovered singleton must independently abort;
   supported original-chain/overlap/candidate/native-selection evidence is
   checked before a complete result is atomically published. Failed partial
   PAFs, unknown confidence and incomplete query × original-index-part cells
   cannot become successful checkpoints.
5. Successful completion still creates the ordinary Full and Light App packages
   and report. On refusal/failure, retain the workspace/logs and private attempt
   evidence for diagnosis. Do not manually rename an experimental PAF to
   `result.paf` or fabricate a success checkpoint.

No new Slurm/cgroup/resource configuration is required. Recovery inherits job
limits; it is sequential and can need substantial temporary disk. A non-target
OOM, unsupported case or interrupted job remains a real failure, not a reason
to discard data, relax validation or retry arbitrary parameters indefinitely.

### Rollback

The original installation and FASTA are untouched. Handoff records are retained
under `.run_all/long-cigar-handoff-*`; partial command handoffs roll back
transactionally, without overwriting concurrent edits. Completed scientific
outputs are not deleted or silently restored to an old failed prefix.

**Switching the installation alone does not undo an already adapted workspace.**
For an independent pure-old-code run, use the old installation with a new output
directory; its original minimap2 limitation will still exist. Preserve the
candidate workspace and backups. Do not manually edit `.prepare_lib` or restore
command journals while a job is running. There is deliberately no generic
workspace downgrade or user-written recovery configuration.

## Maintainer build and acceptance

Run from the repository root. These are maintainer commands, not customer tasks.
Build the separate helper against the **unmodified pinned library**, using an
explicit old glibc sysroot and static zlib, then test that exact binary:

```bash
python3 GPM2.0/experiments/long_query_alignment/build_native_chain_state.py \
  --source /path/to/pinned-upstream-git \
  --out /fresh/build/native/linux-x86_64 \
  --compiler /usr/bin/gcc --sysroot /path/to/glibc-2.17-sysroot \
  --zlib-prefix /path/to/static-zlib-prefix --jobs 2 --execute
```

The builder records the unchanged upstream commit/source hashes, own C source,
compiler, static library, ELF requirements and license identities. A manifest's
`built_unvalidated` field means the build itself runs no tests; actual execution
receipts are separate. Do not relabel an arbitrary host-built GLIBC 2.34 binary
as portable. The tested artifact must also execute on the old target userland.

The final maintainer acceptance receipt is bounded JSON, not customer config.
It binds **all shipped runtime hashes, all base Server hashes and the exact
helper binary + manifest**, and requires passed receipt hashes for:

- the complete no-skip unit suite and normal native candidate/metadata controls;
- GRT/Final Path comparisons, real >268,435,455-bp recovery and actual >8-Gb
  default multipart integration;
- positive/negative per-result admission and real old-glibc helper execution;
- packaged subprocess lifecycle (explicit fake mapper, not scientific evidence);
- a genuine old-version failed-workspace `run.sh` → recovery → all pipeline
  stages → Full/Light delivery, same-command checkpoint reuse;
- Server quality gate, main merge compatibility, actual package import/export.

The acceptance receipt is a maintainer attestation with auditable hashes, not a
signature, automatic proof of arbitrary DP equivalence or customer validation.
It does not bypass any per-result evidence gate. Package preparation without it
still emits a clearly unvalidated development package.

```bash
python3 GPM2.0/experiments/long_query_alignment/prepare_branch_server_package.py \
  --server-source GPM2.0/server \
  --native-state-bundle /tested/build/native/linux-x86_64 \
  --resume-source-revision d1519a76ce1f1df37c9186db1edb26e03a51ab26 \
  --validation-receipt /reviewed/local-acceptance.json \
  --out /fresh/customer-candidate --execute
```

The old-source profile must match the original reference/launch/checkpoint
recipes byte-for-byte, except the explicitly reviewed **hash-pinned** public
GRT-to-LGZ presentation-only transition `fcfb161` → `fe59b81`. The three approved
whole-file hash pairs are recorded by the packager; arbitrary word replacement,
unknown edits or reverse downgrades are not equivalence. The old workspace must
still match its complete immutable tool profile. An archive includes only named regular source/artifact
members, is reopened and hashed against the packaged inventory, and carries
`LOCAL_ACCEPTANCE.json`, `SOURCE.json`, base provenance and licenses. Test the
extracted archive, not only the source tree. Publish neither master nor an
official Release asset merely because candidate packaging succeeded.

Independent read-only publication checks and subprocess controls are available
in `compare_publication_contract.py` and `compare_server_lifecycle.py`; both are
PLAN ONLY unless `--execute` is explicitly supplied. The former requires an
actual retained recovered fixture; the latter explicitly uses a fake mapper.

## Remaining customer acceptance

Use the candidate on the already localized original data. Confirm the original
asserting record is either supported with complete evidence and the whole
workflow finishes correctly, or is refused with a specific unsupported reason.
Check final assignment/path/sequence output, not just exit status. A new
unsupported biological geometry cannot be labelled fixed from the simple
identity controls. ARM/macOS and native desktop UI are not claimed validated by
this Linux x86_64 Server candidate.
