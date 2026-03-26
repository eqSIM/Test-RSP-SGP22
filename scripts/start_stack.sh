#!/usr/bin/env bash
# Start osmo-smdpp (plain HTTP) and nginx (TLS classical :8443 + PQ :8444).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYSIM="$ROOT/pysim"
NGX="$ROOT/nginx"
RUN="$NGX/runtime"
export PYTHONPATH="$PYSIM"
export SMDPP_BENCH_LOG="${SMDPP_BENCH_LOG:-$RUN/smdpp_bench.jsonl}"
mkdir -p "$RUN/logs"

# Prefer nginx built against OpenSSL 3.6+ (PQ) if present
NGINX_BIN="${NGINX_BIN:-}"
if [[ -z "$NGINX_BIN" ]] && [[ -x "$NGX/pq_build/sbin/nginx" ]]; then
  NGINX_BIN="$NGX/pq_build/sbin/nginx"
fi
if [[ -z "$NGINX_BIN" ]]; then
  NGINX_BIN="$(command -v nginx)"
fi

if ! ss -tlnp 2>/dev/null | grep -q ':8000'; then
  echo "Starting osmo-smdpp on :8000 (--nossl)..."
  (
    cd "$PYSIM" && . .venv/bin/activate && exec python3 "$PYSIM/osmo-smdpp.py" -p 8000 --nossl -m -v
  ) >>"$RUN/smdpp.log" 2>&1 &
  sleep 2
fi

if ! ss -tlnp 2>/dev/null | grep -q ':8443'; then
  echo "Starting nginx ($NGINX_BIN) — classical :8443, PQ :8444..."
  "$NGINX_BIN" -p "$RUN" -c "$NGX/nginx.conf"
  sleep 1
fi

echo "Classical SM-DP+ https://testsmdpplus1.example.com:8443"
echo "PQ-TLS SM-DP+     https://testsmdpplus1.example.com:8444 (ensure scripts/gen_pq_certs.sh + build_pq_nginx.sh)"
echo "Ensure /etc/hosts -> 127.0.0.1 testsmdpplus1.example.com"
echo "Bench log: $SMDPP_BENCH_LOG"
