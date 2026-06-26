mod auto_pipeline_cancel;
mod commands;
mod import_cancel;

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::import_zip,
            commands::import_extracted,
            commands::import_add_dataset_package,
            commands::import_add_ctg_package,
            commands::request_import_cancel,
            commands::open_workspace,
            commands::validate_workspace_integrity,
            commands::delete_workspace_directory,
            commands::list_project_initializer_options,
            commands::initialize_project,
            commands::update_project,
            commands::delete_project,
            commands::bootstrap_project_assembly,
            commands::auto_assign_chr,
            commands::auto_orient_contigs,
            commands::auto_orient_contigs_for_dataset,
            commands::request_auto_pipeline_cancel,
            commands::set_project_auto_pipeline_done,
            commands::list_project_chromosomes,
            commands::list_new_sequences,
            commands::list_chr_view_ctgs,
            commands::list_reference_track_members,
            commands::list_phased_chr_tracks,
            commands::create_phased_chr_track,
            commands::delete_phased_chr_track,
            commands::add_ctg_to_phased_chr_track,
            commands::remove_phased_chr_track_item,
            commands::reorder_phased_chr_track_items,
            commands::list_deleted_ctgs,
            commands::get_ctg_detail,
            commands::list_ctg_edit_candidates,
            commands::restore_deleted_ctg,
            commands::run_ctg_editor_action,
            commands::get_junction_inspection,
            commands::get_track_pairwise_evidence,
            commands::list_export_records,
            commands::get_runtime_settings,
            commands::update_runtime_settings,
            commands::get_project_assembly_view_state,
            commands::update_project_assembly_view_state,
            commands::append_edit_audit_log,
            commands::list_edit_audit_logs,
            commands::clear_edit_audit_logs,
            commands::pick_zip_file_path,
            commands::pick_directory_path,
            commands::pick_save_file_path,
            commands::write_final_path_export_text_file,
            commands::write_final_path_export_binary_file,
            commands::export_final_path_fasta,
            commands::export_project_final_path_fasta,
            commands::export_degap_jobs
        ])
        .run(tauri::generate_context!())
        .expect("failed to run tauri application");
}
