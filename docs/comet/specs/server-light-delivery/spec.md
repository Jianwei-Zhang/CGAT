# Server Light Delivery

## Public package tiers

The Server workflow exposes two delivery tiers: Full and Light. Full includes the complete FASTA payload. Light omits FASTA while retaining FAI indexes, metadata, Final Path data, source-card state, PAF views, and the complete embedded report.

The generated Light archive is named `<workspace>.light.zip`. Completion output, generated reports, App-facing progress text, and maintained documentation call this tier `Light`; they do not use `No-FASTA` or `no_fasta` as its public name.

## Compatibility

The established internal delivery-contract value `package_mode=no_fasta` remains valid and continues to identify the reduced payload. Import and validation continue to use archive contents and metadata rather than requiring a `.light.zip` filename, so legacy `.no_fasta.zip` archives remain importable.

## Delivery integrity

Renaming the tier and archive does not alter payload inclusion rules, report embedding, checkpoint behavior, or Full-package output.
