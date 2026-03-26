#!/usr/bin/env python3
"""PC/SC overhead model, host baseline, Platform A fingerprint, optional LPA overhead stub."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from smartcard.System import readers

from config import (
    DATA_ROOT,
    LPAC_BIN,
    LPAC_BUILD,
    PCSC_ITERS_PER_SIZE,
    PCSC_PAYLOAD_SIZES,
    PYSIM_ROOT,
    ROOT,
)
from utils import ensure_dir, fit_linear_pcsc, mean_ci95, write_json


def _lpac_ld_path() -> str:
    return LPAC_BUILD


def _transmit_time_us(connection, apdu: list[int]) -> float:
    t0 = time.perf_counter_ns()
    connection.transmit(apdu)
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1000.0


def pcsc_payload_sweep() -> tuple[list[dict], dict]:
    """Vary Lc on a benign ES10-style APDU; measures transport + card rejection path."""
    rs = readers()
    if not rs:
        raise RuntimeError("No PC/SC readers found")
    conn = rs[0].createConnection()
    conn.connect()

    # Select ISD-R (same AID as lpac default)
    aid = [
        0xA0,
        0x00,
        0x00,
        0x05,
        0x59,
        0x10,
        0x10,
        0xFF,
        0xFF,
        0xFF,
        0xFF,
        0x89,
        0x00,
        0x00,
        0x01,
        0x00,
    ]
    sel = [0x00, 0xA4, 0x04, 0x00, len(aid)] + aid
    conn.transmit(sel)

    rows = []
    raw_times: list[float] = []
    raw_payloads: list[int] = []

    for nbytes in PCSC_PAYLOAD_SIZES:
        for _ in range(PCSC_ITERS_PER_SIZE):
            lc = min(max(nbytes, 0), 255)
            body = [0x00] * lc
            # ES10 STORE DATA first segment style (may return error quickly; measures bytes on wire)
            apdu = [0x80, 0xE2, 0x11, 0x00, lc] + body
            us = _transmit_time_us(conn, apdu)
            rows.append({"payload_bytes": nbytes, "lc": lc, "time_us": us})
            raw_times.append(us)
            raw_payloads.append(nbytes)

    conn.disconnect()

    model = fit_linear_pcsc(raw_times, raw_payloads)
    return rows, model


def host_baseline() -> dict:
    import platform
    import ssl

    uname = " ".join(platform.uname())
    openssl = subprocess.run(["openssl", "version"], capture_output=True, text=True, timeout=5)
    smdpp_hash = ""
    try:
        smdpp_hash = subprocess.run(
            ["git", "-C", str(PYSIM_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except OSError:
        pass
    with open("/proc/cpuinfo") as f:
        cpuinfo = f.read()[:4000]
    return {
        "os_uname": uname,
        "openssl_version": openssl.stdout.strip(),
        "cpuinfo_excerpt": cpuinfo,
        "pysim_git": smdpp_hash,
        "ssl_module": ssl.OPENSSL_VERSION,
    }


def platform_a_fingerprint() -> dict:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = _lpac_ld_path() + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    r = subprocess.run(
        [LPAC_BIN, "chip", "info"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(LPAC_BIN),
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    outer = json.loads(r.stdout)
    data = outer.get("payload", {}).get("data", {})
    try:
        rlist = subprocess.run(["pcsc_scan", "-r"], capture_output=True, text=True, timeout=5)
        readers_txt = (rlist.stdout + rlist.stderr).strip()
    except OSError:
        readers_txt = ""
    return {
        "lpac_chip_info": data,
        "pcsc_scan_readers": readers_txt,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-pcsc", action="store_true", help="Skip PC/SC sweep (no reader)")
    args = ap.parse_args()

    base = Path(DATA_ROOT) / "calibration"
    ensure_dir(base)

    if not args.skip_pcsc:
        try:
            rows, model = pcsc_payload_sweep()
        except Exception as ex:
            print(f"PC/SC sweep failed ({ex}); writing placeholder model. Use --skip-pcsc to silence.", file=sys.stderr)
            model = {"a_us": 0.0, "b_us_per_byte": 0.0, "r_squared": 0.0, "error": str(ex)}
            rows = []
        import csv

        p = base / "pcsc_overhead" / "raw_per_size.csv"
        ensure_dir(p.parent)
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["payload_bytes", "lc", "time_us"])
            w.writeheader()
            for row in rows:
                w.writerow(row)
        write_json(base / "pcsc_overhead" / "model.json", model)
    else:
        model = {"a_us": 0.0, "b_us_per_byte": 0.0, "r_squared": 0.0, "note": "skipped"}
        write_json(base / "pcsc_overhead" / "model.json", model)

    write_json(base / "host_baseline.json", host_baseline())
    write_json(base / "platform_a_fingerprint.json", platform_a_fingerprint())

    lpa_stub = {
        "note": "LPA software overhead vs stdio mock: set up lpac stdio APDU backend and diff timings if needed.",
        "per_command_ms": {},
    }
    write_json(base / "lpa_overhead" / "per_command.json", lpa_stub)

    print(json.dumps({"ok": True, "calibration_dir": str(base), "pcsc_model": model}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
