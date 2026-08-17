use super::*;

#[derive(Debug)]
pub(super) struct AddImportRollback {
    active: bool,
    project_db_path: PathBuf,
    project_db_backup_path: PathBuf,
    file_targets: Vec<(PathBuf, Option<PathBuf>)>,
    created_dirs: Vec<PathBuf>,
    backup_root: PathBuf,
}

impl AddImportRollback {
    pub(super) fn capture(
        workspace_root: &Path,
        project_db_path: &Path,
        payload_root: &Path,
    ) -> Result<Self> {
        let backup_root = workspace_root.join(CACHE_DIR).join(format!(
            "add_import_rollback_{}",
            current_unix_millis_string()
        ));
        fs::create_dir_all(&backup_root).with_context(|| {
            format!(
                "failed to create add import rollback dir {}",
                backup_root.display()
            )
        })?;
        let project_db_backup_path = backup_root.join(PROJECT_DB_NAME);
        fs::copy(project_db_path, &project_db_backup_path).with_context(|| {
            format!(
                "failed to back up project db {} to {}",
                project_db_path.display(),
                project_db_backup_path.display()
            )
        })?;

        let mut targets = Vec::new();
        let mut created_dirs = HashSet::new();
        collect_add_payload_rollback_targets(
            payload_root,
            payload_root,
            workspace_root,
            &backup_root,
            &mut targets,
            &mut created_dirs,
        )?;
        let mut created_dirs = created_dirs.into_iter().collect::<Vec<_>>();
        created_dirs.sort_by_key(|path| std::cmp::Reverse(path.components().count()));

        Ok(Self {
            active: true,
            project_db_path: project_db_path.to_path_buf(),
            project_db_backup_path,
            file_targets: targets,
            created_dirs,
            backup_root,
        })
    }

    pub(super) fn disarm(&mut self) -> Result<()> {
        self.active = false;
        if self.backup_root.exists() {
            fs::remove_dir_all(&self.backup_root).with_context(|| {
                format!(
                    "failed to remove add import rollback dir {}",
                    self.backup_root.display()
                )
            })?;
        }
        Ok(())
    }

    pub(super) fn rollback(&mut self) -> Result<()> {
        self.rollback_in_place()
    }

    pub(super) fn rollback_in_place(&mut self) -> Result<()> {
        if !self.active {
            return Ok(());
        }
        let mut first_error: Option<anyhow::Error> = None;

        for (target, backup) in self.file_targets.iter().rev() {
            let result = if let Some(backup_path) = backup {
                if let Some(parent) = target.parent() {
                    fs::create_dir_all(parent).with_context(|| {
                        format!(
                            "failed to recreate rollback target dir {}",
                            parent.display()
                        )
                    })?;
                }
                fs::copy(backup_path, target).map(|_| ()).with_context(|| {
                    format!(
                        "failed to restore add import file {} from {}",
                        target.display(),
                        backup_path.display()
                    )
                })
            } else if target.exists() {
                fs::remove_file(target).with_context(|| {
                    format!("failed to remove add import file {}", target.display())
                })
            } else {
                Ok(())
            };
            if first_error.is_none() {
                first_error = result.err();
            }
        }

        let db_restore_result = fs::copy(&self.project_db_backup_path, &self.project_db_path)
            .map(|_| ())
            .with_context(|| {
                format!(
                    "failed to restore project db {} from {}",
                    self.project_db_path.display(),
                    self.project_db_backup_path.display()
                )
            });
        if first_error.is_none() {
            first_error = db_restore_result.err();
        }

        for dir in &self.created_dirs {
            if dir.exists() {
                let _ = fs::remove_dir(dir);
            }
        }
        let _ = fs::remove_dir_all(&self.backup_root);
        self.active = false;

        if let Some(error) = first_error {
            Err(error)
        } else {
            Ok(())
        }
    }
}

impl Drop for AddImportRollback {
    fn drop(&mut self) {
        let _ = self.rollback_in_place();
    }
}

