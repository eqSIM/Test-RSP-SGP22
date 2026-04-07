Good. This is the same repo as your uploaded files — I can see the complete architecture from the README and test-all.sh. Now I have everything I need to draft the plan. Here it is.

---

# Experiment 5: Sub-Operation Isolation via Configuration Timing Difference

## Goal
Measure ML-KEM-768 key generation latency directly on a software eUICC executing a real SGP.22 protocol flow, by differencing APDU session timing between configuration (a) (ECDH keygen at step 21a) and a patched configuration (c) partial (ML-KEM-768 keygen at step 21a). This produces the most defensible PQC benchmark result in the paper: a directly measured value in a real SGP.22 session rather than a normalised projection.

---

## Architecture

```
lpac ──socket──> v-euicc-daemon (patched) ──HTTPS/ES9+──> nginx ──> osmo-smdpp (patched)
                 [step 21a: ML-KEM keygen]                           [step 24b: ML-KEM encaps]
```

The v-euicc-daemon handles the eUICC side. osmo-smdpp handles the SM-DP+ side. Both need patching to support ML-KEM-768 for configuration (c). The session timing is measured via lpac BENCH markers on stderr, same as experiments 2 and 3.

---

## Hardware and Software Required
- Host Ubuntu machine only
- virtual-rsp-2 repo (already working)
- liboqs installed on Ubuntu host
- No eUICC hardware, no STM32 needed

---

## Folder Structure

```
thesis_experiments/
│
├── exp5_suboperation_isolation/
│   ├── raw/
│   │   ├── config_a_preparedownload.csv     # 200 PrepareDownload timings config (a)
│   │   ├── config_c_preparedownload.csv     # 200 PrepareDownload timings config (c) partial
│   │   ├── config_a_fullsession.csv         # 200 full session wall times config (a)
│   │   └── config_c_fullsession.csv         # 200 full session wall times config (c) partial
│   ├── processed/
│   │   ├── mlkem_keygen_latency.txt         # T_MLKEM_keygen = T(c) - T(a)
│   │   ├── ecdh_keygen_latency.txt          # T_ECDH_keygen from config (a)
│   │   └── summary_stats.csv               # mean, median, std, CI for all values
│   ├── patches/
│   │   ├── v_euicc_mlkem_patch.diff         # diff of v-euicc C changes
│   │   └── osmo_smdpp_mlkem_patch.diff      # diff of osmo-smdpp Python changes
│   ├── figures/
│   │   └── suboperation_timing_comparison.png
│   ├── notes.md
│   └── README.md
│
├── exp1_pcsc_calibration/
│   └── (complete)
│
└── exp6_ecdh_capture/
    └── (complete)
```

---

## Pre-Experiment Checklist

- [ ] virtual-rsp-2 `./test-all.sh` passes all 7 tests cleanly (baseline confirmed working)
- [ ] liboqs is installed on the host
- [ ] v-euicc source compiles cleanly before any changes
- [ ] lpac BENCH timing markers are enabled and visible on stderr

Install liboqs if not present:
```bash
sudo apt install cmake ninja-build
git clone https://github.com/open-quantum-safe/liboqs.git
cd liboqs
cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DOQS_BUILD_ONLY_LIB=ON
ninja -C build
sudo ninja -C build install
sudo ldconfig
```

Verify:
```bash
ls /usr/local/lib/liboqs*
ls /usr/local/include/oqs/kem_kyber.h
```

---

## Procedure

### Step 1 — Establish the config (a) baseline

Before touching any code, run 200 timed PrepareDownload sessions under the current unmodified setup. This gives you T_PrepareDownload(a) = T_smdpSigned2_verify + T_ECDH_keygen.

Start the virtual stack in one terminal:
```bash
cd virtual-rsp-2
./build/v-euicc/v-euicc-daemon 8765 &
systemctl --user start vrsp-manager.service
nginx -c pysim/nginx-smdpp.conf -p pysim &
```

In a second terminal run 200 timed sessions and extract PrepareDownload timing from BENCH markers. Save each PrepareDownload duration in microseconds to `raw/config_a_preparedownload.csv`. Save total session wall time to `raw/config_a_fullsession.csv`.

This is the same data as Experiment 2 if that is already running — reuse those results and skip re-running.

