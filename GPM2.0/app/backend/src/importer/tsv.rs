use super::*;

pub(super) fn read_tsv_rows<T, F>(path: &Path, mut mapper: F) -> Result<Vec<T>>
where
    F: FnMut(&[String], &[String]) -> Result<T>,
{
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut lines = reader.lines();

    let header_line = lines
        .next()
        .transpose()
        .with_context(|| format!("failed to read header from {}", path.display()))?
        .ok_or_else(|| anyhow::anyhow!("missing header in {}", path.display()))?;
    let header: Vec<String> = header_line
        .split('\t')
        .map(|value| value.trim().to_string())
        .collect();

    let mut rows = Vec::new();
    for (index, line) in lines.enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 2, path.display())
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let cols: Vec<String> = line.split('\t').map(ToString::to_string).collect();
        let row = mapper(&header, &cols).with_context(|| {
            format!(
                "failed to decode line {} from {}",
                index + 2,
                path.display()
            )
        })?;
        rows.push(row);
    }

    Ok(rows)
}

pub(super) fn read_key_value_tsv(path: &Path) -> Result<HashMap<String, String>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut values = HashMap::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!("failed to read line {} from {}", index + 1, path.display())
        })?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let cols = trimmed.split('\t').collect::<Vec<_>>();
        if index == 0 && cols == ["key", "value"] {
            continue;
        }
        if cols.len() != 2 {
            bail!(
                "invalid key/value row at {}:{} => {}",
                path.display(),
                index + 1,
                line
            );
        }
        values.insert(cols[0].trim().to_string(), cols[1].trim().to_string());
    }
    Ok(values)
}

pub(super) fn required_key_value(values: &HashMap<String, String>, key: &str) -> Result<String> {
    values
        .get(key)
        .filter(|value| !value.trim().is_empty())
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("missing required key '{}'", key))
}

pub(super) fn value_by_header(
    header: &[String],
    cols: &[String],
    expected: &str,
) -> Result<String> {
    let index = header
        .iter()
        .position(|value| value == expected)
        .ok_or_else(|| anyhow::anyhow!("missing required header '{}'", expected))?;
    let value = cols
        .get(index)
        .ok_or_else(|| anyhow::anyhow!("missing value for column '{}'", expected))?;
    Ok(value.trim().to_string())
}

pub(super) fn optional_value_by_header(
    header: &[String],
    cols: &[String],
    expected: &str,
) -> Option<String> {
    let index = header.iter().position(|value| value == expected)?;
    cols.get(index).map(|value| value.trim().to_string())
}

pub(super) fn parse_bool_flag(value: &str, column_name: &str) -> Result<bool> {
    match value.trim().to_ascii_lowercase().as_str() {
        "" | "1" | "true" | "yes" => Ok(true),
        "0" | "false" | "no" => Ok(false),
        other => bail!(
            "invalid boolean value for column '{}': {}",
            column_name,
            other
        ),
    }
}

pub(super) fn parse_f64_value(value: &str, column_name: &str) -> Result<f64> {
    value.trim().parse::<f64>().with_context(|| {
        format!(
            "invalid numeric value for column '{}': {}",
            column_name, value
        )
    })
}

pub(super) fn path_to_string(path: &Path) -> Result<String> {
    path.to_str()
        .map(ToString::to_string)
        .ok_or_else(|| anyhow::anyhow!("path contains non-utf8 characters: {}", path.display()))
}
