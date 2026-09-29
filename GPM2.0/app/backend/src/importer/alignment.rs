use super::*;

#[derive(Debug, Clone)]
pub(super) struct PairwiseImportRun {
    run_name: String,
    paf_path: PathBuf,
    query_dataset_id: i64,
    target_dataset_id: i64,
}

pub(super) fn index_alignment_payloads_from_bundle<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
    options: ImportOptions,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    options.resolved_pairwise_parser_workers()?;
    let mut conn = open_workspace_db(project_db_path)?;
    let ref_run_count = count_bundle_ref_alignment_runs(&conn, bundle_root)?;
    let pairwise_runs = discover_pairwise_import_runs(&conn, bundle_root)?;
    let pairwise_remaining = if pairwise_runs.is_empty() { 3 } else { 4 };
    recorder.reserve_remaining(1 + ref_run_count + 1 + pairwise_runs.len() + pairwise_remaining);
    conn.execute("DELETE FROM ref_alignment_hit", [])
        .context("failed to clear old ref alignment hits before import indexing")?;
    recorder.record(
        "index_alignment_reset",
        "cleared previous reference alignment index".to_string(),
    );
    let ref_summary = index_bundle_ref_alignment_hits_with_cancel(
        &mut conn,
        bundle_root,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    bulk_index_pairwise_alignment_runs(
        &mut conn,
        bundle_root,
        pairwise_runs,
        recorder,
        should_cancel,
        options,
    )
}

const PAIRWISE_HIT_INSERT_ROWS: usize = 256;
const PAIRWISE_PARSE_BATCH_ROWS: usize = 2_048;
const PAIRWISE_PROGRESS_BYTES: u64 = 8 * 1024 * 1024;
const PAIRWISE_MESSAGE_POLL: std::time::Duration = std::time::Duration::from_millis(50);
const PAIRWISE_PROGRESS_INTERVAL: std::time::Duration = std::time::Duration::from_millis(250);

const DROP_PAIRWISE_HIT_INDEXES_SQL: &str = "
    DROP INDEX IF EXISTS idx_pairwise_hit_query_target;
    DROP INDEX IF EXISTS idx_pairwise_hit_target_query;
";

const CREATE_PAIRWISE_HIT_INDEXES_SQL: &str = "
    CREATE INDEX IF NOT EXISTS idx_pairwise_hit_query_target
        ON pairwise_alignment_hit(run_id, query_source_seq_id, target_source_seq_id, align_length, mapq);
    CREATE INDEX IF NOT EXISTS idx_pairwise_hit_target_query
        ON pairwise_alignment_hit(run_id, target_source_seq_id, query_source_seq_id, align_length, mapq);
";

#[derive(Debug)]
struct PairwiseHitRow {
    run_id: i64,
    query_source_seq_id: i64,
    target_source_seq_id: i64,
    strand: &'static str,
    query_start: i64,
    query_end: i64,
    target_start: i64,
    target_end: i64,
    match_length: i64,
    align_length: i64,
    mapq: i64,
    identity_pct: f64,
    cg_tag: String,
}

#[derive(Debug, Clone)]
struct PreparedPairwiseImportRun {
    run_id: i64,
    file_index: usize,
    run_name: String,
    paf_path: PathBuf,
    relative_path: String,
    total_bytes: u64,
    query_name_map: std::sync::Arc<HashMap<String, i64>>,
    target_name_map: std::sync::Arc<HashMap<String, i64>>,
    self_run: bool,
}

enum PairwiseWorkerMessage {
    Started {
        file_index: usize,
        run_name: String,
        relative_path: String,
    },
    Batch {
        file_index: usize,
        bytes_read: u64,
        parsed_rows: u64,
        rows: Vec<PairwiseHitRow>,
    },
    Progress {
        file_index: usize,
        bytes_read: u64,
        parsed_rows: u64,
    },
    Finished {
        file_index: usize,
        bytes_read: u64,
        parsed_rows: u64,
    },
    Failed {
        relative_path: String,
        error: String,
    },
}

#[derive(Debug, Default, Clone, Copy)]
struct PairwiseRunProgressState {
    current_bytes: u64,
    parsed_rows: u64,
    written_hits: u64,
}

