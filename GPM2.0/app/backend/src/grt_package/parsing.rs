use super::*;

pub(super) fn read_tsv(
    bundle_root: &Path,
    relpath: &str,
    expected_header: &[&str],
    minimum: usize,
    maximum: Option<usize>,
) -> Result<TsvTable> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let text = fs::read_to_string(&path).map_err(|error| {
        grt_anyhow(
            "INVALID_TSV",
            format!("cannot read {relpath} as UTF-8: {error}"),
        )
    })?;
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(b'\t')
        .has_headers(false)
        .flexible(false)
        .from_reader(text.as_bytes());
    let mut records = reader.records();
    let header = records
        .next()
        .transpose()
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{relpath}: {error}")))?
        .unwrap_or_default()
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    if !header
        .iter()
        .map(String::as_str)
        .eq(expected_header.iter().copied())
    {
        return grt_err(
            "INVALID_TSV",
            format!(
                "{relpath} header must be {:?}, got {:?}",
                expected_header, header
            ),
        );
    }
    let mut rows = Vec::new();
    for record in records {
        let values =
            record.map_err(|error| grt_anyhow("INVALID_TSV", format!("{relpath}: {error}")))?;
        rows.push(
            header
                .iter()
                .zip(values.iter())
                .map(|(key, value)| (key.clone(), value.to_string()))
                .collect(),
        );
    }
    if rows.len() < minimum || maximum.is_some_and(|limit| rows.len() > limit) {
        return grt_err(
            "INVALID_TSV",
            format!(
                "{relpath} row count {} is outside contract bounds",
                rows.len()
            ),
        );
    }
    Ok(TsvTable { rows })
}

pub(super) fn read_json(bundle_root: &Path, relpath: &str) -> Result<Value> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let bytes = fs::read(&path)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("cannot read {relpath}: {error}")))?;
    serde_json::from_slice(&bytes)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{relpath}: {error}")))
}

pub(super) fn read_jsonl(bundle_root: &Path, relpath: &str) -> Result<Vec<Value>> {
    let path = required_bundle_file(bundle_root, relpath, relpath)?;
    let text = fs::read_to_string(&path).map_err(|error| {
        grt_anyhow(
            "INVALID_JSON",
            format!("cannot read {relpath} as UTF-8: {error}"),
        )
    })?;
    text.lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(offset, line)| {
            let value: Value = serde_json::from_str(line).map_err(|error| {
                grt_anyhow("INVALID_JSON", format!("{relpath}:{}: {error}", offset + 1))
            })?;
            if !value.is_object() {
                return grt_err(
                    "INVALID_JSON",
                    format!("{relpath}:{} must contain an object", offset + 1),
                );
            }
            Ok(value)
        })
        .collect()
}

pub(super) fn read_fasta(
    path: &Path,
    label: &str,
    allow_empty: bool,
) -> Result<BTreeMap<String, String>> {
    let text = fs::read_to_string(path)
        .map_err(|error| grt_anyhow("INVALID_FASTA", format!("{label} is not UTF-8: {error}")))?;
    let mut records = BTreeMap::new();
    let mut name: Option<String> = None;
    let mut sequence = String::new();
    for (offset, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if let Some(header) = line.strip_prefix('>') {
            if let Some(previous) = name.take()
                && (sequence.is_empty()
                    || records
                        .insert(previous.clone(), std::mem::take(&mut sequence))
                        .is_some())
            {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has empty or duplicate record", offset + 1),
                );
            }
            let record_name = header.split_whitespace().next().unwrap_or("");
            if record_name.is_empty() || records.contains_key(record_name) {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has empty or duplicate record", offset + 1),
                );
            }
            name = Some(record_name.to_string());
        } else if !line.is_empty() {
            if name.is_none() {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has sequence before header", offset + 1),
                );
            }
            let upper = line.to_ascii_uppercase();
            if !upper.bytes().all(|base| b"ACGTNRYKMSWBDHV".contains(&base)) {
                return grt_err(
                    "INVALID_FASTA",
                    format!("{label}:{} has unsupported bases", offset + 1),
                );
            }
            sequence.push_str(&upper);
        }
    }
    if let Some(previous) = name
        && (sequence.is_empty() || records.insert(previous, sequence).is_some())
    {
        return grt_err(
            "INVALID_FASTA",
            format!("{label} has empty or duplicate record"),
        );
    }
    if records.is_empty() && !allow_empty {
        return grt_err("INVALID_FASTA", format!("{label} has no non-empty records"));
    }
    Ok(records)
}

pub(super) fn validate_fasta_fai_pair(
    fasta_path: &Path,
    fai_path: &Path,
    label: &str,
) -> Result<()> {
    let records = read_fasta(fasta_path, &format!("{label} FASTA"), false)?;
    validate_fasta_fai_records(&records, fai_path, label)
}

