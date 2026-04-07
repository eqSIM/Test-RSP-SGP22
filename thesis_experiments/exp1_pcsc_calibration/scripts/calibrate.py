#!/usr/bin/env python3
"""Extended PC/SC STORE DATA round-trip calibration (Experiment 1)."""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from smartcard.CardConnection import CardConnection
from smartcard.System import readers


def _protocol_name(bits: int) -> str:
    names = []
    if bits & CardConnection.T0_protocol:
        names.append("T=0")
    if bits & CardConnection.T1_protocol:
        names.append("T=1")
    return "+".join(names) if names else str(bits)

SIZES = [0, 32, 64, 128, 255, 512, 1024, 1536, 2048, 2515]
ISD_R_AID = [
    0xA0,
    0x00,
    0x00,
    0x05,
    0x59,
    0x10,
    0x10,
    0xFF,
    0xFF,
    0xFF,
    0xFF,
    0x89,
    0x00,
    0x00,
    0x01,
    0x00,
]
ITERS_PER_SIZE = 500
PAUSE_SEC = 1.0


def exp1_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_apdu(nbytes: int) -> list[int]:
    """STORE DATA (ES10-style) with payload of zeros; short or extended Lc."""
    if nbytes < 0:
        raise ValueError("nbytes must be >= 0")
    data = [0x00] * nbytes
    if nbytes <= 255:
        return [0x80, 0xE2, 0x11, 0x00, nbytes] + data
    # ISO 7816-4 extended Lc: 00 Lc1 Lc2
    return [0x80, 0xE2, 0x11, 0x00, 0x00, (nbytes >> 8) & 0xFF, nbytes & 0xFF] + data


def _transmit_time_us(conn, apdu: list[int]) -> tuple[float, int, int]:
    t0 = time.perf_counter_ns()
    _data, sw1, sw2 = conn.transmit(apdu)
    t1 = time.perf_counter_ns()
    rtt_us = (t1 - t0) / 1000.0
    return rtt_us, sw1, sw2


def connect_prefer_t1(conn) -> None:
    """Use T=1 when available — extended Lc>255 APDUs are not valid on T=0."""
    conn.connect()
    supported = conn.getProtocol()
    conn.disconnect()
    if supported & CardConnection.T1_protocol:
        conn.connect(CardConnection.T1_protocol)
    elif supported & CardConnection.T0_protocol:
        conn.connect(CardConnection.T0_protocol)
    else:
        conn.connect()


def select_isdr(conn) -> None:
    sel = [0x00, 0xA4, 0x04, 0x00, len(ISD_R_AID)] + ISD_R_AID
    conn.transmit(sel)


def run_test_only(raw_dir: Path) -> int:
    """Send one 512-byte extended STORE DATA; print SW and RTT."""
    rs = readers()
    if not rs:
        print("No PC/SC readers found", file=sys.stderr)
        return 1
    conn = rs[0].createConnection()
    connect_prefer_t1(conn)
    active = conn.getProtocol()
    print(
        f"Active protocol: {_protocol_name(active)} (extended APDUs need T=1 or reader support)",
        flush=True,
    )
    select_isdr(conn)
    apdu = build_apdu(512)
    try:
        rtt_us, sw1, sw2 = _transmit_time_us(conn, apdu)
        print(f"test-only: 512-byte STORE DATA  SW={sw1:02X}{sw2:02X}  rtt_us={rtt_us:.1f}")
    except Exception as ex:
        marker = raw_dir / "rejected_at_512.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"512-byte extended STORE DATA failed\n{ex!s}\n", encoding="utf-8")
        print(f"test-only failed: {ex}", file=sys.stderr)
        print(f"(wrote {marker})", file=sys.stderr)
        conn.disconnect()
        return 1
    conn.disconnect()
    return 0 if (sw1, sw2) not in ((0x67, 0x00), (0x6D, 0x00)) else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="PC/SC extended STORE DATA RTT calibration")
    ap.add_argument(
        "--test-only",
        action="store_true",
        help="Send a single 512-byte extended APDU and exit",
    )
    args = ap.parse_args()

    root = exp1_root()
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.test_only:
        return run_test_only(raw_dir)

    rs = readers()
    if not rs:
        print("No PC/SC readers found", file=sys.stderr)
        return 1

    conn = rs[0].createConnection()
    connect_prefer_t1(conn)
    select_isdr(conn)

    size_idx = 0
    for nbytes in SIZES:
        size_idx += 1
        out_csv = raw_dir / f"size_{nbytes}_bytes.csv"
        apdu = build_apdu(nbytes)
        extended = nbytes > 255

        with out_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rtt_us"])

            for i in range(1, ITERS_PER_SIZE + 1):
                try:
                    rtt_us, sw1, sw2 = _transmit_time_us(conn, apdu)
                    if extended and i == 1 and (sw1, sw2) in ((0x67, 0x00), (0x6D, 0x00)):
                        marker = raw_dir / f"rejected_at_{nbytes}.txt"
                        marker.write_text(
                            f"extended STORE DATA rejected at first attempt\n"
                            f"SW={sw1:02X}{sw2:02X}\n",
                            encoding="utf-8",
                        )
                        print(
                            f"[size {size_idx}/{len(SIZES)}] payload={nbytes} bytes  "
                            f"REJECTED SW={sw1:02X}{sw2:02X}  wrote {marker.name}",
                            file=sys.stderr,
                        )
                        break
                    w.writerow([f"{rtt_us:.6f}"])
                    if i == ITERS_PER_SIZE or i % 50 == 0:
                        print(
                            f"[size {size_idx}/{len(SIZES)}] payload={nbytes} bytes  "
                            f"iter={i}/{ITERS_PER_SIZE}  last_us={rtt_us:.1f}")
                except Exception as ex:
                    print(
                        f"[size {size_idx}/{len(SIZES)}] payload={nbytes}  iter={i}  ERROR: {ex}",
                        file=sys.stderr,
                    )
                    if extended and i == 1:
                        marker = raw_dir / f"rejected_at_{nbytes}.txt"
                        marker.write_text(
                            f"extended STORE DATA failed on first attempt\n{ex!s}\n",
                            encoding="utf-8",
                        )
                        print(
                            f"[size {size_idx}/{len(SIZES)}] wrote {marker.name}; skipping size",
                            file=sys.stderr,
                        )
                        break

        if size_idx < len(SIZES):
            time.sleep(PAUSE_SEC)

    conn.disconnect()
    print("Calibration complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