---

### Step 2 — Patch v-euicc-daemon for ML-KEM-768 keygen at step 21a

The v-euicc-daemon source is at `v-euicc/src/apdu_handler.c`. Step 21a is the `PrepareDownload` (BF21) APDU handler where the eUICC generates its ephemeral key pair.

The patch replaces the ECDH key generation block with ML-KEM-768 key generation using liboqs. The logic change at step 21a is:

**Before (ECDH):**
- Generate ephemeral ECDH-P256 key pair `(otSK.EUICC.ECKA, otPK.EUICC.ECKA)`
- Store `otSK.EUICC.ECKA` for later use at step 27b
- Return `otPK.EUICC.ECKA` (65 bytes) in the response

**After (ML-KEM-768):**
- Call `OQS_KEM_keypair()` for ML-KEM-768
- Store `otSK.EUICC.MLKEM` (2400 bytes) for later use at step 27b
- Return `otPK.EUICC.MLKEM` (1184 bytes) in the response

For step 27b (decapsulation), the eUICC receives the ciphertext from the SM-DP+ and calls `OQS_KEM_decaps()` to recover the shared secret.

Add liboqs to the CMakeLists.txt for v-euicc:
```cmake
find_package(liboqs REQUIRED)
target_link_libraries(v-euicc-daemon oqs)
target_include_directories(v-euicc-daemon PRIVATE /usr/local/include)
```

Save the complete diff to `patches/v_euicc_mlkem_patch.diff` before and after so the patch is reproducible and can be included in the thesis supplementary material.

---

### Step 3 — Patch osmo-smdpp for ML-KEM-768 encapsulation at step 24b

The SM-DP+ side at step 24b normally performs ECDH shared secret computation using the eUICC's ephemeral public key. The patch replaces this with ML-KEM-768 encapsulation.

The relevant Python file is `pysim/osmo-smdpp.py` or its session handler module. The logic change at step 24b is:

**Before (ECDH):**
- Receive `otPK.EUICC.ECKA` (65 bytes) from eUICC
- Perform `ECDH.agree(otPK.EUICC.ECKA, SK.DPpb)` to derive `ShS`
- Send `otPK.DP.ECKA` back to eUICC in bind_body

**After (ML-KEM-768):**
- Receive `otPK.EUICC.MLKEM` (1184 bytes) from eUICC
- Call `liboqs Python bindings`: `kem.encap_secret(otPK.EUICC.MLKEM)` → `(ciphertext, ShS)`
- Send `ciphertext` (1088 bytes) back to eUICC in bind_body in place of `otPK.DP.ECKA`

Install liboqs Python bindings:
```bash
source pysim/venv/bin/activate
pip install liboqs-python
```

The key detection logic: if the received ephemeral public key is 1184 bytes, use ML-KEM encapsulation. If it is 65 bytes, use ECDH. This allows both configuration (a) and configuration (c) sessions to run against the same SM-DP+ instance by switching based on key size.

Save the diff to `patches/osmo_smdpp_mlkem_patch.diff`.

---

### Step 4 — Rebuild and verify

```bash
cd virtual-rsp-2
cmake --build build -j$(nproc)
./test-all.sh --tests-only
```

The existing 7 tests must still pass. If any test fails after the patch, the patch broke the classical path. Fix before proceeding.

Then run one manual configuration (c) session to confirm it completes end-to-end:
```bash
./build/v-euicc/v-euicc-daemon 8765 &
LPAC_APDU=socket ./build/lpac/src/lpac profile download \
  -s testsmdpplus1.example.com:8443 \
  -m <available_profile_id>
```

If the session completes with `"message":"success"` the ML-KEM path is working end-to-end.

---

### Step 5 — Run 200 timed configuration (c) sessions

With the patched stack running, execute 200 complete profile download sessions and record PrepareDownload timing from BENCH markers. Save to `raw/config_c_preparedownload.csv` and `raw/config_c_fullsession.csv`. Use the same cooldown protocol as experiment 2 (15-second pause every 50 iterations). Reset the profile database between runs with `./reset-manager.sh`.

---

### Step 6 — Compute the timing difference

```
T_MLKEM_keygen_eUICC = median(config_c_PrepareDownload) - median(config_a_PrepareDownload)
T_ECDH_keygen_eUICC  = extracted from config_a PrepareDownload sub-operation
```

