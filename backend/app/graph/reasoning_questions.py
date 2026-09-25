"""Conceptual scenarios grounded in the selected module's real evidence."""
from .questions import Ctx, QSpec, _choices, _cite

SCENARIOS = [
    ('A change passes unit tests but breaks a downstream integration. Which investigation best reduces uncertainty?',
     'Trace the changed contract through its consumers and test a representative integration boundary.',
     ['Increase unit-test repetitions before checking the integration.', 'Revert the consumer while leaving its contract undocumented.', 'Add retries at every call site before isolating the failure.'],
     'Unit tests isolate behavior; contract and integration checks test assumptions across component boundaries.', 'testing-fundamentals'),
    ('A retried operation can repeat a side effect after a timeout. Which design best addresses that ambiguity?',
     'Persist an idempotency key with the operation result and return the prior result on retries.',
     ['Increase the timeout so duplicate requests become less likely.', 'Keep retry identifiers only in the browser memory.', 'Retry only once and assume the first operation did not commit.'],
     'A timeout does not prove failure. Durable deduplication must cover the side effect and its recorded result.', 'api-design'),
    ('You need to assess the impact of changing a shared component. What should guide the first review?',
     'Inspect its dependants and public contracts, then verify the affected flows.',
     ['Review only the component with the most lines.', 'Begin by renaming its callers to match the new design.', 'Assume unchanged callers are unaffected if the component compiles.'],
     'Dependencies identify possible propagation paths; contract and behavior checks determine actual impact.', 'code-review-practices'),
    ('Two users request the same protected resource. What makes an authorization test meaningful?',
     'Check each identity against resource ownership, including a valid identity from another workspace.',
     ['Check that both users can authenticate successfully.', 'Use an obscure resource identifier and verify it is hard to guess.', 'Hide the resource in navigation and test only the visible page.'],
     'Authentication establishes identity; authorization must enforce the identity-resource relationship on the server.', 'security-basics'),
    ('A regression is intermittent under concurrent requests. Which test provides the strongest evidence for a fix?',
     'Synchronize competing requests at the critical boundary and assert the persisted invariant.',
     ['Run one request many times without overlap.', 'Assert that the endpoint returns a success status.', 'Add a delay to every client request and check the UI.'],
     'A concurrency regression needs overlapping operations and a durable-state assertion, not only response checks.', 'testing-fundamentals'),
    ('A dependency graph shows no test edge for a component. What conclusion is justified?',
     'The graph has not identified a test relationship; inspect test discovery before claiming missing coverage.',
     ['The component has never been exercised by a test.', 'The component must be safe because nothing depends on its tests.', 'The component should be deleted before further investigation.'],
     'Static extraction is incomplete evidence. Absence of an extracted relationship is not proof of absence.', 'testing-fundamentals'),
]


def generate(ctx: Ctx, limit: int = 4) -> list[QSpec]:
    """Pick scenarios relevant to this module's concepts, not the whole fixed bank every time.

    Modules that share concepts (e.g. two "testing-fundamentals" sections in different projects) would
    otherwise draw the identical scenario set on every call, regardless of the module's own content.
    Relevant scenarios come first; if there are fewer than `limit`, a deterministic (seeded) sample of the
    rest fills the remainder so quizzes still vary by module instead of always shipping the same six.
    """
    nodes = ctx.files or ctx.docs or ctx.all_files[:3]
    if not nodes:
        return []
    evidence = [_cite(ctx.v.node(n)) for n in nodes[:3]]
    relevant = [(i, s) for i, s in enumerate(SCENARIOS) if s[4] in ctx.concept_ids]
    rest = [(i, s) for i, s in enumerate(SCENARIOS) if s[4] not in ctx.concept_ids]
    ctx.rng.shuffle(rest)
    picked = (relevant + rest)[:max(1, limit)]
    out = []
    for idx, (prompt, correct, distractors, explanation, concept) in picked:
        choices, answer = _choices(ctx.rng, [correct], distractors)
        out.append(QSpec('mcq',prompt,choices,answer,explanation,evidence,concept,2,'graph-and-concept',1.0,f'reasoning-{idx}'))
    return out
