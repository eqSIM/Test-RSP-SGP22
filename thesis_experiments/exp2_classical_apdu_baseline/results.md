# Experiment 2: Results summary

## Objective

Measure full classical **SGP.22 profile download** timings on the **real sysmocom eUICC** over PC/SC (BENCH lines from `lpac`), subtract Experiment 1 PC/SC overhead where Lc is known, and derive **α anchors** (BF38 proxy; BF21 with optional ECDH split via `--smdp2-verify-us`).

## Campaign status

| Item | Value |
|------|--------|
| Iterations attempted | 200 (`scripts/run_sessions.py`) |
| Successful end-to-end downloads (runner `rc=0`, ICCID parsed) | **176** |
| Failed iterations | **24** (iters **177–200**, `rc=255`) |
| Raw session logs | `raw/session_001.log` … `raw/session_200.log` |
| Logs used by `analyse.py` | **176** with a **successful last `profile download`** and parsed BENCH (see `processed/alpha_anchors.txt`) |

Earlier runs hit **DPauth / `initiateAuthentication`** chain issues; the **2026-04-07** campaign (`run_log.txt`: start **05:20:26 UTC**) completed the driver loop with the success/fail split above. Investigate `raw/session_177.log` (and neighbours) if you need **200** usable sessions.

## PC/SC correction

- Model: `processed/pcsc_model.json` — `T_PCSC(n) = 1073.7516 + 62.295119 × n` (µs).
- **`scripts/payload_sizes_ref.json`** still has **Lc = null** for all listed ops → **no subtraction**; **`duration_net_us` = `duration_us`** (`alpha_anchors.txt`: “All rows had Lc … subtracted: False”).

## α anchors (medians, net = gross today)

From `processed/alpha_anchors.txt` (**n = 176** sessions):

| Anchor | Median net | Notes |
|--------|------------|--------|
| **BF38** AuthenticateServer | **3 117 160.5 µs** (~3.12 s) | Thesis proxy for on-card verify / ECDSA; not a single primitive. |
| **BF21** PrepareDownload | **3 749 753 µs** (~3.75 s) | Blended path (incl. smdpSigned2 verify + ECDH on eUICC). |
| **T_eUICC(ECDH_keygen)** | *not computed* | Pass **`--smdp2-verify-us`** to `analyse.py` with your smdpSigned2 verify estimate (µs). |

## Session operations — summary (`processed/summary_stats.csv`, **n = 176**)

Lc unset → **median “net” = measured BENCH** (µs). Rounded for readability; exact values in CSV.

| Operation | Median (µs) | Mean (µs) | Std (µs) |
|-----------|-------------|-----------|---------|
| BF2E GetEuiccChallenge | 5 863.5 | 5 947.0 | 288.6 |
| BF20 GetEuiccInfo1 | 41 424 | 41 462 | 301.3 |
| ES9P …/initiateAuthentication | 14 084.5 | 12 531.8 | 4 268.7 |
| BF38 AuthenticateServer | **3 117 160.5** | **3 174 106.7** | 288 518.4 |
| ES9P …/authenticateClient | 32 367.5 | 32 427.4 | 7 881.0 |
| BF21 PrepareDownload | **3 749 753** | **3 749 769.0** | 12 973.2 |
| ES9P …/getBoundProfilePackage | 20 533 | 21 207.8 | 6 127.1 |

**BF36** (`LoadBPP_seg0` … `seg17`): per-segment medians range from about **1.7 ms** to **3.79 s** with **high** variability on some segments (profile/package split); see full table in `summary_stats.csv`.

95% CI half-widths for the **mean** are in `summary_stats.csv` (µs).

## Outputs on disk

| Path | Contents |
|------|----------|
| `processed/apdu_timings_raw.csv` | Per-iteration BENCH rows + gross/net columns |
| `processed/apdu_timings_net.csv` | Iteration, tag, name, `duration_net_us` |
| `processed/summary_stats.csv` | Aggregates (mean / median / std / CI) |
| `processed/alpha_anchors.txt` | PC/SC note + BF38/BF21 + session count |
| `processed/pcsc_model.json` | Exp1 linear PC/SC model |
| `processed/HARDWARE_RUN_STATUS.txt` | Short run note (may predate last campaign; see **Campaign status** above) |
| `figures/figure6_apdu_breakdown.png` | Regenerate with `analyse.py` if **matplotlib** is installed (otherwise the script skips the figure). |

## Next steps

1. **Optional:** Diagnose failures **177–200** and re-run or patch slots until **200** usable logs if the thesis requires it.
2. Re-run analysis with ECDH split:  
   `python3 scripts/analyse.py … --smdp2-verify-us <µs>`
3. Fill `scripts/payload_sizes_ref.json` from an `LPAC_APDU_DEBUG` (or equivalent) capture so net times apply **T_PCSC** per command.
4. Install **matplotlib** and re-run `analyse.py` to refresh **`figures/figure6_apdu_breakdown.png`**.

## Demos / fixtures

`fixtures/session_*.log` are **synthetic** logs for parser checks only; they are **not** part of the hardware dataset.
