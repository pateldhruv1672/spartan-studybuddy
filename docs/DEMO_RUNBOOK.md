# Demo runbook — enterprise onboarding

1. On the DGX Spark run `cp .env.example .env && make dgx-setup`.
2. Run `make test`. This is the release gate: real PostgreSQL+pgvector integration tests plus Chrome/VS Code extension contract tests.
3. Run `make seed` for the fraud-platform demo workspace, or ingest a real private GitHub repository from Sources.
4. Run `make start` and open the Spark URL from the MacBook.
5. Create/choose a workspace and show repo architecture + hybrid RAG search with file/line citations.
6. Create a role-specific onboarding path; invite another user and show XP/leaderboard progress.
7. Ask a direct factual question (e.g. “What does this function do?”), then switch to Socratic mode for an exercise/debugging question.
8. Install the packaged VS Code extension and show editor-context Q&A plus on-save re-indexing.
9. Load the Chrome extension and show a YouTube learning session/resume card.
10. Start the Mac Browser-Use bridge and show Resource Scout curating public learning material from sanitized prerequisite concepts.
11. Open Engineering Lab/Grafana and show measured TTFT, TPS, p50/p95 and agent traces.
12. For the model story, show base vs tuned Socratic evaluation and standard-vLLM vs speculative-decoding results generated on this Spark.

## Demo recovery

- **Model not ready:** product still boots; model fallback keeps ingestion/UI flows testable, but label it clearly.
- **Browser-Use fails:** use already-curated path resources; do not make browser automation the first live step.
- **Network blocks Mac→Spark:** use Tailscale or SSH port forwarding.
- **Database issue:** `make db-status`; if the demo database can be discarded, `make db-reset -- --yes` then `make seed`.
- **Extension configuration:** Chrome popup/VS Code settings only require Spark API URL, project ID and user ID; no source edits are required.
