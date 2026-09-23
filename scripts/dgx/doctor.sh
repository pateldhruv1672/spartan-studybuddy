#!/usr/bin/env bash
set -u
fail=0
ok(){ printf '  [OK] %s\n' "$1"; }
warn(){ printf '  [WARN] %s\n' "$1"; }
bad(){ printf '  [FAIL] %s\n' "$1"; fail=1; }
echo "Spartan StudyBuddy • DGX Spark doctor"
echo
arch="$(uname -m)"; [[ "$arch" == "aarch64" || "$arch" == "arm64" ]] && ok "ARM64 host ($arch)" || warn "Host is $arch; expected ARM64 on DGX Spark"
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1 && ok "NVIDIA GPU visible" || bad "nvidia-smi/GPU unavailable"
command -v docker >/dev/null 2>&1 && ok "Docker installed" || bad "Docker missing"
docker ps >/dev/null 2>&1 && ok "Docker usable without sudo" || bad "Docker permission/runtime problem"
command -v curl >/dev/null 2>&1 && ok "curl installed" || bad "curl missing"
command -v python3 >/dev/null 2>&1 && ok "Python $(python3 --version 2>&1)" || bad "python3 missing"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'spartan-studybuddy-postgres'; then
  if docker exec spartan-studybuddy-postgres pg_isready -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" >/dev/null 2>&1; then
    ok "PostgreSQL container healthy"
    vec="$(docker exec spartan-studybuddy-postgres psql -U "${POSTGRES_USER:-studybuddy}" -d "${POSTGRES_DB:-studybuddy}" -Atc "SELECT extversion FROM pg_extension WHERE extname='vector'" 2>/dev/null || true)"
    [[ -n "$vec" ]] && ok "pgvector extension $vec" || warn "PostgreSQL is up but pgvector has not been initialized yet"
  else
    bad "PostgreSQL container is not healthy"
  fi
else
  warn "PostgreSQL container is not running (make db-start)"
fi
mem_kb="$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0)"; mem_gb=$((mem_kb/1024/1024)); [[ $mem_gb -ge 100 ]] && ok "System memory ~${mem_gb} GiB" || warn "System memory ~${mem_gb} GiB; DGX Spark normally has 128 GB unified memory"
disk_gb="$(df -Pk . | awk 'NR==2{print int($4/1024/1024)}')"; [[ $disk_gb -ge 80 ]] && ok "Free disk ${disk_gb} GiB" || warn "Only ${disk_gb} GiB free; models + merged weights can consume tens of GB"
[[ -f .env ]] && ok ".env present" || warn ".env missing (run cp .env.example .env)"
[[ -f artifacts/socratic-merged/config.json ]] && ok "Fine-tuned merged model present" || warn "No fine-tuned merged model yet (run make train)"
[[ -f experiments/results/summary.json ]] && ok "Measured competition results present" || warn "No benchmark results yet (run make benchmark)"
echo
if [[ $fail -eq 0 ]]; then echo "Doctor passed critical checks."; else echo "Doctor found critical setup failures."; fi
exit $fail
