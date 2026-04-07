#!/usr/bin/env python3
"""Summarise calibration CSVs, fit regressions, plot Figure 4 (Experiment 1)."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

SIZES = [0, 32, 64, 128, 255, 512, 1024, 1536, 2048, 2515]
ORIGINAL_SIZES = [0, 32, 64, 128, 255]
R2_THRESHOLD = 0.99


def exp1_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_rtts(path: Path) -> list[float]:
    out: list[float] = []
    with path.open(newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or "rtt_us" not in r.fieldnames:
            raise ValueError(f"Missing rtt_us column in {path}")
        for row in r:
            v = row.get("rtt_us", "").strip()
            if not v:
                continue
            out.append(float(v))
    return out


def mean_ci95(values: list[float]) -> tuple[float, float, float, float]:
    """mean, median, std, half-width of 95% CI for the mean."""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    mean = float(np.mean(arr))
    median = float(np.median(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    if n <= 1:
        return mean, median, std, float("nan")
    t = stats.t.ppf(0.975, df=n - 1)
    half = t * std / math.sqrt(n)
    return mean, median, std, half


def linregress_with_ci(
    x: np.ndarray, y: np.ndarray
) -> tuple[float, float, float, float, float, tuple[float, float], tuple[float, float]]:
    """Return slope, intercept, r2, stderr_slope, stderr_intercept, slope_ci, intercept_ci."""
    res = stats.linregress(x, y)
    slope = float(res.slope)
    intercept = float(res.intercept)
    r2 = float(res.rvalue**2)
    n = len(x)
    stderr_slope = float(res.stderr) if res.stderr is not None else float("nan")
    # scipy >= 1.7: intercept_stderr on result
    intercept_stderr = getattr(res, "intercept_stderr", None)
    if intercept_stderr is None:
        # fallback: rough estimate from residuals
        pred = slope * x + intercept
        resid = y - pred
        s = float(np.sqrt(np.sum(resid**2) / max(n - 2, 1)))
        xbar = float(np.mean(x))
        sxx = float(np.sum((x - xbar) ** 2))
        intercept_stderr = s * math.sqrt(1.0 / n + xbar**2 / sxx) if sxx > 0 else float("nan")
    else:
        intercept_stderr = float(intercept_stderr)
    df = max(n - 2, 1)
    t = stats.t.ppf(0.975, df=df)
    slope_ci = (slope - t * stderr_slope, slope + t * stderr_slope)
    intercept_ci = (intercept - t * intercept_stderr, intercept + t * intercept_stderr)
    return slope, intercept, r2, stderr_slope, intercept_stderr, slope_ci, intercept_ci


def write_regression_txt(
    path: Path,
    title: str,
    slope: float,
    intercept: float,
    r2: float,
    slope_ci: tuple[float, float],
    intercept_ci: tuple[float, float],
    extra: str = "",
) -> None:
    lines = [
        title,
        "",
        f"Model: T_PCSC(n) = a + b*n",
        f"Intercept a: {intercept:.4f} µs  (95% CI: {intercept_ci[0]:.4f} to {intercept_ci[1]:.4f})",
        f"Slope b:     {slope:.6f} µs/byte  (95% CI: {slope_ci[0]:.6f} to {slope_ci[1]:.6f})",
        f"R-squared:   {r2:.6f}",
    ]
    if extra:
        lines.extend(["", extra])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Experiment root (default: parent of scripts/)",
    )
    args = ap.parse_args()
    root = args.root or exp1_root()
    raw_dir = root / "raw"
    proc = root / "processed"
    fig_dir = root / "figures"
    proc.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    means: list[float] = []
    medians: list[float] = []
    stds: list[float] = []
    ci_hw: list[float] = []
    ns: list[int] = []

    for n in SIZES:
        p = raw_dir / f"size_{n}_bytes.csv"
        if not p.exists():
            print(f"Missing {p}", file=sys.stderr)
            return 1
        rtts = load_rtts(p)
        m, med, s, hw = mean_ci95(rtts)
        means.append(m)
        medians.append(med)
        stds.append(s)
        ci_hw.append(hw)
        ns.append(len(rtts))

    summary_path = proc / "summary_stats.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "payload_bytes",
                "n_samples",
                "mean_rtt_us",
                "median_rtt_us",
                "std_rtt_us",
                "ci95_halfwidth_mean_us",
            ]
        )
        for i, n in enumerate(SIZES):
            w.writerow(
                [
                    n,
                    ns[i],
                    f"{means[i]:.6f}",
                    f"{medians[i]:.6f}",
                    f"{stds[i]:.6f}",
                    f"{ci_hw[i]:.6f}",
                ]
            )

    n_by = {SIZES[i]: ns[i] for i in range(len(SIZES))}
    mean_by = {SIZES[i]: means[i] for i in range(len(SIZES))}
    ci_by = {SIZES[i]: ci_hw[i] for i in range(len(SIZES))}

    x_all = np.asarray([s for s in SIZES if n_by[s] > 0], dtype=float)
    y_all = np.asarray([mean_by[int(s)] for s in x_all], dtype=float)

    # Original range (sizes ⊆ ORIGINAL_SIZES with samples)
    x_o = np.asarray([s for s in ORIGINAL_SIZES if n_by[s] > 0], dtype=float)
    y_o = np.asarray([mean_by[int(s)] for s in x_o], dtype=float)
    if len(x_o) < 2:
        (proc / "regression_original.txt").write_text(
            "Linear regression — original calibration sizes (0, 32, 64, 128, 255 bytes)\n\n"
            f"Insufficient data: need ≥2 sizes with samples, got {len(x_o)}.\n",
            encoding="utf-8",
        )
        so = io = r2_o = float("nan")
        slo_ci = int_ci = (float("nan"), float("nan"))
    else:
        so, io, r2_o, _, _, slo_ci, int_ci = linregress_with_ci(x_o, y_o)
        write_regression_txt(
            proc / "regression_original.txt",
            "Linear regression — original calibration sizes (0, 32, 64, 128, 255 bytes)",
            so,
            io,
            r2_o,
            slo_ci,
            int_ci,
        )

    # Extended range (all sizes with samples)
    s1 = i1 = r2_1 = s2 = i2 = r2_2 = float("nan")
    se = ie = r2_e = float("nan")
    sle_ci = int_e_ci = (float("nan"), float("nan"))
    use_piecewise = False

    if len(x_all) < 2:
        (proc / "regression_extended.txt").write_text(
            "Extended range regression\n\n"
            f"Insufficient data: need ≥2 sizes with samples, got {len(x_all)}.\n",
            encoding="utf-8",
        )
    else:
        se, ie, r2_e, _, _, sle_ci, int_e_ci = linregress_with_ci(x_all, y_all)
        use_piecewise = r2_e < R2_THRESHOLD
        x_lo, y_lo = x_all[x_all <= 255], y_all[x_all <= 255]
        x_hi, y_hi = x_all[x_all > 255], y_all[x_all > 255]
        if use_piecewise and len(x_lo) >= 2 and len(x_hi) >= 2:
            s1, i1, r2_1, _, _, sl1, in1 = linregress_with_ci(x_lo, y_lo)
            s2, i2, r2_2, _, _, sl2, in2 = linregress_with_ci(x_hi, y_hi)
            piecewise_note = (
                f"Extended single-line R² = {r2_e:.6f} < {R2_THRESHOLD}; piecewise models:\n"
                f"  Segment 1 (n ≤ 255):  T = {i1:.4f} + {s1:.6f}*n  R²={r2_1:.6f}\n"
                f"     95% CI intercept: {in1[0]:.4f}–{in1[1]:.4f} µs  slope: {sl1[0]:.6f}–{sl1[1]:.6f} µs/byte\n"
                f"  Segment 2 (n > 255): T = {i2:.4f} + {s2:.6f}*n  R²={r2_2:.6f}\n"
                f"     95% CI intercept: {in2[0]:.4f}–{in2[1]:.4f} µs  slope: {sl2[0]:.6f}–{sl2[1]:.6f} µs/byte\n"
            )
            ext_body = piecewise_note + "\n" + (
                "Reference single fit (all sizes with samples):\n"
                f"  T = {ie:.4f} + {se:.6f}*n  R²={r2_e:.6f}\n"
                f"  95% CI intercept: {int_e_ci[0]:.4f}–{int_e_ci[1]:.4f} µs  slope: {sle_ci[0]:.6f}–{sle_ci[1]:.6f} µs/byte"
            )
            (proc / "regression_extended.txt").write_text(
                "Extended range regression\n\n" + ext_body + "\n",
                encoding="utf-8",
            )
        else:
            use_piecewise = False
            write_regression_txt(
                proc / "regression_extended.txt",
                "Linear regression — extended sizes (all payload points with samples, 0–2515 byte design)",
                se,
                ie,
                r2_e,
                sle_ci,
                int_e_ci,
            )

    # Figure 4 — only plot points with samples (skip empty sizes)
    plot_x = [SIZES[i] for i in range(len(SIZES)) if ns[i] > 0]
    plot_y = [means[i] for i in range(len(SIZES)) if ns[i] > 0]
    plot_e = [ci_hw[i] for i in range(len(SIZES)) if ns[i] > 0]

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)
    if plot_x:
        ax.errorbar(
            plot_x,
            plot_y,
            yerr=plot_e,
            fmt="o",
            capsize=3,
            color="tab:blue",
            ecolor="tab:blue",
            alpha=0.85,
            label="Mean RTT ±95% CI",
        )
    xs = np.linspace(0, 2515, 300)
    if len(x_all) >= 2 and np.isfinite(se) and np.isfinite(ie) and np.isfinite(r2_e):
        if use_piecewise and np.isfinite(s1) and np.isfinite(s2):
            xs1 = np.linspace(0, 255, 100)
            xs2 = np.linspace(255, 2515, 200)
            ax.plot(xs1, s1 * xs1 + i1, "-", color="tab:orange", lw=2, label=f"Piecewise ≤255: T={i1:.0f}+{s1:.2f}·n  R²={r2_1:.4f}")
            ax.plot(xs2, s2 * xs2 + i2, "-", color="darkorange", lw=2, label=f"Piecewise >255: T={i2:.0f}+{s2:.2f}·n  R²={r2_2:.4f}")
            ax.plot(xs, se * xs + ie, ":", color="gray", lw=1.5, alpha=0.9, label=f"Single fit (ref) R²={r2_e:.4f}")
        else:
            ys = se * xs + ie
            ax.plot(xs, ys, "-", color="tab:orange", lw=2, label=f"Fit: T = {ie:.0f} + {se:.2f}·n  R²={r2_e:.4f}")

    ax.axvline(255, color="gray", ls="--", lw=1.2, label="original calibration range")
    ax.axvline(2515, color="purple", ls="--", lw=1.2, label="measured 4-cert chain (this setup)")
    ax.set_xlabel("Payload size (bytes)")
    ax.set_ylabel("Round-trip time (µs)")
    ax.set_title("PC/SC STORE DATA RTT vs payload size (extended calibration)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_png = fig_dir / "figure4_pcsc_calibration.png"
    fig.savefig(out_png, dpi=300)
    plt.close(fig)

    print(f"Wrote {summary_path}")
    print(f"Wrote {proc / 'regression_original.txt'}")
    print(f"Wrote {proc / 'regression_extended.txt'}")
    print(f"Wrote {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