pub(super) fn collect_add_payload_rollback_targets(
    payload_root: &Path,
    path: &Path,
    workspace_root: &Path,
    backup_root: &Path,
    targets: &mut Vec<(PathBuf, Option<PathBuf>)>,
    created_dirs: &mut HashSet<PathBuf>,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            collect_add_payload_rollback_targets(
                payload_root,
                &source,
                workspace_root,
                backup_root,
                targets,
                created_dirs,
            )?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let target = workspace_root.join(relpath);
        record_missing_parent_dirs(workspace_root, &target, created_dirs);
        if target.exists() {
            let backup_path = backup_root.join(format!("file_{}.bak", targets.len()));
            fs::copy(&target, &backup_path).with_context(|| {
                format!(
                    "failed to back up add import target {} to {}",
                    target.display(),
                    backup_path.display()
                )
            })?;
            targets.push((target, Some(backup_path)));
        } else {
            targets.push((target, None));
        }
    }
    Ok(())
}

pub(super) fn record_missing_parent_dirs(
    workspace_root: &Path,
    target: &Path,
    created_dirs: &mut HashSet<PathBuf>,
) {
    let mut current = target.parent();
    while let Some(dir) = current {
        if dir == workspace_root {
            break;
        }
        if dir.exists() {
            break;
        }
        created_dirs.insert(dir.to_path_buf());
        current = dir.parent();
    }
}

pub(super) fn copy_add_payload_into_workspace(
    payload_root: &Path,
    workspace_root: &Path,
) -> Result<()> {
    copy_add_payload_entry(payload_root, payload_root, workspace_root)
}

pub(super) fn copy_add_ctg_payload_into_workspace(
    payload_root: &Path,
    workspace_root: &Path,
) -> Result<()> {
    copy_add_ctg_payload_entry(payload_root, payload_root, workspace_root)
}