pub(super) fn validate_fasta_fai_records(
    records: &BTreeMap<String, String>,
    fai_path: &Path,
    label: &str,
) -> Result<()> {
    let text = fs::read_to_string(fai_path)
        .map_err(|error| grt_anyhow("INVALID_TSV", format!("{label} FAI is not UTF-8: {error}")))?;
    let mut indexed = BTreeMap::<String, usize>::new();
    for (offset, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let columns = line.trim_end_matches('\r').split('\t').collect::<Vec<_>>();
        if columns.len() < 2 || columns[0].is_empty() {
            return grt_err(
                "INVALID_TSV",
                format!("{label} FAI row {} is invalid", offset + 1),
            );
        }
        let length = columns[1].parse::<usize>().map_err(|_| {
            grt_anyhow(
                "INVALID_VALUE",
                format!("{label} FAI row {} has invalid length", offset + 1),
            )
        })?;
        if length == 0 || indexed.insert(columns[0].to_string(), length).is_some() {
            return grt_err(
                "DUPLICATE_ID",
                format!("{label} FAI has empty or duplicate sequence {}", columns[0]),
            );
        }
    }
    let actual = records
        .iter()
        .map(|(name, sequence)| (name.clone(), sequence.len()))
        .collect::<BTreeMap<_, _>>();
    if indexed != actual {
        return grt_err(
            "COUNT_MISMATCH",
            format!("{label} FASTA and FAI sequence names/lengths differ"),
        );
    }
    Ok(())
}

pub(super) fn required_bundle_file(
    bundle_root: &Path,
    relpath: &str,
    label: &str,
) -> Result<PathBuf> {
    validate_relpath(relpath, label)?;
    let path = bundle_root.join(relpath);
    if !path.is_file() {
        return grt_err(
            "MISSING_REQUIRED_FILE",
            format!("{label} does not exist: {relpath}"),
        );
    }
    Ok(path)
}

pub(super) fn validate_relpath(relpath: &str, label: &str) -> Result<()> {
    if relpath.is_empty() || relpath.contains('\\') {
        return grt_err(
            "INVALID_PATH",
            format!("{label} is not a safe relative path: {relpath}"),
        );
    }
    let path = Path::new(relpath);
    if path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return grt_err(
            "INVALID_PATH",
            format!("{label} is not a safe relative path: {relpath}"),
        );
    }
    Ok(())
}

pub(super) fn validate_artifact(
    bundle_root: &Path,
    relpath: &str,
    expected: &str,
    label: &str,
) -> Result<PathBuf> {
    validate_sha256(expected, &format!("{label}.sha256"))?;
    let path = required_bundle_file(bundle_root, relpath, label)?;
    let actual = sha256_file(&path)?;
    if actual != expected {
        return grt_err(
            "CHECKSUM_MISMATCH",
            format!("{label} expected {expected}, got {actual}"),
        );
    }
    Ok(path)
}

pub(super) fn sha256_file(path: &Path) -> Result<String> {
    let bytes =
        fs::read(path).with_context(|| format!("failed to read artifact {}", path.display()))?;
    Ok(sha256_bytes(&bytes))
}

pub(super) fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(super) fn validate_sha256(value: &str, label: &str) -> Result<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return grt_err(
            "INVALID_VALUE",
            format!("{label} must be a lowercase SHA-256"),
        );
    }
    Ok(())
}

pub(super) fn reverse_complement(sequence: &str) -> String {
    sequence
        .chars()
        .rev()
        .map(|base| match base {
            'A' => 'T',
            'C' => 'G',
            'G' => 'C',
            'T' => 'A',
            'N' => 'N',
            'R' => 'Y',
            'Y' => 'R',
            'K' => 'M',
            'M' => 'K',
            'S' => 'S',
            'W' => 'W',
            'B' => 'V',
            'D' => 'H',
            'H' => 'D',
            'V' => 'B',
            other => other,
        })
        .collect()
}

pub(super) fn orient_sequence(sequence: &str, orientation: &str) -> String {
    if orientation == "-" {
        reverse_complement(sequence)
    } else {
        sequence.to_string()
    }
}