This difference is valid because both runs use the same virtual eUICC on the same hardware under the same conditions, and the only change between configuration (a) and configuration (c) at the PrepareDownload step is the key generation algorithm. The `smdpSigned2` verification (ECDSA-P256) is identical in both runs and cancels out in the difference.

Also compute for GetBoundProfilePackage and first LoadBPP APDU if the session proceeds fully — these isolate T_MLKEM_encaps and T_MLKEM_decaps respectively.

Report with 200-iteration statistics: mean, median, standard deviation, 95% CI.

---

## Data to Record

| Data Item | File |
|---|---|
| 200 PrepareDownload timings config (a) | `raw/config_a_preparedownload.csv` |
| 200 PrepareDownload timings config (c) | `raw/config_c_preparedownload.csv` |
| 200 full session times config (a) | `raw/config_a_fullsession.csv` |
| 200 full session times config (c) | `raw/config_c_fullsession.csv` |
| Computed T_MLKEM_keygen with 95% CI | `processed/mlkem_keygen_latency.txt` |
| Computed T_ECDH_keygen with 95% CI | `processed/ecdh_keygen_latency.txt` |
| v-euicc patch diff | `patches/v_euicc_mlkem_patch.diff` |
| osmo-smdpp patch diff | `patches/osmo_smdpp_mlkem_patch.diff` |

---

## Important Caveat for the Paper

This experiment runs on a software eUICC (v-euicc-daemon) on an x86_64 host, not on silicon. The measured T_MLKEM_keygen value reflects the liboqs ML-KEM-768 implementation running on a 64-bit Linux process, not constrained ARM hardware. In the paper this result must be labelled explicitly as:

> ML-KEM-768 key generation latency measured on a software eUICC reference implementation (v-euicc-daemon with liboqs 0.x on Ubuntu x86_64)

This value is then used in Experiment 15 to validate the α normalisation methodology. The comparison question is: does the α-projected value from the STM32 M4 agree with this software-eUICC measurement? If yes, the normalisation methodology is validated across both software and hardware proxies. If they disagree, the discrepancy quantifies the x86_64-to-ARM computational ratio for ML-KEM, which is itself an interesting finding.

---

## Expected Output

A new table in Section VI-F with three rows:

| Operation | Platform | Method | Value (ms) | 95% CI |
|---|---|---|---|---|
| ML-KEM-768 KeyGen | v-euicc software | Directly measured (timing diff) | ___ | ___ |
| ML-KEM-768 Encaps | v-euicc software | Directly measured (timing diff) | ___ | ___ |
| ML-KEM-768 Decaps | v-euicc software | Directly measured (timing diff) | ___ | ___ |

Labelled explicitly as software eUICC measurement, distinguished from the STM32 α-projected values in the same table.

---

## README.md Template

```markdown
# Experiment 5: Sub-Operation Isolation via Configuration Timing Difference

**Date:**
**Status:** [ ] In Progress / [ ] Complete

## Summary
Measured ML-KEM-768 keygen, encaps, and decaps latency on a software
eUICC (v-euicc-daemon + liboqs) by differencing PrepareDownload APDU
timing between configuration (a) (ECDH) and configuration (c) partial
(ML-KEM-768). The smdpSigned2 ECDSA verification sub-operation is
identical in both runs and cancels out in the difference.

## Setup
- virtual-rsp-2 repo with v-euicc ML-KEM patch applied
- osmo-smdpp with ML-KEM encapsulation at step 24b
- liboqs version: ___
- 200 iterations per configuration, 15s cooldown every 50

## Key Results
- T_MLKEM_keygen (software eUICC): ___ ms (95% CI: ___ to ___)
- T_ECDH_keygen  (software eUICC): ___ ms (95% CI: ___ to ___)
- T_MLKEM_encaps (software eUICC): ___ ms (if measured)
- T_MLKEM_decaps (software eUICC): ___ ms (if measured)

## Caveat
Results are from a software eUICC on x86_64, not silicon.
Used in Experiment 15 to validate the STM32 α normalisation methodology.

## Paper Section
Section VI-F, new table: Directly Measured ML-KEM-768 Latency
```