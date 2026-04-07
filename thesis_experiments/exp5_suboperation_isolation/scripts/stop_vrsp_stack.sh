#!/usr/bin/env bash
set +e
pkill -f "v-euicc-daemon" || true
pkill -f "osmo-smdpp.py" || true
pkill -f "nginx.*nginx-smdpp" || true
sleep 1
echo "Stopped v-euicc / osmo-smdpp / nginx"
