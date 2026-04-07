# Experiment 1: Extended PC/SC Overhead Calibration

**Date:** 2026-04-06  
**Status:** [x] Complete (measurement); extended range **pending** on T=1 hardware

## Summary

Calibrated PC/SC STORE DATA round-trip times at **10** target payload sizes (0–2,515 bytes). On the **current** reader/eUICC path the card negotiated **T=0 only**; **extended-length APDUs (512+ byte)** did not transmit (PC/SC `0x80100016`). **Five sizes** (0–255 byte payload) yielded **500 samples each**; the **0–255 byte** linear model matches the paper closely.

Re-run `python scripts/calibrate.py` on hardware that negotiates **T=1** (or otherwise accepts extended APDUs) to fill `raw/size_{512..2515}_bytes.csv` and refresh the extended regression.

## Certificate Sizes (Measured from this Setup)

| Cert | DER bytes |
|------|-----------|
| CERT.EUM | 731 |
| CERT.EUICC | 615 |
| CERT.CI | 596 |
| CERT.DPpb | 573 |
| CERT.DPauth | 572 |
| 4-cert chain total | 2,515 |

Note: Paper Table 11 used 659 B/cert analytically (2,636 B total). Actual average is ~629 B/cert from real SGP.26 v3 test certs.

## Model Result (this run — 0–255 byte data only)

**T_PCSC(n) = 1073.75 µs + 62.30 µs · n**

**R-squared (0–255, five mean points):** 0.999942  

**R-squared (0–2515):** same as above until extended CSVs contain samples; see `processed/regression_extended.txt`.

**Linear model valid to 2515 bytes:** **Not yet** — requires successful extended APDU measurements.

## Comparison with Original Paper

- Original: **T_PCSC(n) = 1160 µs + 62.4 µs·n**, R²≈0.999  
- Updated (this run, 0–255): **1073.75 µs + 62.30 µs·n**, R²=0.999942  

## APDU Rejection Events

Extended sizes **512, 1024, 1536, 2048, 2515** bytes: first transmit failed; see `raw/rejected_at_*.txt`. Short APDU sizes **0–255** completed **500** iterations each.

## Files

- `raw/size_{n}_bytes.csv` — column `rtt_us` (500 rows when successful; header-only when skipped)
- `processed/summary_stats.csv`
- `processed/regression_original.txt`
- `processed/regression_extended.txt`
- `figures/figure4_pcsc_calibration.png`
- `scripts/calibrate.py`, `scripts/analyse.py`
- `run_log.txt` — run summary

## Paper Section

Section VI-C, Figure 4 replacement (after extended data is collected on T=1)

## Python environment

Use `../../benchmark/.venv/bin/python` (has `pyscard`, `scipy`, `matplotlib`) or `pip install pyscard scipy matplotlib numpy` in your own venv.
