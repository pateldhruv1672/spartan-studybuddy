# AGENTS.md — Member 4: Chrome Extension, Browser-Use & Resource Intelligence Lead

## Mission

Own everything that happens while a learner is on the public web. The browser system should curate high-quality resources, track learning progress, create useful return summaries/questions, and synchronize that learning into central memory — without leaking private company code to public sites.

## Branch

`agent/browser-agent`

## You own

- `apps/chrome-extension/**`
- `bridges/mac_bridge.py`
- Browser-Use integration/prompts/tools
- browser-agent job processing
- browser-side resource session logic
- browser-focused tests

Do not alter backend core retrieval or model-training code.

## Core architecture

```text
FastAPI job queue on DGX
      ↓
Mac bridge claims job
      ↓
Browser-Use agent
      ↓
visible authenticated Chrome via CDP
      ↓
YouTube / docs / blogs / arXiv / public resources
      ↓
structured result
      ↓
complete agent job on DGX
```

Chrome extension independently observes learner activity and posts resource sessions/events.

## Privacy invariant

Public Browser-Use searches receive only sanitized generic topics such as:
- “Kafka consumer groups beginner tutorial”
- “feature stores production ML explanation”

Never:
- proprietary function bodies;
- private repository filenames revealing confidential products when avoidable;
- secrets/tokens;
- internal docs pasted into search queries.

## Day-by-day tasks

### Day 1
- extension installs in Chrome;
- backend URL + user/project connection persists;
- project list refresh works;
- one browser learning event reaches backend;
- one YouTube session reaches `/api/resource/session`.

### Day 2
- Browser-Use bridge claims and completes `resource_scout` jobs;
- resource output is structured and ranked enough for roadmap use;
- track YouTube progress, active time, last position;
- track article/paper active time and progress signals where practical;
- support “ask StudyBuddy about selection/page” flow.

### Day 3
- resume summary + recall questions work for incomplete resources;
- web research jobs return synthesis/sources;
- agent job benchmark runs;
- harden retries/timeouts/browser disconnects;
- confirm private-source sanitizer with test payloads.

### Day 4
- package extension;
- launch dedicated StudyBuddy Chrome profile via provided script;
- pre-authenticate required demo sites;
- rehearse one resource-scout and one YouTube resume flow twice.

## Resource scout output contract

Return objects containing, when available:
- title
- URL
- source/provider
- resource type: video/article/docs/paper/book
- difficulty
- estimated duration
- concepts
- why it fits the requested prerequisite
- recommended order

Do not scrape or redistribute paywalled book contents. Deep-link/metadata/recommended chapter is acceptable when authorized.

## Tracking behavior

YouTube:
- current time;
- duration;
- play/pause/ended;
- active visibility;
- progress;
- last position.

Articles/papers:
- active visible time;
- scroll/progress estimate;
- title/url;
- optional selected/visible learning context.

Activity is not proof of mastery. Completion should be reinforced by checkpoints in the StudyBuddy product.

## Required acceptance criteria

- `make extensions-test` passes Chrome checks;
- extension installs with no manifest errors;
- connection settings persist after browser restart;
- same user/project ID is used as web/VS Code;
- agent bridge authenticates through `/agent-llm/v1`, not raw vLLM;
- resource-scout job completes end-to-end;
- YouTube incomplete session produces a resume entry;
- extension failures never break normal browsing;
- no private code appears in outbound public-web agent queries.

## Fallback order

1. Browser-Use + vLLM teacher proxy.
2. Browser-Use + Ollama if configured.
3. Manual/public-resource seed only for emergency demo continuity — clearly label it if used.
