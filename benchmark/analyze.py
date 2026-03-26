#!/usr/bin/env python3
"""Stationarity, PC/SC correction, summaries, prerequisites.json."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from config import DATA_ROOT
from utils import mann_kendall_test, mean_ci95, percentile, write_json


def load_pcsc_model() -> dict:
    p = Path(DATA_ROOT) / "calibration" / "pcsc_overhead" / "model.json"
    if not p.is_file():
        return {"a_us": 0.0, "b_us_per_byte": 0.0}
    return json.loads(p.read_text())


def apdu_estimate_for_tag(tag: str, name: str) -> tuple[int, int]:
    """Rough (n_apdu, payload_bytes) for PC/SC correction."""
    if tag == "ES9P":
        return 0, 0
    if tag in ("BF2E", "BF20", "BF38", "BF21", "BF41"):
        return 1, 2000
    if tag == "BF36":
        seg = 1
        if name.startswith("LoadBPP_seg"):
            try:
                seg = int(name.replace("LoadBPP_seg", "")) + 1
            except ValueError:
                seg = 1
        return seg, 8000 * seg
    if tag == "ES10X":
        return 1, 120
    return 1, 500


def delta_pcsc_us(model: dict, n_apdu: int, nbytes: int) -> float:
    a = float(model.get("a_us", 0.0))
    b = float(model.get("b_us_per_byte", 0.0))
    return n_apdu * a + nbytes * b


def summarize_ops(files: list[Path], model: dict) -> dict[str, dict]:
    by_tag: dict[str, list[float]] = defaultdict(list)
    for fp in files:
        data = json.loads(fp.read_text())
        for b in data.get("bench", []):
            tag = b["tag"]
            name = b["name"]
            tus = float(b["duration_us"])
            by_tag[f"{tag}|{name}"].append(tus)

    summaries = {}
    for k, xs in by_tag.items():
        mu, sig, ha = mean_ci95(xs)
        tau, p = mann_kendall_test(xs)
        summaries[k] = {
            "n": len(xs),
            "mean_us": mu,
            "sigma_us": sig,
            "ci95_half_us": ha,
            "p99_us": percentile(xs, 99),
            "mann_kendall_tau": tau,
            "mann_kendall_p": p,
        }
    return summaries


def main() -> int:
    model = load_pcsc_model()
    sess_dir = Path(DATA_ROOT) / "platform_a" / "sessions"
    if not sess_dir.is_dir():
        print("No session data; run run_benchmark.py first", file=sys.stderr)
        return 1

    files = sorted(sess_dir.glob("iter_*.json"))
    if not files:
        print("No iter_*.json files", file=sys.stderr)
        return 1

    summaries_all = summarize_ops(files, model)

    by_mode: dict[str, list[Path]] = defaultdict(list)
    for fp in files:
        data = json.loads(fp.read_text())
        mode = data.get("tls_mode") or "classical"
        by_mode[mode].append(fp)

    by_tls_mode = {mode: summarize_ops(fps, model) for mode, fps in by_mode.items()}

    out = Path(DATA_ROOT) / "normalization"
    out.mkdir(parents=True, exist_ok=True)
    write_json(
        out / "prerequisites.json",
        {
            "schema_version": "1.1",
            "platform_a_bench": summaries_all,
            "platform_a_bench_by_tls_mode": by_tls_mode,
            "pcsc_model": model,
        },
    )

    rdir = Path(DATA_ROOT) / "results" / "phase1_options_ab"
    rdir.mkdir(parents=True, exist_ok=True)
    write_json(
        rdir / "summary.json",
        {"operations": summaries_all, "operations_by_tls_mode": by_tls_mode},
    )
    print(json.dumps({"ok": True, "tags": len(summaries_all), "tls_modes": list(by_tls_mode.keys())}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
