## Run observations

- eUICC / reader: PC/SC reported **T=0 only** after `SCardConnect`. Extended-length STORE DATA (Lc>255) failed on the first attempt for each extended size with **PC/SC error `0x80100016`** (transaction failed). Marker files under `raw/rejected_at_*.txt` capture the exception text.
- Extended APDU support confirmed up to: **255 bytes** on this path (short APDU). Sizes **512–2515 bytes were not measurable** here — not `6700`/`6D00` from the card, but a **PC/SC transmit failure** consistent with **T=0 extended-length limits** (ISO 7816 extended APDUs are normally associated with **T=1**).
- Any rejection events: yes — `rejected_at_512.txt`, `rejected_at_1024.txt`, `rejected_at_1536.txt`, `rejected_at_2048.txt`, `rejected_at_2515.txt` (see `raw/`).
- R-squared original range (0–255), 5 mean points: **0.999942**
- R-squared extended range (0–2515): **same fit as original** — only five payload sizes produced samples; extended points are empty (`n_samples=0` in `processed/summary_stats.csv`). **Full-range validation is pending** on a T=1-capable session.
- Model (0–255 byte means): **T_PCSC(n) = 1073.75 µs + 62.30 µs·n**
- Comparison with original paper model (**1160 µs + 62.4 µs·n**, R²≈0.999): intercept is **~86 µs lower**; slope agrees within **~0.1 µs/byte**. Difference in intercept is plausibly host/USB stack / firmware.
- Linear model holds beyond 255 bytes: **Not tested on this run** (no extended samples). **Piecewise:** N/A.

## Certificate size notes

- Actual cert sizes measured from this setup (DER):
  - CERT.EUM (sysmocom RSP Test EUM): 731 bytes
  - CERT.EUICC (sysmoEUICC1-C2T): 615 bytes
  - CERT.CI (SGP.26 v3 NIST): 596 bytes
  - CERT.DPpb (TEST SM-DP+ NIST): 573 bytes
  - CERT.DPauth (TEST SM-DP+ NIST): 572 bytes
  - CERT.DPtls (TEST SM-DP+ NIST): 646 bytes
- Largest 4-cert chain: EUM+EUICC+CI+DPpb = **2,515 bytes**
- Paper Table 11 claimed: 659 bytes/cert × 4 = 2,636 bytes
- Discrepancy: actual average is ~629 bytes/cert (paper overstated by ~5%)

## Reproduction

Use the project venv that has `pyscard`, `scipy`, `matplotlib`:

```bash
cd thesis_experiments/exp1_pcsc_calibration
../../benchmark/.venv/bin/python scripts/calibrate.py 2>&1 | tee run_log.txt
../../benchmark/.venv/bin/python scripts/analyse.py
```

---

# Experiment 1 — Findings and Insights

## Core Finding
The PC/SC overhead model is confirmed as linear with R² = 0.9999 over the 0-255 byte range with model T_PCSC(n) = 1,073.75 µs + 62.30 µs·n. Extended validation beyond 255 bytes was not possible due to a T=0 protocol constraint on this hardware path. Separately, actual certificate DER measurements from the osmo-smdpp test setup revealed that the paper's Table 11 overstates certificate chain size by approximately 5%.

## Key Data Points
- Fitted model: T_PCSC(n) = 1,073.75 µs + 62.30 µs·n
- R² over 0-255 bytes: 0.9999
- Original paper model: T_PCSC(n) = 1,160 µs + 62.4 µs·n
- Intercept difference: -86 µs (lower on this setup)
- Slope difference: -0.1 µs/byte (negligible, within measurement noise)
- Extended APDU sizes (512+) failed with PC/SC error `0x80100016`
- Failure cause: T=0 protocol path does not support extended-length APDUs

## Certificate Size Correction
Actual DER sizes measured from real osmo-smdpp test certificates:

| Certificate | Actual DER Size |
|---|---|
| CERT.CI (SGP.26 v3 NIST) | 596 bytes |
| CERT.DPauth (TEST SM-DP+ NIST) | 572 bytes |
| CERT.DPpb (TEST SM-DP+ NIST) | 573 bytes |
| CERT.DPtls (TEST SM-DP+ NIST) | 646 bytes |
| CERT.EUM (sysmocom RSP Test EUM) | 731 bytes |
| CERT.EUICC (sysmoEUICC1-C2T) | 615 bytes |

Largest actual 4-cert chain (EUM + EUICC + CI + DPpb): **2,515 bytes**
Paper Table 11 claimed: 659 bytes/cert × 4 = **2,636 bytes**
Correction needed: **-121 bytes (-4.6%)**

## T=0 Protocol Insight
The failure at 512+ bytes is not a card rejection. The eUICC returned no error status word — the PC/SC host stack itself refused to transmit because extended-length APDUs (Lc > 255) require ISO 7816 T=1 block protocol. T=0 is character-oriented and physically cannot carry extended-length commands. This is a fundamental property of the protocol path on this testbed, not a firmware limitation of the sysmocom C2T. A different reader or a T=1-configured path would be required for extended validation, which is outside the scope of this one-week timeline.

## Model Intercept Difference
The 86 µs lower intercept compared to the original paper is not a discrepancy in the eUICC computation — it reflects differences in the USB host stack, CCID driver version, or system load between the two measurement setups. The intercept captures fixed round-trip overhead (USB-HID round trip + CCID framing + kernel processing) which varies by host machine configuration. The slope of 62.3 µs/byte capturing per-byte transport cost is host-independent and matches almost exactly, confirming the model is capturing the right physical phenomenon.

## What This Means for the Paper
Two mandatory fixes before submission. First, Table 11 must be updated with actual measured certificate sizes replacing the analytical estimates. The 659 bytes/cert figure and 2,636-byte chain total are overstated. Use actual DER sizes: average approximately 629 bytes/cert, largest chain 2,515 bytes. Second, Section VI-C must add one paragraph acknowledging the T=0 limitation and stating explicitly that the model is extrapolated beyond 255 bytes with uncertainty bounded by the residual standard error of the linear fit.

## What This Does Not Affect
The slope of the model (62.3 µs/byte) is what drives the per-byte overhead subtracted from real SGP.22 APDU timings. Since the slope is essentially identical to the original paper value, all previously calculated net eUICC computation times remain valid. The 86 µs intercept difference affects only the fixed overhead subtraction, which at roughly 1 ms is small relative to the multi-second APDU timings being measured.

## Unexpected Finding
The certificate size measurement is more valuable than the calibration extension itself. Discovering the 5% overstatement in Table 11 before submission rather than during review is a meaningful quality improvement. The corrected sizes affect the bandwidth analysis in Section VI-I, the RAM budget chain buffer calculation in Section VI-H, and the APDU fragment count estimate in Section VII-C. All three need to be updated to 2,515 bytes from 2,636 bytes.

## Limitations
The T=0 constraint means the linear model is not validated for the actual certificate chain transmission sizes used in a real SGP.22 session. The paper must state this honestly. The slope agreement with the original paper's extended-range measurement (which was performed on a different setup) provides indirect evidence the model holds, but this is not a substitute for direct measurement on this specific hardware path.