pub(super) fn copy_add_payload_entry(
    payload_root: &Path,
    path: &Path,
    workspace_root: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            copy_add_payload_entry(payload_root, &source, workspace_root)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!("failed to relativize add payload path {}", source.display())
        })?;
        let target = workspace_root.join(relpath);
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if is_appendable_add_payload_tsv(&rel) {
            append_tsv_payload_rows(&source, &target)?;
            continue;
        }
        if rel == "tel/rules.tsv" && target.exists() {
            validate_tsv_payload_header(&source, &target)?;
            continue;
        }
        if target.exists() {
            bail!(
                "add dataset payload target already exists: {}",
                target.display()
            );
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create add payload target dir {}",
                    parent.display()
                )
            })?;
        }
        fs::copy(&source, &target).with_context(|| {
            format!(
                "failed to copy add payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }
    Ok(())
}

pub(super) fn copy_add_ctg_payload_entry(
    payload_root: &Path,
    path: &Path,
    workspace_root: &Path,
) -> Result<()> {
    for entry in fs::read_dir(path)
        .with_context(|| format!("failed to read add_ctg payload dir {}", path.display()))?
    {
        let entry =
            entry.with_context(|| format!("failed to read entry under {}", path.display()))?;
        let source = entry.path();
        if source.is_dir() {
            copy_add_ctg_payload_entry(payload_root, &source, workspace_root)?;
            continue;
        }
        let relpath = source.strip_prefix(payload_root).with_context(|| {
            format!(
                "failed to relativize add_ctg payload path {}",
                source.display()
            )
        })?;
        let target = workspace_root.join(relpath);
        let rel = relpath.to_string_lossy().replace('\\', "/");
        if rel == "metadata/datasets.tsv" {
            append_dataset_tsv_if_new(&source, &target, "derived_ctg")?;
            continue;
        }
        if rel == "metadata/track_member_orders.tsv" {
            replace_track_member_order_groups(&source, &target)?;
            continue;
        }
        if is_appendable_add_ctg_payload_tsv(&rel) {
            append_tsv_payload_rows(&source, &target)?;
            continue;
        }
        if is_appendable_add_ctg_fasta(&rel) {
            append_fasta_payload_records(&source, &target)?;
            continue;
        }
        if is_appendable_add_ctg_fai(&rel) {
            append_plain_payload_lines(&source, &target)?;
            continue;
        }
        if target.exists() {
            bail!(
                "add_ctg payload target already exists: {}",
                target.display()
            );
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create add_ctg payload target dir {}",
                    parent.display()
                )
            })?;
        }
        fs::copy(&source, &target).with_context(|| {
            format!(
                "failed to copy add_ctg payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
    }
    Ok(())
}

pub(super) fn is_allowed_add_payload_file(rel: &str) -> bool {
    is_appendable_add_payload_tsv(rel)
        || rel == "tel/rules.tsv"
        || rel.starts_with("data/datasets/")
        || rel.starts_with("data/partitions/")
        || rel.starts_with("runs/")
}

pub(super) fn is_allowed_add_ctg_payload_file(rel: &str) -> bool {
    rel == "metadata/datasets.tsv"
        || rel == "metadata/track_member_orders.tsv"
        || is_appendable_add_ctg_payload_tsv(rel)
        || rel.starts_with("data/derived_ctgs/")
        || rel == "data/datasets/derived_ctg.fa"
        || rel == "data/datasets/derived_ctg.fa.fai"
        || rel.starts_with("runs/add_ctg/")
        || rel.starts_with("runs/chr_")
}

pub(super) fn is_appendable_add_payload_tsv(rel: &str) -> bool {
    rel == "metadata/datasets.tsv"
        || rel == "metadata/chr_assignments.tsv"
        || rel == "metadata/track_member_orders.tsv"
        || rel == "metadata/source_seq_locator.tsv"
        || rel == "metadata/source_seq_n_regions.tsv"
        || (rel.starts_with("tel/chr_") && rel.ends_with(".tsv"))
        || (rel.starts_with("cen/chr_") && rel.ends_with("/marks.tsv"))
}

pub(super) fn is_appendable_add_ctg_payload_tsv(rel: &str) -> bool {
    rel == "metadata/chr_assignments.tsv"
        || rel == "metadata/source_seq_locator.tsv"
        || rel == "metadata/source_seq_n_regions.tsv"
        || rel == "metadata/derived_ctgs.tsv"
        || rel == "metadata/track_members.tsv"
}

pub(super) fn is_appendable_add_ctg_fasta(rel: &str) -> bool {
    rel == "data/datasets/derived_ctg.fa"
        || (rel.starts_with("runs/chr_") && rel.ends_with("/datasets/derived_ctg.fa"))
}

pub(super) fn is_appendable_add_ctg_fai(rel: &str) -> bool {
    rel == "data/datasets/derived_ctg.fa.fai"
}

pub(super) fn append_tsv_payload_rows(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add payload tsv {}", source.display()))?;
    let mut source_lines = source_text.lines();
    let Some(source_header) = source_lines.next() else {
        bail!("add payload tsv is empty: {}", source.display());
    };
    let rows = source_lines
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if rows.is_empty() {
        return Ok(());
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add payload tsv dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add payload tsv {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }

    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if target_header != source_header {
        bail!("add payload tsv header mismatch for {}", target.display());
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace tsv {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    for row in rows {
        writeln!(file, "{row}")
            .with_context(|| format!("failed to append row to {}", target.display()))?;
    }
    Ok(())
}

pub(super) fn replace_track_member_order_groups(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source).with_context(|| {
        format!(
            "failed to read add_ctg track order tsv {}",
            source.display()
        )
    })?;
    let mut source_lines = source_text.lines();
    let source_header = source_lines
        .next()
        .context("add_ctg track member order tsv is empty")?;
    let source_rows = source_lines
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if source_rows.is_empty() {
        bail!("add_ctg track member order snapshot has no members");
    }
    let groups = source_rows
        .iter()
        .map(|line| {
            let columns = line.split('\t').collect::<Vec<_>>();
            if columns.len() != 5 {
                bail!("invalid add_ctg track member order row: {line}");
            }
            Ok((columns[0].to_string(), columns[1].to_string()))
        })
        .collect::<Result<HashSet<_>>>()?;

    let mut merged_rows = Vec::new();
    if target.exists() {
        let target_text = fs::read_to_string(target).with_context(|| {
            format!(
                "failed to read workspace track order tsv {}",
                target.display()
            )
        })?;
        let mut target_lines = target_text.lines();
        let target_header = target_lines.next().unwrap_or_default();
        if target_header != source_header {
            bail!(
                "add_ctg track member order tsv header mismatch for {}",
                target.display()
            );
        }
        for line in target_lines.filter(|line| !line.trim().is_empty()) {
            let columns = line.split('\t').collect::<Vec<_>>();
            if columns.len() != 5 {
                bail!("invalid workspace track member order row: {line}");
            }
            if !groups.contains(&(columns[0].to_string(), columns[1].to_string())) {
                merged_rows.push(line.to_string());
            }
        }
    } else if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).with_context(|| {
            format!(
                "failed to create track member order metadata dir {}",
                parent.display()
            )
        })?;
    }
    merged_rows.extend(source_rows.into_iter().map(ToString::to_string));
    let mut output = String::new();
    output.push_str(source_header);
    output.push('\n');
    for row in merged_rows {
        output.push_str(&row);
        output.push('\n');
    }
    fs::write(target, output).with_context(|| {
        format!(
            "failed to replace track member order groups in {}",
            target.display()
        )
    })?;
    Ok(())
}

pub(super) fn append_dataset_tsv_if_new(
    source: &Path,
    target: &Path,
    dataset_name: &str,
) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg dataset tsv {}", source.display()))?;
    let mut source_lines = source_text.lines();
    let Some(source_header) = source_lines.next() else {
        bail!("add_ctg dataset tsv is empty: {}", source.display());
    };
    let source_rows = source_lines
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if source_rows.is_empty() {
        return Ok(());
    }
    if source_rows.len() != 1 || !source_rows[0].starts_with(&format!("{dataset_name}\t")) {
        bail!("add_ctg dataset payload must contain only dataset {dataset_name}");
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!(
                    "failed to create add_ctg dataset tsv dir {}",
                    parent.display()
                )
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg dataset tsv {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }

    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace dataset tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if target_header != source_header {
        bail!(
            "add_ctg dataset tsv header mismatch for {}",
            target.display()
        );
    }
    let already_present = target_text
        .lines()
        .skip(1)
        .any(|line| line.split('\t').next() == Some(dataset_name));
    if already_present {
        return Ok(());
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace dataset tsv {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    writeln!(file, "{}", source_rows[0])
        .with_context(|| format!("failed to append dataset row to {}", target.display()))?;
    Ok(())
}

pub(super) fn append_fasta_payload_records(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg fasta {}", source.display()))?;
    if !source_text.lines().any(|line| line.starts_with('>')) {
        bail!(
            "add_ctg fasta payload has no FASTA header: {}",
            source.display()
        );
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg fasta dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg fasta {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace fasta {}", target.display()))?;
    let source_headers = source_text
        .lines()
        .filter_map(|line| line.strip_prefix('>'))
        .map(|line| {
            line.split_whitespace()
                .next()
                .unwrap_or_default()
                .to_string()
        })
        .collect::<Vec<_>>();
    for header in &source_headers {
        if target_text
            .lines()
            .filter_map(|line| line.strip_prefix('>'))
            .any(|line| line.split_whitespace().next() == Some(header.as_str()))
        {
            bail!("add_ctg fasta target already contains record: {header}");
        }
    }
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace fasta {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    write!(file, "{source_text}")
        .with_context(|| format!("failed to append fasta record to {}", target.display()))?;
    if !source_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to terminate fasta {}", target.display()))?;
    }
    Ok(())
}

pub(super) fn append_plain_payload_lines(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add_ctg payload {}", source.display()))?;
    let rows = source_text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    if rows.is_empty() {
        return Ok(());
    }
    if !target.exists() {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| {
                format!("failed to create add_ctg payload dir {}", parent.display())
            })?;
        }
        fs::copy(source, target).with_context(|| {
            format!(
                "failed to copy add_ctg payload {} to {}",
                source.display(),
                target.display()
            )
        })?;
        return Ok(());
    }
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace payload {}", target.display()))?;
    let mut file = OpenOptions::new()
        .append(true)
        .open(target)
        .with_context(|| format!("failed to open workspace payload {}", target.display()))?;
    if !target_text.ends_with('\n') {
        writeln!(file)
            .with_context(|| format!("failed to append newline to {}", target.display()))?;
    }
    for row in rows {
        writeln!(file, "{row}")
            .with_context(|| format!("failed to append row to {}", target.display()))?;
    }
    Ok(())
}

pub(super) fn validate_tsv_payload_header(source: &Path, target: &Path) -> Result<()> {
    let source_text = fs::read_to_string(source)
        .with_context(|| format!("failed to read add payload tsv {}", source.display()))?;
    let source_header = source_text.lines().next().unwrap_or_default();
    let target_text = fs::read_to_string(target)
        .with_context(|| format!("failed to read workspace tsv {}", target.display()))?;
    let target_header = target_text.lines().next().unwrap_or_default();
    if source_header != target_header {
        bail!("add payload tsv header mismatch for {}", target.display());
    }
    Ok(())
}
