## Experimental Plan: Phase 1 (Platform A + Host) with Phase 2 Normalization Prerequisites

---

## Overview

Options (a) and (b) are **identical at every application-layer step**. The only difference is step 5 — TLS 1.3 versus PQ-TLS on the ES9+ transport. The sysmocom eUICC produces ground-truth classical timings on real secure-element silicon. That is the strongest data in the paper.

What Phase 1 cannot produce is α or projected PQC timings. Every number collected now **is** the T\_sysmocom(op) left-hand side of the α equation. Stored correctly, the normalization pass reduces to a single arithmetic run once Platform B arrives.

The plan splits into two clearly bounded phases:

```
Phase 1 (now)      — Platform A + Measurement Host
                   — Full options (a) and (b) results
                   — All normalization prerequisite data stored

Phase 2 (Pi arrives) — Platform B added
                     — Classical cross-platform runs to compute α
                     — PQC latency runs (liboqs/OQS-OpenSSL)
                     — Options (c) and (d) latency results
                     — Memory profiling (valgrind massif)
                     — ARM PMU cross-check
                     — Combined end-to-end session analysis
```

---

## Phase 1 Architecture (Current State)

```
┌──────────────────────────────────────────────────────────┐
│                  Measurement Host (PC)                   │
│                                                          │
│  ┌───────────────┐      ┌───────────────────────────┐    │
│  │  SM-DP+       │      │   Orchestration Layer     │    │
│  │  server       │      │   - Experiment runner     │    │
│  │  OpenSSL      │      │   - Result collector      │    │
│  │  (classical)  │      │   - Prerequisite store    │    │
│  └──────┬────────┘      └───────────────────────────┘    │
│         │ ES9+ (loopback)                                 │
└─────────┼────────────────────────────────────────────────┘
          │
    ┌─────┴────────────────┐
    │    LPA (lpac)         │
    │    Relay only         │
    └──────┬───────────────┘
           │ PC/SC (USB)
           ▼
  ┌─────────────────────┐
  │   Platform A        │         ┌────────────────────────────────┐
  │   sysmocom eUICC    │         │   Platform B (Phase 2)         │
  │   Classical only    │         │   Raspberry Pi Zero 2W         │
  │   ECDSA + ECDH      │         │   ARM Cortex-A53 @ 1 GHz       │
  │   ← ACTIVE NOW      │         │   512 MB RAM, RPi OS Lite      │
  └─────────────────────┘         │   aarch64 liboqs               │
                                  │   ← NOT YET / PLACEHOLDER      │
                                  └────────────────────────────────┘
```

**Platform B rationale:** ARMv8-A (Cortex-A53) is architecturally comparable to the SecurCore-family cores in production eUICC silicon, making cycle-count comparison meaningful. CPU frequency is locked at 1 GHz for all Platform B runs to eliminate DVFS noise.

---

## Section 1 — Environment Calibration (Do Once, Store Permanently)

These are one-time characterization runs whose results become fixed constants referenced throughout all future experiment phases. Label them clearly as calibration artifacts in your data store.

### 1.1 PC/SC Null-APDU Overhead

Send a null APDU — a GET RESPONSE command with an empty payload — to the sysmocom eUICC 10,000 times following the full warm-up protocol. The mean round-trip time is your PC/SC stack overhead constant `Δ_pcsc`.

Every eUICC-side timing you measure at the PC/SC boundary will be corrected as:

```
T_corrected(op) = T_measured(op) - Δ_pcsc
```

Store `Δ_pcsc` with its σ and 95% CI. This constant is reused in Phase 2 unchanged because the PC/SC stack and USB hardware do not change.

### 1.2 Measurement Host Baseline

On the measurement host, record:

- CPU model, core count, base and boost clock
- OS and kernel version
- OpenSSL version and build flags (note if AES-NI, AVX2 are active)
- osmo-smdpp commit hash
- liboqs version if already installed for future use

Run a 60-second idle CPU cycle count capture to establish a host noise floor. This tells you the minimum timing resolution you can trust for SM-DP+-side measurements.

### 1.3 Platform A Hardware Fingerprint

Record the following and store permanently — these become the Platform A reference descriptor that Phase 2 normalization is anchored to:

- sysmocom eUICC firmware version and model identifier
- PC/SC reader model and driver version
- USB host controller type
- Confirmed supported algorithms from ATR parsing
- Confirmed APDU extended length support (yes/no)

---