fn bulk_index_pairwise_alignment_runs<P, C>(
    conn: &mut rusqlite::Connection,
    bundle_root: &Path,
    pairwise_runs: Vec<PairwiseImportRun>,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
    options: ImportOptions,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let requested_workers = options.resolved_pairwise_parser_workers()?;
    let name_maps = pairwise_source_seq_name_maps(conn, &pairwise_runs)?;
    conn.execute_batch("PRAGMA cache_size = -262144;")
        .context("failed to configure pairwise bulk-load sqlite cache")?;
    let tx = conn
        .transaction()
        .context("failed to begin initial pairwise bulk load")?;
    tx.execute_batch(DROP_PAIRWISE_HIT_INDEXES_SQL)
        .context("failed to defer pairwise hit indexes")?;
    tx.execute("DELETE FROM pairwise_alignment_run", [])
        .context("failed to clear old pairwise alignment runs before bulk load")?;

    let indexed_at = current_unix_millis_string();
    let mut prepared_runs = Vec::with_capacity(pairwise_runs.len());
    for (file_index, run) in pairwise_runs.into_iter().enumerate() {
        let metadata = fs::metadata(&run.paf_path)
            .with_context(|| format!("failed to stat pairwise paf {}", run.paf_path.display()))?;
        let total_bytes = metadata.len();
        let paf_mtime_ms = metadata
            .modified()
            .ok()
            .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
            .map(|duration| i64::try_from(duration.as_millis()).unwrap_or(i64::MAX))
            .unwrap_or(0);
        let paf_size_bytes = i64::try_from(total_bytes).unwrap_or(i64::MAX);
        let paf_path_text = run.paf_path.to_string_lossy().to_string();
        tx.execute(
            "INSERT INTO pairwise_alignment_run (
                run_name, paf_path, query_dataset_id, target_dataset_id,
                paf_mtime_ms, paf_size_bytes, indexed_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                run.run_name,
                paf_path_text,
                run.query_dataset_id,
                run.target_dataset_id,
                paf_mtime_ms,
                paf_size_bytes,
                indexed_at,
            ],
        )
        .with_context(|| format!("failed to insert pairwise run {}", run.run_name))?;
        let run_id = tx.last_insert_rowid();
        let query_name_map = name_maps
            .get(&run.query_dataset_id)
            .cloned()
            .with_context(|| {
                format!(
                    "missing source sequence map for dataset {}",
                    run.query_dataset_id
                )
            })?;
        let target_name_map = name_maps
            .get(&run.target_dataset_id)
            .cloned()
            .with_context(|| {
                format!(
                    "missing source sequence map for dataset {}",
                    run.target_dataset_id
                )
            })?;
        prepared_runs.push(PreparedPairwiseImportRun {
            run_id,
            file_index,
            relative_path: path_relative_to(bundle_root, &run.paf_path),
            run_name: run.run_name,
            paf_path: run.paf_path,
            total_bytes,
            query_name_map,
            target_name_map,
            self_run: run.query_dataset_id == run.target_dataset_id,
        });
    }

    let file_total = prepared_runs.len();
    let total_bytes = prepared_runs.iter().map(|run| run.total_bytes).sum::<u64>();
    let parser_workers = requested_workers.min(file_total.max(1));
    recorder.record(
        "index_pairwise_paf_start",
        format!(
            "files={file_total}, total_bytes={total_bytes}, parser_workers={parser_workers}, sqlite_writers=1, deferred_indexes=2"
        ),
    );

    if prepared_runs.is_empty() {
        check_import_cancel(should_cancel)?;
        tx.execute_batch(CREATE_PAIRWISE_HIT_INDEXES_SQL)
            .context("failed to create pairwise hit indexes after empty bulk load")?;
        check_import_cancel(should_cancel)?;
        tx.commit()
            .context("failed to commit empty pairwise bulk load")?;
        recorder.record(
            "index_pairwise_paf_complete",
            "indexed_runs=0, indexed_hits=0, parsed_rows=0, parser_workers=0".to_string(),
        );
        return Ok(());
    }

    let queue = std::sync::Arc::new(std::sync::Mutex::new(
        prepared_runs
            .iter()
            .cloned()
            .collect::<std::collections::VecDeque<_>>(),
    ));
    let cancelled = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let channel_capacity = parser_workers.saturating_mul(2).max(1);
    let (sender, receiver) = std::sync::mpsc::sync_channel(channel_capacity);
    let mut worker_handles = Vec::with_capacity(parser_workers);
    for worker_index in 0..parser_workers {
        let queue = std::sync::Arc::clone(&queue);
        let cancelled = std::sync::Arc::clone(&cancelled);
        let sender = sender.clone();
        worker_handles.push(
            std::thread::Builder::new()
                .name(format!("pairwise-paf-parser-{}", worker_index + 1))
                .spawn(move || pairwise_parser_worker(queue, sender, cancelled))
                .context("failed to spawn pairwise parser worker")?,
        );
    }
    drop(sender);

    let mut states = vec![PairwiseRunProgressState::default(); file_total];
    let mut first_error: Option<anyhow::Error> = None;
    let mut last_progress_emit = std::time::Instant::now() - PAIRWISE_PROGRESS_INTERVAL;
    loop {
        if first_error.is_none() && should_cancel() {
            cancelled.store(true, std::sync::atomic::Ordering::Release);
            first_error = Some(anyhow::anyhow!("import cancelled"));
        }
        match receiver.recv_timeout(PAIRWISE_MESSAGE_POLL) {
            Ok(PairwiseWorkerMessage::Started {
                file_index,
                run_name,
                relative_path,
            }) => {
                recorder.record(
                    "index_pairwise_paf",
                    format!(
                        "{} ({}) file={}/{}",
                        run_name,
                        relative_path,
                        file_index + 1,
                        file_total
                    ),
                );
            }
            Ok(PairwiseWorkerMessage::Batch {
                file_index,
                bytes_read,
                parsed_rows,
                rows,
            }) => {
                let row_count = rows.len() as u64;
                if first_error.is_none() {
                    if let Err(error) = insert_pairwise_hit_batch(&tx, rows) {
                        cancelled.store(true, std::sync::atomic::Ordering::Release);
                        first_error = Some(error);
                    } else {
                        states[file_index].written_hits += row_count;
                    }
                }
                states[file_index].current_bytes = bytes_read;
                states[file_index].parsed_rows = parsed_rows;
                if last_progress_emit.elapsed() >= PAIRWISE_PROGRESS_INTERVAL {
                    emit_pairwise_progress(
                        recorder,
                        &prepared_runs,
                        &states,
                        file_index,
                        total_bytes,
                    );
                    last_progress_emit = std::time::Instant::now();
                }
            }
            Ok(PairwiseWorkerMessage::Progress {
                file_index,
                bytes_read,
                parsed_rows,
            }) => {
                states[file_index].current_bytes = bytes_read;
                states[file_index].parsed_rows = parsed_rows;
                if last_progress_emit.elapsed() >= PAIRWISE_PROGRESS_INTERVAL {
                    emit_pairwise_progress(
                        recorder,
                        &prepared_runs,
                        &states,
                        file_index,
                        total_bytes,
                    );
                    last_progress_emit = std::time::Instant::now();
                }
            }
            Ok(PairwiseWorkerMessage::Finished {
                file_index,
                bytes_read,
                parsed_rows,
            }) => {
                states[file_index].current_bytes = bytes_read;
                states[file_index].parsed_rows = parsed_rows;
                emit_pairwise_progress(recorder, &prepared_runs, &states, file_index, total_bytes);
                last_progress_emit = std::time::Instant::now();
            }
            Ok(PairwiseWorkerMessage::Failed {
                relative_path,
                error,
            }) => {
                cancelled.store(true, std::sync::atomic::Ordering::Release);
                if first_error.is_none() {
                    first_error = Some(anyhow::anyhow!(
                        "failed to parse pairwise paf {relative_path}: {error}"
                    ));
                }
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => continue,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
        }
    }

    for handle in worker_handles {
        if handle.join().is_err() && first_error.is_none() {
            first_error = Some(anyhow::anyhow!("pairwise parser worker panicked"));
        }
    }
    if let Some(error) = first_error {
        return Err(error);
    }

    check_import_cancel(should_cancel)?;
    recorder.record(
        "index_pairwise_paf_indexes",
        "creating pairwise query indexes after bulk load".to_string(),
    );
    check_import_cancel(should_cancel)?;
    tx.execute_batch(CREATE_PAIRWISE_HIT_INDEXES_SQL)
        .context("failed to create pairwise hit indexes after bulk load")?;
    check_import_cancel(should_cancel)?;
    tx.commit()
        .context("failed to commit initial pairwise bulk load")?;

    let indexed_hit_count = states.iter().map(|state| state.written_hits).sum::<u64>();
    let parsed_row_count = states.iter().map(|state| state.parsed_rows).sum::<u64>();
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={file_total}, indexed_hits={indexed_hit_count}, parsed_rows={parsed_row_count}, parser_workers={parser_workers}"
        ),
    );
    Ok(())
}

