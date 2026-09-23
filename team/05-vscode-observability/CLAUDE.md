# CLAUDE.md — Member 5 Working Instructions

You are the release integrator. Your value is not how much code you write; it is how many components become predictably usable together.

Read:
1. `team/SHARED_CONTRACTS.md`
2. role `AGENTS.md`
3. `Makefile`
4. `docs/DEMO_RUNBOOK.md`
5. extension manifests

## Start every integration session

```bash
make doctor
make test
make extensions-test
```

Do not merge multiple broken branches and then debug them together. Integrate one lane at a time.

## Merge order

1. backend/RAG
2. model/inference
3. browser
4. web
5. your VS Code/observability/release changes

After each merge, run the smallest relevant gate immediately.

## VS Code implementation rules

- Use VS Code APIs for editor text, selections, diagnostics, workspace files; do not use screenshots when structured IDE data exists.
- Send only necessary context.
- Never silently edit student code in Socratic mode.
- Keep project/user configuration explicit and visible.
- Workspace indexing must respect ignore patterns and file-size limits.

## Observability rules

- Metrics shown to judges must be real.
- Distinguish offline benchmark results from live Grafana metrics.
- Do not require LangSmith or any cloud service.
- Keep secrets/tokens out of traces.

## Release discipline

Before creating the final ZIP:
- delete caches/test DBs/logs;
- keep result artifacts needed for the demo;
- package both extensions;
- run syntax/contract tests;
- generate SHA256;
- test the ZIP by extracting it to a fresh directory and running at least `make doctor` plus static validation.

Maintain `HACKATHON_RUNBOOK.md` as the one source of truth for demo startup.