## Section 2 — Classical Baseline: Platform A (Core Measurements)

This is the primary deliverable of Phase 1. Every operation listed here produces T\_sysmocom(op), which is simultaneously a publishable result for options (a) and (b) and the left-hand side of the α equation for Phase 2.

### 2.1 Measurement Protocol Per Operation

Apply this sequence to every operation without exception:

```
Step 0  — Record timestamp, CPU temp, platform state
          [Platform B only: verify CPU frequency locked at 1 GHz]
Step 1  — 100-iteration warm-up (results discarded)
Step 2  — 10,000-iteration measurement window
          Record each iteration individually (not just aggregates)
Step 3  — 30-second cool-down idle
Step 4  — Record end timestamp, CPU temp
Step 5  — Verify temperature returned within 2°C of baseline
          If not, extend cool-down and re-check before next op
```

For each 10,000-iteration window compute and store:

| Statistic | Symbol | Purpose |
|---|---|---|
| Mean | μ | Primary reported metric |
| Median | M | Outlier robustness check |
| Standard deviation | σ | Spread; inputs α uncertainty |
| 95% confidence interval | CI₉₅ | Reportable precision bound |
| 99th percentile | P99 | Provisioning SLA tail latency |
| Outlier count | n_out | Quality indicator |
| Outlier threshold | 3σ | Document exclusion criterion |

Store the raw per-iteration array, not just these aggregates. You will need the raw array when you compute α later — if you only stored aggregates, you cannot propagate uncertainty correctly.

### 2.2 eUICC-Side Operations (Platform A)

**Important constraint:** The sysmocom eUICC processes compound ES10 commands (e.g., `AuthenticateServer`, `AuthenticateClient`, `PrepareDownload`, `LoadBoundProfilePackage`) that bundle multiple cryptographic primitives internally. It is not possible to time individual ECDSA/ECDH primitives in isolation on the eUICC via PC/SC. The practical approach is to time the ES10 command round-trips and document which cryptographic operations each command encompasses (per Table~5 in the paper). These round-trip times are corrected by Δ_pcsc and reported per-command. Per-primitive decomposition uses the normalization factor α from Phase 2.

Run each ES10 command in isolation (not as part of a live session), fix all inputs to representative protocol values, and use the standard 100 + 10,000 iteration protocol.

| Operation | SGP.22 steps | Key material | Notes |
|---|---|---|---|
| ECDSA-P256 Sign | 13b, 21c, 27f | SK.EUICC.ECDSA | Run for each step separately — signing input differs |
| ECDSA-P256 Verify | 12c, 16d (mirror), 20b, 24a, 27a | PK.DPauth / PK.DPpb / PK.EUICC | Vary the input message size to match protocol reality |
| ECDH-P256 KeyGen | 21a | fresh ephemeral | Generate new keypair per iteration |
| ECDH-P256 Scalar Multiply | 27b | otSK.EUICC × otPK.DP | Use representative public key |
| SHA-256 (KDF input) | 24d, 27c | n/a | Fix input length to match X9.63 KDF context |
| AES-128 Decrypt | 27e | fixed test key | Fix BPP payload to 64 KB representative profile |
| AES-128-CMAC Verify | 27d | fixed test key | Match bind_body size per option |

For signing operations (13b, 21c, 27f), the input message differs slightly per step. Time each step's signing input separately — do not assume ECDSA-P256 Sign latency is constant across different message lengths, because the eUICC may hash the message internally and the hash length matters.

### 2.3 SM-DP+-Side Operations (Measurement Host)

These run on the measurement host in software. They do not involve Platform A and can run in parallel with Platform A sessions on different days.

| Operation | SGP.22 steps | Options |
|---|---|---|
| ECDSA-P256 Sign | 8e, 17c, 24h | (a, b) |
| ECDSA-P256 Verify | 16d, 24a | (a, b) |
| ECDH-P256 KeyGen + Scalar Multiply | 24b–24c | (a, b, c) |
| SHA-256 / X9.63 KDF | 24d | all |
| AES-128 Encrypt | 24e | all |
| AES-128-CMAC Compute | 24g | all |

Apply the same 100-iteration warm-up, 10,000-iteration measurement, and full statistical treatment. Note explicitly in your data files that these are host-side software timings, not eUICC hardware timings.

---

## Section 3 — Bandwidth Measurement (Fully Completable Now)

