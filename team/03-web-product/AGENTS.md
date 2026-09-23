# AGENTS.md — Member 3: Web Product, UX & Gamification Lead

## Mission

Make Spartan StudyBuddy look and feel like a real premium enterprise product, not a hackathon AI dashboard. Own the manager and learner journeys, interaction design, onboarding roadmap experience, gamification, central assistant presentation, continuation/resume surfaces, and Engineering Lab visualization.

## Branch

`agent/web-product`

## You own

- `apps/web/**`
- visual design system
- frontend state/API adapters
- motion/animation
- product copy inside web UI

Do not modify backend response schemas. Request contract changes through `SHARED_CONTRACTS.md`.

## Design direction

- Apple-level restraint: whitespace, hierarchy, typography, soft depth, fluid motion.
- No generic purple-gradient “AI slop.”
- Avoid walls of cards. Use deliberate information architecture.
- The AI pet/companion can be expressive but must not make enterprise workflows childish.
- Use animation for state/continuity, not decoration.
- Make the product understandable in <10 seconds to a judge.

## Required experiences

### Manager
1. Create/select company workspace.
2. Add source: GitHub, Drive, URL, upload.
3. See ingestion/index status and repository knowledge map.
4. Choose target role/level and create onboarding path.
5. Invite team member / share path code.
6. See progress, XP, leaderboard, common knowledge gaps.
7. See engineering/AI metrics sourced from real backend artifacts.

### Learner
1. See “Today” mission and current roadmap.
2. Resume unfinished video/article/paper with summary and recall question.
3. Open resource.
4. Complete checkpoint and earn XP.
5. Ask direct factual question.
6. Switch to “Teach me” Socratic mode.
7. Switch to “Explain simply.”
8. See citations to repo/docs.
9. See personal progress/mastery.

## Day-by-day tasks

### Day 1
- Implement stable API client/base state.
- Source ingestion screen against real APIs.
- Assistant shell with modes.
- Project/repo overview.
- No mocks for critical flows after end of Day 1.

### Day 2
- Role-based roadmap UI.
- Resource list/progress.
- manager invites/team.
- leaderboard/XP.
- resume/continuation experience.
- visual polish + meaningful transitions.

### Day 3
- Manager analytics.
- Engineering Lab reads real experiment artifacts/admin endpoint.
- empty/loading/error/offline states.
- responsive MacBook demo layout.
- UX polish from live repo data.

### Day 4
- freeze layout;
- replace all placeholder metrics;
- rehearse exact demo click path;
- eliminate scroll traps, hidden controls, broken states;
- capture screenshots for submission/pitch.

## Required acceptance criteria

- no critical demo path relies on hard-coded fake data;
- no displayed benchmark metric is fabricated;
- every asynchronous action has loading + error feedback;
- uploads show indexing status/result;
- assistant visually differentiates Direct / Socratic / Explain / Research;
- citations are clickable/readable;
- roadmap item state persists after refresh;
- leaderboard reflects backend state, not client-calculated points;
- resume card appears after a tracked resource session;
- UI works at typical MacBook 1440×900 and 1728×1117 scales;
- keyboard focus and contrast are acceptable for demo.

## Performance budget

Do not let visual effects compromise responsiveness. Target:
- initial interactive UI under ~2s on local network after static assets load;
- assistant streaming/feedback visible immediately;
- avoid huge unoptimized images/video backgrounds.

## Handoff

Provide Member 5:
- the exact final demo route/click sequence;
- any required environment/API base configuration;
- final screenshots;
- a list of every backend endpoint actually exercised by the demo.
