# Experiment 1: Extended PC/SC Overhead Calibration

## Goal

Validate the linear PC/SC overhead model across the full payload range actually used in SGP.22 provisioning sessions. The current calibration range of 0–255 bytes represents extrapolation for all real SGP.22 logical payloads. Extending to 2,515 bytes (the measured 4-certificate ECDSA chain from this exact test setup) removes this methodological gap and gives reviewers a validated model rather than an extrapolated one.

---

## Background: Where the 2,515-Byte Upper Bound Comes From

The original paper (Table 11) cited 2,636 bytes as the four-certificate chain size, derived analytically using an average of 659 bytes per ECDSA-P256 X.509 certificate. The actual certificate sizes measured from the **real eUICC and osmo-smdpp SGP.26 v3 test certificates in this repository** are:

| Certificate | Role | Measured DER size |
|---|---|---|
| sysmocom RSP Test EUM | CERT.EUM | 731 bytes |
| sysmoEUICC1-C2T Test eUICC | CERT.EUICC | 615 bytes |
| Test CI (SGP.26 NIST) | CERT.CI | 596 bytes |
| TEST SM-DP+ DPpb NIST | CERT.DPpb | 573 bytes |
| TEST SM-DP+ DPauth NIST | CERT.DPauth | 572 bytes |
| TEST SM-DP+ DPtls NIST | CERT.DPtls | 646 bytes |

The largest four-certificate chain that actually flows through the APDU interface in one SGP.22 provisioning session is **CERT.EUM + CERT.EUICC + CERT.CI + CERT.DPpb/DPauth = 731 + 615 + 596 + 573 = 2,515 bytes**. This is the empirically correct ceiling for this test setup. The paper's 2,636-byte figure (average 659 bytes/cert) overstates by ~5% relative to these actual SGP.26 v3 test certificates.

**Note on individual APDU segments:** lpac chunks logical payloads into segments of at most 120 bytes (default ES10x MSS), and the eUICC returns GET RESPONSE data in up to 256-byte chunks. Every single APDU exchange in a real session is well within the existing 0–255-byte calibration range. The 2,515-byte target validates the model over the *logical* payload range, which is the relevant scale for the overhead correction formula applied per-operation in the paper.

---

## Hardware and Software Required

- Host Ubuntu machine
- sysmocom eUICC C2T
- HID Omnikey 3x21 reader
- USB cable
- Python 3 with `scipy`, `numpy`, `matplotlib`, `pyscard`

Install dependencies if not present:
```bash
pip install scipy numpy matplotlib pyscard
```

---

## Folder Structure

```
thesis_experiments/
│
├── exp1_pcsc_calibration/
│   ├── raw/
│   │   ├── size_0_bytes.csv          # 500 round-trip times at 0 bytes
│   │   ├── size_32_bytes.csv
│   │   ├── size_64_bytes.csv
│   │   ├── size_128_bytes.csv
│   │   ├── size_255_bytes.csv
│   │   ├── size_512_bytes.csv
│   │   ├── size_1024_bytes.csv
│   │   ├── size_1536_bytes.csv
│   │   ├── size_2048_bytes.csv
│   │   └── size_2515_bytes.csv
│   ├── processed/
│   │   ├── summary_stats.csv         # mean, median, std, CI per size
│   │   ├── regression_original.txt   # fit over 0-255 bytes
│   │   └── regression_extended.txt   # fit over 0-2515 bytes
│   ├── figures/
│   │   └── figure4_pcsc_calibration.png   # replacement for Figure 4
│   ├── scripts/
│   │   ├── calibrate.py              # main measurement script
│   │   └── analyse.py                # regression and plotting script
│   ├── notes.md
│   └── README.md
│
├── exp2_classical_apdu_baseline/
│   └── (later)
│
├── exp5_suboperation_isolation/
│   └── (later)
│
├── exp6_ecdh_capture/
│   └── (complete)
│
└── shared/
    ├── config/
    │   ├── nginx_classical.conf
    │   └── nginx_pqtls.conf
    └── scripts/
        └── (shared helpers)
```

---

## Pre-Experiment Checklist

Before running anything confirm:

- [ ] pySIM is installed and can communicate with the eUICC
- [ ] HID Omnikey reader is connected and recognized (`pcsc_scan` shows a card)
- [ ] eUICC is responsive (test with a simple `SELECT` APDU via pySIM)
- [ ] Python environment has `scipy`, `numpy`, `matplotlib` installed
- [ ] No other process is holding the PC/SC reader open (close lpac, close any other terminal using the reader)

Test the reader is free:
```bash
pcsc_scan
# Should show your reader and card without errors
```

---

## Procedure

### Step 1 — Confirm extended-length APDU support