Bandwidth measurement requires no Platform B and no PQC operations. It is a static structural analysis that you can complete in full for all four options using computed byte counts.

### 3.1 Certificate Generation and Sizing

Generate real DER-encoded X.509 certificates for every certificate type in the SGP.22 CI hierarchy. Use OpenSSL for ECDSA certificates now. When Platform B arrives, repeat for ML-DSA certificates using OQS-OpenSSL.

For each certificate type, measure and record:

```
cert_size_total     — total DER-encoded bytes
cert_size_tbsCert   — TBSCertificate field only
cert_size_pubkey    — SubjectPublicKeyInfo field
cert_size_signature — SignatureValue field
cert_size_overhead  — total minus pubkey minus signature
                      (covers subject, issuer, extensions, OIDs)
```

The overhead field is critical. Raw primitive sizes from Table 2 significantly underestimate real certificate sizes because ASN.1 DER encoding, X.509 extension fields, GSMA-specific OID inclusions, and validity periods all add bytes. Your analysis must use real certificate sizes, not derived estimates.

Certificate types to generate and measure:

| Certificate | Key type | Signed by |
|---|---|---|
| CI Root | ECDSA-P384 | Self-signed |
| CI Sub-CA | ECDSA-P384 | CI Root |
| CERT.DPauth | ECDSA-P256 | CI Sub-CA |
| CERT.DPpb | ECDSA-P256 | CI Sub-CA |
| CERT.EUICC | ECDSA-P256 | EUM |
| CERT.EUM | ECDSA-P256 | CI Sub-CA |

Store the DER-encoded bytes of each certificate as binary files. When Phase 2 arrives, you replace these with ML-DSA equivalents and rerun the analysis — the session-level calculation is the same arithmetic.

### 3.2 Session-Level Message Sizing

For options (a) and (b), trace every message transmitted and record its byte count. Structure your records as:

```
session_bandwidth/
  option_a/
    step_07_LPA_to_SMDP.bytes
    step_09_SMDP_to_LPA.bytes
    step_11_LPA_to_eUICC.bytes
    step_14_eUICC_to_LPA.bytes
    step_15_LPA_to_SMDP.bytes
    step_18_SMDP_to_LPA.bytes
    step_19_LPA_to_eUICC.bytes
    step_22_eUICC_to_LPA.bytes
    step_23_LPA_to_SMDP.bytes
    step_25_SMDP_to_LPA.bytes
    step_26_LPA_to_eUICC.bytes
    step_28_eUICC_to_LPA.bytes
    step_29_LPA_to_SMDP.bytes
    summary.json
  option_b/
    [identical structure — transport overhead added at step_05]
```

For option (b), the ES9+ transport carries PQ-TLS handshake overhead that option (a) does not. Measure the TLS 1.3 handshake size for option (a) and the PQ-TLS handshake size for option (b) separately and record both. This is the one bandwidth difference between the two options.

Fix BPP profile payload to 64 KB for all runs. Document this constant.

### 3.3 Fragmentation Analysis (Completable Now for Options a and b)

For every message that crosses the ES9+ and PC/SC boundaries, check against three thresholds and record the verdict:

```
For each message M in each option:
  check_1: M.size > 1400 B  → ES9+ IP fragmentation likely
  check_2: M.size > 32767 B → PC/SC standard APDU limit exceeded
  check_3: M.size > 65535 B → PC/SC extended APDU limit exceeded

Record: { message_id, size_bytes, check_1, check_2, check_3 }
```

Options (a) and (b) are unlikely to trigger these thresholds — ECDSA certificates are small. Record the verdicts anyway so the Phase 2 comparison against options (c) and (d) is directly parallel.

---

## Section 4 — Hardware-Gap Normalization Methodology and Prerequisite Data Store

### 4.0 Normalization Framework

Classical operations are timed on both platforms. The per-operation scaling factor is:

```
α_i = T_sysmocom(op_i) / T_Pi(op_i)
```

PQC latency on the eUICC is projected as:

```
T̂_eUICC(PQC) = ᾱ × T_Pi(PQC)
```

**CV decision rules (fixed before data collection):**

The validity of a pooled ᾱ is assessed via the coefficient of variation CV = σ(α_i)/μ(α_i), evaluated globally and per category (asymmetric: ECDSA, ECDH; symmetric: AES, SHA):

