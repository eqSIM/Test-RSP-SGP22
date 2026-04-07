#!/usr/bin/env python3
"""Load exp5 raw CSVs, compute summary stats, BF21 median delta, and comparison figure."""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
PROC = ROOT / "processed"
FIG = ROOT / "figures"


def load_prep_col(path: Path) -> list[int]:
    out: list[int] = []
    with path.open(newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(int(row["prepare_download_us"]))
    return out


def load_prep_by_iteration(path: Path) -> dict[int, int]:
    d: dict[int, int] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            d[int(row["iteration"])] = int(row["prepare_download_us"])
    return d


def load_full_col(path: Path) -> list[float]:
    out: list[float] = []
    with path.open(newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(float(row["wall_time_ms"]))
    return out


def load_full_by_iteration(path: Path) -> dict[int, float]:
    d: dict[int, float] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            d[int(row["iteration"])] = float(row["wall_time_ms"])
    return d


def paired_bf21_diff_us(a_map: dict[int, int], c_map: dict[int, int]) -> list[float]:
    common = sorted(set(a_map.keys()) & set(c_map.keys()))
    return [float(c_map[i] - a_map[i]) for i in common]


def ci95_mean(xs: list[float]) -> tuple[float, float, float]:
    """Return (low, mean, high) for 95% CI of the mean (t-distribution)."""
    n = len(xs)
    m = statistics.mean(xs)
    if n < 2:
        return m, m, m
    s = statistics.stdev(xs)
    se = s / math.sqrt(n)
    try:
        from scipy import stats as scipy_stats

        h = float(scipy_stats.t.ppf(0.975, n - 1)) * se
    except ImportError:
        h = 1.96 * se
    return m - h, m, m + h


def main() -> int:
    PROC.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    a_prep = load_prep_col(RAW / "config_a_preparedownload.csv")
    c_prep = load_prep_col(RAW / "config_c_preparedownload.csv")
    a_prep_map = load_prep_by_iteration(RAW / "config_a_preparedownload.csv")
    c_prep_map = load_prep_by_iteration(RAW / "config_c_preparedownload.csv")
    a_full = load_full_col(RAW / "config_a_fullsession.csv")
    c_full = load_full_col(RAW / "config_c_fullsession.csv")

    med_a = statistics.median(a_prep)
    med_c = statistics.median(c_prep)
    delta_median = med_c - med_a
    paired_diff = paired_bf21_diff_us(a_prep_map, c_prep_map)
    med_paired = statistics.median(paired_diff) if paired_diff else delta_median
    pct_of_bf21 = (100.0 * delta_median / med_a) if med_a else 0.0
    med_wall_a = statistics.median(a_full)
    med_wall_c = statistics.median(c_full)
    delta_wall_ms = med_wall_c - med_wall_a

    rows = []
    for label, xs in (
        ("config_a_prepare_download_us", [float(x) for x in a_prep]),
        ("config_c_prepare_download_us", [float(x) for x in c_prep]),
        ("config_a_fullsession_wall_ms", a_full),
        ("config_c_fullsession_wall_ms", c_full),
    ):
        lo, m, hi = ci95_mean(xs)
        rows.append(
            {
                "series": label,
                "n": len(xs),
                "mean": m,
                "median": statistics.median(xs),
                "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
                "ci95_mean_low": lo,
                "ci95_mean_high": hi,
            }
        )

    summary_path = PROC / "summary_stats.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "series",
                "n",
                "mean",
                "median",
                "stdev",
                "ci95_mean_low",
                "ci95_mean_high",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    (PROC / "mlkem_keygen_latency.txt").write_text(
        "Experiment 5 — BF21 PrepareDownload RTT difference (config c vs config a)\n"
        "Interpretation: median(config_c) − median(config_a) isolates the incremental cost\n"
        "of replacing ECDH P-256 key generation with ML-KEM-768 keygen in the BF21 path,\n"
        "plus any fixed TLV/encoding differences between the two stacks.\n\n"
        f"median_BF21_us_config_a (ECDH path): {med_a:.1f}\n"
        f"median_BF21_us_config_c (ML-KEM path): {med_c:.1f}\n"
        f"T_delta_median_us: {delta_median:.1f}\n",
        encoding="utf-8",
    )

    (PROC / "ecdh_keygen_latency.txt").write_text(
        "Experiment 5 — Baseline BF21 PrepareDownload RTT (config a, ECDH P-256)\n"
        "Note: BF21 RTT includes host↔v-euicc APDU handling and other work besides keygen.\n"
        f"median_prepare_download_us: {med_a:.1f}\n"
        f"mean_prepare_download_us: {statistics.mean(a_prep):.1f}\n",
        encoding="utf-8",
    )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # --- Figure A: BF21 RTT distributions (nearly overlapping — intended) ---
        fig_a, ax_a = plt.subplots(figsize=(8, 5))
        ax_a.violinplot(
            [a_prep, c_prep],
            positions=[1, 2],
            showmeans=True,
            showmedians=True,
        )
        ax_a.set_xticks([1, 2])
        ax_a.set_xticklabels(["(a) ECDH P-256", "(c) ML-KEM-768"])
        ax_a.set_ylabel("PrepareDownload BF21 RTT (μs)")
        ax_a.set_title(
            "PrepareDownload (BF21) RTT Distribution — Configuration (a) vs (c)\n"
            "(near-identical shapes are the expected result at this scale)"
        )
        ax_a.grid(axis="y", alpha=0.3)
        ann = (
            f"Median difference: {delta_median:.0f} μs ({pct_of_bf21:.2f}% of BF21 RTT)\n"
            f"Note: ~{delta_median:.0f} μs gap not visible at this y-axis scale"
        )
        ax_a.text(
            0.5,
            0.02,
            ann,
            transform=ax_a.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
        )
        fig_a.tight_layout()
        path_a = FIG / "suboperation_timing_comparison.png"
        fig_a.savefig(path_a, dpi=150)
        plt.close(fig_a)
        print(f"Wrote {path_a} (Figure A)")

        # --- Figure B: paired per-iteration BF21 difference BF21(c)_i − BF21(a)_i ---
        fig_b, ax_b = plt.subplots(figsize=(7, 4.5))
        ax_b.violinplot([paired_diff], positions=[1], showmeans=True, showmedians=True)
        ax_b.axhline(0.0, color="gray", linestyle="--", linewidth=1, alpha=0.8)
        ax_b.set_xticks([1])
        ax_b.set_xticklabels(["Per-iteration Δ (c − a)"])
        ax_b.set_ylabel("Δ BF21 RTT (μs)")
        ax_b.set_title(
            "Paired difference: PrepareDownload BF21 — (c) minus (a) per iteration i"
        )
        ax_b.grid(axis="y", alpha=0.3)
        ax_b.text(
            0.5,
            0.95,
            f"Median Δ ≈ {med_paired:.0f} μs (spread shows run-to-run variation)",
            transform=ax_b.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.85),
        )
        fig_b.tight_layout()
        path_b = FIG / "fig_b_bf21_paired_difference.png"
        fig_b.savefig(path_b, dpi=150)
        plt.close(fig_b)
        print(f"Wrote {path_b} (Figure B)")

        # --- Figure C: full profile download wall time (ms) ---
        fig_c, ax_c = plt.subplots(figsize=(8, 5))
        ax_c.violinplot(
            [a_full, c_full],
            positions=[1, 2],
            showmeans=True,
            showmedians=True,
        )
        ax_c.set_xticks([1, 2])
        ax_c.set_xticklabels(["(a) ECDH", "(c) ML-KEM-768"])
        ax_c.set_ylabel("Wall time (ms)")
        ax_c.set_title(
            "Full session: lpac profile download wall time — (a) vs (c)"
        )
        lo = min(min(a_full), min(c_full))
        hi = max(max(a_full), max(c_full))
        pad = (hi - lo) * 0.05
        ax_c.set_ylim(lo - pad, hi + pad)
        ax_c.grid(axis="y", alpha=0.3)
        ax_c.text(
            0.5,
            0.02,
            f"Median overhead (c − a): {delta_wall_ms:.0f} ms — session-level cost of ML-KEM path vs ECDH",
            transform=ax_c.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
        )
        fig_c.tight_layout()
        path_c = FIG / "fig_c_fullsession_wall_time.png"
        fig_c.savefig(path_c, dpi=150)
        plt.close(fig_c)
        print(f"Wrote {path_c} (Figure C)")

    except ImportError as e:
        print("matplotlib not available; skip figure:", e)

    print(f"Wrote {summary_path}")
    print(f"T_delta_median_us (c−a): {delta_median:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
