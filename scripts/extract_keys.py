#!/usr/bin/env python3
"""Parse LPAC_APDU_DEBUG log from Experiment 6; extract otPK.EUICC.ECKA and otPK.DP.ECKA.

Inputs: thesis_experiments/exp6_ecdh_capture/raw/apdu_debug.txt
Outputs under thesis_experiments/exp6_ecdh_capture/extracted/ and notes to stdout.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXP6 = ROOT / "thesis_experiments" / "exp6_ecdh_capture"

APDU_LINE = re.compile(
    r"\[DEBUG\] \[APDU\] \[(TX|RX)\].*Data:\s*([0-9a-fA-F]*)\s*$"
)


def parse_tlv_length(hexdata: str, off: int) -> tuple[int, int]:
    """DER length from hex string starting at byte offset `off` (each byte = 2 hex chars). Returns (length_value, num_length_bytes)."""
    b0 = int(hexdata[off * 2 : off * 2 + 2], 16)
    if b0 < 0x80:
        return b0, 1
    n = b0 & 0x7F
    acc = 0
    for i in range(n):
        acc = (acc << 8) | int(hexdata[(off + 1 + i) * 2 : (off + 1 + i) * 2 + 2], 16)
    return acc, 1 + n


def find_5f49_p256_point(hexdata: str, start: int = 0) -> tuple[int, str] | None:
    """Find first 5F49 TLV whose value is 65 bytes starting with 04 (P-256). Returns (hex_offset_of_value_start, key_hex_130_chars)."""
    h = hexdata.lower()
    pos = start
    while True:
        idx = h.find("5f49", pos)
        if idx < 0:
            return None
        if idx % 2 != 0:
            pos = idx + 1
            continue
        off = idx // 2
        try:
            vlen, lbytes = parse_tlv_length(h, off + 2)
        except (ValueError, IndexError):
            pos = idx + 4
            continue
        vstart = off + 2 + lbytes
        vstart_hex = vstart * 2
        try:
            chunk = h[vstart_hex : vstart_hex + vlen * 2]
        except IndexError:
            pos = idx + 4
            continue
        if vlen == 65 and chunk.startswith("04") and len(chunk) >= 130:
            return vstart_hex, chunk[:130]
        pos = idx + 4


def parse_rows(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = APDU_LINE.match(line.strip())
        if m:
            rows.append((m.group(1), m.group(2).lower().replace(" ", "")))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--raw",
        type=Path,
        default=EXP6 / "raw" / "apdu_debug.txt",
        help="Path to apdu_debug.txt",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=EXP6 / "extracted",
        help="Output directory",
    )
    args = ap.parse_args()

    if not args.raw.is_file():
        print(f"error: missing {args.raw}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    rows = parse_rows(args.raw)
    if not rows:
        print("error: no APDU lines found", file=sys.stderr)
        return 1

    bf21_rx = None
    for _i, (d, data) in enumerate(rows):
        if d == "RX" and data.startswith("bf21") and "5f49" in data:
            bf21_rx = data
            break

    if not bf21_rx:
        print("error: could not find PrepareDownload response (RX bf21... with 5f49)", file=sys.stderr)
        return 1

    eu = find_5f49_p256_point(bf21_rx)
    if not eu:
        print("error: could not find otPK.EUICC.ECKA in BF21 response", file=sys.stderr)
        return 1
    eu_off_hex, eu_key = eu

    bf36_tx = None
    for d, data in rows:
        if d == "TX" and "bf36" in data and "5f49" in data:
            bf36_tx = data
            break

    if not bf36_tx:
        print("error: could not find LoadBoundProfilePackage command (TX bf36... with 5f49)", file=sys.stderr)
        return 1

    dp = find_5f49_p256_point(bf36_tx)
    if not dp:
        print("error: could not find otPK.DP.ECKA in BF36 command", file=sys.stderr)
        return 1
    dp_off_hex, dp_key = dp

    (args.out / "apdu_euiccsigned2.txt").write_text(bf21_rx + "\n", encoding="utf-8")
    (args.out / "apdu_boundbody.txt").write_text(bf36_tx + "\n", encoding="utf-8")
    (args.out / "otPK_EUICC_ECKA_bytes.txt").write_text(eu_key + "\n", encoding="utf-8")
    (args.out / "otPK_DP_ECKA_bytes.txt").write_text(dp_key + "\n", encoding="utf-8")

    notes = EXP6 / "notes.md"
    notes.write_text(
        f"""# Experiment 6 — capture notes

**Date:** {date.today().isoformat()}

## TLS / host

- ES9+ target during capture: `testsmdpplus1.example.com:8444` (PQ-TLS)
- On this host, lpac requires Homebrew OpenSSL in `LD_LIBRARY_PATH` for ML-KEM handshake, e.g.:
  `export LD_LIBRARY_PATH=/home/linuxbrew/.linuxbrew/opt/openssl/lib:$LPAC_BUILD:$LD_LIBRARY_PATH`

## APDU sources (from `raw/apdu_debug.txt`)

| Item | Description |
|------|-------------|
| PrepareDownload response | First RX line with `BF21` containing `euiccOtpk` (tag `5F49`) |
| Load BPP / Initialise SC | First TX line with `BF36` containing SM-DP+ `smdpOtpk` (tag `5F49`) |

## Byte offsets (within the **Data:** hex field only)

- **otPK.EUICC.ECKA** — start of uncompressed point (`04`): hex character offset **{eu_off_hex}** (byte offset {eu_off_hex // 2})
- **otPK.DP.ECKA** — start of uncompressed point (`04`): hex character offset **{dp_off_hex}** (byte offset {dp_off_hex // 2})

## Keys (130 hex chars = 65 bytes, format `04 || X || Y`)

### otPK.EUICC.ECKA
```
{eu_key}
```

### otPK.DP.ECKA
```
{dp_key}
```

## Observation

Both ephemeral ECDH public keys are visible in the PC/SC APDU hex without decryption, while ES9+ uses PQ-TLS (`X25519MLKEM768`) on the network path.
""",
        encoding="utf-8",
    )

    print("Experiment 6 extraction OK")
    print(f"  BF21 response saved -> {args.out / 'apdu_euiccsigned2.txt'}")
    print(f"  BF36 command saved   -> {args.out / 'apdu_boundbody.txt'}")
    print(f"  otPK.EUICC.ECKA      -> {args.out / 'otPK_EUICC_ECKA_bytes.txt'}  (offset bytes {eu_off_hex // 2})")
    print(f"  otPK.DP.ECKA         -> {args.out / 'otPK_DP_ECKA_bytes.txt'}   (offset bytes {dp_off_hex // 2})")
    print(f"  notes.md             -> {notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
