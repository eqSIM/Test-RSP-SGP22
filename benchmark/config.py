"""Paths and iteration counts for Platform A benchmarks."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LPAC_BUILD = os.environ.get("LPAC_BUILD", os.path.join(ROOT, "lpac", "build"))
LPAC_BIN = os.path.join(LPAC_BUILD, "src", "lpac")
PYSIM_ROOT = os.path.join(ROOT, "pysim")
DATA_ROOT = os.environ.get("PQC_BENCHMARK_DATA", os.path.join(ROOT, "pqc_benchmark_data"))

SMDP_HOST = os.environ.get("SMDP_HOST", "testsmdpplus1.example.com")
SMDP_PORT = int(os.environ.get("SMDP_PORT", "8443"))
SMDP_PORT_PQ = int(os.environ.get("SMDP_PORT_PQ", "8444"))
MATCHING_ID = os.environ.get("MATCHING_ID", "TS48v1_A")

SMDP_ADDR = f"{SMDP_HOST}:{SMDP_PORT}"
SMDP_ADDR_CLASSICAL = SMDP_ADDR
SMDP_ADDR_PQ = f"{SMDP_HOST}:{SMDP_PORT_PQ}"

# When true: run MEASURE_ITERS classical then MEASURE_ITERS PQ (total 2N measured iterations)
PQ_TLS_PHASE = os.environ.get("PQ_TLS_PHASE", "1").lower() in ("1", "true", "yes", "on")
PQ_WARMUP = int(os.environ.get("PQ_WARMUP", "2"))

# TLS 1.3 hybrid group (ML-KEM-768); used by tls_handshake_bench PQ client
PQ_TLS_GROUPS_DEFAULT = os.environ.get("PQ_TLS_GROUPS", "X25519MLKEM768")

# Prepend to LD_LIBRARY_PATH for lpac on PQ phase so libcurl uses OpenSSL with ML-KEM/ML-DSA
OQS_LPAC_LD_LIBRARY_PATH = os.environ.get("OQS_LPAC_LD_LIBRARY_PATH", "").strip()

PCSC_PAYLOAD_SIZES = [0, 32, 64, 128, 255]
PCSC_ITERS_PER_SIZE = 500

WARMUP_ITERS = 10
MEASURE_ITERS = int(os.environ.get("MEASURE_ITERS", "200"))
COOLDOWN_SEC = 15
COOLDOWN_EVERY = 50

HOST_CRYPTO_ITERS = int(os.environ.get("HOST_CRYPTO_ITERS", "200"))
TLS_HANDSHAKE_ITERS = 200
