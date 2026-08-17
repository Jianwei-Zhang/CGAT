use super::*;

pub(super) struct ImportProgressWriter<'a, P>
where
    P: FnMut(ImportProgress),
{
    progress: Vec<ImportProgress>,
    on_progress: &'a mut P,
    log_path: Option<PathBuf>,
    emitted_count: usize,
    expected_total: Option<usize>,
    phase_index: Option<usize>,
    phase_total: Option<usize>,
}

impl<'a, P> ImportProgressWriter<'a, P>
where
    P: FnMut(ImportProgress),
{
    pub(super) fn new(on_progress: &'a mut P) -> Self {
        Self {
            progress: Vec::new(),
            on_progress,
            log_path: None,
            emitted_count: 0,
            expected_total: None,
            phase_index: None,
            phase_total: None,
        }
    }

    pub(super) fn set_phase(&mut self, phase_index: usize, phase_total: usize) {
        self.phase_index = Some(phase_index);
        self.phase_total = Some(phase_total.max(phase_index));
    }

    pub(super) fn reserve_remaining(&mut self, remaining_count: usize) {
        self.set_expected_total(self.progress.len() + remaining_count);
    }

    pub(super) fn set_expected_total(&mut self, total: usize) {
        let normalized = total.max(self.progress.len());
        self.expected_total = Some(normalized);
    }

    pub(super) fn enable_log(&mut self, workspace_root: &Path) -> Result<()> {
        let cache_dir = workspace_root.join(CACHE_DIR);
        fs::create_dir_all(&cache_dir).with_context(|| {
            format!(
                "failed to create import log cache dir under {}",
                workspace_root.display()
            )
        })?;
        let log_path = cache_dir.join("import.log");
        append_import_log_line(
            &log_path,
            &format!(
                "# import_session\t{}",
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|duration| duration.as_millis().to_string())
                    .unwrap_or_else(|_| "0".to_string())
            ),
        )?;
        for step in &self.progress {
            append_import_log_step(&log_path, step)?;
        }
        self.log_path = Some(log_path);
        Ok(())
    }

    pub(super) fn record(&mut self, stage: &'static str, detail: String) {
        self.record_step(step(stage, detail));
    }

    pub(super) fn record_step(&mut self, mut item: ImportProgress) {
        self.emitted_count += 1;
        let progress_index = self.emitted_count;
        let progress_total = self
            .expected_total
            .unwrap_or(progress_index)
            .max(progress_index);
        item.progress_index = Some(progress_index);
        item.progress_total = Some(progress_total);
        if item.phase_index.is_none() {
            item.phase_index = self.phase_index;
        }
        if item.phase_total.is_none() {
            item.phase_total = self.phase_total;
        }
        (self.on_progress)(item.clone());
        if let Some(log_path) = self.log_path.as_deref() {
            let _ = append_import_log_step(log_path, &item);
        }
        self.progress.push(item);
    }

    pub(super) fn into_progress(mut self) -> Vec<ImportProgress> {
        let final_total = self
            .expected_total
            .unwrap_or(self.progress.len())
            .max(self.progress.len());
        for (index, step) in self.progress.iter_mut().enumerate() {
            step.progress_index = Some(index + 1);
            step.progress_total = Some(final_total);
        }
        self.progress
    }
}

pub(super) fn append_import_log_step(path: &Path, step: &ImportProgress) -> Result<()> {
    append_import_log_line(path, &format!("{}\t{}", step.stage, step.detail))
}

pub(super) fn append_import_log_line(path: &Path, line: &str) -> Result<()> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open import log {}", path.display()))?;
    writeln!(file, "{line}")
        .with_context(|| format!("failed to write import log {}", path.display()))?;
    Ok(())
}