pub(super) fn table<'a>(
    tables: &'a HashMap<&'static str, TsvTable>,
    name: &str,
) -> Result<&'a TsvTable> {
    tables.get(name).ok_or_else(|| {
        grt_anyhow(
            "MISSING_REQUIRED_FILE",
            format!("missing parsed table {name}"),
        )
    })
}
pub(super) fn one_row<'a>(
    tables: &'a HashMap<&'static str, TsvTable>,
    name: &str,
) -> Result<&'a TsvRow> {
    table(tables, name)?
        .rows
        .first()
        .ok_or_else(|| grt_anyhow("INVALID_TSV", format!("{name} requires exactly one row")))
}
pub(super) fn field<'a>(row: &'a TsvRow, key: &str) -> Result<&'a str> {
    row.get(key)
        .map(String::as_str)
        .ok_or_else(|| grt_anyhow("INVALID_TSV", format!("missing field {key}")))
}
pub(super) fn nonempty<'a>(row: &'a TsvRow, key: &str, label: &str) -> Result<&'a str> {
    let value = field(row, key)?;
    if value.is_empty() {
        return grt_err("INVALID_VALUE", format!("{label} must not be empty"));
    }
    Ok(value)
}
pub(super) fn parse_bool(value: &str, label: &str) -> Result<bool> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => grt_err("INVALID_VALUE", format!("{label} must be true or false")),
    }
}
pub(super) fn parse_i64(value: &str, label: &str) -> Result<i64> {
    value
        .parse()
        .map_err(|_| grt_anyhow("INVALID_VALUE", format!("{label} must be an integer")))
}
pub(super) fn parse_positive_i64(value: &str, label: &str) -> Result<i64> {
    let parsed = parse_i64(value, label)?;
    if parsed < 1 {
        return grt_err("INVALID_COORDINATE", format!("{label} must be >= 1"));
    }
    Ok(parsed)
}
pub(super) fn parse_nonnegative_i64(value: &str, label: &str) -> Result<i64> {
    let parsed = parse_i64(value, label)?;
    if parsed < 0 {
        return grt_err("INVALID_VALUE", format!("{label} must be >= 0"));
    }
    Ok(parsed)
}
pub(super) fn parse_f64(value: &str, label: &str) -> Result<f64> {
    value
        .parse()
        .map_err(|_| grt_anyhow("INVALID_VALUE", format!("{label} must be numeric")))
}
pub(super) fn interval(row: &TsvRow, start: &str, end: &str, label: &str) -> Result<(i64, i64)> {
    let start = parse_positive_i64(field(row, start)?, &format!("{label}.start"))?;
    let end = parse_positive_i64(field(row, end)?, &format!("{label}.end"))?;
    if start > end {
        return grt_err(
            "INVALID_COORDINATE",
            format!("{label} must satisfy start <= end"),
        );
    }
    Ok((start, end))
}
pub(super) fn orientation<'a>(value: &'a str, label: &str) -> Result<&'a str> {
    enum_value(value, &["+", "-"], label)
}
pub(super) fn enum_value<'a>(value: &'a str, allowed: &[&str], label: &str) -> Result<&'a str> {
    if !allowed.contains(&value) {
        return grt_err(
            "INVALID_VALUE",
            format!("{label} has unsupported value {value}"),
        );
    }
    Ok(value)
}
pub(super) fn json_string_list(value: &str, label: &str) -> Result<Vec<String>> {
    let parsed: Value = serde_json::from_str(value)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{label}: {error}")))?;
    json_value_string_list(&parsed, label)
}
pub(super) fn json_value_string_list(value: &Value, label: &str) -> Result<Vec<String>> {
    let array = value
        .as_array()
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label} must contain an array")))?;
    array
        .iter()
        .map(|item| {
            item.as_str().map(ToString::to_string).ok_or_else(|| {
                grt_anyhow("INVALID_JSON", format!("{label} must contain only strings"))
            })
        })
        .collect()
}
pub(super) fn parse_json_object(value: &str, label: &str) -> Result<Value> {
    let parsed: Value = serde_json::from_str(value)
        .map_err(|error| grt_anyhow("INVALID_JSON", format!("{label}: {error}")))?;
    if !parsed.is_object() {
        return grt_err("INVALID_JSON", format!("{label} must contain an object"));
    }
    Ok(parsed)
}
pub(super) fn json_str<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a str> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label}.{key} must be a string")))
}
pub(super) fn json_nonempty_str<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a str> {
    let value = json_str(object, key, label)?;
    if value.is_empty() {
        return grt_err("INVALID_VALUE", format!("{label}.{key} must not be empty"));
    }
    Ok(value)
}
pub(super) fn json_positive_i64(
    object: &Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<i64> {
    let value = object
        .get(key)
        .and_then(Value::as_i64)
        .ok_or_else(|| grt_anyhow("INVALID_JSON", format!("{label}.{key} must be an integer")))?;
    if value < 1 {
        return grt_err("INVALID_COORDINATE", format!("{label}.{key} must be >= 1"));
    }
    Ok(value)
}
pub(super) fn grt_anyhow(code: &str, message: impl std::fmt::Display) -> anyhow::Error {
    anyhow!("GRT_IMPORT_{code}: {message}")
}
pub(super) fn grt_err<T>(code: &str, message: impl std::fmt::Display) -> Result<T> {
    Err(grt_anyhow(code, message))
}

// Persistence and query functions are intentionally colocated with validation so the
// importer can pass one already-validated in-memory package into the catalog transaction.
