#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
RESULTS="$ROOT/experiments/results"
mkdir -p "$RESULTS"
API_KEY="${VLLM_API_KEY:-local-edge}"
REQS="${BENCH_REQUESTS:-16}"
CONC="${BENCH_CONCURRENCY:-1}"

stop_profile(){ "$ROOT/scripts/models/stop_one.sh" "$1" || true; sleep 2; }

# Base quality + performance.
BENCH_PORT=8200 "$ROOT/scripts/models/start_benchmark_base.sh"
python3 experiments/evaluate_socratic.py --base http://127.0.0.1:8200/v1 --model studybuddy-base --profile base --api-key "$API_KEY" --output "$RESULTS/base_eval.json"
python3 experiments/benchmark_serving.py --base http://127.0.0.1:8200/v1 --model studybuddy-base --profile base --api-key "$API_KEY" --requests "$REQS" --concurrency "$CONC" --output "$RESULTS/base_bench.json"
stop_profile bench-base

# Fine-tuned merged model.
BENCH_PORT=8201 "$ROOT/scripts/models/start_benchmark_tuned.sh"
python3 experiments/evaluate_socratic.py --base http://127.0.0.1:8201/v1 --model studybuddy-socratic --profile tuned --api-key "$API_KEY" --output "$RESULTS/tuned_eval.json"
python3 experiments/benchmark_serving.py --base http://127.0.0.1:8201/v1 --model studybuddy-socratic --profile tuned --api-key "$API_KEY" --requests "$REQS" --concurrency "$CONC" --output "$RESULTS/tuned_bench.json"
stop_profile bench-tuned

# Generic n-gram speculation: no extra draft-model training and works with the merged target.
BENCH_PORT=8202 "$ROOT/scripts/models/start_benchmark_spec_ngram.sh"
python3 experiments/benchmark_serving.py --base http://127.0.0.1:8202/v1 --model studybuddy-socratic-spec-ngram --profile tuned-spec-ngram --api-key "$API_KEY" --requests "$REQS" --concurrency "$CONC" --output "$RESULTS/spec_ngram_bench.json"
stop_profile bench-spec-ngram

# Optional EAGLE-3. Because our target is fine-tuned, acceptance can differ from the base-Qwen verifier it was trained for.
# Treat this as an empirical optimization, not a guaranteed win.
if [[ "${TRY_EAGLE3:-1}" == "1" ]]; then
  if BENCH_PORT=8203 "$ROOT/scripts/models/start_benchmark_spec_eagle3.sh"; then
    if python3 experiments/benchmark_serving.py --base http://127.0.0.1:8203/v1 --model studybuddy-socratic-spec-eagle3 --profile tuned-spec-eagle3 --api-key "$API_KEY" --requests "$REQS" --concurrency "$CONC" --output "$RESULTS/spec_eagle3_bench.json"; then
      echo "EAGLE-3 benchmark captured."
    else
      echo "EAGLE-3 benchmark failed; continuing with n-gram." >&2
    fi
    stop_profile bench-spec-eagle3
  else
    echo "EAGLE-3 server could not start; continuing with n-gram." >&2
  fi
fi

python3 experiments/select_best_spec.py --tuned "$RESULTS/tuned_bench.json" --ngram "$RESULTS/spec_ngram_bench.json" --eagle3 "$RESULTS/spec_eagle3_bench.json" --output "$RESULTS/spec_selection.json"
BEST_METHOD="$(python3 -c 'import json; print(json.load(open("experiments/results/spec_selection.json"))["recommended_method"])')"
BEST_SPEC="$RESULTS/tuned_bench.json"
[[ "$BEST_METHOD" == "ngram" ]] && BEST_SPEC="$RESULTS/spec_ngram_bench.json"
[[ "$BEST_METHOD" == "eagle3" ]] && BEST_SPEC="$RESULTS/spec_eagle3_bench.json"
python3 experiments/compare_results.py --base-eval "$RESULTS/base_eval.json" --tuned-eval "$RESULTS/tuned_eval.json" --base-bench "$RESULTS/base_bench.json" --tuned-bench "$RESULTS/tuned_bench.json" --spec-bench "$BEST_SPEC" --output "$RESULTS/summary.json"
python3 experiments/make_report.py --summary "$RESULTS/summary.json" --output "$RESULTS/HACKATHON_RESULTS.md"
python3 experiments/make_qualitative_examples.py --base "$RESULTS/base_eval.json" --tuned "$RESULTS/tuned_eval.json" --output "$RESULTS/QUALITATIVE_EXAMPLES.md"
STRICT_ARGS=(); [[ "${REQUIRE_QUALITY_WIN:-0}" == "1" ]] && STRICT_ARGS+=(--strict)
python3 experiments/quality_gate.py --summary "$RESULTS/summary.json" "${STRICT_ARGS[@]}" --output "$RESULTS/quality_gate.json"

echo
echo "Results: $RESULTS/HACKATHON_RESULTS.md"
echo "Recommended serving profile: SPECULATION_METHOD=$BEST_METHOD"