fn pairwise_source_seq_name_maps(
    conn: &rusqlite::Connection,
    runs: &[PairwiseImportRun],
) -> Result<HashMap<i64, std::sync::Arc<HashMap<String, i64>>>> {
    let dataset_ids = runs
        .iter()
        .flat_map(|run| [run.query_dataset_id, run.target_dataset_id])
        .collect::<HashSet<_>>();
    let mut maps = HashMap::with_capacity(dataset_ids.len());
    let mut stmt = conn
        .prepare("SELECT seq_name, id FROM source_seq WHERE dataset_id = ?1")
        .context("failed to prepare pairwise source sequence map query")?;
    for dataset_id in dataset_ids {
        let entries = stmt
            .query_map(params![dataset_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
            })?
            .collect::<std::result::Result<HashMap<_, _>, _>>()
            .with_context(|| {
                format!("failed to load source sequence map for dataset {dataset_id}")
            })?;
        maps.insert(dataset_id, std::sync::Arc::new(entries));
    }
    Ok(maps)
}

fn pairwise_parser_worker(
    queue: std::sync::Arc<std::sync::Mutex<std::collections::VecDeque<PreparedPairwiseImportRun>>>,
    sender: std::sync::mpsc::SyncSender<PairwiseWorkerMessage>,
    cancelled: std::sync::Arc<std::sync::atomic::AtomicBool>,
) {
    loop {
        if cancelled.load(std::sync::atomic::Ordering::Acquire) {
            break;
        }
        let next_run = match queue.lock() {
            Ok(mut queue) => queue.pop_front(),
            Err(error) => {
                let _ = sender.send(PairwiseWorkerMessage::Failed {
                    relative_path: "<queue>".to_string(),
                    error: format!("pairwise parser queue poisoned: {error}"),
                });
                cancelled.store(true, std::sync::atomic::Ordering::Release);
                break;
            }
        };
        let Some(run) = next_run else {
            break;
        };
        if let Err(error) = parse_pairwise_import_run(&run, &sender, &cancelled) {
            let _ = sender.send(PairwiseWorkerMessage::Failed {
                relative_path: run.relative_path.clone(),
                error: format!("{error:#}"),
            });
            cancelled.store(true, std::sync::atomic::Ordering::Release);
            break;
        }
    }
}