Before running the full measurement, send one test STORE DATA APDU at 512 bytes to confirm the eUICC accepts extended-length APDUs without rejecting them. If the eUICC returns `6700` (wrong length) or `6D00` (instruction not supported), fall back to UPDATE BINARY with chained APDUs for sizes above 255 bytes and note this in your results.

```bash
# Quick test via pySIM interactive shell
pySim-shell.py -p 0
# then try sending a STORE DATA at 512 bytes
```

---

### Step 2 — Write the calibration script

Save as `exp1_pcsc_calibration/scripts/calibrate.py`. The script logic is:

For each payload size in `[0, 32, 64, 128, 255, 512, 1024, 1536, 2048, 2515]`:
- Build a STORE DATA APDU with a payload of that exact size filled with `0x00` bytes
- Send it to the eUICC 500 times
- Record the wall-clock round-trip time for each iteration using `time.perf_counter()` immediately before and after the APDU transmission call
- Save all 500 values to `raw/size_{n}_bytes.csv` with a single column header `rtt_us`

Key points for the script:
- Use `time.perf_counter()` not `time.time()` — perf_counter has nanosecond resolution on Linux
- Convert the result to microseconds before saving
- For sizes above 255 bytes, use extended-length APDU encoding: Lc = 3 bytes (`0x00, size >> 8, size & 0xFF`)
- Add a 1-second pause between payload sizes to let the eUICC settle
- Print progress to terminal so you can monitor it while it runs unattended
- Wrap each APDU call in a try/except and log any errors separately rather than crashing the whole run

---

### Step 3 — Run the script unattended

```bash
cd thesis_experiments/exp1_pcsc_calibration
python scripts/calibrate.py 2>&1 | tee run_log.txt
```

This runs for approximately 2-3 hours total. Let it run completely unattended. The `tee` command saves the terminal output to `run_log.txt` as a log. Check on it occasionally to confirm it is progressing through the size steps.

Expected total time per size at 500 iterations:
- 0 bytes: ~10 minutes
- 32-255 bytes: ~10-12 minutes each
- 512+ bytes: ~12-15 minutes each

---

### Step 4 — Write the analysis script

Save as `exp1_pcsc_calibration/scripts/analyse.py`. The script logic is:

For each CSV in `raw/`:
- Load the 500 values
- Compute mean, median, standard deviation, 95% CI
- Save to `processed/summary_stats.csv`

Then fit two linear regression models using `scipy.stats.linregress`:
- **Original range**: use only sizes 0, 32, 64, 128, 255
- **Extended range**: use all 10 sizes

For each model compute:
- Slope `b` (µs per byte)
- Intercept `a` (fixed overhead µs)
- R-squared
- 95% CI on slope and intercept

Save both fits to `processed/regression_original.txt` and `processed/regression_extended.txt`.

If R-squared for the extended range drops below 0.99, fit a piecewise model with breakpoint at 255 bytes and report both segments.

---

### Step 5 — Generate Figure 4 replacement

In `analyse.py`, produce a plot with:
- X axis: payload size in bytes (0 to 2515)
- Y axis: mean round-trip time in microseconds
- Error bars: 95% CI at each measurement point
- Fitted line for the extended model
- A vertical dashed line at 255 bytes labelled "original calibration range"
- A vertical dashed line at 2,515 bytes labelled "measured 4-cert chain (this setup)"
- The equation `T_PCSC(n) = a + b·n` with R² shown on the plot

Save to `figures/figure4_pcsc_calibration.png` at 300 DPI.

---

### Step 6 — Run the analysis script

```bash
python scripts/analyse.py
```

This takes less than a minute. Check that both regression output files were created and the figure looks correct.

---

### Step 7 — Check for APDU rejection events

Review `run_log.txt` for any error lines. If any size was rejected by the eUICC, note it in `notes.md`. If sizes above 255 bytes were rejected, the extended calibration stops at 255 bytes and you report the original model as the validated range, noting the eUICC does not support extended-length STORE DATA. This does not break your paper — it just means the linear model is validated to 255 bytes and extrapolation beyond that carries a larger stated uncertainty.

---

### Step 8 — Record your notes

Open `exp1_pcsc_calibration/notes.md` and record:

