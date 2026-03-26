# PQC Consumer RSP Benchmarks

Benchmarking suite for the paper *"Evaluating Post-Quantum Cryptography for Consumer Remote SIM Provisioning: Benchmarks and Migration Outlook"*. Measures latency, bandwidth, and projected eUICC overhead of ML-KEM-768 and ML-DSA-44 across all 29 SGP.22 protocol steps.

---

## Repository layout

```
benchmark/          # All measurement scripts
scripts/            # Build helpers (nginx, liboqs, certs)
nginx/              # nginx config + PQ TLS cert output
pysim/              # osmo-smdpp SM-DP+ server (osmocom fork, as git subtree)
lpac/               # lpac local profile agent (as git subtree)
pqc_benchmark_data/ # Output data (gitignored; created by scripts)
plan-2.md           # Experiment completion plan
```

---

## Prerequisites

### System packages

```bash
# Ubuntu / Debian
sudo apt install -y \
  build-essential cmake git curl \
  python3 python3-venv python3-pip \
  pcscd pcsc-tools libpcsclite-dev \
  nginx
```

### OpenSSL 3.5+ with ML-DSA / ML-KEM support

The system OpenSSL on Ubuntu 22/24 (3.0.x) does **not** support ML-DSA or ML-KEM.
Install a newer build — Homebrew on Linux is the easiest path:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
brew install openssl
# Verify:
/home/linuxbrew/.linuxbrew/opt/openssl/bin/openssl version   # expect 3.5+
```

### /etc/hosts entry

```bash
echo "127.0.0.1 testsmdpplus1.example.com" | sudo tee -a /etc/hosts
```

### PC/SC reader + eUICC (Platform A)

Connect an SGP.22-compatible eUICC via a PC/SC reader (tested: HID OMNIKEY 3x21).
Confirm the reader is detected:

```bash
sudo systemctl enable --now pcscd
pcsc_scan -r
```

---

## One-time build steps

### 1. Build lpac

```bash
cd lpac
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
# Binary: lpac/build/src/lpac
```

### 2. Set up the pysim / osmo-smdpp SM-DP+ server

```bash
cd pysim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

The SM-DP+ test certificates (from SGP.26 v3) live in `pysim/smdpp-data/certs/`.
No additional cert generation is needed for the classical TLS stack.

### 3. Build PQ-capable nginx (required for port 8444 / PQ-TLS)

```bash
OPENSSL_ROOT=/home/linuxbrew/.linuxbrew/opt/openssl \
  bash scripts/build_pq_nginx.sh
# Binary: nginx/pq_build/sbin/nginx
```

### 4. Generate the ML-DSA-44 TLS certificate for nginx :8444

```bash
bash scripts/gen_pq_certs.sh
# Writes: nginx/ssl_pq/dptls.pem  nginx/ssl_pq/dptls.key
```

### 5. Create the benchmark Python venv

```bash
cd /path/to/pq-rsp-benchmarks
python3 -m venv .venv-bench
.venv-bench/bin/pip install -r benchmark/requirements.txt
```

---

## Running the full experiment

### Step 1 — Start the server stack

```bash
bash scripts/start_stack.sh
```

This starts:
- **osmo-smdpp** on `127.0.0.1:8000` (plain HTTP)
- **nginx** on `:8443` (classical TLS, ECDSA P-256) and `:8444` (PQ-TLS, ML-DSA-44)

Logs go to `nginx/runtime/logs/` and `nginx/runtime/smdpp.log`.

### Step 2 — PC/SC overhead calibration

Run once per physical setup (re-run if the eUICC or reader is reconnected):

```bash
.venv-bench/bin/python benchmark/calibrate.py
# Output: pqc_benchmark_data/calibration/
```

### Step 3 — Session benchmarks (Platform A, ~3 hours)

200 classical TLS iterations followed by 200 PQ-TLS iterations:

```bash
.venv-bench/bin/python benchmark/run_benchmark.py
# Output: pqc_benchmark_data/platform_a/sessions/iter_NNNN.json
```

