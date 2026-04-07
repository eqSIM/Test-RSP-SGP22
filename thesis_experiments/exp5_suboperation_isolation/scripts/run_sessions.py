#!/usr/bin/env python3
"""Run N profile downloads; record BF21 BENCH microseconds and wall time per session."""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BENCH_RE = re.compile(r"^BENCH\|BF21\|PrepareDownload\|(-?\d+)\|(-?\d+)\s*$")

ROOT = Path(__file__).resolve().parents[1]
VRSP = Path(os.environ.get("VIRTUAL_RSP2", "/home/jhubuntu/projects/virtual-rsp-2")).resolve()
BUILD = VRSP / "build"
LPAC = BUILD / "lpac" / "src" / "lpac"
PROFILE_ID = "TS48V2-SAIP2-1-BERTLV-UNIQUE"
SMDPP_HOST = "testsmdpplus1.example.com:8443"


def parse_bench_bf21(stderr_text: str) -> int | None:
    for line in stderr_text.splitlines():
        m = BENCH_RE.match(line.strip())
        if m:
            return int(m.group(1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=("a", "c"), required=True)
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument(
        "--openssl-ld",
        default="/home/linuxbrew/.linuxbrew/opt/openssl/lib",
        help="prepend to LD_LIBRARY_PATH for lpac TLS",
    )
    args = ap.parse_args()

    if not LPAC.is_file():
        print(f"lpac not found: {LPAC}", file=sys.stderr)
        return 1

    raw_dir = ROOT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prep_path = raw_dir / f"config_{args.config}_preparedownload.csv"
    full_path = raw_dir / f"config_{args.config}_fullsession.csv"

    env = os.environ.copy()
    env["LPAC_APDU"] = "socket"
    env["LPAC_BENCH"] = "1"
    if args.openssl_ld:
        env["LD_LIBRARY_PATH"] = args.openssl_ld + os.pathsep + env.get("LD_LIBRARY_PATH", "")

    with prep_path.open("w", newline="") as fprep, full_path.open("w", newline="") as ffull:
        wp = csv.writer(fprep)
        wf = csv.writer(ffull)
        wp.writerow(["iteration", "prepare_download_us"])
        wf.writerow(["iteration", "wall_time_ms"])

        for i in range(1, args.iterations + 1):
            t0 = time.perf_counter()
            r = subprocess.run(
                [str(LPAC), "profile", "download", "-s", SMDPP_HOST, "-m", PROFILE_ID],
                cwd=str(BUILD),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            dt_ms = (time.perf_counter() - t0) * 1000.0
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            bf21 = parse_bench_bf21(out)
            if bf21 is None:
                print(f"[iter {i}] WARNING: no BF21 BENCH line; exit={r.returncode}", file=sys.stderr)
                print(out[-2000:], file=sys.stderr)
            else:
                wp.writerow([i, bf21])
            wf.writerow([i, f"{dt_ms:.3f}"])
            print(f"[iter {i}/{args.iterations}] BF21_us={bf21} wall_ms={dt_ms:.1f} rc={r.returncode}", flush=True)

            if i % 50 == 0 and i < args.iterations:
                print(f"cooldown 15s after {i} iterations...", flush=True)
                time.sleep(15)

    print(f"Wrote {prep_path} and {full_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