| CV condition | Strategy |
|---|---|
| CV_global ≤ 0.10 | Single pooled ᾱ; projection error ≲10% |
| CV_global > 0.10 and per-category CV ≤ 0.10 | Separate ᾱ_asym and ᾱ_sym; PQC sign/KEM ops use ᾱ_asym |
| Per-category CV > 0.10 | Per-operation α_i; PQC ops with no classical analogue use ᾱ_asym with ±CV systematic uncertainty |
| CV_global > 0.25 and no category convergence | Report Platform B native timings only; linear normalization deemed unreliable |

**Uncertainty propagation:**

```
σ²_{T̂} = T_Pi² · σ²_α + α² · σ²_{T_Pi}
```

Report all projected timings with 95% CIs derived from this formula.

**ARM PMU cross-check (Phase 2):**

ARM performance counter cycle counts on Platform B are normalised to the 80–200 MHz eUICC clock range as an independent cross-check on the α-based projections. Where PMU-projected timings agree with α-projected timings within the reported CI, normalisation is validated.

---

This section also defines exactly what you must collect and how you must store it so that when the Pi Zero 2W arrives, the normalization computation is a clean, deterministic process rather than a scramble to reconstruct missing values.

### 4.1 Directory Structure

Create this directory structure now and populate it as you run Phase 1:

```
pqc_benchmark_data/
│
├── calibration/
│   ├── pcsc_null_apdu/
│   │   ├── raw_iterations.csv      ← all 10,000 rows
│   │   └── summary.json            ← Δ_pcsc, σ, CI₉₅
│   ├── host_baseline.json          ← CPU, OS, OpenSSL, commit hashes
│   └── platform_a_fingerprint.json ← eUICC firmware, reader model
│
├── platform_a/                     ← T_sysmocom(op) for all ops
│   ├── ecdsa_p256_sign/
│   │   ├── step_13b_raw.csv        ← raw per-iteration timing
│   │   ├── step_21c_raw.csv
│   │   ├── step_27f_raw.csv
│   │   └── summary.json            ← μ, M, σ, CI₉₅, P99, n_out
│   ├── ecdsa_p256_verify/
│   │   ├── step_12c_raw.csv
│   │   ├── step_20b_raw.csv
│   │   ├── step_24a_raw.csv
│   │   ├── step_27a_raw.csv
│   │   └── summary.json
│   ├── ecdh_p256_keygen/
│   │   ├── step_21a_raw.csv
│   │   └── summary.json
│   ├── ecdh_p256_scalarmult/
│   │   ├── step_27b_raw.csv
│   │   └── summary.json
│   ├── sha256_kdf/
│   │   ├── step_24d_27c_raw.csv
│   │   └── summary.json
│   ├── aes128_decrypt/
│   │   ├── step_27e_raw.csv
│   │   └── summary.json
│   └── aes128_cmac_verify/
│       ├── step_27d_raw.csv
│       └── summary.json
│
├── host_smdp/                      ← SM-DP+-side software timings
│   ├── ecdsa_p256_sign/
│   ├── ecdsa_p256_verify/
│   ├── ecdh_p256_keygen_scalarmult/
│   ├── sha256_kdf/
│   ├── aes128_encrypt/
│   ├── aes128_cmac_compute/
│   └── [same structure as platform_a/]
│
├── bandwidth/
│   ├── certificates/
│   │   ├── classical/
│   │   │   ├── ci_root.der
│   │   │   ├── ci_subca.der
│   │   │   ├── cert_dpauth.der
│   │   │   ├── cert_dppb.der
│   │   │   ├── cert_euicc.der
│   │   │   ├── cert_eum.der
│   │   │   └── sizes.json
│   │   └── pqc/                    ← EMPTY NOW, populate in Phase 2
│   │       └── .gitkeep
│   ├── option_a/
│   ├── option_b/
│   ├── option_c/                   ← EMPTY NOW
│   └── option_d/                   ← EMPTY NOW
│
├── normalization/
│   ├── prerequisites.json          ← populated in Phase 1 (see 4.2)
│   ├── alpha_values.json           ← EMPTY NOW, populated in Phase 2
│   └── README.md                   ← normalization procedure doc
│
└── results/
    ├── phase1_options_ab/          ← complete Phase 1 results
    └── phase2_options_cd/          ← EMPTY NOW
```

### 4.2 Prerequisites JSON — The Normalization Input File

Create `normalization/prerequisites.json` during Phase 1 and treat it as a living document you update as each measurement completes. Its schema is:

