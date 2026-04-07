#!/usr/bin/env python3
"""Experiment 2: parse BENCH session logs, PC/SC correction, stats, figure, alpha anchors."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EXP2_ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_ORDER: list[tuple[str, str]] = [
    ("BF2E", "GetEuiccChallenge"),
    ("BF20", "GetEuiccInfo1"),
    ("ES9P", "/gsma/rsp2/es9plus/initiateAuthentication"),
    ("BF38", "AuthenticateServer"),
    ("ES9P", "/gsma/rsp2/es9plus/authenticateClient"),
    ("BF21", "PrepareDownload"),
    ("ES9P", "/gsma/rsp2/es9plus/getBoundProfilePackage"),
]

BENCH_LINE_RE = re.compile(r"^BENCH\|")


def parse_bench_stderr(stderr: str) -> list[dict[str, str | int]]:
    """Same format as benchmark/utils.parse_bench_stderr (stdlib only)."""
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


def mean_ci95(xs: list[float]) -> tuple[float, float, float]:
    """mean, std (sample), half-width of 95%% CI for the mean."""
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    mu = statistics.mean(xs)
    if n == 1:
        return mu, 0.0, float("nan")
    sigma = statistics.stdev(xs)
    try:
        from scipy import stats as scipy_stats

        t = scipy_stats.t.ppf(0.975, df=n - 1)
        half = t * sigma / math.sqrt(n)
    except ImportError:
        half = 1.96 * sigma / math.sqrt(n)
    return mu, sigma, half


def load_pcsc_model(path: Path) -> tuple[float, float]:
    with path.open() as f:
        m = json.load(f)
    return float(m["a_us"]), float(m["b_us_per_byte"])


def load_payload_sizes(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    with path.open() as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def payload_bytes_for_row(tag: str, name: str, pmap: dict) -> float | None:
    """Return Lc n for model, or None if unknown (no PC/SC subtraction)."""
    if not pmap:
        return None
    st = pmap.get(tag)
    if not isinstance(st, dict):
        return None
    if tag == "BF36" and name.startswith("LoadBPP_seg"):
        v = st.get("_default_per_segment")
        if v is None or isinstance(v, str):
            return None
        return float(v)
    v = st.get(name)
    if v is None or isinstance(v, str):
        return None
    return float(v)


def t_pcsc_us(n: float | None, a: float, b: float) -> float | None:
    if n is None:
        return None
    return a + b * n


def iter_profile_download_stderr_exit(text: str):
    """Yield (stderr_text, exit_code) for each `profile download` invocation in log order."""
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if line.startswith("$ ") and "profile download" in line:
            j = i + 1
            if j < n and lines[j] == "--- stdout ---":
                j += 1
                while j < n and lines[j] != "--- stderr ---":
                    j += 1
                if j < n and lines[j] == "--- stderr ---":
                    j += 1
                    stderr_parts: list[str] = []
                    while j < n and not lines[j].startswith("--- exit "):
                        stderr_parts.append(lines[j])
                        j += 1
                    if j < n:
                        m = re.match(r"--- exit (\d+) ---\s*", lines[j])
                        code = int(m.group(1)) if m else -1
                        yield ("\n".join(stderr_parts), code)
                        i = j + 1
                        continue
        i += 1


def parse_bench_from_stderr_blob(blob: str) -> list[dict]:
    """BENCH rows from one stderr blob: high-level tags only, rv==0, no ES10X."""
    lines: list[dict] = []
    for line in blob.splitlines():
        s = line.strip()
        if not BENCH_LINE_RE.match(s) or s.startswith("BENCH|ES10X|"):
            continue
        parsed = parse_bench_stderr(s + "\n")
        for rec in parsed:
            if int(rec.get("rv", -1)) == 0:
                lines.append(rec)
    return lines


def extract_bench_from_session_log_legacy(text: str) -> list[dict]:
    """Fixtures / old logs without `$ profile download` lines (scan whole file)."""
    lines: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not BENCH_LINE_RE.match(s) or s.startswith("BENCH|ES10X|"):
            continue
        for rec in parse_bench_stderr(s + "\n"):
            if int(rec.get("rv", -1)) == 0:
                lines.append(rec)
    return lines


def extract_bench_from_session_log(text: str) -> list[dict]:
    """BENCH for one iteration: last successful `profile download` only (retry-safe).

    Mixing stderr from a failed first attempt (e.g. BF41 cancel path) with a later
    successful download corrupts medians. Logs from run_sessions.py always include
    `$ ... profile download`; older fixtures without that line fall back to a full-file scan.
    """
    chunks = list(iter_profile_download_stderr_exit(text))
    if chunks:
        ok_blobs = [b for b, c in chunks if c == 0]
        if not ok_blobs:
            return []
        for blob in reversed(ok_blobs):
            bench = parse_bench_from_stderr_blob(blob)
            if bench:
                return bench
        return parse_bench_from_stderr_blob(ok_blobs[-1])
    return extract_bench_from_session_log_legacy(text)


def sort_key_row(tag: str, name: str) -> tuple[int, str, str]:
    try:
        idx = PROTOCOL_ORDER.index((tag, name))
        sec = 0
    except ValueError:
        if tag == "BF36" and name.startswith("LoadBPP_seg"):
            m = re.match(r"LoadBPP_seg(\d+)$", name)
            n = int(m.group(1)) if m else 0
            idx = len(PROTOCOL_ORDER)
            sec = n
        else:
            idx = 999
            sec = 0
    return (idx, tag, f"{sec:05d}_{name}")


def self_test() -> None:
    sample = """
