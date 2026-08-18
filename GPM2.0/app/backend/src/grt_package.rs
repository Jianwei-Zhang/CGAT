//! GRT v2 package facade.
//!
//! Validation is pure and completes before the importer opens or mutates a
//! workspace database. A validated in-memory contract is then persisted by the
//! caller's single transaction. Read models, initialization, and trace queries
//! depend only on persisted domain rows and never on raw package parser state.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::db::open_workspace_db;
use crate::project_initializer::{
    ProjectInitializationRequest, bootstrap_project_assembly_with_connection,
    delete_project_with_connection, initialize_project_with_connection,
    list_initializer_options_with_connection, set_project_auto_pipeline_done_with_connection,
};

mod contract_validator;
mod delivery_validator;
mod domain_validation;
mod initialization;
mod parsing;
mod persistence;
mod read_model;
mod trace_queries;
mod types;

#[cfg(test)]
pub(crate) use contract_validator::validate_grt_package;
pub(crate) use contract_validator::validate_grt_package_with_progress;
pub(crate) use delivery_validator::validate_grt_delivery_package_with_progress;
pub use initialization::{initialize_grt_project, initialize_grt_project_with_options};
pub(crate) use persistence::persist_grt_package;
pub use read_model::{
    load_grt_final_path, load_grt_final_path_by_chr, load_grt_final_path_by_chr_for_project,
    load_grt_locked_recipe, load_grt_object_attempts, load_grt_project_view,
    load_grt_project_view_for_project, load_grt_source_card_statuses, load_grt_source_cards,
    load_persisted_grt_final_path_verification,
};
pub use trace_queries::{
    load_grt_event_trace, load_grt_evidence, load_grt_source_card_trace,
    verify_persisted_grt_final_path,
};
pub(crate) use types::ValidatedGrtPackage;
pub use types::{
    GRT_APP_DISPLAY_FINAL_PATH_SCHEMA_VERSION, GRT_APP_WORKFLOW, GRT_FINAL_PATH_SCHEMA_VERSION,
    GRT_SCHEMA_VERSION, GRT_WORKFLOW, GrtEventTrace, GrtFinalPathVerification, GrtLockedRecipe,
    GrtProjectInitializationSummary, GrtProjectView, GrtSourceCardStatus, GrtSourceCardTrace,
};

use domain_validation::*;
use parsing::*;
#[cfg(test)]
use read_model::project_grt_final_path_chromosome;
use trace_queries::load_matching_json;
use types::{
    AppQ4Validation, CHR_ASSIGNMENTS_HEADER, DATASETS_HEADER, DONOR_MEMBERS_HEADER, PACKAGE_HEADER,
    RECIPE_HEADER, REFERENCE_CHR_LOCATOR_HEADER, REFERENCE_HEADER, REQUIRED_FILES,
    SOURCE_LOCATOR_HEADER, SOURCE_N_REGIONS_HEADER, STAGE_TRANSITIONS, TABLE_SPECS,
    TRACK_MEMBER_ORDERS_HEADER, TsvRow, TsvTable, USED_CONTIGS_HEADER,
    is_supported_app_final_path_schema,
};

#[cfg(test)]
mod tests;
