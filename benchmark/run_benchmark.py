#!/usr/bin/env python3
"""Warm-up + measurement: classical TLS then PQ-TLS (same N each); LPAC_BENCH timing on stderr."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from config import (
    COOLDOWN_EVERY,
    COOLDOWN_SEC,
    DATA_ROOT,
    LPAC_BIN,
    LPAC_BUILD,
    MATCHING_ID,
    MEASURE_ITERS,
    OQS_LPAC_LD_LIBRARY_PATH,
    PQ_TLS_PHASE,
    PQ_WARMUP,
    SMDP_ADDR_CLASSICAL,
    SMDP_ADDR_PQ,
    WARMUP_ITERS,
)
from utils import ensure_dir, parse_bench_stderr, read_cpu_temp_c, write_json


def log(msg: str) -> None:
    print(msg, flush=True)


def _env_lpac() -> dict[str, str]:
    e = os.environ.copy()
    e["LD_LIBRARY_PATH"] = LPAC_BUILD + os.pathsep + e.get("LD_LIBRARY_PATH", "")
    e["LPAC_BENCH"] = "1"
    return e


def run_download(
    capture_apdu: bool,
    smdp_addr: str,
    extra_ld: str | None = None,
    verbose: bool = False,
) -> tuple[int, str, str]:
    env = _env_lpac()
    if extra_ld:
        env["LD_LIBRARY_PATH"] = extra_ld + os.pathsep + env["LD_LIBRARY_PATH"]
    if capture_apdu:
        env["LPAC_APDU_DEBUG"] = "1"
    cmd = [LPAC_BIN, "profile", "download", "-s", smdp_addr, "-m", MATCHING_ID]
    cwd = os.path.dirname(LPAC_BIN)

    if not verbose:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=300,
        )
        return r.returncode, r.stdout, r.stderr

    out_chunks: list[str] = []
    err_chunks: list[str] = []

    def pump(stream, chunks: list[str], sink) -> None:
        for line in iter(stream.readline, ""):
            chunks.append(line)
            sink.write(line)
            sink.flush()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=cwd,
        bufsize=1,
    )
    assert proc.stdout is not None and proc.stderr is not None
    t_out = threading.Thread(target=pump, args=(proc.stdout, out_chunks, sys.stdout))
    t_err = threading.Thread(target=pump, args=(proc.stderr, err_chunks, sys.stderr))
    t_out.start()
    t_err.start()
    try:
        rc = proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        raise
    t_out.join()
    t_err.join()
    return rc, "".join(out_chunks), "".join(err_chunks)


def iccid_for_matching_profile(stdout: str) -> str | None:
    try:
        data = json.loads(stdout)
        pl = data.get("payload", {}).get("data", [])
        if not isinstance(pl, list):
            return None
        for p in pl:
            if p.get("profileName") == MATCHING_ID:
                return p.get("iccid")
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def run_profile_list() -> str | None:
    env = _env_lpac()
    del env["LPAC_BENCH"]
    r = subprocess.run(
        [LPAC_BIN, "profile", "list"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(LPAC_BIN),
        timeout=120,
    )
    if r.returncode != 0:
        return None
    return iccid_for_matching_profile(r.stdout)


def delete_matching_profile_if_present() -> None:
    iccid = run_profile_list()
    if iccid:
        rc = run_profile_delete(iccid)
        if rc != 0:
            print(
                f"Warning: could not delete existing profile {MATCHING_ID} ({iccid}) rc={rc}",
                file=sys.stderr,
            )
        time.sleep(0.5)


def run_profile_delete(iccid: str) -> int:
    env = _env_lpac()
    del env["LPAC_BENCH"]
    r = subprocess.run(
        [LPAC_BIN, "profile", "delete", iccid],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(LPAC_BIN),
        timeout=120,
    )
    return r.returncode


def run_warmup_rounds(
    label: str,
    n: int,
    smdp_addr: str,
    skip_delete: bool,
    extra_ld: str | None = None,
    verbose: bool = False,
) -> int:
    for i in range(n):
        log(f"[warmup {label}] {i + 1}/{n}  smdp={smdp_addr}  starting…")
        t0 = time.time()
        code, _, err = run_download(
            capture_apdu=False,
            smdp_addr=smdp_addr,
            extra_ld=extra_ld,
            verbose=verbose,
        )
        elapsed = time.time() - t0
        if code != 0:
            log(f"[warmup {label}] FAILED  {i + 1}/{n}  rc={code}  wall_s={elapsed:.2f}")
            print(f"stderr (tail): {err[-800:]}", file=sys.stderr)
            return 1
        log(f"[warmup {label}] done {i + 1}/{n}  rc=0  wall_s={elapsed:.2f}")
        iccid = run_profile_list()
        if iccid and not skip_delete:
            run_profile_delete(iccid)
        time.sleep(0.5)
    return 0


def measure_phase(
    tls_mode: str,
    smdp_addr: str,
    iters: int,
    global_iter_start: int,
    capture_apdu_global_iter: int,
    out_dir: Path,
    rows: list[dict],
    skip_delete: bool,
    extra_ld: str | None = None,
    verbose: bool = False,
) -> tuple[int, int]:
    """Returns (exit_code, next_global_iter)."""
    g = global_iter_start
    for i in range(iters):
        log(
            f"[measure {tls_mode}] phase {i + 1}/{iters}  global_iter={g}  "
            f"smdp={smdp_addr}  starting…"
        )
        temp = read_cpu_temp_c()
        t0 = time.time()
        code, _, err = run_download(
            capture_apdu=(g == capture_apdu_global_iter),
            smdp_addr=smdp_addr,
            extra_ld=extra_ld,
            verbose=verbose,
        )
        elapsed = time.time() - t0
        if code != 0:
            bench = parse_bench_stderr(err)
            row = {
                "iter": g,
                "phase_iter": i + 1,
                "tls_mode": tls_mode,
                "smdp_addr": smdp_addr,
                "returncode": code,
                "session_wall_s": elapsed,
                "cpu_temp_c": temp,
                "bench": bench,
            }
            rows.append(row)
            write_json(out_dir / f"iter_{g:04d}.json", row)
            log(
                f"[measure {tls_mode}] FAILED  global_iter={g}  rc={code}  "
                f"wall_s={elapsed:.2f}  temp_C={temp}"
            )
            print(f"stderr (tail): {err[-800:]}", file=sys.stderr)
            return 1, g
        bench = parse_bench_stderr(err)
        row = {
            "iter": g,
            "phase_iter": i + 1,
            "tls_mode": tls_mode,
            "smdp_addr": smdp_addr,
            "returncode": code,
            "session_wall_s": elapsed,
            "cpu_temp_c": temp,
            "bench": bench,
        }
        rows.append(row)
        write_json(out_dir / f"iter_{g:04d}.json", row)

        if g == capture_apdu_global_iter and err:
            (out_dir / "sample_apdu_debug.txt").write_text(err[:500000])

        iccid = run_profile_list()
        if iccid and not skip_delete:
            run_profile_delete(iccid)
        log(
            f"[measure {tls_mode}] done  global_iter={g}  rc=0  wall_s={elapsed:.2f}  "
            f"temp_C={temp}  bench_tags={len(bench)}"
        )
        time.sleep(0.5)

        if (i + 1) % COOLDOWN_EVERY == 0 and (i + 1) < iters:
            log(f"[cooldown] sleeping {COOLDOWN_SEC}s after {tls_mode} phase_iter {i + 1}")
            time.sleep(COOLDOWN_SEC)
        g += 1
    return 0, g


def _load_existing_rows(out_dir: Path) -> list[dict]:
    import re as _re

    files = sorted(out_dir.glob("iter_*.json"), key=lambda p: int(_re.search(r"(\d+)", p.name).group(1)))
    return [json.loads(fp.read_text()) for fp in files]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warmup", type=int, default=WARMUP_ITERS, help="Warm-up iterations (classical only)")
    ap.add_argument("--iters", type=int, default=MEASURE_ITERS, help="Measured iterations per TLS mode (total 2x if PQ phase on)")
    ap.add_argument("--pq-warmup", type=int, default=PQ_WARMUP, help="Warm-up iterations before PQ phase")
    ap.add_argument("--no-pq-phase", action="store_true", help="Classical TLS only (single phase, --iters total)")
    ap.add_argument(
        "--pq-only",
        action="store_true",
        help="Skip classical phase; append PQ-TLS iterations to existing session data, continuing global iter numbering",
    )
    ap.add_argument("--skip-delete", action="store_true", help="Do not delete profile after each run (not recommended)")
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Stream lpac stdout/stderr to the terminal during each download (live; noisy)",
    )
    args = ap.parse_args()

    pq_phase = PQ_TLS_PHASE and not args.no_pq_phase

    out_dir = Path(DATA_ROOT) / "platform_a" / "sessions"
    ensure_dir(out_dir)

    pq_ld = OQS_LPAC_LD_LIBRARY_PATH or None

    if args.pq_only:
        existing = _load_existing_rows(out_dir)
        g = (max((r["iter"] for r in existing), default=0) + 1) if existing else 1
        log("=== run_benchmark (--pq-only) ===")
        log(f"DATA_ROOT={DATA_ROOT}  existing_iters={len(existing)}  starting_global_iter={g}")
        log(f"pq_tls smdp={SMDP_ADDR_PQ}  pq_warmup={args.pq_warmup}  measure_iters={args.iters}")
        if not args.skip_delete:
            log("[init] deleting existing matching profile if present…")
            delete_matching_profile_if_present()
        if (
            run_warmup_rounds(
                "pq_tls",
                args.pq_warmup,
                SMDP_ADDR_PQ,
                args.skip_delete,
                extra_ld=pq_ld,
                verbose=args.verbose,
            )
            != 0
        ):
            return 1
        new_rows: list[dict] = []
        code, _ = measure_phase(
            "pq_tls",
            SMDP_ADDR_PQ,
            args.iters,
            g,
            capture_apdu_global_iter=-1,
            out_dir=out_dir,
            rows=new_rows,
            skip_delete=args.skip_delete,
            extra_ld=pq_ld,
            verbose=args.verbose,
        )
        if code != 0:
            return code
        all_rows = existing + new_rows
        write_json(out_dir / "all_iterations.json", all_rows)
        log("=== finished ===")
        print(json.dumps({"ok": True, "sessions": str(out_dir), "classical_iters": len(existing), "pq_iters": len(new_rows), "total": len(all_rows)}, indent=2), flush=True)
        return 0

    total_measured = args.iters * (2 if pq_phase else 1)
    log("=== run_benchmark ===")
    log(f"DATA_ROOT={DATA_ROOT}")
    log(f"lpac={LPAC_BIN}")
    log(f"match={MATCHING_ID}")
    log(f"measure per phase: {args.iters}  total measured iterations: {total_measured}  pq_phase={pq_phase}")
    log(f"classical smdp={SMDP_ADDR_CLASSICAL}")
    if pq_phase:
        log(f"pq_tls smdp={SMDP_ADDR_PQ}  pq_warmup={args.pq_warmup}")
    log(f"warmup (classical only)={args.warmup}  verbose_lpac={args.verbose}")

    if not args.skip_delete:
        log("[init] deleting existing matching profile if present…")
        delete_matching_profile_if_present()

    if (
        run_warmup_rounds(
            "classical",
            args.warmup,
            SMDP_ADDR_CLASSICAL,
            args.skip_delete,
            extra_ld=None,
            verbose=args.verbose,
        )
        != 0
    ):
        return 1

    rows: list[dict] = []
    g = 1

    code, g = measure_phase(
        "classical",
        SMDP_ADDR_CLASSICAL,
        args.iters,
        g,
        capture_apdu_global_iter=1,
        out_dir=out_dir,
        rows=rows,
        skip_delete=args.skip_delete,
        extra_ld=None,
        verbose=args.verbose,
    )
    if code != 0:
        return code

    if pq_phase:
        if not args.skip_delete:
            log("[between phases] deleting matching profile before PQ…")
            delete_matching_profile_if_present()
        if (
            run_warmup_rounds(
                "pq_tls",
                args.pq_warmup,
                SMDP_ADDR_PQ,
                args.skip_delete,
                extra_ld=pq_ld,
                verbose=args.verbose,
            )
            != 0
        ):
            return 1
        code, g = measure_phase(
            "pq_tls",
            SMDP_ADDR_PQ,
            args.iters,
            g,
            capture_apdu_global_iter=-1,
            out_dir=out_dir,
            rows=rows,
            skip_delete=args.skip_delete,
            extra_ld=pq_ld,
            verbose=args.verbose,
        )
        if code != 0:
            return code

    write_json(out_dir / "all_iterations.json", rows)
    total = len(rows)
    log("=== finished ===")
    summary = {
        "ok": True,
        "sessions": str(out_dir),
        "iters_per_phase": args.iters,
        "pq_phase": pq_phase,
        "total_measured_iterations": total,
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
