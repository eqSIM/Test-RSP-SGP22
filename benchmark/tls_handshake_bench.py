#!/usr/bin/env python3
"""Measure TLS handshake latency and message sizes via openssl s_client (classical :8443, PQ :8444)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from config import DATA_ROOT, PQ_TLS_GROUPS_DEFAULT, SMDP_HOST, SMDP_PORT, SMDP_PORT_PQ, TLS_HANDSHAKE_ITERS
from utils import ensure_dir, mean_ci95, write_json

_MSG_RE = re.compile(r"(>>>|<<<) TLS \S+, Handshake \[length ([0-9a-f]+)\](?:, (.+))?")

_MSG_ORDER = ["ClientHello", "ServerHello", "Certificate", "CertificateVerify", "Finished"]


def parse_handshake_sizes(stderr: str) -> dict[str, int]:
    """Return per-message-type byte counts from openssl s_client -msg stderr."""
    sizes: dict[str, int] = {}
    for line in stderr.splitlines():
        m = _MSG_RE.match(line.strip())
        if not m:
            continue
        _, hex_len, msg_type = m.groups()
        msg_type = (msg_type or "Other").strip()
        sizes[msg_type] = sizes.get(msg_type, 0) + int(hex_len, 16)
    return sizes


def handshake_once(
    host: str,
    port: int,
    openssl_bin: str = "openssl",
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[float, dict[str, int]]:
    """Return (elapsed_ms, per_message_sizes)."""
    cmd = [openssl_bin, "s_client", "-connect", f"{host}:{port}", "-tls1_3", "-brief", "-msg"]
    if extra_args:
        cmd.extend(extra_args)
    t0 = time.perf_counter()
    r = subprocess.run(cmd, input=b"", capture_output=True, timeout=30, env=env)
    dt = (time.perf_counter() - t0) * 1000.0
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode()[:500])
    return dt, parse_handshake_sizes(r.stdout.decode())


def main() -> int:
    iters = TLS_HANDSHAKE_ITERS
    out = Path(DATA_ROOT) / "bandwidth" / "tls_handshake"
    ensure_dir(out)

    classical_times: list[float] = []
    classical_sizes: dict[str, list[int]] = {}
    for i in range(iters):
        try:
            ms, sizes = handshake_once(SMDP_HOST, SMDP_PORT)
            classical_times.append(ms)
            for k, v in sizes.items():
                classical_sizes.setdefault(k, []).append(v)
        except Exception as e:
            print(f"iter {i} classical failed: {e}", file=sys.stderr)
            break

    pq_times: list[float] = []
    pq_sizes: dict[str, list[int]] = {}
    pq_port = int(os.environ.get("PQ_TLS_PORT", str(SMDP_PORT_PQ)))
    oqs_openssl = os.environ.get("OQS_OPENSSL", "openssl")
    pq_groups = os.environ.get("PQ_TLS_GROUPS", PQ_TLS_GROUPS_DEFAULT)
    oqs_ld = os.environ.get("OQS_LPAC_LD_LIBRARY_PATH", "").strip()
    pq_env = os.environ.copy()
    if oqs_ld:
        pq_env["LD_LIBRARY_PATH"] = oqs_ld + os.pathsep + pq_env.get("LD_LIBRARY_PATH", "")

    for i in range(iters):
        try:
            extra = ["-groups", pq_groups] if pq_groups else None
            ms, sizes = handshake_once(SMDP_HOST, pq_port, openssl_bin=oqs_openssl, extra_args=extra, env=pq_env)
            pq_times.append(ms)
            for k, v in sizes.items():
                pq_sizes.setdefault(k, []).append(v)
        except Exception:
            pass

    def summarise_sizes(acc: dict[str, list[int]]) -> dict[str, float]:
        return {k: round(sum(vs) / len(vs)) for k, vs in acc.items() if vs}

    def save(name: str, times: list[float], sizes: dict[str, list[int]]) -> None:
        if not times:
            return
        mu, sig, ha = mean_ci95(times)
        write_json(
            out / f"{name}_summary.json",
            {
                "mean_ms": mu,
                "sigma_ms": sig,
                "ci95_half_ms": ha,
                "n": len(times),
                "msg_sizes_bytes": summarise_sizes(sizes),
            },
        )

    save("classical_nginx", classical_times, classical_sizes)
    save("pqtls_nginx", pq_times, pq_sizes)

    write_json(
        out / "summary.json",
        {
            "classical_ms": classical_times[:5] if classical_times else [],
            "pq_tls_available": len(pq_times) > 0,
            "pq_groups": pq_groups,
            "note": "PQ: OQS_OPENSSL + nginx on PQ_TLS_PORT; ML-KEM hybrid via PQ_TLS_GROUPS (default X25519MLKEM768).",
        },
    )
    print(json.dumps({"ok": True, "out": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
