# Experiment Completion Plan

## Phase 1 — Complete Platform A Data (Ubuntu + eUICC, before Pi arrives)

### 1.1 Finish session iterations
- Run `run_benchmark.py` to full 200 classical + 200 PQ-TLS iterations (currently n=9 classical only)
- Total expected runtime: ~200 × 25s × 2 modes ≈ 2.8 hours plus cooldowns
- Verify `returncode == 0` on all iterations; discard any failures from latency stats

### 1.2 Verify stationarity
- Run `analyze.py` → check Mann-Kendall p-values in `normalization/prerequisites.json`
- Confirm PrepareDownload (BF21) variance stabilises at n=200 (currently CV ~12% at n=9)
- Confirm LoadBPP segments (BF36) become usable (currently CV 30–70%)

### 1.3 PC/SC calibration consistency
- Verify `calibration/pcsc_overhead/model.json` was generated in the same physical session
- If eUICC was re-seated or reader reconnected, re-run `calibrate.py`
- Current model: a=1160 µs, b=62.4 µs/byte, R²=0.999 — looks good

### 1.4 TLS handshake isolation
- Run `tls_handshake_bench.py` (200 iterations classical port 8443, 200 PQ-TLS port 8444)
- Produces bandwidth/tls_handshake/{classical_nginx,pqtls_nginx}_summary.json
- Captures per-message byte breakdowns (Certificate, CertificateVerify, etc.)

### 1.5 Host server crypto baselines
- Run `host_crypto_bench.py` with `HOST_CRYPTO_ITERS=10000` for high-fidelity SM-DP+ timings
- These are server-side reference numbers only — NOT inputs to normalisation

### 1.6 Bandwidth / certificate sizes
- Run `bandwidth.py` to capture per-certificate DER sizes for classical chain
- Manually populate PQ certificate sizes once available from osmo-smdpp ML-DSA certs

### Phase 1 execution notes (completed on Ubuntu)
- Use project venv for bench tools: `python3 -m venv .venv-bench && .venv-bench/bin/pip install -r benchmark/requirements.txt`, then `.venv-bench/bin/python benchmark/….py` (system Python is PEP 668 externally managed).
- Sessions were already complete: **400** files (200 classical, 200 `pq_tls`), all `returncode` 0.
- PC/SC `model.json` mtime precedes `iter_0001.json` by ~10 min (same campaign); no recalibration.
- **BF21 PrepareDownload** over all 400: mean ≈ 4.09 s, σ ≈ 0.62 s (CV ≈ 0.15); Mann–Kendall pooled *p* ≈ 0.031 (weak upward trend — interpret cautiously).
- Per TLS mode (n=200 each): BF21 Mann–Kendall *p* ≈ 0.12 (classical) and ≈ 0.58 (PQ-TLS).
- Plots refreshed via `plot_results.py`.

---

## Phase 2 — Platform B Setup (Raspberry Pi Zero 2W)

### 2.1 OS and toolchain
- Flash Raspberry Pi OS Lite 64-bit (aarch64)
- Install build-essential, cmake, python3, pip
- Lock CPU frequency: `sudo cpufreq-set -g performance -f 1000000` (1 GHz fixed)
- Verify: `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq` should report 1000000

### 2.2 Build liboqs for aarch64
- Clone liboqs, build with cmake (Release mode, no OpenSSL provider — standalone)
- Verify ML-KEM-768 and ML-DSA-44 are enabled: `./tests/speed_kem` and `./tests/speed_sig`

### 2.3 Build OpenSSL + python cryptography
- System OpenSSL or build from source — needed for ECDSA P-256, ECDH, AES, SHA baselines
- pip install cryptography (for `host_crypto_bench.py` compatibility)

### 2.4 Write `platform_b_crypto_bench.py`
New script (does not exist yet) that measures isolated crypto primitives:

**Classical (via python cryptography — same as host_crypto_bench.py):**
- ECDSA P-256 sign
- ECDSA P-256 verify
- ECDH P-256 keygen
- ECDH P-256 exchange
- AES-128-CBC encrypt 4kB
- AES-128-CMAC 256B
- SHA-256 4kB
- X9.63 KDF

**PQC (via liboqs Python bindings or ctypes):**
- ML-KEM-768 keygen
- ML-KEM-768 encaps
- ML-KEM-768 decaps
- ML-DSA-44 keygen
- ML-DSA-44 sign
- ML-DSA-44 verify

**Protocol:**
- 100 warm-up iterations (discarded)
- 10,000 measured iterations per operation
- Record mean, σ, 95% CI
- Output to `pqc_benchmark_data/platform_b/crypto_summary.json`

