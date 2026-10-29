# Minimap2 2.31 long-CIGAR parameter audit — 2026-10-29

## Scope

Unmodified `2.31-r1302`, Linux x86_64; no customer data, no patched minimap2,
no automatic parameter fallback and no CGAT default-parameter change.
One deterministic 270,000,000-base FASTA record (xorshift32 seed `0x12345678`)
is aligned to itself without `-X`, modelling an extremely long shared sequence
between assemblies. A 1,000,000-base prefix provides a successful control.
This demonstrates a real executable failure, not just a fabricated CIGAR record;
it does **not** establish the cause of the customer's wheat failure.

- Executable SHA-256: `b6c81294dc0b68b2f54f8e2f6f3ad6be71a40bccc47a6e244ecebc73bae9501d`
- 270 Mb FASTA SHA-256: `0fbc225dfa32c1e4e99ed4cfb611f5023768423fbc5c4f6ec789342aff1e6fc4`
- 1 Mb FASTA SHA-256: `de9ffb54d4d3563d3a53a49b3c3eb825495ebccd09f6737b7a7f227ff441e96b`
- Two mapping threads, except the single-thread query-name diagnostic; 10 GiB
  address-space cap per process, 600-second timeout per command, core dumps disabled.
- Target index built once with `-x asm10`; `index_batch_50M` instead indexes the
  FASTA directly. All mapping cases retain `-c`.

## Results

| Case | Exit | Same assertion | PAF bytes | Seconds | Peak RSS, KiB |
| --- | ---: | --- | ---: | ---: | ---: |
| `index` | 0 | no | 0 | 6.38 | 1589368 |
| `control_1M` | 0 | no | 194 | 1.82 | 1285780 |
| `baseline_270M` | 134 | yes | 0 | 65.07 | 4396816 |
| `no_long_join_narrow_band` | 134 | yes | 0 | 63.52 | 4396652 |
| `eqx` | 134 | yes | 0 | 62.77 | 4396772 |
| `asm5` | 134 | yes | 0 | 68.37 | 4396528 |
| `query_batch_50M` | 134 | yes | 0 | 70.48 | 4396756 |
| `index_batch_50M` | 134 | yes | 0 | 75.84 | 4806848 |
| `zdrop_1` | 134 | yes | 0 | 71.4 | 4396516 |
| `sw_cap_1M` | 134 | yes | 0 | 70.64 | 4396608 |
| `max_qlen_250M` | 0 | no | 0 | 3.53 | 1708060 |
| `debug_qname` | 134 | yes | 0 | 95.93 | 4396656 |

The assertion is exactly `align.c:301: mm_update_extra` with
`qoff == r->qe - r->qs && toff == r->re - r->rs`. The failing baseline used
about 4.2 GiB RSS, below its resource cap; this reproduction is not an OOM kill.
The 1 Mb control contains one `cg:Z:1000000M` alignment spanning the entire query.

Candidate overrides:

- `no_long_join_narrow_band`: `--no-long-join -r 500,1000`.
- `eqx`: `--eqx`.
- `asm5`: `-x asm5` instead of `asm10` (same indexing parameters).
- `query_batch_50M`: `-K 50M`.
- `index_batch_50M`: `-I 50M` on the unsplit 270 Mb FASTA record.
- `zdrop_1`: `-z 1,1`.
- `sw_cap_1M`: `--cap-sw-mem=1M`.
- `max_qlen_250M`: `--max-qlen=250M` returns zero but **skips the query** and
  produces an empty PAF. This is data omission, not a successful workaround.
- `debug_qname`: `--print-qname -t 1` still fails, but prints
  `QR synthetic_270M 0 270000000` before aborting. This can identify a query in
  an explicitly approved diagnostic rerun; it is not a fix or a default flag.

## Interpretation and limits

The tested tuning flags do not repair this demonstrated single-operation-length
failure. Bandwidth and Z-drop do not bound a long uninterrupted diagonal; batch
sizes do not divide one FASTA record. CIGAR encoding still uses 28 length bits.
`--eqx` conversion occurs after the failing check; `-L` addresses the number of
SAM/BAM CIGAR operators, not the length of an individual operator.
Do not remove `-c`, suppress long queries, automatically skip failed work, or
claim lower memory/thread settings repair this case. Do not infer that every
record above 268,435,455 bases fails: the *individual CIGAR operation* matters.
Different customer assertions can have different causes; command/version/input
and scheduler evidence are still needed. No biological acceptance or customer
rerun was performed.

## Repeat the opt-in experiment

```bash
python3 validation/minimap2_long_cigar_parameters.py \
  --minimap2 /absolute/path/to/minimap2 \
  --out /tmp/new-minimap2-long-cigar-audit
```

Requires a C compiler and `/usr/bin/time`. Use an empty output directory and
suitable local compute resources. The script records commands, tool/input hashes,
logs, partial PAFs and results; it never patches the executable or touches a
customer workspace. It is intentionally excluded from routine tests.

The original execution artifacts are local under
`/tmp/cgat-mm231-params.EKIqus/`; the generator and audit script are tracked here
so the experiment does not depend on retaining that temporary directory.
