# Working in VORTEX

- Keep the user's requested changes in this repository so Git diffs explain what changed. Use focused commits and a short validation note when publishing; do not fabricate earlier commits or rewrite shared history.
- Treat historical experiment inputs and reports as versioned evidence. Do not overwrite `reports/v0.1` to make new parameters appear to be the old result. Use a new experiment identifier and output directory.
- Keep broker/VPS credentials, account identifiers, remote-access profiles, raw personal screenshots, and `.env` files out of Git and browser assets.
- The dashboard currently displays historical research snapshots. Do not label it live or show broker account data until a real authenticated integration exists. Six module scores belong to one combined strategy, not six independently profitable agents.
- Preserve full dataset hashes and disclose when raw data or large generated journals remain local. A viewed holdout cannot be reused as an unseen test set.
- Run meaningful checks for changes: research unit tests for simulator/signal/audit behavior; source-data reconciliation and browser interaction checks for dashboard changes. A successful build alone does not verify displayed numbers.
- Trading execution is outside the current implementation. Do not add or activate broker orders as a side effect of dashboard, deployment, or research work.