fn parse_pairwise_import_run(
    run: &PreparedPairwiseImportRun,
    sender: &std::sync::mpsc::SyncSender<PairwiseWorkerMessage>,
    cancelled: &std::sync::atomic::AtomicBool,
) -> Result<()> {
    send_pairwise_worker_message(
        sender,
        cancelled,
        PairwiseWorkerMessage::Started {
            file_index: run.file_index,
            run_name: run.run_name.clone(),
            relative_path: run.relative_path.clone(),
        },
    )?;
    let file = File::open(&run.paf_path)
        .with_context(|| format!("failed to open pairwise paf {}", run.paf_path.display()))?;
    let mut reader = BufReader::with_capacity(256 * 1024, file);
    let mut line = Vec::with_capacity(512);
    let mut batch = Vec::with_capacity(PAIRWISE_PARSE_BATCH_ROWS);
    let mut bytes_read = 0_u64;
    let mut parsed_rows = 0_u64;
    let mut last_reported_bytes = 0_u64;
    loop {
        if cancelled.load(std::sync::atomic::Ordering::Acquire) {
            bail!("import cancelled");
        }
        line.clear();
        let read = reader
            .read_until(b'\n', &mut line)
            .with_context(|| format!("failed to read {}", run.paf_path.display()))?;
        if read == 0 {
            break;
        }
        bytes_read = bytes_read.saturating_add(read as u64);
        parsed_rows += 1;
        while matches!(line.last(), Some(b'\n' | b'\r')) {
            line.pop();
        }
        if let Some(row) = parse_pairwise_paf_row(&line, run) {
            batch.push(row);
        }
        if batch.len() >= PAIRWISE_PARSE_BATCH_ROWS {
            let rows = std::mem::replace(&mut batch, Vec::with_capacity(PAIRWISE_PARSE_BATCH_ROWS));
            send_pairwise_worker_message(
                sender,
                cancelled,
                PairwiseWorkerMessage::Batch {
                    file_index: run.file_index,
                    bytes_read,
                    parsed_rows,
                    rows,
                },
            )?;
            last_reported_bytes = bytes_read;
        } else if bytes_read.saturating_sub(last_reported_bytes) >= PAIRWISE_PROGRESS_BYTES {
            send_pairwise_worker_message(
                sender,
                cancelled,
                PairwiseWorkerMessage::Progress {
                    file_index: run.file_index,
                    bytes_read,
                    parsed_rows,
                },
            )?;
            last_reported_bytes = bytes_read;
        }
    }
    if !batch.is_empty() {
        send_pairwise_worker_message(
            sender,
            cancelled,
            PairwiseWorkerMessage::Batch {
                file_index: run.file_index,
                bytes_read,
                parsed_rows,
                rows: batch,
            },
        )?;
    }
    send_pairwise_worker_message(
        sender,
        cancelled,
        PairwiseWorkerMessage::Finished {
            file_index: run.file_index,
            bytes_read,
            parsed_rows,
        },
    )
}

