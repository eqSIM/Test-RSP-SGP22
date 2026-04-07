#!/usr/bin/env bash
# Stop stray benchmark stacks, trim oversized logs under the repo.
# Hard wall-clock limit: 2 hours (SIGTERM, then SIGKILL after grace period).
#
# Usage:
#   ./scripts/cleanup_benchmark_environment.sh
#   CLEANUP_TRUNCATE_MB=200 CLEANUP_JOURNAL_VACUUM=1 ./scripts/cleanup_benchmark_environment.sh
#
# CLEANUP_JOURNAL_VACUUM=1 runs: sudo journalctl --vacuum-size=500M (optional, needs sudo)
# CLEANUP_TRUNCATE_MB: truncate *.log / run_log*.txt larger than this (default 250). Set 0 to skip.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRUNC_MB="${CLEANUP_TRUNCATE_MB:-250}"
JOURNAL_VACUUM="${CLEANUP_JOURNAL_VACUUM:-0}"
GRACE_SEC="${CLEANUP_KILL_AFTER_SEC:-120}"
TIME_LIMIT_SEC=7200

# Re-exec under timeout so the whole run (including children) cannot exceed 2 hours.
if [[ -z "${CLEANUP_TIME_LIMIT_ACTIVE:-}" ]]; then
  export CLEANUP_TIME_LIMIT_ACTIVE=1
  if ! command -v timeout >/dev/null 2>&1; then
    echo "ERROR: GNU timeout not found; install coreutils." >&2
    exit 1
  fi
  exec timeout --foreground --signal=TERM --kill-after="${GRACE_SEC}" "${TIME_LIMIT_SEC}" \
    "$0" "$@"
fi

log() { echo "[cleanup $(date -Is)] $*"; }

stop_processes() {
  log "Stopping v-euicc / virtual-rsp osmo-smdpp / nginx-smdpp…"
  pkill -f "v-euicc-daemon" 2>/dev/null || true
  pkill -f "${ROOT}/pysim/osmo-smdpp.py" 2>/dev/null || true
  pkill -f "nginx.*nginx-smdpp\.conf" 2>/dev/null || true
  pkill -f "pysim/nginx-smdpp\.conf" 2>/dev/null || true

  log "Stopping pq-rsp TLS proxy nginx (if running from this repo)…"
  if [[ -x "${ROOT}/nginx/pq_build/sbin/nginx" ]]; then
    "${ROOT}/nginx/pq_build/sbin/nginx" -p "${ROOT}/nginx/runtime" -c "${ROOT}/nginx/nginx.conf" -s quit 2>/dev/null || true
  fi
  pkill -f "${ROOT}/nginx/pq_build/sbin/nginx" 2>/dev/null || true

  sleep 2
}

truncate_large_logs() {
  if [[ "${TRUNC_MB}" == "0" ]]; then
    log "Skipping log truncation (CLEANUP_TRUNCATE_MB=0)."
    return 0
  fi
  local min_bytes=$((TRUNC_MB * 1024 * 1024))
  log "Truncating files larger than ${TRUNC_MB} MB under ${ROOT} (logs only, not CSV/jsonl data)…"
  # shellcheck disable=SC2312
  find "${ROOT}" -type f \( \
      -path '*/nginx/runtime/logs/*' -o \
      -name 'smdpp.log' -o \
      -name 'run_log*.txt' -o \
      \( -name 'access.log' -o -name 'error.log' \) \
    \) ! -name '*.csv' ! -name '*.jsonl' 2>/dev/null | while read -r f; do
    [[ -f "$f" ]] || continue
    local sz
    sz=$(stat -c%s "$f" 2>/dev/null) || continue
    if [[ "${sz}" -gt "${min_bytes}" ]]; then
      log "Truncate: $f ($(numfmt --to=iec "${sz}" 2>/dev/null || echo "${sz} bytes"))"
      : >"$f"
    fi
  done
}

vacuum_journal_optional() {
  if [[ "${JOURNAL_VACUUM}" != "1" ]]; then
    return 0
  fi
  if ! command -v journalctl >/dev/null 2>&1; then
    log "journalctl not available; skip."
    return 0
  fi
  log "Vacuum systemd journal to ~500M (requires sudo)…"
  sudo journalctl --vacuum-size=500M || log "journalctl vacuum failed (ignore if not using journald)."
}

main() {
  log "Start (time limit ${TIME_LIMIT_SEC}s already enforced by timeout wrapper)."
  stop_processes
  truncate_large_logs
  vacuum_journal_optional
  log "Done. Check: ss -tlnp ':8000|:8443|:8444' — ports should be free unless system nginx binds them."
}

main "$@"
