use std::collections::{HashSet, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::SystemTime;

use anyhow::{Result, anyhow};

use crate::exporter::load_named_sequences_from_fasta;
use crate::reference_segments::{
    ReferenceGapInterval, ReferenceSegment, detect_reference_segments,
};

type Geometry = (Vec<ReferenceSegment>, Vec<ReferenceGapInterval>);
const MAX_CACHED_CHROMOSOMES: usize = 32;

#[derive(PartialEq, Eq)]
struct CacheKey {
    path: PathBuf,
    size: u64,
    modified: SystemTime,
    chr_name: String,
}

#[derive(Default)]
struct ReferenceCache {
    entries: VecDeque<(CacheKey, Geometry)>,
}

impl ReferenceCache {
    fn load(&mut self, path: &Path, chr_name: &str) -> Result<Geometry> {
        let path = path.canonicalize()?;
        let metadata = path.metadata()?;
        let key = CacheKey {
            path,
            size: metadata.len(),
            modified: metadata.modified()?,
            chr_name: chr_name.to_owned(),
        };
        if let Some(index) = self.entries.iter().position(|(cached, _)| cached == &key) {
            let entry = self.entries.remove(index).unwrap();
            let geometry = entry.1.clone();
            self.entries.push_back(entry);
            return Ok(geometry);
        }

        let names = HashSet::from([chr_name.to_owned()]);
        let mut sequences = load_named_sequences_from_fasta(&key.path, &names)?;
        let sequence = sequences
            .remove(chr_name)
            .ok_or_else(|| anyhow!("missing {chr_name}"))?;
        let segments = detect_reference_segments(chr_name, &sequence, 100);
        let gaps = super::derive_reference_gaps_from_segments(&segments, sequence.len() as i64);
        let geometry = (segments, gaps);
        // Retain only coordinates, never chromosome sequences or mutable project data.
        self.entries.retain(|(cached, _)| {
            cached.path != key.path || (cached.size == key.size && cached.modified == key.modified)
        });
        if self.entries.len() >= MAX_CACHED_CHROMOSOMES {
            self.entries.pop_front();
        }
        self.entries.push_back((key, geometry.clone()));
        Ok(geometry)
    }
}

pub(super) fn load_reference_geometry(path: &Path, chr_name: &str) -> Result<Geometry> {
    static CACHE: OnceLock<Mutex<ReferenceCache>> = OnceLock::new();
    // Serialize cold reads so overlapping track requests do not scan the same FASTA twice.
    CACHE
        .get_or_init(Mutex::default)
        .lock()
        .map_err(|_| anyhow!("reference geometry cache lock poisoned"))?
        .load(path, chr_name)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::reference_segments::detect_reference_gap_intervals;

    #[test]
    fn cached_geometry_matches_sequence_detection_and_is_bounded() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let path = temp.path().join("ref.fa");
        let sequence = format!(
            "{}ACGT{}AC{}",
            "N".repeat(101),
            "n".repeat(100),
            "N".repeat(102)
        );
        std::fs::write(
            &path,
            (0..40)
                .map(|i| format!(">chr{i}\n{sequence}\n"))
                .collect::<String>(),
        )?;
        let mut cache = ReferenceCache::default();
        for i in 0..40 {
            let chr = format!("chr{i}");
            let expected = (
                detect_reference_segments(&chr, &sequence, 100),
                detect_reference_gap_intervals(&sequence, 100),
            );
            assert_eq!(cache.load(&path, &chr)?, expected);
            assert_eq!(cache.load(&path, &chr)?, expected);
        }
        assert_eq!(cache.entries.len(), MAX_CACHED_CHROMOSOMES);
        Ok(())
    }

    #[test]
    fn changed_missing_and_recreated_files_do_not_reuse_stale_geometry() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let path = temp.path().join("ref.fa");
        std::fs::write(&path, format!(">chr1\n{}\n", "A".repeat(100)))?;
        let mut cache = ReferenceCache::default();
        let first = cache.load(&path, "chr1")?;
        let modified = path.metadata()?.modified()?;
        std::fs::write(&path, format!(">chr1\n{}\n", "N".repeat(100)))?;
        std::fs::File::options()
            .write(true)
            .open(&path)?
            .set_modified(modified + std::time::Duration::from_secs(2))?;
        let second = cache.load(&path, "chr1")?;
        assert_ne!(first, second);
        assert!(second.0.is_empty());
        assert_eq!(
            second.1,
            vec![ReferenceGapInterval {
                start_bp: 1,
                end_bp: 100
            }]
        );
        assert_eq!(cache.entries.len(), 1);
        std::fs::remove_file(&path)?;
        assert!(cache.load(&path, "chr1").is_err());
        std::fs::write(&path, ">chr1\nAC\n")?;
        assert_eq!(cache.load(&path, "chr1")?.0[0].end_bp, 2);
        assert!(cache.load(&path, "missing").is_err());
        assert_eq!(cache.entries.len(), 1);
        Ok(())
    }

    #[test]
    fn metadata_overrides_warm_fasta_cache_and_workspaces_stay_separate() -> Result<()> {
        let first = tempfile::tempdir()?;
        let second = tempfile::tempdir()?;
        let path = first.path().join("ref.fa");
        let other = second.path().join("ref.fa");
        std::fs::write(&path, ">chr1\nACGT\n")?;
        std::fs::write(&other, ">chr1\nAC\n")?;
        assert_eq!(load_reference_geometry(&path, "chr1")?.0[0].end_bp, 4);
        assert_eq!(load_reference_geometry(&other, "chr1")?.0[0].end_bp, 2);
        std::fs::create_dir(first.path().join("metadata"))?;
        let metadata = first.path().join("metadata/reference_segments.tsv");
        let header = "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp\n";
        for end in [3, 2] {
            std::fs::write(&metadata, format!("{header}chr1\t1\t1\t{end}\n"))?;
            let geometry = super::super::resolve_reference_track_segments(
                Some(first.path()),
                path.to_str().unwrap(),
                "chr1",
                4,
            )?;
            assert_eq!(geometry.0[0].end_bp, end);
        }
        Ok(())
    }
}