fn send_pairwise_worker_message(
    sender: &std::sync::mpsc::SyncSender<PairwiseWorkerMessage>,
    cancelled: &std::sync::atomic::AtomicBool,
    message: PairwiseWorkerMessage,
) -> Result<()> {
    if cancelled.load(std::sync::atomic::Ordering::Acquire) {
        bail!("import cancelled");
    }
    sender
        .send(message)
        .map_err(|_| anyhow::anyhow!("pairwise writer stopped before parsers completed"))
}

fn parse_pairwise_paf_row(line: &[u8], run: &PreparedPairwiseImportRun) -> Option<PairwiseHitRow> {
    let mut fields = line.split(|byte| *byte == b'\t');
    let query_name = std::str::from_utf8(fields.next()?).ok()?;
    parse_paf_i64(fields.next()?)?;
    let query_start_0 = parse_paf_i64(fields.next()?)?;
    let query_end = parse_paf_i64(fields.next()?)?;
    let strand = match fields.next()? {
        b"+" => "+",
        b"-" => "-",
        _ => return None,
    };
    let target_name = std::str::from_utf8(fields.next()?).ok()?;
    parse_paf_i64(fields.next()?)?;
    let target_start_0 = parse_paf_i64(fields.next()?)?;
    let target_end = parse_paf_i64(fields.next()?)?;
    let match_length = parse_paf_i64(fields.next()?)?;
    let align_length = parse_paf_i64(fields.next()?)?;
    let mapq = parse_paf_i64(fields.next()?)?;
    if align_length <= 0 {
        return None;
    }
    let query_start = query_start_0 + 1;
    let target_start = target_start_0 + 1;
    if query_start < 1 || query_end < query_start || target_start < 1 || target_end < target_start {
        return None;
    }
    let query_source_seq_id = run.query_name_map.get(query_name).copied()?;
    let target_source_seq_id = run.target_name_map.get(target_name).copied()?;
    if run.self_run && query_source_seq_id == target_source_seq_id {
        return None;
    }
    let cg_tag = fields
        .find_map(|field| field.strip_prefix(b"cg:Z:"))
        .and_then(|value| String::from_utf8(value.to_vec()).ok())
        .unwrap_or_default();
    Some(PairwiseHitRow {
        run_id: run.run_id,
        query_source_seq_id,
        target_source_seq_id,
        strand,
        query_start,
        query_end,
        target_start,
        target_end,
        match_length,
        align_length,
        mapq,
        identity_pct: (match_length as f64) * 100.0 / (align_length as f64),
        cg_tag,
    })
}

fn parse_paf_i64(value: &[u8]) -> Option<i64> {
    if value.is_empty() {
        return None;
    }
    let (negative, digits) = match value.first() {
        Some(b'-') => (true, &value[1..]),
        Some(b'+') => (false, &value[1..]),
        _ => (false, value),
    };
    if digits.is_empty() {
        return None;
    }
    let mut parsed = 0_i64;
    for digit in digits {
        if !digit.is_ascii_digit() {
            return None;
        }
        parsed = parsed
            .checked_mul(10)?
            .checked_add(i64::from(digit - b'0'))?;
    }
    negative.then_some(-parsed).or(Some(parsed))
}

