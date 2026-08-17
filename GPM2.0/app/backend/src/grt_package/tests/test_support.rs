pub(super) use std::fs;
pub(super) use std::io::Write;

pub(super) use serde_json::Value;
pub(super) use tempfile::tempdir;
pub(super) use zip::CompressionMethod;
pub(super) use zip::write::FileOptions;

pub(super) use super::super::*;

pub(super) fn fixture_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/grt_contract_v2/valid/gpm_server")
}

pub(super) fn invalid_cases_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures/grt_contract_v2/invalid_cases.json")
}

pub(super) fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() {
            copy_tree(&source_path, &target_path);
        } else {
            fs::copy(source_path, target_path).unwrap();
        }
    }
}

pub(super) fn write_bundle_zip(source: &Path, zip_path: &Path) {
    let file = fs::File::create(zip_path).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    append_tree_to_zip(&mut zip, source, Path::new("gpm_server"));
    zip.finish().unwrap();
}

pub(super) fn append_tree_to_zip(
    zip: &mut zip::ZipWriter<fs::File>,
    source: &Path,
    archive_path: &Path,
) {
    let options = FileOptions::default().compression_method(CompressionMethod::Stored);
    zip.add_directory(
        format!("{}/", archive_path.to_string_lossy().replace('\\', "/")),
        options,
    )
    .unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let source_path = entry.path();
        let child_archive_path = archive_path.join(entry.file_name());
        if source_path.is_dir() {
            append_tree_to_zip(zip, &source_path, &child_archive_path);
        } else {
            zip.start_file(
                child_archive_path.to_string_lossy().replace('\\', "/"),
                options,
            )
            .unwrap();
            zip.write_all(&fs::read(source_path).unwrap()).unwrap();
        }
    }
}
