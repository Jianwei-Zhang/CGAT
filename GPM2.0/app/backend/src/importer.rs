//! Workspace import facade.
//!
//! Public callers enter through one of the workflow modules (`initial`,
//! `add_dataset`, or `add_ctg`). Those workflows depend on neutral manifest and
//! payload validation, workspace I/O, catalog persistence, and alignment
//! indexing modules; infrastructure modules never call a workflow entrypoint.
//!
//! Initial ZIP import owns a newly created workspace and removes that whole
//! workspace on any failure. Incremental imports validate before mutation,
//! snapshot `project.sqlite` plus every affected payload target through
//! `AddImportRollback`, and disarm the snapshot only after catalog, assembly,
//! alignment, and orientation work completes. This preserves the existing
//! file-plus-database rollback contract while keeping the public API stable.

use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use rusqlite::{OptionalExtension, Transaction, params};
use zip::ZipArchive;

use crate::alignment_cache::{
    index_bundle_ref_alignment_hits_for_dataset_with_cancel,
    index_bundle_ref_alignment_hits_with_cancel,
    index_ref_alignment_hits_for_source_seq_with_cancel,
};
use crate::db::open_workspace_db;
use crate::grt_package::{
    ValidatedGrtPackage, persist_grt_package, validate_grt_delivery_package_with_progress,
};
use crate::junction_inspection::ensure_pairwise_alignment_run_cache_cancel;
use crate::workspace::{resolve_bundle_root_dir, resolve_extracted_bundle_workspace};

mod add_catalog;
mod add_ctg;
mod add_dataset;
mod alignment;
mod catalog_common;
mod initial;
mod initial_catalog;
mod initial_persistence;
mod manifests;
mod payload_rollback;
mod payload_validation;
mod progress;
mod tsv;
mod types;
mod workspace_io;

pub use add_ctg::{import_add_ctg_package, import_add_ctg_package_with_hooks};
pub use add_dataset::{
    import_add_dataset_package, import_add_dataset_package_with_hooks,
    import_workspace_add_dataset_package, import_workspace_add_dataset_package_with_hooks,
};
pub use initial::{
    import_from_extracted_bundle, import_from_extracted_bundle_with_hooks, import_from_zip,
    import_from_zip_with_hooks,
};
pub use types::{
    AddCtgImportOutcome, AddCtgImportTarget, AddDatasetImportOutcome, CACHE_DIR, EXPORTS_DIR,
    ImportMode, ImportOutcome, ImportProgress, PROJECT_DB_NAME,
};

use add_catalog::*;
use alignment::*;
use catalog_common::*;
use initial_catalog::*;
use initial_persistence::*;
use manifests::*;
use payload_rollback::*;
use payload_validation::*;
use progress::*;
use tsv::*;
use types::{
    AddCtgCatalogAppend, AddCtgManifest, AddDatasetManifest, CentromereMarkRow, DatasetRow,
    DerivedCtgRow, EXTRACTED_IMPORT_PHASE_TOTAL, FaiRow, ImportedChrAssignmentRow,
    ImportedTrackMemberOrderRow, PackageRow, ReferenceChrLocatorRow, ReferenceRow,
    SourceSeqLocatorRow, SourceSeqNRegionRow, TelomereMarkRow, TelomereRuleRow, TrackMemberRow,
    ValidatedAddCtgPackage, ZIP_IMPORT_PHASE_TOTAL,
};
use workspace_io::*;

#[cfg(test)]
mod tests;
