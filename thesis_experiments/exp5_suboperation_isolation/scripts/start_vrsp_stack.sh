#!/usr/bin/env bash
# Start virtual-rsp-2 v-euicc + osmo-smdpp + nginx (same layout as test-all.sh).
set -euo pipefail
VRSP="${VIRTUAL_RSP2:-/home/jhubuntu/projects/virtual-rsp-2}"
cd "$VRSP"
source pysim/venv/bin/activate
cd pysim
python3 osmo-smdpp.py -H 127.0.0.1 -p 8000 --nossl -c generated -m &
echo $! > /tmp/vrsp_smdpp.pid
cd "$VRSP"
export VRSP_BF21_MODE="${VRSP_BF21_MODE:-mlkem}"
echo "VRSP_BF21_MODE=$VRSP_BF21_MODE (ecdh=config a baseline, mlkem=config c)"
./build/v-euicc/v-euicc-daemon 8765 &
echo $! > /tmp/vrsp_veuicc.pid
sleep 1
nginx -c "$VRSP/pysim/nginx-smdpp.conf" -p "$VRSP/pysim" &
echo $! > /tmp/vrsp_nginx.pid
sleep 2
echo "Started SM-DP+ PID $(cat /tmp/vrsp_smdpp.pid) v-euicc $(cat /tmp/vrsp_veuicc.pid) nginx $(cat /tmp/vrsp_nginx.pid)"
