# AGENTS.md — Member 5: VS Code, Observability, Release Integration & Demo Reliability Lead

## Mission

Own the final mile: the IDE learning experience, system observability, deployment scripts, shared route integration, extension packaging, and release reliability. Your job is to ensure the other four lanes become one product that starts cleanly and survives a live demo.

## Branch

`agent/vscode-integration`

## You own

- `apps/vscode-extension/**`
- `deploy/observability/**`
- `scripts/dgx/**`
- `scripts/observability/**`
- `scripts/extensions/**`
- top-level `Makefile` integration targets
- route-level merge coordination in `backend/app/main.py`
- final packaging/runbook/validation

Do not rewrite model training or RAG internals unless their owner requests integration help.

## VS Code mission

The extension is not a generic Copilot clone. It should:
- connect to the same StudyBuddy project as the web/Chrome app;
- index opted-in code files/workspace;
- re-index supported files on save;
- send active editor/selection/diagnostics context;
- support Direct Q&A, Socratic Hint, Explain Simply;
- preserve central memory across surfaces;
- avoid automatically writing assignment solutions.

## Observability mission

Provide live evidence that edge inference is engineered, not merely “runs locally.”

Stack:
- Prometheus metrics;
- Grafana dashboard;
- Tempo/OpenTelemetry traces;
- local `agent_traces` persistence;
- optional LangSmith exporter only when explicitly configured.

Dashboard should show as available:
- request rate;
- backend latency;
- model route/model name;
- TTFT;
- tokens generated;
- decode tokens/sec;
- p50/p95 latency where aggregated;
- errors;
- active connections;
- agent job latency;
- retrieval/model traces.

## Day-by-day tasks

### Day 1
- VS Code extension installs/activates;
- workspace connect command works;
- direct ask/hint/explain commands reach backend;
- route integration from all owners remains green;
- create first clean deploy script path.

### Day 2
- index workspace command;
- index-on-save;
- include selection/current code/file path/diagnostics;
- ensure ignore rules for dependencies/build/binaries;
- start observability stack;
- Grafana has useful dashboard instead of empty default panels.

### Day 3
- integrate Member 1 benchmark artifacts into admin/observability surfaces where appropriate;
- package `.vsix` and Chrome ZIP;
- test fresh deployment from clean checkout/ZIP;
- run restart/failure recovery drill;
- maintain merge order and resolve contracts, not features.

### Day 4
- own release candidate;
- run every gate;
- freeze ZIP/checksum;
- rehearse exact startup commands;
- keep backup copy of DB volume/results/config;
- operate demo stack while others present.

## Release gates

Before tagging a release:

```bash
make doctor
make test
make extensions-test
make extensions-package
make models-health
make models-test
```

When hardware/time allows:

```bash
make benchmark
```

For clean demo deployment:

```bash
make deploy
```

## API integration responsibility

`backend/app/main.py` is your merge choke point. When another lane needs a route:
1. confirm it matches `team/SHARED_CONTRACTS.md`;
2. add/import route wiring;
3. run tests;
4. avoid reformatting unrelated route code.

## Required acceptance criteria

### VS Code
- `.vsix` installs without manifest errors;
- activity bar icon renders;
- Connect to Workspace persists at workspace scope;
- current code/selection is included only when requested;
- index-on-save works and is configurable;
- commands work after VS Code restart;
- failure to reach DGX produces clear UI, not extension crash.

### Observability
- Grafana loads from the MacBook;
- panels show real values during an assistant request;
- trace for one request can be followed from API → retrieval/model call;
- no cloud telemetry is required;
- optional LangSmith is clearly opt-in.

### Release
- clean ZIP can be deployed without source edits;
- environment changes are `.env` only;
- package contains both extension artifacts;
- startup/restart commands are documented;
- final checksum generated.

## Incident priorities during demo

1. Keep UI + direct Q&A alive.
2. Keep DB/RAG alive.
3. Keep tuned teacher alive.
4. Keep extensions alive.
5. Browser automation/observability are allowed to degrade gracefully if necessary.

Do not reboot or rebuild models in front of judges unless absolutely necessary.