```json
{
  "schema_version": "1.0",
  "phase1_completed": "YYYY-MM-DD",
  "platform_a": {
    "eUICC_firmware": "...",
    "reader_model": "...",
    "pcsc_overhead_ms": {
      "mean": null,
      "sigma": null,
      "ci95_lower": null,
      "ci95_upper": null,
      "raw_file": "calibration/pcsc_null_apdu/raw_iterations.csv"
    },
    "operations": {
      "ecdsa_p256_sign": {
        "step_13b": {
          "mean_ms": null,
          "sigma_ms": null,
          "ci95_lower_ms": null,
          "ci95_upper_ms": null,
          "p99_ms": null,
          "n_iterations": 10000,
          "n_outliers_excluded": null,
          "pcsc_corrected": true,
          "raw_file": "platform_a/ecdsa_p256_sign/step_13b_raw.csv",
          "measured_date": null
        },
        "step_21c": { "...same schema..." },
        "step_27f": { "...same schema..." }
      },
      "ecdsa_p256_verify": {
        "step_12c": { "...same schema..." },
        "step_20b": { "...same schema..." },
        "step_24a": { "...same schema..." },
        "step_27a": { "...same schema..." }
      },
      "ecdh_p256_keygen": {
        "step_21a": { "...same schema..." }
      },
      "ecdh_p256_scalarmult": {
        "step_27b": { "...same schema..." }
      },
      "sha256_kdf": {
        "step_24d_27c": { "...same schema..." }
      },
      "aes128_decrypt": {
        "step_27e": { "...same schema..." }
      },
      "aes128_cmac_verify": {
        "step_27d": { "...same schema..." }
      }
    }
  },
  "platform_b": {
    "status": "not_yet_available",
    "board_revision": null,
    "cpu_frequency_locked_mhz": null,
    "liboqs_version": null,
    "liboqs_build_flags": null,
    "operations": {}
  },
  "alpha_computation": {
    "status": "pending_platform_b",
    "operations_required": [
      "ecdsa_p256_sign",
      "ecdsa_p256_verify",
      "ecdh_p256_keygen",
      "ecdh_p256_scalarmult",
      "sha256",
      "aes128"
    ],
    "alpha_values": {},
    "cv_across_operations": null,
    "normalization_strategy": null
  }
}
```

Every null field in this file is a placeholder you will fill either in Phase 1 (platform\_a fields) or Phase 2 (platform\_b and alpha fields). The file should never have empty fields you forgot — if a measurement is pending, the value is explicitly `null` with a `"status"` sibling field explaining why.

### 4.3 What Phase 2 Needs From Phase 1

This is the checklist you hand to yourself when the Pi arrives. Every item must be complete before Phase 2 begins:

```
Phase 1 completion checklist — must all be GREEN before Phase 2:

[ ] Δ_pcsc measured and stored with raw iterations
[ ] T_sysmocom(ECDSA-P256 Sign) — all three step variants (ES10 round-trips)
[ ] T_sysmocom(ECDSA-P256 Verify) — all four step variants
[ ] T_sysmocom(ECDH-P256 KeyGen)
[ ] T_sysmocom(ECDH-P256 Scalar Multiply)
[ ] T_sysmocom(SHA-256 / KDF)
[ ] T_sysmocom(AES-128 Decrypt)
[ ] T_sysmocom(AES-128-CMAC Verify)
[ ] All raw CSVs stored (not just summaries)
[ ] Platform A fingerprint JSON complete
[ ] Classical DER certificates generated and sized
[ ] prerequisites.json fully populated for platform_a section
[ ] Options (a) and (b) session bandwidth fully recorded
[ ] Fragmentation analysis complete for options (a) and (b)
```

Phase 2 adds:

```
Phase 2 additions (Pi required):

[ ] CPU frequency locked at 1 GHz and verified (cpufreq-info)
[ ] T_Pi(op) for all six classical operation families (same measurement protocol)
[ ] α_i computed per operation; CV_global and per-category CV computed
[ ] Normalization strategy selected per CV decision rules above
[ ] T_Pi(ML-DSA-44 Sign), T_Pi(ML-DSA-44 Verify) — aarch64 liboqs
[ ] T_Pi(ML-KEM-768 KeyGen), T_Pi(ML-KEM-768 Encaps), T_Pi(ML-KEM-768 Decaps)
[ ] Projected eUICC timings T̂_eUICC with 95% CIs from uncertainty propagation
[ ] ARM PMU cycle count cross-check (normalised to 80–200 MHz eUICC clock)
[ ] Memory: peak heap for ML-DSA Sign and ML-KEM Decaps via valgrind massif
    — compare against eUICC RAM budget (<500 KB)
[ ] Options (c) and (d) session bandwidth recorded
[ ] prerequisites.json platform_b section fully populated
[ ] alpha_values.json populated with chosen strategy and per-operation α_i
```

