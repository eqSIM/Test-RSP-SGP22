"""Shared stats, CSV, thermal helpers."""
from __future__ import annotations

import csv
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, List, Sequence

import numpy as np


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_cpu_temp_c() -> float | None:
    base = Path("/sys/class/thermal")
    if not base.is_dir():
        return None
    for z in sorted(base.glob("thermal_zone*")):
        t = z / "temp"
        if t.is_file():
            try:
                return int(t.read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
    return None


def mean_ci95(xs: Sequence[float]) -> tuple[float, float, float]:
    a = np.asarray(xs, dtype=np.float64)
    mu = float(np.mean(a))
    sigma = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
    n = len(a)
    if n < 2:
        return mu, sigma, float("nan")
    # Normal approx 95% CI
    from scipy import stats

    t = stats.t.ppf(0.975, df=n - 1)
    half = t * sigma / math.sqrt(n)
    return mu, sigma, half


def percentile(xs: Sequence[float], p: float) -> float:
    return float(np.percentile(np.asarray(xs, dtype=np.float64), p))


def fit_linear_pcsc(times_us: Sequence[float], payload_bytes: Sequence[int]) -> dict[str, Any]:
    """Fit delta_pcsc(n) = a + b*n_bytes; times_us and payload_bytes same length (one row per measurement)."""
    x = np.asarray(payload_bytes, dtype=np.float64)
    y = np.asarray(times_us, dtype=np.float64)
    if len(x) < 2:
        return {"a_us": float(np.mean(y)), "b_us_per_byte": 0.0, "r_squared": 0.0}
    coeffs = np.polyfit(x, y, 1)
    b, a = coeffs[0], coeffs[1]
    y_pred = a + b * x
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"a_us": float(a), "b_us_per_byte": float(b), "r_squared": float(r2)}


def mann_kendall_test(y: Sequence[float]) -> tuple[float, float]:
    """Returns (tau-like trend statistic, approximate p-value via scipy kendalltau on index)."""
    from scipy.stats import kendalltau

    arr = np.asarray(y, dtype=np.float64)
    if len(arr) < 3:
        return float("nan"), float("nan")
    idx = np.arange(len(arr), dtype=np.float64)
    tau, p = kendalltau(idx, arr)
    return float(tau), float(p)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w") as f:
        json.dump(obj, f, indent=2)


def run_lpac_chip_info(lpac_bin: str, ld_path: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ld_path + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    r = subprocess.run(
        [lpac_bin, "chip", "info"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(lpac_bin),
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    return json.loads(r.stdout)


def parse_bench_stderr(stderr: str) -> list[dict[str, Any]]:
    out = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("BENCH|"):
            continue
        parts = line.split("|")
        if len(parts) >= 5:
            out.append(
                {
                    "tag": parts[1],
                    "name": parts[2],
                    "duration_us": int(parts[3]),
                    "rv": int(parts[4]),
                }
            )
    return out