Key environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `MEASURE_ITERS` | `200` | Iterations per phase |
| `MATCHING_ID` | `TS48v1_A` | Profile name on SM-DP+ |
| `SMDP_HOST` | `testsmdpplus1.example.com` | SM-DP+ hostname |
| `PQ_TLS_PHASE` | `1` | Set to `0` to skip PQ-TLS phase |
| `OQS_LPAC_LD_LIBRARY_PATH` | `` | Extra `LD_LIBRARY_PATH` for lpac PQ phase |

### Step 4 — Analyze sessions and verify stationarity

```bash
.venv-bench/bin/python benchmark/analyze.py
# Output: pqc_benchmark_data/normalization/prerequisites.json
#         pqc_benchmark_data/results/phase1_options_ab/summary.json
```

### Step 5 — TLS handshake isolation

```bash
.venv-bench/bin/python benchmark/tls_handshake_bench.py
# Output: pqc_benchmark_data/bandwidth/tls_handshake/
```

PQ handshake uses `OQS_OPENSSL` env var (defaults to system `openssl`; point to a
build with oqs-provider for genuine ML-KEM group negotiation).

### Step 6 — Host server crypto baselines

```bash
HOST_CRYPTO_ITERS=10000 .venv-bench/bin/python benchmark/host_crypto_bench.py
# Output: pqc_benchmark_data/host_smdp/host_crypto_summary.json
```

### Step 7 — Certificate / bandwidth sizes

```bash
.venv-bench/bin/python benchmark/bandwidth.py
# Output: pqc_benchmark_data/bandwidth/
```

### Step 8 — Generate plots

```bash
.venv-bench/bin/python benchmark/plot_results.py
# Output: pqc_benchmark_data/plots/*.png
```

---

## Hardware-gap normalisation (Platform B — Raspberry Pi)

Because no production eUICC supports ML-KEM or ML-DSA yet, PQC eUICC latency is
projected via a scaling factor α derived from classical operations timed on both the
real eUICC (Platform A) and a Raspberry Pi Zero 2W (Platform B, ARM Cortex-A53,
same ISA family as eUICC SecurCore).

See `plan-2.md` — Phases 2 and 3 — for the full Pi setup and normalisation procedure.

---

## Expected outputs

| File | Contents |
|---|---|
| `pqc_benchmark_data/calibration/pcsc_overhead/model.json` | PC/SC linear model (a, b, R²) |
| `pqc_benchmark_data/platform_a/sessions/iter_NNNN.json` | Per-iteration timing for all APDU / ES9+ operations |
| `pqc_benchmark_data/normalization/prerequisites.json` | Per-operation means, σ, CI, Mann–Kendall |
| `pqc_benchmark_data/host_smdp/host_crypto_summary.json` | SM-DP+ host crypto baselines |
| `pqc_benchmark_data/bandwidth/tls_handshake/*.json` | TLS handshake latency + per-message byte counts |
| `pqc_benchmark_data/plots/*.png` | All figures used in the paper |

---

## Troubleshooting

**`No PC/SC readers found`** — ensure `pcscd` is running (`sudo systemctl start pcscd`) and the reader is plugged in before running `calibrate.py` or `run_benchmark.py`.

**`lpac: error while loading shared libraries`** — set `LPAC_BUILD` to the lpac build directory so the loader finds `libeuicc.so`:
```bash
export LPAC_BUILD=/path/to/pq-rsp-benchmarks/lpac/build
```

**`ModuleNotFoundError: No module named 'numpy'`** — use `.venv-bench/bin/python`, not the system Python (which is externally managed on Ubuntu 24.04+).

**nginx fails to start on :8444** — check that `scripts/gen_pq_certs.sh` has been run and `scripts/build_pq_nginx.sh` completed. Verify with:
```bash
nginx/pq_build/sbin/nginx -V 2>&1 | grep -o 'OpenSSL [0-9.]*'
```
It must report OpenSSL 3.5 or later.

**`testsmdpplus1.example.com` not resolving** — add the `/etc/hosts` entry from the prerequisites section.
