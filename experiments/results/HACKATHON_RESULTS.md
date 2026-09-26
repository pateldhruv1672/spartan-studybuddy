# Spartan StudyBuddy — measured model results

> Generated from measurements on the deployment hardware. Do not replace these values with estimated claims.

## Socratic behavior

| Metric | Base | Fine-tuned |
|---|---:|---:|
| Held-out rubric score / 100 | 43.12 | 71.25 |
| Direct-answer leakage rate | 62.5% | 0.0% |
| Probing-question rate | 12.5% | 0.0% |

## Base vs tuned serving

| Metric | Base | Tuned |
|---|---:|---:|
| p50 TTFT | 0.565s | 0.575s |
| p50 decode throughput | 3.6 tok/s | 3.7 tok/s |
| aggregate output throughput | 3.6 tok/s | 3.5 tok/s |

## Speculative decoding A/B

| Metric | Tuned | Tuned + speculation | Change |
|---|---:|---:|---:|
| p50 TTFT | 0.575s | 0.244s | -57.6% |
| p50 decode throughput | 3.7 tok/s | 20.6 tok/s | +459.1% |
| aggregate output throughput | — | — | +467.4% |

**Interpretation:** use the speculative profile only if the measured workload improves. Speculative decoding is workload-dependent; the experiment script does not manufacture a speedup.
