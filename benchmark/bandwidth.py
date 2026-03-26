#!/usr/bin/env python3
"""Certificate field sizes, session capture pointers, fragmentation checks."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from config import DATA_ROOT, PYSIM_ROOT, ROOT
from utils import ensure_dir, write_json


def measure_pem_fields(path: Path) -> dict:
    data = path.read_bytes()
    cert = x509.load_pem_x509_certificate(data, default_backend())
    der = cert.public_bytes(serialization.Encoding.DER)
    pk = cert.public_key()
    pk_der = pk.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Signature is last field in TBSCertificate is complex; store totals
    return {
        "path": str(path),
        "cert_size_total": len(der),
        "subject": cert.subject.rfc4514_string(),
    }


def fragmentation_check(size: int) -> dict:
    return {
        "size_bytes": size,
        "check_ip_frag": size > 1400,
        "check_apdu_std": size > 32767,
        "check_apdu_ext": size > 65535,
    }


def main() -> int:
    out = Path(DATA_ROOT) / "bandwidth"
    ensure_dir(out / "certificates" / "classical")
    certs_dir = Path(PYSIM_ROOT) / "smdpp-data" / "certs" / "DPtls"
    sizes = []
    for name in ["CERT_S_SM_DP_TLS_NIST.pem", "CERT_S_SM_DP_TLS_BRP.pem"]:
        p = certs_dir / name
        if p.is_file():
            sizes.append(measure_pem_fields(p))
    write_json(out / "certificates" / "classical" / "sizes.json", {"certificates": sizes})

    # Placeholder session step sizes (fill from captured HTTP/APDU logs in a full run)
    session = {
        "option_a": {"note": "Populate from LPAC_HTTP_DEBUG + ES9+ JSON sizes per step"},
        "option_b": {"note": "option_a + TLS handshake delta from tls_handshake_bench"},
    }
    write_json(out / "option_a" / "summary.json", session["option_a"])

    frag = [fragmentation_check(s) for s in [512, 4096, 12000, 70000]]
    write_json(out / "fragmentation_examples.json", {"examples": frag})

    print(json.dumps({"ok": True, "out": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