### 2.5 ARM PMU cycle counts (cross-check)
- Enable perf counters: `sudo sh -c 'echo 1 > /proc/sys/kernel/perf_event_paranoid'`
- Wrap each operation with `perf_event_open` PERF_COUNT_HW_CPU_CYCLES or use `perf stat`
- Record raw cycle counts alongside wall-clock µs
- These normalise to 80–200 MHz eUICC clock range as an independent validation

---

## Phase 3 — Hardware-Gap Normalisation

### 3.1 Compute per-operation α
For each classical operation i that exists on both platforms:

    α_i = T_sysmocom(op_i) / T_Pi(op_i)

Where:
- T_sysmocom = Platform A APDU mean from Phase 1 (PC/SC-corrected)
- T_Pi = Platform B isolated crypto mean from Phase 2

Relevant pairings:
- AuthenticateServer (BF38) → maps to ECDSA verify + ECDH exchange
- PrepareDownload (BF21) → maps to ECDSA sign + ECDH keygen + AES/SHA
- LoadBPP segments → maps to AES-CBC decrypt + CMAC verify
- GetEuiccChallenge → maps to RNG (baseline)

### 3.2 Apply CV decision rule
Compute CV = σ(α_i) / μ(α_i) at three levels:

| Condition | Action |
|-----------|--------|
| CV_global ≤ 0.10 | Use single pooled ᾱ for everything |
| CV_global > 0.10, per-category CV ≤ 0.10 | Use ᾱ_asym for PQC ops, ᾱ_sym for symmetric |
| Per-category CV > 0.10 | Per-operation α_i; PQC ops without classical analogue use ᾱ_asym ± CV |
| CV_global > 0.25, no convergence | Report Platform B native timings only; normalization unreliable |

### 3.3 Project PQC eUICC latency
    T̂_eUICC(PQC_op) = ᾱ_asym × T_Pi(PQC_op)

With uncertainty:
    σ²_T̂ = T_Pi² · σ²_α + α² · σ²_T_Pi

Report with 95% CI. Cross-check against PMU cycle counts scaled to 80–200 MHz.

---

## Phase 4 — Analysis and Paper Results

### 4.1 Generate all plots
- Run `plot_results.py` after all data is in place
- Verify: session_wall_time, operation_means (all/classical/pq_tls), pcsc_calibration,
  host_crypto, tls_handshake, timeseries_key_ops

### 4.2 Populate paper tables
- Table 2 (session wall time): from 200+200 iteration means
- Table 3 (ES9+ HTTP latency): from session bench data, ES9P tags
- Table 4 (option b overhead): TLS handshake + session + certificate sizes
- Add normalisation results table: α values, CV, projected PQC eUICC latencies

### 4.3 Options (c) and (d) projections
- Option (c): replace ECDSA sign/verify with ML-DSA-44 in AuthenticateServer/PrepareDownload
  → projected via ᾱ_asym × T_Pi(ML-DSA sign/verify)
- Option (d): additionally replace ECDH with ML-KEM-768 in PrepareDownload
  → add ᾱ_asym × T_Pi(ML-KEM encaps/decaps)
- Compute projected session wall times for options (c) and (d)

### 4.4 Memory analysis
- Run valgrind massif on Pi for ML-DSA-44 sign and ML-KEM-768 decaps
- Compare peak heap to eUICC RAM budget (9,539 B volatile from chip info)

---

## Checklist Summary

- [x] Phase 1.1: 200+200 Platform A sessions
- [x] Phase 1.2: Stationarity check (`analyze.py` → `normalization/prerequisites.json`)
- [x] Phase 1.3: PC/SC model verification (model dated ~10 min before first session; no re-run)
- [x] Phase 1.4: TLS handshake bench
- [x] Phase 1.5: Host crypto bench (10k iters)
- [x] Phase 1.6: Bandwidth/certificate sizes
- [ ] Phase 2.1: Pi OS + frequency lock
- [ ] Phase 2.2: liboqs aarch64 build
- [ ] Phase 2.3: OpenSSL + cryptography on Pi
- [ ] Phase 2.4: platform_b_crypto_bench.py written and run
- [ ] Phase 2.5: PMU cycle counts collected
- [ ] Phase 3.1: α_i values computed
- [ ] Phase 3.2: CV decision rule applied
- [ ] Phase 3.3: PQC latencies projected with uncertainty
- [ ] Phase 4.1: All plots regenerated
- [ ] Phase 4.2: Paper tables populated
- [ ] Phase 4.3: Options (c)/(d) projected
- [ ] Phase 4.4: Memory analysis complete
