# CLAUDE.md — Member 4 Working Instructions

You own the browser learning layer.

Read:
1. `team/SHARED_CONTRACTS.md`
2. role `AGENTS.md`
3. `apps/chrome-extension/README.md`
4. Browser bridge code before editing prompts

## Start-of-session test

```bash
make extensions-test
```

Then launch the dedicated Chrome/CDP profile and bridge using the repository scripts.

## Development priorities

P0:
- extension connects to workspace;
- events/resource sessions persist;
- Browser-Use can claim and finish a job;
- privacy sanitizer holds.

P1:
- YouTube resume;
- research papers/articles;
- resource ranking;
- page selection → ask/explain.

P2:
- cosmetic popup enhancements and extra site-specific adapters.

## Robustness rules

- Never assume DOM selectors are permanent. Guard every page-specific query.
- Content scripts must fail silently/non-destructively on unsupported pages.
- Debounce telemetry; do not POST every second.
- Do not store access tokens in page DOM/localStorage accessible to websites.
- Do not let Browser-Use take irreversible account actions in the demo.
- Treat authenticated content access as user-authorized browsing, not permission to bulk-copy protected material.

## Before handoff

Verify:
1. install extension from package/unpacked folder;
2. connect project;
3. watch 30–60 seconds of a YouTube video;
4. pause/close/reopen app;
5. see resume state;
6. run a resource-scout job;
7. inspect the public search prompt for proprietary leakage.