```markdown
## Run observations
- eUICC firmware version: ___
- Extended APDU support confirmed up to: ___ bytes
- Any rejection events: ___
- R-squared original range (0-255): ___
- R-squared extended range (0-2515): ___
- Model: T_PCSC(n) = ___ µs + ___ µs · n
- Comparison with original paper model (1160 µs + 62.4 µs·n): ___
- Linear model holds beyond 255 bytes: Yes / No / Piecewise

## Certificate size notes
- Actual cert sizes measured from this setup (DER):
  - CERT.EUM (sysmocom RSP Test EUM):  731 bytes
  - CERT.EUICC (sysmoEUICC1-C2T):      615 bytes
  - CERT.CI (SGP.26 v3 NIST):          596 bytes
  - CERT.DPpb (TEST SM-DP+ NIST):      573 bytes
  - CERT.DPauth (TEST SM-DP+ NIST):    572 bytes
  - CERT.DPtls (TEST SM-DP+ NIST):     646 bytes
- Largest 4-cert chain: EUM+EUICC+CI+DPpb = 2,515 bytes
- Paper Table 11 claimed: 659 bytes/cert × 4 = 2,636 bytes
- Discrepancy: actual average is 629 bytes/cert (paper overstated by ~5%)
```

---

## Data to Record

| Data Item | File Location |
|---|---|
| 500 RTT values per payload size | `raw/size_{n}_bytes.csv` |
| Summary statistics per size | `processed/summary_stats.csv` |
| Original range regression fit | `processed/regression_original.txt` |
| Extended range regression fit | `processed/regression_extended.txt` |
| Figure 4 replacement | `figures/figure4_pcsc_calibration.png` |
| Run log | `run_log.txt` |
| Observations | `notes.md` |

---

## Expected Output

### From regression_extended.txt
```
Model: T_PCSC(n) = a + b*n
Intercept a: ___ µs  (95% CI: ___ to ___)
Slope b:     ___ µs/byte  (95% CI: ___ to ___)
R-squared (original range 0-255):  ___
R-squared (extended range 0-2515): ___
Conclusion: linear model [holds / does not hold] to 2515 bytes
```

### Comparison with original paper
The original paper reported `T_PCSC(n) = 1,160 µs + 62.4 µs·n` with R² = 0.999 over 0–255 bytes. Your extended model should be close to these values if the linear relationship holds. If the intercept or slope differs significantly, note this — it may reflect differences in eUICC firmware version or USB host stack.

### Figure 4 replacement
Updated calibration plot showing measurements across the full 0–2,515 byte range, fitted line, equation and R², and both the 255-byte and 2,515-byte boundary markers. This replaces the original Figure 4 in Section VI-C and validates the model over the operational range of real SGP.22 APDUs from this test setup.

---

## What This Fixes in the Paper

Section VI-C currently says the calibration was derived from 0–255 bytes with R² = 0.999. Reviewers — specifically Prof. Seo — will note that the real SGP.22 certificate chains (up to 2,515 bytes in this setup) are well outside this calibrated range. After this experiment you can state:

> The calibration model was validated over the full 0–2,515 byte range covering the actual ECDSA certificate chain sizes measured from this test setup (CERT.EUM=731 B, CERT.EUICC=615 B, CERT.CI=596 B, CERT.DPpb=573 B). The linear model holds with R² = ___ across this range. The paper's Table 11 analytical estimate of 2,636 bytes (659 B/cert × 4) was derived from average X.509 framing overhead and slightly overstates the actual sizes by ~5%.

That is a much stronger claim than extrapolation, and it corrects the Table 11 discrepancy proactively.

---

## README.md Template

```markdown
# Experiment 1: Extended PC/SC Overhead Calibration

**Date:**
**Status:** [ ] In Progress / [ ] Complete

## Summary
Extended the PC/SC overhead calibration model from the original
0–255 byte range to 0–2,515 bytes, covering the actual ECDSA
certificate chain size measured from this test setup for
SGP.22 configurations (a), (b), (c).

## Certificate Sizes (Measured from this Setup)
| Cert | DER bytes |
|------|-----------|
| CERT.EUM | 731 |
| CERT.EUICC | 615 |
| CERT.CI | 596 |
| CERT.DPpb | 573 |
| CERT.DPauth | 572 |
| 4-cert chain total | 2,515 |

Note: Paper Table 11 used 659 B/cert analytically (2,636 B total).
Actual average is 629 B/cert from real SGP.26 v3 test certs.

## Model Result
T_PCSC(n) = ___ µs + ___ µs · n
R-squared (0-255):  ___
R-squared (0-2515): ___
Linear model valid to 2515 bytes: Yes / No

## Comparison with Original Paper
Original: T_PCSC(n) = 1160 µs + 62.4 µs·n, R² = 0.999
Updated:  T_PCSC(n) = ___ µs + ___ µs·n, R² = ___

## APDU Rejection Events
None / List any rejections here

## Files
- raw/size_{n}_bytes.csv (10 files, 500 iterations each)
- processed/summary_stats.csv
- processed/regression_original.txt
- processed/regression_extended.txt
- figures/figure4_pcsc_calibration.png

## Paper Section
Section VI-C, Figure 4 replacement
```