fn insert_pairwise_hit_batch(conn: &rusqlite::Connection, rows: Vec<PairwiseHitRow>) -> Result<()> {
    for chunk in rows.chunks(PAIRWISE_HIT_INSERT_ROWS) {
        let placeholders =
            std::iter::repeat_n("(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", chunk.len())
                .collect::<Vec<_>>()
                .join(",");
        let sql = format!(
            "INSERT INTO pairwise_alignment_hit (
                run_id, query_source_seq_id, target_source_seq_id, strand,
                query_start, query_end, target_start, target_end,
                match_length, align_length, mapq, identity_pct, cg_tag
             ) VALUES {placeholders}"
        );
        let mut values = Vec::<&dyn rusqlite::ToSql>::with_capacity(chunk.len() * 13);
        for row in chunk {
            values.extend([
                &row.run_id as &dyn rusqlite::ToSql,
                &row.query_source_seq_id,
                &row.target_source_seq_id,
                &row.strand,
                &row.query_start,
                &row.query_end,
                &row.target_start,
                &row.target_end,
                &row.match_length,
                &row.align_length,
                &row.mapq,
                &row.identity_pct,
                &row.cg_tag,
            ]);
        }
        conn.prepare_cached(&sql)
            .context("failed to prepare pairwise alignment hit batch insert")?
            .execute(rusqlite::params_from_iter(values))
            .context("failed to insert pairwise alignment hit batch")?;
    }
    Ok(())
}

fn emit_pairwise_progress<P>(
    recorder: &mut ImportProgressWriter<'_, P>,
    runs: &[PreparedPairwiseImportRun],
    states: &[PairwiseRunProgressState],
    file_index: usize,
    overall_total_bytes: u64,
) where
    P: FnMut(ImportProgress),
{
    let run = &runs[file_index];
    let state = states[file_index];
    let overall_bytes = states.iter().map(|state| state.current_bytes).sum::<u64>();
    let detail = format!(
        "{} ({}) bytes={}/{} parsed_rows={} written_hits={} file={}/{} overall_bytes={}/{}",
        run.run_name,
        run.relative_path,
        state.current_bytes,
        run.total_bytes,
        state.parsed_rows,
        state.written_hits,
        file_index + 1,
        runs.len(),
        overall_bytes,
        overall_total_bytes,
    );
    let mut item = step("index_pairwise_paf_progress", detail);
    item.pairwise = Some(PairwiseImportProgress {
        active_run: run.run_name.clone(),
        active_path: run.relative_path.clone(),
        current_bytes: state.current_bytes,
        total_bytes: run.total_bytes,
        parsed_rows: state.parsed_rows,
        written_hits: state.written_hits,
        file_index: file_index + 1,
        file_total: runs.len(),
        overall_bytes,
        overall_total_bytes,
    });
    recorder.emit_transient(item);
}

pub(super) fn count_bundle_ref_alignment_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<usize> {
    let mut stmt = conn
        .prepare("SELECT name FROM dataset ORDER BY id")
        .context("failed to prepare dataset list for ref paf import progress")?;
    let dataset_names = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for ref paf import progress")?;
    Ok(dataset_names
        .iter()
        .filter(|dataset_name| {
            bundle_root
                .join("runs")
                .join(format!("{}_vs_ref", dataset_name))
                .join("result.paf")
                .exists()
        })
        .count())
}

pub(super) fn discover_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        run_orientation_by_name.insert(
            format!("{}_vs_self", target_name),
            (*target_dataset_id, *target_dataset_id),
        );
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}

