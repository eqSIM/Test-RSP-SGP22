#!/usr/bin/env python3
"""Isolated host crypto timings (ECDSA, ECDH, SHA256/KDF, AES, CMAC)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.x963kdf import X963KDF
from cryptography.hazmat.backends import default_backend

from config import DATA_ROOT, HOST_CRYPTO_ITERS
from utils import ensure_dir, mean_ci95, write_json


def bench_ecdsa(iters: int) -> dict:
    priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pub = priv.public_key()
    msg = b"benchmark-message-" * 8
    sign_t = []
    verify_t = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        sig = priv.sign(msg, ec.ECDSA(hashes.SHA256()))
        t1 = time.perf_counter_ns()
        sign_t.append((t1 - t0) / 1000.0)
        t0 = time.perf_counter_ns()
        pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))
        t1 = time.perf_counter_ns()
        verify_t.append((t1 - t0) / 1000.0)
    return {
        "ecdsa_p256_sign_us": _stats(sign_t),
        "ecdsa_p256_verify_us": _stats(verify_t),
    }


def _stats(xs: list[float]) -> dict:
    mu, sigma, half = mean_ci95(xs)
    return {"mean_us": mu, "sigma_us": sigma, "ci95_half_us": half, "n": len(xs)}


def bench_ecdh(iters: int) -> dict:
    peer = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pub = peer.public_key()
    kg_t = []
    dh_t = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        ephem = ec.generate_private_key(ec.SECP256R1(), default_backend())
        t1 = time.perf_counter_ns()
        kg_t.append((t1 - t0) / 1000.0)
        t0 = time.perf_counter_ns()
        _ = ephem.exchange(ec.ECDH(), pub)
        t1 = time.perf_counter_ns()
        dh_t.append((t1 - t0) / 1000.0)
    return {"ecdh_keygen_us": _stats(kg_t), "ecdh_exchange_us": _stats(dh_t)}


def bench_sha_kdf_aes_cmac(iters: int) -> dict:
    key = os.urandom(16)
    iv = os.urandom(16)
    pt = os.urandom(4096)
    sha_t = []
    kdf_t = []
    aes_t = []
    cmac_t = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        h = hashlib.sha256(pt).digest()
        t1 = time.perf_counter_ns()
        sha_t.append((t1 - t0) / 1000.0)

        t0 = time.perf_counter_ns()
        xkdf = X963KDF(algorithm=hashes.SHA256(), length=32, sharedinfo=b"info")
        _ = xkdf.derive(key + h[:8])
        t1 = time.perf_counter_ns()
        kdf_t.append((t1 - t0) / 1000.0)

        t0 = time.perf_counter_ns()
        c = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        enc = c.encryptor()
        _ = enc.update(pt) + enc.finalize()
        t1 = time.perf_counter_ns()
        aes_t.append((t1 - t0) / 1000.0)

        from cryptography.hazmat.primitives.cmac import CMAC

        t0 = time.perf_counter_ns()
        cm = CMAC(algorithms.AES(key), backend=default_backend())
        cm.update(pt[:256])
        _ = cm.finalize()
        t1 = time.perf_counter_ns()
        cmac_t.append((t1 - t0) / 1000.0)

    return {
        "sha256_4kB_us": _stats(sha_t),
        "x963kdf_us": _stats(kdf_t),
        "aes128_cbc_encrypt_4k_us": _stats(aes_t),
        "aes128_cmac_256B_us": _stats(cmac_t),
    }


def main() -> int:
    iters = HOST_CRYPTO_ITERS
    out = Path(DATA_ROOT) / "host_smdp"
    ensure_dir(out)
    res = {}
    res.update(bench_ecdsa(iters))
    res.update(bench_ecdh(iters))
    res.update(bench_sha_kdf_aes_cmac(iters))
    write_json(out / "host_crypto_summary.json", res)
    print(json.dumps({"ok": True, "out": str(out / "host_crypto_summary.json")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