The α computation itself takes a single afternoon — the months of setup is the careful collection of T\_sysmocom and the raw CSV files needed for correct uncertainty propagation.

---

## Section 5 — Phase 1 Execution Schedule

```
Day 1 — Environment calibration
  Morning : PC/SC null-APDU characterization (Δ_pcsc)
  Afternoon: Host baseline recording, Platform A fingerprint
             Verify osmo-smdpp classical provisioning session
             Initialize directory structure and prerequisites.json

Day 2 — eUICC Sign operations (Platform A)
  Morning : ECDSA-P256 Sign — step 13b (warm-up + 10,000 iters)
  Midday  : ECDSA-P256 Sign — step 21c
  Afternoon: ECDSA-P256 Sign — step 27f
  Evening : Update prerequisites.json with Day 2 results

Day 3 — eUICC Verify operations (Platform A)
  Morning : ECDSA-P256 Verify — step 12c
  Late AM : ECDSA-P256 Verify — step 20b
  Afternoon: ECDSA-P256 Verify — step 24a
  Late PM : ECDSA-P256 Verify — step 27a
  Evening : Update prerequisites.json

Day 4 — eUICC Key Agreement + Symmetric operations (Platform A)
  Morning : ECDH-P256 KeyGen — step 21a
  Late AM : ECDH-P256 Scalar Multiply — step 27b
  Afternoon: SHA-256 / KDF — steps 24d, 27c
  Late PM : AES-128 Decrypt — step 27e
             AES-128-CMAC Verify — step 27d
  Evening : Update prerequisites.json

Day 5 — SM-DP+-side operations (Measurement Host)
  Morning : ECDSA Sign (8e, 17c, 24h)
  Afternoon: ECDSA Verify (16d, 24a)
             ECDH KeyGen + Scalar Multiply (24b–24c)
             KDF, AES Encrypt, CMAC Compute
  Evening : Store host_smdp/ results

Day 6 — Bandwidth and Certificates
  Morning : Generate and measure all classical DER certificates
  Afternoon: Trace and measure all session messages for options (a) and (b)
             Run fragmentation threshold analysis
  Evening : Store bandwidth/ results, update prerequisites.json

Day 7 — Verification and Reproducibility Check
  Repeat Days 2–4 measurements for a subset (Sign + Verify at minimum)
  Verify agreement within 5% against first run
  If disagreement found: investigate thermal / frequency drift
  Finalize prerequisites.json — confirm no null fields remain
  that should have been populated
```

---

## Section 6 — What Phase 1 Results Support

When Phase 1 is complete the following paper sections can be written with real data:

**Section 5 (Methodology)** — fully writable now:
- Testbed description (two-platform setup with rationale)
- Platform A characterization and PC/SC correction procedure
- Measurement protocol (warm-up, 10k iterations, temperature check)
- Bandwidth methodology
- Normalization framework with CV decision rules and uncertainty propagation formula — written as a forward-looking section with prerequisite data confirmed

**Section 6 (Results) — partial but substantive after Phase 1:**
- Table: classical latency on eUICC (ES10 command round-trips, Δ_pcsc corrected) — complete
- Table: SM-DP+-side host latency — complete
- Table: per-step breakdown for options (a) and (b) — complete; options (c) and (d) as pending columns
- Table: bandwidth — complete for all four options at certificate level; session level complete for (a) and (b)
- Table: PQC projected latency — placeholder rows with "pending Platform B"
- Table: memory — pending Platform B entirely

**Section 7 (Discussion):**
- Option (b) deployment outlook fully arguable from Phase 1 data: HNDL transport protection, zero-eUICC-change feasibility, PQ-TLS bandwidth overhead vs. TLS 1.3
- Options (c) and (d) framed as pending, with normalization methodology as the described bridge
- NSA CNSA 2.0 / GSMA PQ.04 timeline argument grounded in Phase 1 measurements

Phase 1 alone supports a strong short-paper or poster submission. The full results paper requires Phase 2 for PQC latency projections, memory data, and options (c)/(d) completion.