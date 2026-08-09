use super::*;

pub(super) fn dispatch(command: Commands) -> Result<Option<Commands>> {
    match command {
        Commands::InspectBundleRoot { path } => {
            let resolved = resolve_extracted_bundle_workspace(&path)?;
            println!("bundle_root={}", resolved.bundle_root.display());
            println!("workspace_root={}", resolved.workspace_root.display());
        }
        Commands::ImportExtracted { path } => {
            let (outcome, progress) = import_from_extracted_bundle(&path)?;
            print_progress(&progress);
            print_outcome(&outcome);
        }
        Commands::ImportZip {
            zip_path,
            workspace_root,
        } => {
            let (outcome, progress) = import_from_zip(&zip_path, &workspace_root)?;
            print_progress(&progress);
            print_outcome(&outcome);
        }
        Commands::ImportAddDatasetPackage {
            zip_path,
            workspace_root,
        } => {
            let (outcome, progress) =
                import_workspace_add_dataset_package(&zip_path, &workspace_root)?;
            print_progress(&progress);
            print_add_dataset_outcome(&outcome);
        }
        command => return Ok(Some(command)),
    }
    Ok(None)
}
