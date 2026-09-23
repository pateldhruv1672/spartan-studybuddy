# Spartan StudyBuddy — 5-Member Agent Pack

This folder contains a four-day execution plan and role-specific instructions for five parallel developers/AI coding agents.

## Files

- `TEAM_EXECUTION_PLAN.md` — team-level schedule, ownership, demo definition of done.
- `SHARED_CONTRACTS.md` — APIs, ports, model names, database/retrieval invariants.
- `01-model-inference/AGENTS.md` + `CLAUDE.md`
- `02-backend-rag/AGENTS.md` + `CLAUDE.md`
- `03-web-product/AGENTS.md` + `CLAUDE.md`
- `04-browser-agent/AGENTS.md` + `CLAUDE.md`
- `05-vscode-observability/AGENTS.md` + `CLAUDE.md`

## Recommended use

Each teammate checks out their own branch and copies/uses the role's `AGENTS.md` and `CLAUDE.md` as the local working instructions for their coding agent. Keep `TEAM_EXECUTION_PLAN.md` and `SHARED_CONTRACTS.md` visible to everyone.

The role files are intentionally opinionated about ownership. Their purpose is to prevent five agents from editing the same backend/frontend files and creating integration conflicts.
