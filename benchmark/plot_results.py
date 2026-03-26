#!/usr/bin/env python3
"""Generate matplotlib figures from pqc_benchmark_data (sessions, calibration, host crypto, TLS)."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from config import DATA_ROOT

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print("matplotlib is required: pip install matplotlib", file=sys.stderr)
    raise SystemExit(1) from e


def _iter_sort_key(p: Path) -> int:
    m = re.search(r"iter_(\d+)", p.name)
    return int(m.group(1)) if m else 0


def load_session_rows(sess_dir: Path) -> list[dict]:
    files = sorted(sess_dir.glob("iter_*.json"), key=_iter_sort_key)
    return [json.loads(fp.read_text()) for fp in files]


def _tls_mode(row: dict) -> str:
    return row.get("tls_mode") or "classical"


def plot_session_wall(rows: list[dict], out: Path) -> None:
    if not rows:
        return
    iters = [r["iter"] for r in rows]
    walls = [r.get("session_wall_s", 0.0) for r in rows]
    ok = [r.get("returncode", 0) == 0 for r in rows]
    modes = [_tls_mode(r) for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4))
    for mode, color, label in (
        ("classical", "steelblue", "classical TLS"),
        ("pq_tls", "mediumpurple", "PQ-TLS"),
    ):
        mi = [i for i, m in enumerate(modes) if m == mode]
        if not mi:
            continue
        ax.plot(
            [iters[i] for i in mi],
            [walls[i] for i in mi],
            color=color,
            linewidth=1.2,
            alpha=0.85,
            label=label,
            marker=".",
            markersize=3,
        )
    if "pq_tls" in modes and "classical" in modes:
        first_pq = next((i for i, m in enumerate(modes) if m == "pq_tls"), None)
        if first_pq is not None:
            ax.axvline(iters[first_pq], color="0.5", linestyle="--", linewidth=1, label="PQ phase start")
    bad_i = [i for i, o in enumerate(ok) if not o]
    if bad_i:
        ax.scatter(
            [iters[i] for i in bad_i],
            [walls[i] for i in bad_i],
            color="crimson",
            s=36,
            zorder=5,
            label="returncode != 0",
        )
    ax.set_xlabel("global iteration")
    ax.set_ylabel("session wall time (s)")
    ax.set_title("Platform A profile download — session duration")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def build_series(rows: list[dict]) -> dict[str, list[float | None]]:
    n = len(rows)
    series: dict[str, list[float | None]] = defaultdict(lambda: [None] * n)
    for i, row in enumerate(rows):
        for b in row.get("bench", []):
            k = f"{b['tag']}|{b['name']}"
            series[k][i] = float(b["duration_us"])
    return dict(series)


def _plot_operation_means_subset(
    rows: list[dict],
    out: Path,
    top_n: int,
    title_suffix: str,
    bar_color: str,
) -> None:
    sums: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("returncode", 0) != 0:
            continue
        seen: dict[str, float] = {}
        for b in row.get("bench", []):
            k = f"{b['tag']}|{b['name']}"
            seen[k] = float(b["duration_us"])
        for k, v in seen.items():
            sums[k].append(v)
    means = [(k, float(np.mean(vs)), float(np.std(vs)), len(vs)) for k, vs in sums.items() if vs]
    means.sort(key=lambda x: -x[1])
    means = means[:top_n]
    if not means:
        return
    labels = [m[0].replace("|", "\n") for m in means]
    y = np.arange(len(means))
    mu = [m[1] for m in means]
    sig = [m[2] for m in means]
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(means))))
    ax.barh(y, mu, xerr=sig, color=bar_color, ecolor="0.45", capsize=2, height=0.65)
    ax.set_yticks(y, labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("duration (µs)")
    ax.set_title(f"Mean ± std per operation — {title_suffix} (top {len(means)})")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_operation_means(rows: list[dict], out: Path, top_n: int) -> None:
    if not rows:
        return
    _plot_operation_means_subset(rows, out, top_n, "all modes", "steelblue")
    classical = [r for r in rows if _tls_mode(r) == "classical"]
    pq = [r for r in rows if _tls_mode(r) == "pq_tls"]
    if classical:
        _plot_operation_means_subset(
            classical, out.parent / "operation_means_classical.png", top_n, "classical TLS", "steelblue"
        )
    if pq:
        _plot_operation_means_subset(
            pq, out.parent / "operation_means_pq_tls.png", top_n, "PQ-TLS", "mediumpurple"
        )


def plot_timeseries_key_ops(rows: list[dict], series: dict[str, list[float | None]], out: Path) -> None:
    if not rows:
        return
    iters = [r["iter"] for r in rows]
    modes = [_tls_mode(r) for r in rows]
    # Pick ops with highest mean duration (successful rows only)
    sums: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("returncode", 0) != 0:
            continue
        for b in row.get("bench", []):
            k = f"{b['tag']}|{b['name']}"
            sums[k].append(float(b["duration_us"]))
    ranked = sorted(((k, float(np.mean(v))) for k, v in sums.items()), key=lambda x: -x[1])
    pick = [k for k, _ in ranked[:6]]
    if not pick:
        return
    fig, axes = plt.subplots(len(pick), 1, figsize=(10, 2.2 * len(pick)), sharex=True)
    if len(pick) == 1:
        axes = [axes]
    for ax, key in zip(axes, pick):
        vals = series.get(key, [None] * len(rows))
        ys = [np.nan if v is None else v / 1e6 for v in vals]
        for mode, color in (("classical", "steelblue"), ("pq_tls", "mediumpurple")):
            idx = [i for i, m in enumerate(modes) if m == mode]
            if not idx:
                continue
            ax.plot(
                [iters[i] for i in idx],
                [ys[i] for i in idx],
                ".-",
                markersize=4,
                linewidth=0.9,
                color=color,
                label=mode,
            )
        ax.legend(fontsize=7, loc="upper right")
        ax.set_ylabel("s")
        ax.set_title(key.replace("|", " — "), fontsize=9)
        ax.grid(True, alpha=0.3)
        if "pq_tls" in modes and "classical" in modes:
            fp = next((i for i, m in enumerate(modes) if m == "pq_tls"), None)
            if fp is not None:
                ax.axvline(iters[fp], color="0.6", linestyle=":", linewidth=1)
    axes[-1].set_xlabel("iteration")
    fig.suptitle("Per-operation duration over iterations (seconds)", y=1.01, fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_pcsc_calibration(data_root: Path, out: Path) -> bool:
    csv_path = data_root / "calibration" / "pcsc_overhead" / "raw_per_size.csv"
    model_path = data_root / "calibration" / "pcsc_overhead" / "model.json"
    if not csv_path.is_file():
        return False
    by_size: dict[int, list[float]] = defaultdict(list)
    with csv_path.open(newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                pb = int(row["payload_bytes"])
                by_size[pb].append(float(row["time_us"]))
            except (KeyError, ValueError):
                continue
    if not by_size:
        return False
    sizes = sorted(by_size.keys())
    mus = [float(np.mean(by_size[s])) for s in sizes]
    sgs = [float(np.std(by_size[s])) for s in sizes]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.errorbar(sizes, mus, yerr=sgs, fmt="o-", capsize=3, color="darkgreen", ecolor="0.4")
    ax.set_xlabel("payload (bytes)")
    ax.set_ylabel("round-trip time (µs)")
    ax.set_title("PC/SC calibration (per payload size)")
    ax.grid(True, alpha=0.3)
    if model_path.is_file():
        m = json.loads(model_path.read_text())
        a, b = float(m.get("a_us", 0)), float(m.get("b_us_per_byte", 0))
        xs = np.linspace(min(sizes), max(sizes), 50)
        ax.plot(xs, a + b * xs, "--", color="crimson", linewidth=1.5, label=f"fit: {a:.0f} + {b:.2f}·L")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return True


def plot_host_crypto(data_root: Path, out: Path) -> bool:
    p = data_root / "host_smdp" / "host_crypto_summary.json"
    if not p.is_file():
        return False
    data = json.loads(p.read_text())
    items = []
    for name, stats in data.items():
        if isinstance(stats, dict) and "mean_us" in stats:
            items.append((name, float(stats["mean_us"]), float(stats.get("ci95_half_us", 0))))
    if not items:
        return False
    items.sort(key=lambda x: -x[1])
    labels = [x[0] for x in items]
    means = [x[1] for x in items]
    err = [x[2] for x in items]
    y = np.arange(len(items))
    fig, ax = plt.subplots(figsize=(8, max(3, 0.32 * len(items))))
    ax.barh(y, means, xerr=err, color="darkorange", ecolor="0.4", capsize=2, height=0.65)
    ax.set_yticks(y, labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("time (µs)")
    ax.set_title("Host crypto micro-benchmarks (mean ± 95% CI half-width)")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return True


_TLS_MSG_ORDER = ["ClientHello", "ServerHello", "Certificate", "CertificateVerify", "Finished"]
_TLS_MSG_COLORS = {
    "ClientHello": "#4c9be8",
    "ServerHello": "#6db8f5",
    "Certificate": "#e07b39",
    "CertificateVerify": "#e8a95c",
    "Finished": "#7ec87e",
}


def plot_tls_latency(data_root: Path, out: Path) -> bool:
    classical_path = data_root / "bandwidth" / "tls_handshake" / "classical_nginx_summary.json"
    pq_path = data_root / "bandwidth" / "tls_handshake" / "pqtls_nginx_summary.json"

    entries: list[tuple[str, str, dict]] = []
    if classical_path.is_file():
        entries.append(("Classical TLS\n(X25519+ECDSA)", "steelblue", json.loads(classical_path.read_text())))
    if pq_path.is_file():
        entries.append(("PQ-TLS\n(X25519MLKEM768+ML-DSA-44)", "mediumpurple", json.loads(pq_path.read_text())))
    if not entries:
        return False

    has_sizes = any("msg_sizes_bytes" in e[2] for e in entries)
    ncols = 2 if has_sizes and len(entries) > 1 else 1
    fig, axes = plt.subplots(1, ncols, figsize=(5 * ncols, 4))
    if ncols == 1:
        axes = [axes]

    # Left panel: latency bar chart
    ax = axes[0]
    labels = [e[0] for e in entries]
    colors = [e[1] for e in entries]
    means = [float(e[2]["mean_ms"]) for e in entries]
    errs = [float(e[2].get("ci95_half_ms", 0)) for e in entries]
    x = np.arange(len(entries))
    bars = ax.bar(x, means, yerr=errs, capsize=5, color=colors, ecolor="0.35", width=0.5)
    for bar, mu in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, mu + max(errs) * 0.1, f"{mu:.1f} ms",
                ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("handshake time (ms)")
    ax.set_title("TLS handshake latency\n(openssl s_client, loopback)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(0, max(means) * 1.35)

    # Right panel: stacked message-size bar chart
    if has_sizes and len(entries) > 1:
        ax2 = axes[1]
        all_keys = _TLS_MSG_ORDER + sorted(
            set(k for _, _, j in entries for k in j.get("msg_sizes_bytes", {}) if k not in _TLS_MSG_ORDER)
        )
        bottoms = [0.0] * len(entries)
        for key in all_keys:
            vals = [e[2].get("msg_sizes_bytes", {}).get(key, 0) / 1024 for e in entries]
            if not any(vals):
                continue
            color = _TLS_MSG_COLORS.get(key, "#aaaaaa")
            ax2.bar(x, vals, bottom=bottoms, label=key, color=color, width=0.5)
            for xi, (v, b) in enumerate(zip(vals, bottoms)):
                if v > 0.1:
                    ax2.text(xi, b + v / 2, f"{v * 1024:.0f} B", ha="center", va="center",
                             fontsize=7, color="white" if v > 0.5 else "black")
            bottoms = [b + v for b, v in zip(bottoms, vals)]
        for xi, total in enumerate(bottoms):
            ax2.text(xi, total + 0.05, f"{total:.1f} KB", ha="center", va="bottom", fontsize=8, fontweight="bold")
        ax2.set_xticks(x, labels, fontsize=8)
        ax2.set_ylabel("handshake message size (KB)")
        ax2.set_title("TLS handshake message sizes\nper message type")
        ax2.legend(loc="upper left", fontsize=7)
        ax2.grid(True, axis="y", alpha=0.3)
        ax2.set_ylim(0, max(bottoms) * 1.25)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot benchmark outputs under DATA_ROOT.")
    ap.add_argument(
        "--data-root",
        type=Path,
        default=Path(DATA_ROOT),
        help="Benchmark data directory (default: PQC_BENCHMARK_DATA or pqc_benchmark_data)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for PNG files (default: DATA_ROOT/plots)",
    )
    ap.add_argument("--top-ops", type=int, default=20, help="Max operations in mean-duration bar chart")
    args = ap.parse_args()

    root: Path = args.data_root.resolve()
    out_dir = (args.out or (root / "plots")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sess_dir = root / "platform_a" / "sessions"
    if not sess_dir.is_dir():
        print(f"No sessions dir: {sess_dir}", file=sys.stderr)
        return 1

    rows = load_session_rows(sess_dir)
    if not rows:
        print(f"No iter_*.json under {sess_dir}", file=sys.stderr)
        return 1

    plot_session_wall(rows, out_dir / "session_wall_time.png")
    plot_operation_means(rows, out_dir / "operation_means.png", top_n=args.top_ops)
    ser = build_series(rows)
    plot_timeseries_key_ops(rows, ser, out_dir / "timeseries_key_ops.png")

    plot_pcsc_calibration(root, out_dir / "pcsc_calibration.png")
    plot_host_crypto(root, out_dir / "host_crypto.png")
    plot_tls_latency(root, out_dir / "tls_handshake.png")

    print(json.dumps({"ok": True, "plots_dir": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