pub(super) fn index_add_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    dataset_id: i64,
    dataset_name: &str,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs =
        discover_pairwise_import_runs_for_dataset(&conn, bundle_root, dataset_id, dataset_name)?;
    recorder.reserve_remaining(1 + pairwise_runs.len() + 2);
    let ref_summary = index_bundle_ref_alignment_hits_for_dataset_with_cancel(
        &mut conn,
        bundle_root,
        dataset_id,
        dataset_name,
        should_cancel,
        &mut |run_name, paf_path| {
            recorder.record(
                "index_ref_paf",
                format!("{} ({})", run_name, path_relative_to(bundle_root, paf_path)),
            );
        },
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!(
            "loaded_datasets={}, loaded_hits={}, skipped_datasets={}",
            ref_summary.loaded_dataset_count,
            ref_summary.loaded_hit_count,
            ref_summary.skipped_dataset_count
        ),
    );

    let mut indexed_run_count = 0_i64;
    let mut indexed_hit_count = 0_i64;
    for run in pairwise_runs {
        check_import_cancel(should_cancel)?;
        recorder.record(
            "index_pairwise_paf",
            format!(
                "{} ({})",
                run.run_name,
                path_relative_to(bundle_root, &run.paf_path)
            ),
        );
        let cache = ensure_pairwise_alignment_run_cache_cancel(
            &mut conn,
            run.query_dataset_id,
            run.target_dataset_id,
            &run.run_name,
            &run.paf_path,
            should_cancel,
        )?;
        indexed_run_count += 1;
        indexed_hit_count += cache.hit_count;
    }
    recorder.record(
        "index_pairwise_paf_complete",
        format!(
            "indexed_runs={}, indexed_hits={}",
            indexed_run_count, indexed_hit_count
        ),
    );
    Ok(())
}

pub(super) fn index_add_ctg_alignment_payloads<P, C>(
    project_db_path: &Path,
    bundle_root: &Path,
    manifest: &AddCtgManifest,
    catalog: &AddCtgCatalogAppend,
    project_id: i64,
    recorder: &mut ImportProgressWriter<'_, P>,
    should_cancel: &mut C,
) -> Result<()>
where
    P: FnMut(ImportProgress),
    C: FnMut() -> bool,
{
    check_import_cancel(should_cancel)?;
    let mut conn = open_workspace_db(project_db_path)?;
    let pairwise_runs = if manifest.skip_self {
        Vec::new()
    } else {
        discover_add_ctg_pairwise_import_runs(&conn, bundle_root, project_id, manifest)?
    };
    recorder.reserve_remaining(
        2 + if pairwise_runs.is_empty() {
            0
        } else {
            pairwise_runs.len() + 1
        },
    );
    let ref_run_name = format!("{}_vs_ref", manifest.ctg_name);
    let ref_paf_path = bundle_root
        .join("runs")
        .join("add_ctg")
        .join(&ref_run_name)
        .join("result.paf");
    recorder.record(
        "index_ref_paf",
        format!(
            "{} ({})",
            ref_run_name,
            path_relative_to(bundle_root, &ref_paf_path)
        ),
    );
    let loaded_ref_hits = index_ref_alignment_hits_for_source_seq_with_cancel(
        &mut conn,
        catalog.dataset_id,
        catalog.source_seq_id,
        &manifest.ctg_name,
        &ref_run_name,
        &ref_paf_path,
        should_cancel,
    )?;
    recorder.record(
        "index_ref_paf_complete",
        format!("loaded_datasets=1, loaded_hits={loaded_ref_hits}, skipped_datasets=0"),
    );

    if !pairwise_runs.is_empty() {
        let mut indexed_run_count = 0_i64;
        let mut indexed_hit_count = 0_i64;
        for run in pairwise_runs {
            check_import_cancel(should_cancel)?;
            recorder.record(
                "index_pairwise_paf",
                format!(
                    "{} ({})",
                    run.run_name,
                    path_relative_to(bundle_root, &run.paf_path)
                ),
            );
            let cache = ensure_pairwise_alignment_run_cache_cancel(
                &mut conn,
                catalog.dataset_id,
                run.target_dataset_id,
                &run.run_name,
                &run.paf_path,
                should_cancel,
            )?;
            indexed_run_count += 1;
            indexed_hit_count += cache.hit_count;
        }
        recorder.record(
            "index_pairwise_paf_complete",
            format!(
                "indexed_runs={}, indexed_hits={}",
                indexed_run_count, indexed_hit_count
            ),
        );
    }
    Ok(())
}

pub(super) fn discover_add_ctg_pairwise_import_runs(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    project_id: i64,
    manifest: &AddCtgManifest,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = required_add_ctg_pairwise_datasets(conn, project_id, &manifest.target_chr)?;
    let mut runs = Vec::new();
    for (target_dataset_id, target_dataset_name) in datasets {
        let pair_run_name = format!("{}_vs_{}", target_dataset_name, manifest.ctg_name);
        let pair_paf_path = bundle_root
            .join("runs")
            .join(format!("chr_{}", manifest.target_chr))
            .join("add_ctg")
            .join(&pair_run_name)
            .join("result.paf");
        if !pair_paf_path.is_file() {
            bail!(
                "add_ctg payload is missing chr-group pairwise alignment payload: {}",
                pair_paf_path.display()
            );
        }
        runs.push(PairwiseImportRun {
            run_name: pair_run_name,
            paf_path: pair_paf_path,
            query_dataset_id: 0,
            target_dataset_id,
        });
    }
    runs.sort_by(|a, b| a.run_name.cmp(&b.run_name));
    Ok(runs)
}

