#!/usr/bin/env python3
"""Experiment 2: run N full profile downloads on real PC/SC; log BENCH lines; disable+delete on success."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Repo root = parents[2] from thesis_experiments/exp2_classical_apdu_baseline/scripts/
REPO_ROOT = Path(__file__).resolve().parents[3]
EXP2_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_LPAC = REPO_ROOT / "lpac" / "build" / "src" / "lpac"
DEFAULT_OPENSSL_LD = "/home/linuxbrew/.linuxbrew/opt/openssl/lib"
DEFAULT_SMDP = "testsmdpplus1.example.com:8443"
DEFAULT_MATCHING_ID = os.environ.get("MATCHING_ID", "TS48v1_A")
COOLDOWN_EVERY = int(os.environ.get("COOLDOWN_EVERY", "50"))
COOLDOWN_SEC = float(os.environ.get("COOLDOWN_SEC", "15"))


def lpac_env(openssl_lib: str | None, lpac_bin: Path) -> dict[str, str]:
    e = os.environ.copy()
    e["LPAC_BENCH"] = "1"
    e.pop("LPAC_APDU", None)
    lpac_build_lib = str(lpac_bin.resolve().parent.parent)
    parts = [lpac_build_lib]
    if openssl_lib:
        parts.insert(0, openssl_lib)
    e["LD_LIBRARY_PATH"] = os.pathsep.join(parts + [e.get("LD_LIBRARY_PATH", "")]).strip(os.pathsep)
    return e


def extract_iccid_from_failed_download_stdout(stdout_text: str) -> str | None:
    """ICCID from es8p_metadata_parse JSON line (profile already on card errors)."""
    for line in stdout_text.splitlines():
        if "es8p_metadata_parse" in line and "iccid" in line:
            m = re.search(r'"iccid"\s*:\s*"([0-9]+)"', line)
            if m:
                return m.group(1).strip()
    m = re.search(r'"iccid"\s*:\s*"([0-9]+)"', stdout_text)
    return m.group(1).strip() if m else None


def parse_success_iccid(stdout_text: str) -> str | None:
    """Last JSON line with payload.message == success and iccid in payload.data."""
    for line in reversed(stdout_text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") != "lpa":
            continue
        pl = j.get("payload") or {}
        if pl.get("message") != "success":
            continue
        data = pl.get("data")
        if isinstance(data, dict) and data.get("iccid"):
            return str(data["iccid"]).strip()
    return None


def run_lpac(
    lpac_bin: Path,
    env: dict[str, str],
    args: list[str],
    timeout: int,
    log_fp,
) -> tuple[int, str, str]:
    log_fp.write(f"$ {' '.join([str(lpac_bin)] + args)}\n")
    log_fp.flush()
    r = subprocess.run(
        [str(lpac_bin), *args],
        cwd=str(lpac_bin.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = r.stdout or ""
    err = r.stderr or ""
    log_fp.write("--- stdout ---\n")
    log_fp.write(out)
    if not out.endswith("\n"):
        log_fp.write("\n")
    log_fp.write("--- stderr ---\n")
    log_fp.write(err)
    if err and not err.endswith("\n"):
        log_fp.write("\n")
    log_fp.write(f"--- exit {r.returncode} ---\n")
    log_fp.flush()
    return r.returncode, out, err


def cleanup_installed_profile(
    lpac_bin: Path,
    env: dict[str, str],
    iccid: str,
    timeout: int,
    log_fp,
    iter_label: str,
) -> int:
    """Disable (best effort) then delete. New installs are often *disabled* already;
    lpac then returns 'profile not in enabled state' — still run delete."""
    rc_d, o_d, e_d = run_lpac(
        lpac_bin, env, ["profile", "disable", iccid], timeout, log_fp
    )
    comb_d = (o_d or "") + (e_d or "")
    if rc_d != 0 and "profile not in enabled state" not in comb_d:
        print(f"[iter {iter_label}] disable failed rc={rc_d}", file=sys.stderr)
    rc_x, _, _ = run_lpac(
        lpac_bin, env, ["profile", "delete", iccid], timeout, log_fp
    )
    if rc_x != 0:
        print(f"[iter {iter_label}] delete failed rc={rc_x}", file=sys.stderr)
    return rc_x


def main() -> int:
    ap = argparse.ArgumentParser(description="Exp2: PC/SC profile download sessions with BENCH logging.")
    ap.add_argument("--iterations", type=int, default=int(os.environ.get("MEASURE_ITERS", "200")))
    ap.add_argument("--lpac-bin", type=Path, default=Path(os.environ.get("LPAC_BIN", str(DEFAULT_LPAC))))
    ap.add_argument("--smdp", default=os.environ.get("SMDP_ADDR", DEFAULT_SMDP))
    ap.add_argument("--matching-id", "-m", default=DEFAULT_MATCHING_ID)
    ap.add_argument("--openssl-ld", default=os.environ.get("OPENSSL_LD", DEFAULT_OPENSSL_LD))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--cooldown-every", type=int, default=COOLDOWN_EVERY)
    ap.add_argument("--cooldown-sec", type=float, default=COOLDOWN_SEC)
    ap.add_argument("--skip-cleanup", action="store_true", help="Do not disable/delete after download")
    args = ap.parse_args()

    if not args.lpac_bin.is_file():
        print(f"lpac not found: {args.lpac_bin}", file=sys.stderr)
        return 1

    raw_dir = EXP2_ROOT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    env = lpac_env(args.openssl_ld or None, args.lpac_bin)
    run_log = raw_dir / "run_log.txt"

    with run_log.open("a", encoding="utf-8") as run_ledger:
        start_ts = datetime.now(timezone.utc).isoformat()
        run_ledger.write(f"\n=== exp2 run_sessions start {start_ts} iterations={args.iterations} ===\n")
        run_ledger.flush()

        failed: list[int] = []
        for i in range(1, args.iterations + 1):
            sess_path = raw_dir / f"session_{i:03d}.log"
            dl_cmd = ["profile", "download", "-s", args.smdp, "-m", args.matching_id]
            iter_ts = datetime.now(timezone.utc).isoformat()
            with sess_path.open("w", encoding="utf-8") as sf:
                sf.write(f"iteration {i} {iter_ts}\n")
                rc, out, err = run_lpac(args.lpac_bin, env, dl_cmd, args.timeout, sf)
                combined = (out or "") + (err or "")
                if rc != 0 and "iccid_already_exists" in combined:
                    dup_iccid = extract_iccid_from_failed_download_stdout(out or "")
                    if dup_iccid:
                        sf.write(
                            f"\n# iccid_already_exists_on_euicc — remove {dup_iccid} then retry download\n"
                        )
                        sf.flush()
                        cleanup_installed_profile(
                            args.lpac_bin,
                            env,
                            dup_iccid,
                            args.timeout,
                            sf,
                            f"{i} pre-retry",
                        )
                        sf.write("\n# second download attempt\n")
                        sf.flush()
                        rc, out, err = run_lpac(args.lpac_bin, env, dl_cmd, args.timeout, sf)

            iccid = parse_success_iccid(out) if rc == 0 else None
            if rc != 0 or not iccid:
                failed.append(i)
                print(
                    f"[iter {i}/{args.iterations}] FAIL rc={rc} iccid={iccid!r} log={sess_path}",
                    flush=True,
                )
                run_ledger.write(f"iter {i} FAIL rc={rc} iccid={iccid!r}\n")
            else:
                print(f"[iter {i}/{args.iterations}] OK iccid={iccid}", flush=True)
                run_ledger.write(f"iter {i} OK iccid={iccid}\n")
                if not args.skip_cleanup:
                    with sess_path.open("a", encoding="utf-8") as sf:
                        cleanup_installed_profile(
                            args.lpac_bin, env, iccid, args.timeout, sf, str(i)
                        )

            if args.cooldown_every > 0 and i % args.cooldown_every == 0 and i < args.iterations:
                print(f"cooldown {args.cooldown_sec}s after {i} iterations...", flush=True)
                run_ledger.write(f"cooldown {args.cooldown_sec}s\n")
                time.sleep(args.cooldown_sec)

        run_ledger.write(f"done failed_iters={failed}\n")
    print(f"Wrote logs under {raw_dir}; failures: {len(failed)} {failed[:20]}{'...' if len(failed) > 20 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
