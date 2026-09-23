# CLAUDE.md — Member 3 Working Instructions

You are the product/UX engineer. Do not redesign backend architecture. Make the existing capabilities feel coherent, premium, and obvious.

Read:
1. `team/SHARED_CONTRACTS.md`
2. role `AGENTS.md`
3. current `apps/web/index.html`, `styles.css`, `app.js`

## Start each session

Run the backend and open the real app. Work with actual data as early as possible.

```bash
make run
```

If model endpoints are unavailable, use existing backend error states; do not permanently bake mock answers into production paths.

## UI principles

- One primary action per screen/section.
- Use progressive disclosure for technical details.
- Make source ingestion and onboarding generation feel deterministic and trustworthy.
- Always show where an answer came from.
- Different AI modes need distinct language and iconography, not separate disconnected products.
- Manager analytics should answer “who is ready, what are they stuck on, what should happen next?”

## Avoid

- neon gradients everywhere;
- random glass cards;
- excessive badges;
- auto-playing animation;
- fake charts;
- lorem ipsum or placeholder benchmark numbers.

## Test manually before commit

1. create/select project;
2. add a source;
3. ask direct question;
4. ask Socratic question;
5. create onboarding path;
6. join/update progress;
7. open leaderboard;
8. inspect resume card;
9. open Engineering Lab.

Keep edits inside `apps/web/**` unless explicitly coordinated.