$ /tmp/lpac profile download -s smdp -m mid
--- stdout ---
ok
--- stderr ---
BENCH|BF2E|GetEuiccChallenge|50000|0
BENCH|BF20|GetEuiccInfo1|48000|0
BENCH|ES9P|/gsma/rsp2/es9plus/initiateAuthentication|100000|0
BENCH|BF38|AuthenticateServer|3000000|0
BENCH|ES9P|/gsma/rsp2/es9plus/authenticateClient|120000|0
BENCH|BF21|PrepareDownload|4000000|0
BENCH|ES9P|/gsma/rsp2/es9plus/getBoundProfilePackage|900000|0
BENCH|BF36|LoadBPP_seg0|800000|0
BENCH|BF36|LoadBPP_seg1|810000|0
--- exit 0 ---
"""
    rows = extract_bench_from_session_log(sample)
    assert len(rows) == 9, rows
    assert rows[3]["tag"] == "BF38"

    retry = """
$ /tmp/lpac profile download -s smdp -m mid
--- stdout ---
fail
--- stderr ---
BENCH|BF2E|GetEuiccChallenge|1|0
BENCH|BF41|CancelSession|2|0
--- exit 255 ---
$ /tmp/lpac profile download -s smdp -m mid
--- stdout ---
ok
--- stderr ---
BENCH|BF2E|GetEuiccChallenge|999|0
BENCH|BF20|GetEuiccInfo1|888|0
--- exit 0 ---
"""
    r2 = extract_bench_from_session_log(retry)
    assert len(r2) == 2, r2
    assert r2[0]["duration_us"] == 999 and r2[1]["duration_us"] == 888
    print("analyse self-test OK (single + retry parse)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=EXP2_ROOT / "raw")
    ap.add_argument("--pcsc-model", type=Path, default=EXP2_ROOT / "processed" / "pcsc_model.json")
    ap.add_argument("--payload-sizes", type=Path, default=EXP2_ROOT / "scripts" / "payload_sizes_ref.json")
    ap.add_argument("--out-processed", type=Path, default=EXP2_ROOT / "processed")
    ap.add_argument("--out-figures", type=Path, default=EXP2_ROOT / "figures")
    ap.add_argument(
        "--smdp2-verify-us",
        type=float,
        default=None,
        help="Subtract this many µs from median BF21 net for ECDH anchor (your estimate for smdpSigned2 verify)",
    )
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0

    a_us, b_us = load_pcsc_model(args.pcsc_model)
    pmap = load_payload_sizes(args.payload_sizes if Path(args.payload_sizes).is_file() else None)
    if not pmap:
        pmap = {}

    session_files = sorted(args.raw_dir.glob("session_*.log"))
    if not session_files:
        print(f"No session_*.log in {args.raw_dir}", file=sys.stderr)
        return 1

    def _no_rows_exit() -> int:
        print(
            f"No BENCH rows parsed (need a successful profile download per log). Checked {args.raw_dir}.",
            file=sys.stderr,
        )
        return 1

    raw_rows: list[dict] = []
    m_iter = re.compile(r"^iteration\s+(\d+)\s")
    n_logs = len(session_files)
    n_sessions_used = 0

    for sf in session_files:
        text = sf.read_text(encoding="utf-8", errors="replace")
        m = m_iter.match(text.split("\n", 1)[0] if text else "")
        iteration = int(m.group(1)) if m else int(sf.stem.split("_")[-1])
        bench_recs = extract_bench_from_session_log(text)
        if not bench_recs:
            continue
        n_sessions_used += 1
        for rec in bench_recs:
            tag = rec["tag"]
            name = rec["name"]
            dus = rec["duration_us"]
            n = payload_bytes_for_row(tag, name, pmap)
            adj = t_pcsc_us(n, a_us, b_us)
            net = float(dus) if adj is None else max(float(dus) - adj, 0.0)
            raw_rows.append(
                {
                    "iteration": iteration,
                    "tag": tag,
                    "name": name,
                    "duration_us": dus,
                    "payload_bytes": "" if n is None else n,
                    "t_pcsc_us": "" if adj is None else round(adj, 3),
                    "duration_net_us": round(net, 3),
                }
            )

    if not raw_rows:
        return _no_rows_exit()

    args.out_processed.mkdir(parents=True, exist_ok=True)
    args.out_figures.mkdir(parents=True, exist_ok=True)

    raw_csv = args.out_processed / "apdu_timings_raw.csv"
    with raw_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "iteration",
                "tag",
                "name",
                "duration_us",
                "payload_bytes",
                "t_pcsc_us",
                "duration_net_us",
            ],
        )
        w.writeheader()
        for row in raw_rows:
            w.writerow(row)

    net_csv = args.out_processed / "apdu_timings_net.csv"
    with net_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["iteration", "tag", "name", "duration_net_us"],
        )
        w.writeheader()
        for row in raw_rows:
            w.writerow(
                {
                    "iteration": row["iteration"],
                    "tag": row["tag"],
                    "name": row["name"],
                    "duration_net_us": row["duration_net_us"],
                }
            )

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    all_corrected = True
    for row in raw_rows:
        key = (row["tag"], row["name"])
        grouped[key].append(float(row["duration_net_us"]))
        if row["t_pcsc_us"] == "":
            all_corrected = False

    summary_path = args.out_processed / "summary_stats.csv"
    summary_rows = []
    for (tag, name), xs in sorted(grouped.items(), key=lambda kv: sort_key_row(kv[0][0], kv[0][1])):
        mu, sigma, half = mean_ci95(xs)
        med = float(statistics.median(xs))
        summary_rows.append(
            {
                "tag": tag,
                "name": name,
                "n_sessions": len(xs),
                "mean_net_us": round(mu, 3),
                "median_net_us": round(med, 3),
                "std_net_us": round(sigma, 3),
                "ci95_half_us": round(half, 3) if not math.isnan(half) else "",
            }
        )
    with summary_path.open("w", newline="") as f:
        fieldnames = [
            "tag",
            "name",
            "n_sessions",
            "mean_net_us",
            "median_net_us",
            "std_net_us",
            "ci95_half_us",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in summary_rows:
            w.writerow(row)

    def median_for(tag: str, name: str) -> float | None:
        xs = grouped.get((tag, name))
        if not xs:
            return None
        return float(statistics.median(xs))

    bf38 = median_for("BF38", "AuthenticateServer")
    bf21 = median_for("BF21", "PrepareDownload")
    ecdh = None
    if bf21 is not None and args.smdp2_verify_us is not None:
        ecdh = max(bf21 - args.smdp2_verify_us, 0.0)

    alpha_path = args.out_processed / "alpha_anchors.txt"
    with alpha_path.open("w") as f:
        f.write(f"PC/SC model: T_PCSC(n) = {a_us} + {b_us} * n (µs)\n")
        f.write(f"Payload sizes file: {args.payload_sizes}\n")
        f.write(f"All rows had Lc and T_PCSC subtracted: {all_corrected}\n\n")
        if bf38 is not None:
            f.write(f"T_eUICC BF38 AuthenticateServer median net: {bf38:.3f} µs\n")
            f.write("(Thesis: proxy for on-card verify work / ECDSA anchor — interpret cautiously.)\n\n")
        else:
            f.write("T_eUICC BF38: missing (no data)\n\n")
        if bf21 is not None:
            f.write(f"T_eUICC BF21 PrepareDownload median net: {bf21:.3f} µs\n")
        if bf21 is not None and args.smdp2_verify_us is not None:
            f.write(
                f"T_eUICC(ECDH_keygen) ≈ BF21_net - smdp2_verify "
                f"= {bf21:.3f} - {args.smdp2_verify_us:.3f} = {ecdh:.3f} µs\n"
            )
        elif bf21 is not None:
            f.write(
                "T_eUICC(ECDH_keygen): not computed — pass --smdp2-verify-us with your smdpSigned2 verify estimate (µs).\n"
            )
        f.write(
            f"\nSession logs with usable BENCH (successful profile download): "
            f"{n_sessions_used} / {n_logs}\n"
        )

    # Figure: aggregate BF36 as sum per session for bar chart clarity
    bar_labels: list[str] = []
    bar_means: list[float] = []
    bar_err: list[float] = []
    for row in summary_rows:
        tag, name = row["tag"], row["name"]
        if tag == "BF36":
            continue
        bar_labels.append(f"{tag} {name}" if len(name) < 40 else f"{tag} …")
        bar_means.append(row["median_net_us"] / 1000.0)
        bar_err.append(float(row["std_net_us"]) / 1000.0)

    bf36_by_iter: dict[int, float] = defaultdict(float)
    for row in raw_rows:
        if row["tag"] == "BF36":
            bf36_by_iter[row["iteration"]] += float(row["duration_net_us"])
    if bf36_by_iter:
        totals = list(bf36_by_iter.values())
        med_t = float(statistics.median(totals))
        sig_t = statistics.stdev(totals) if len(totals) > 1 else 0.0
        bar_labels.append("BF36 sum all segments")
        bar_means.append(med_t / 1000.0)
        bar_err.append(float(sig_t) / 1000.0)

    fig_path: Path | None = args.out_figures / "figure6_apdu_breakdown.png"
    try:
        import matplotlib.pyplot as plt

        if bar_labels:
            y_pos = list(range(len(bar_labels)))
            fig, ax = plt.subplots(figsize=(10, max(4, len(bar_labels) * 0.35)))
            ax.barh(y_pos, bar_means, xerr=bar_err, capsize=3, color="steelblue", ecolor="gray")
            ax.set_yticks(y_pos)
            ax.set_yticklabels(bar_labels, fontsize=8)
            ax.set_xlabel("Duration (ms): median net (where Lc known); error bars ± std across sessions")
            ax.set_title("Experiment 2: session operation times (PC/SC corrected if Lc known)")
            ax.invert_yaxis()
            fig.tight_layout()
            fig.savefig(fig_path, dpi=300)
            plt.close(fig)
        else:
            fig_path = None
            print("No data for figure; skipped", file=sys.stderr)
    except ImportError:
        print("matplotlib not installed; skipped figure", file=sys.stderr)
        fig_path = None

    print(f"Wrote {summary_path}, {alpha_path}" + (f", {fig_path}" if fig_path else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
