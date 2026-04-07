#!/usr/bin/env bash
# Full Experiment 5 rerun: config (a) ECDH then (c) ML-KEM, then analyse.py.
set -euo pipefail
EXP="$(cd "$(dirname "$0")/.." && pwd)"
cd "$EXP/scripts"
ARCH="$EXP/raw/archive_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ARCH"
shopt -s nullglob
for f in "$EXP"/raw/*.csv; do cp -a "$f" "$ARCH/"; done || true
echo "Archived prior CSVs to $ARCH"

bash stop_vrsp_stack.sh || true
sleep 2
export VRSP_BF21_MODE=ecdh
bash start_vrsp_stack.sh
sleep 2
python3 run_sessions.py --config a --iterations 200

bash stop_vrsp_stack.sh || true
sleep 2
export VRSP_BF21_MODE=mlkem
bash start_vrsp_stack.sh
sleep 2
python3 run_sessions.py --config c --iterations 200

bash stop_vrsp_stack.sh || true
python3 analyse.py
echo "Experiment 5 full rerun finished at $(date -Is)" | tee "$EXP/processed/RERUN_LAST_COMPLETED.txt"
