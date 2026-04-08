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

The **2026-04-07** campaign (`run_log.txt`: start **05:20:26 UTC**) completed the driver loop with the success/fail split above. Sample failures (e.g. `raw/session_177.log`, `raw/session_200.log`) show **`HTTP transport failed` / `curl_easy_perform: Couldn't connect to server`** around ES9+—consistent with **osmo-smdpp or nginx dropping mid-run**, not only eUICC slot exhaustion. For a clean **200 × usable** dataset: stop the stack, reset the SM-DP+ session store (optional but recommended), restart, then top up (see below).

## PC/SC correction

- Model: `processed/pcsc_model.json` — `T_PCSC(n) = 1073.7516 + 62.295119 × n` (µs).
- `scripts/payload_sizes_ref.json` now sets **Lc** for on-card steps:
  - **BF2E** GetEuiccChallenge — **3** (`bf2e00` command data).
  - **BF20** GetEuiccInfo1 — **3** (`bf2000`).
  - **BF38** AuthenticateServer — **2515** (Experiment 1 extended calibration anchor; thesis PC/SC subtraction for this α step).
  - **BF21** PrepareDownload — **663** (`0x0297` from `LPAC_APDU` / `exp6_ecdh_capture` trace — same profile path).
- **BF38 overhead removed (median path):** `T_PCSC(2515) ≈ 157 746 µs` (~**158 ms**); gross BF38 medians included this in the old “net = gross” table.
- **ES9P** rows stay **gross** (host HTTP; not card Lc). **BF36** segments stay **gross** (Lc varies per segment; no single `_default_per_segment`). So `alpha_anchors.txt` still reports **`All rows had Lc and T_PCSC subtracted: False`** — interpretation: **card-tagged BENCH lines use net where Lc is set**; ES9P/BF36 medians in `summary_stats.csv` remain **uncorrected** unless you extend the table.

## α anchors (medians; BF38/BF21/BF2E/BF20 are PC/SC–corrected)

From `processed/alpha_anchors.txt` (**n = 176** sessions):

| Anchor | Median net (µs) | Notes |
|--------|------------------|--------|
| **BF38** AuthenticateServer | **2 959 414.5** (~**2.96 s**) | After subtracting `T_PCSC(2515)`; thesis proxy for on-card verify / ECDSA. |
| **BF21** PrepareDownload | **3 707 377.5** (~**3.71 s**) | After subtracting `T_PCSC(663)`. |
| **T_eUICC(ECDH_keygen)** | *not computed* | Pass **`--smdp2-verify-us`** to `analyse.py` with your smdpSigned2 verify estimate (µs). |

## Session operations — summary (`processed/summary_stats.csv`, **n = 176**)

Card steps (BF2E, BF20, BF38, BF21) use **net** = BENCH − `T_PCSC(Lc)`; ES9P and BF36 = **raw BENCH** here. Rounded for readability; exact values in CSV.

| Operation | Median (µs) | Mean (µs) | Std (µs) |
|-----------|-------------|-----------|---------|
| BF2E GetEuiccChallenge | 4 602.9 | 4 686.3 | 288.6 |
| BF20 GetEuiccInfo1 | 40 163 | 40 202 | 301.3 |
| ES9P …/initiateAuthentication | 14 084.5 | 12 531.8 | 4 268.7 |
| BF38 AuthenticateServer | **2 959 414.5** | **3 016 360.7** | 288 518.4 |
| ES9P …/authenticateClient | 32 367.5 | 32 427.4 | 7 881.0 |
| BF21 PrepareDownload | **3 707 377.5** | **3 707 393.6** | 12 973.2 |
| ES9P …/getBoundProfilePackage | 20 533 | 21 207.8 | 6 127.1 |

**BF36** (`LoadBPP_seg0` … `seg17`): values in CSV are still **gross** BENCH; per-segment medians range from about **1.7 ms** to **3.79 s** with high variability; see `summary_stats.csv`.

95% CI half-widths for the **mean** are in `summary_stats.csv` (µs).

## Top up to 200 usable sessions

1. Stop **osmo-smdpp** (free **:8000**) and optionally nginx if you restart everything.
2. Remove the file-backed session DB (recreates on next start):  
   `rm -f pysim/smdpp-data/sm-dp-sessions-NIST`
3. From repo root: **`bash scripts/start_stack.sh`** (confirms **`SMDPP_DATA_DIR`** → bundled `smdpp-data`).
4. Re-run only failed slots:  
   `python3 thesis_experiments/exp2_classical_apdu_baseline/scripts/run_sessions.py --start 177 --iterations 24`  
   This overwrites `raw/session_177.log` … `session_200.log` while preserving **001–176**.
5. Re-run **`python3 …/scripts/analyse.py`**.

`--start` / `--iterations` were added to `run_sessions.py` for this **partial re-run** workflow.

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

1. **Hardware:** Run the **Top up** block when the eUICC and stack are available until `alpha_anchors.txt` reports **200 / 200** usable sessions.
2. Re-run analysis with ECDH split:  
   `python3 scripts/analyse.py … --smdp2-verify-us <µs>`
3. Optional: capture per-**BF36** segment Lc (or a justified `_default_per_segment`) if you need net times for load-BPP bars.
4. Install **matplotlib** and re-run `analyse.py` to refresh **`figures/figure6_apdu_breakdown.png`**.

## Demos / fixtures

`fixtures/session_*.log` are **synthetic** logs for parser checks only; they are **not** part of the hardware dataset.
