#!/usr/bin/env python3
"""Generate Experiment 6 two-panel figures: PQ-TLS summary + APDU hex with EC key highlighted."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parents[1]
EXP6 = ROOT / "thesis_experiments" / "exp6_ecdh_capture"
DEFAULT_OPENSSL = Path("/home/linuxbrew/.linuxbrew/opt/openssl/bin/openssl")


def run_openssl_client(host: str, port: int, openssl_bin: Path, groups: str) -> str:
    cmd = [
        str(openssl_bin),
        "s_client",
        "-connect",
        f"{host}:{port}",
        "-groups",
        groups,
        "-msg",
    ]
    p = subprocess.run(
        cmd,
        input=b"Q\n",
        capture_output=True,
        timeout=30,
    )
    out = (p.stdout or b"").decode("utf-8", errors="replace")
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    return out + "\n" + err


def extract_tls_summary(text: str) -> list[str]:
    lines: list[str] = []
    for pat in (
        r"Negotiated TLS1\.3 group:\s*.+",
        r"Peer signature type:\s*.+",
        r"Cipher is\s+.+",
        r"Protocol:\s*TLSv1\.3",
    ):
        m = re.search(pat, text, re.I | re.M)
        if m:
            lines.append(m.group(0).strip())
    if not lines:
        for ln in text.splitlines():
            if "Cipher" in ln or "Negotiated" in ln or "mldsa" in ln.lower():
                lines.append(ln.strip())
            if len(lines) >= 6:
                break
    return lines or ["(Could not parse openssl output — check OPEN_SSL path and :8444)"]


def figure_left(summary_lines: list[str], outfile: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(9, 5), dpi=dpi)
    ax.set_axis_off()
    title = "PQ-TLS ES9+ (same session class as lpac on :8444)\nopenssl s_client — key facts"
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", family="monospace")
    body = "\n".join(summary_lines)
    ax.text(
        0.02,
        0.95,
        body,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f4f4f4", edgecolor="#333"),
    )
    fig.savefig(outfile, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def hex_rows(apdu_hex: str, key_hex: str, bytes_per_row: int) -> tuple[list[str], int, int]:
    """Return rows of 'offset  hex...', and start/end byte indices of key in apdu_hex (hex string)."""
    h = apdu_hex.strip().lower()
    kh = key_hex.strip().lower()
    start = h.find(kh)
    if start < 0 or start % 2:
        raise ValueError("key hex not found in APDU hex")
    start_b = start // 2
    end_b = start_b + len(kh) // 2
    rows: list[str] = []
    for off in range(0, len(h), bytes_per_row * 2):
        chunk = h[off : off + bytes_per_row * 2]
        spaced = " ".join(chunk[i : i + 2] for i in range(0, len(chunk), 2))
        rows.append(f"{off // 2:04x}  {spaced}")
    return rows, start_b, end_b


def figure_right(apdu_hex_path: Path, key_hex_path: Path, outfile: Path, dpi: int) -> None:
    apdu_hex = apdu_hex_path.read_text(encoding="utf-8").strip()
    key_hex = key_hex_path.read_text(encoding="utf-8").strip()
    rows, start_b, end_b = hex_rows(apdu_hex, key_hex, 16)
    fig, ax = plt.subplots(figsize=(11, min(22, 0.35 * len(rows) + 2)), dpi=dpi)
    ax.set_axis_off()
    ax.set_title(
        "APDU payload (PrepareDownload response BF21)\notPK.EUICC.ECKA — visible in plaintext on PC/SC",
        fontsize=11,
        fontweight="bold",
        loc="left",
        family="sans-serif",
    )
    y = 0.99
    line_h = 0.028
    mono = {"family": "monospace", "size": 8}
    key_start_row = start_b // 16
    key_end_row = (end_b - 1) // 16
    for i, row in enumerate(rows):
        y -= line_h
        if y < 0.02:
            break
        color = "#b00020" if key_start_row <= i <= key_end_row else "#111"
        weight = "bold" if key_start_row <= i <= key_end_row else "normal"
        ax.text(0.01, y, row, transform=ax.transAxes, color=color, weight=weight, **mono)
    fig.savefig(outfile, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp6", type=Path, default=EXP6)
    ap.add_argument("--openssl", type=Path, default=DEFAULT_OPENSSL)
    ap.add_argument("--host", default="testsmdpplus1.example.com")
    ap.add_argument("--port", type=int, default=8444)
    ap.add_argument("--groups", default="X25519MLKEM768")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    fig_dir = args.exp6 / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    ext = args.exp6 / "extracted"

    if not args.openssl.is_file():
        print(f"warning: openssl not found at {args.openssl}", file=sys.stderr)

    txt = run_openssl_client(args.host, args.port, args.openssl, args.groups)
    summary = extract_tls_summary(txt)
    left = fig_dir / "panel_left_pqtls_handshake.png"
    figure_left(summary, left, args.dpi)
    print(f"wrote {left}")

    apdu_euicc = ext / "apdu_euiccsigned2.txt"
    key_euicc = ext / "otPK_EUICC_ECKA_bytes.txt"
    if not apdu_euicc.is_file() or not key_euicc.is_file():
        print(f"error: missing {apdu_euicc} or {key_euicc}", file=sys.stderr)
        return 1
    right = fig_dir / "panel_right_ecdh_plaintext.png"
    figure_right(apdu_euicc, key_euicc, right, args.dpi)
    print(f"wrote {right}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