pub(super) fn required_add_ctg_pairwise_datasets(
    conn: &rusqlite::Connection,
    project_id: i64,
    target_chr: &str,
) -> Result<Vec<(i64, String)>> {
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT d.id, d.name
             FROM project_dataset pd
             JOIN dataset d ON d.id = pd.dataset_id
             JOIN source_seq ss ON ss.dataset_id = d.id
             JOIN imported_chr_assignment ica ON ica.source_seq_id = ss.id
             JOIN reference_chr rc ON rc.id = ica.reference_chr_id
             WHERE pd.project_id = ?1
               AND rc.chr_name = ?2
               AND d.name <> 'derived_ctg'
             ORDER BY d.id",
        )
        .context("failed to prepare add_ctg required pairwise dataset query")?;
    stmt.query_map(params![project_id, target_chr], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })?
    .collect::<std::result::Result<Vec<_>, _>>()
    .context("failed to decode add_ctg required pairwise datasets")
}

pub(super) fn discover_pairwise_import_runs_for_dataset(
    conn: &rusqlite::Connection,
    bundle_root: &Path,
    added_dataset_id: i64,
    added_dataset_name: &str,
) -> Result<Vec<PairwiseImportRun>> {
    let datasets = {
        let mut stmt = conn
            .prepare("SELECT id, name FROM dataset ORDER BY id")
            .context("failed to prepare dataset list for add-package pairwise paf import")?;
        stmt.query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("failed to decode dataset rows for add-package pairwise paf import")?
    };
    let mut run_orientation_by_name = HashMap::<String, (i64, i64)>::new();
    for (target_dataset_id, target_name) in &datasets {
        if *target_dataset_id == added_dataset_id {
            run_orientation_by_name.insert(
                format!("{}_vs_self", target_name),
                (*target_dataset_id, *target_dataset_id),
            );
        }
        for (query_dataset_id, query_name) in &datasets {
            if target_dataset_id == query_dataset_id {
                continue;
            }
            if *target_dataset_id != added_dataset_id && *query_dataset_id != added_dataset_id {
                continue;
            }
            run_orientation_by_name.insert(
                format!("{}_vs_{}", target_name, query_name),
                (*query_dataset_id, *target_dataset_id),
            );
        }
    }

    let runs_root = bundle_root.join("runs");
    if !runs_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut runs = Vec::new();
    for chr_entry in fs::read_dir(&runs_root)
        .with_context(|| format!("failed to read runs dir {}", runs_root.display()))?
    {
        let chr_entry = chr_entry
            .with_context(|| format!("failed to read entry under {}", runs_root.display()))?;
        let chr_path = chr_entry.path();
        if !chr_path.is_dir() {
            continue;
        }
        let chr_name = chr_entry.file_name().to_string_lossy().to_string();
        if !chr_name.starts_with("chr_") {
            continue;
        }
        for run_entry in fs::read_dir(&chr_path)
            .with_context(|| format!("failed to read chr run dir {}", chr_path.display()))?
        {
            let run_entry = run_entry
                .with_context(|| format!("failed to read entry under {}", chr_path.display()))?;
            let run_path = run_entry.path();
            if !run_path.is_dir() {
                continue;
            }
            let run_name = run_entry.file_name().to_string_lossy().to_string();
            if !run_name.contains(added_dataset_name) {
                continue;
            }
            let Some((query_dataset_id, target_dataset_id)) =
                run_orientation_by_name.get(&run_name).copied()
            else {
                continue;
            };
            let paf_path = run_path.join("result.paf");
            if !paf_path.exists() {
                continue;
            }
            runs.push(PairwiseImportRun {
                run_name,
                paf_path,
                query_dataset_id,
                target_dataset_id,
            });
        }
    }
    runs.sort_by(|a, b| a.paf_path.cmp(&b.paf_path));
    Ok(runs)
}
