mod cli;

fn main() -> anyhow::Result<()> {
    // Windows debug CLI imports traverse the complete nested package contract
    // and can exceed the platform's default main-thread stack.
    std::thread::Builder::new()
        .name("gpm-next-backend-cli".to_string())
        .stack_size(8 * 1024 * 1024)
        .spawn(cli::run)?
        .join()
        .map_err(|_| anyhow::anyhow!("backend CLI worker panicked"))?
}
