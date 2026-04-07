# Experiment 2: Classical APDU Baseline — Full Session Timing

## Goal
Measure complete per-APDU timing for a full SGP.22 provisioning session under configuration (a) against the **real sysmocom eUICC C2T** over PC/SC. This is the classical ground truth that all normalisation and comparison is anchored to. Every α value in Experiment 14, every net eUICC computation time, and every projected PQC latency depends on getting this right.

---

## Critical Distinction from Experiment 5

Experiment 5 measured timing on the **software eUICC** (v-euicc-daemon on x86_64). Experiment 2 measures timing on the **real sysmocom eUICC C2T** over HID Omnikey PC/SC. These are completely different platforms. The real eUICC results are what get subtracted using the T_PCSC model and become T_eUICC(op_i) in the normalisation formula.

Do not mix the two datasets. Experiment 5 timing deltas are **not** valid inputs for splitting BF21 on real silicon; use them only as informal sanity checks if at all.

---

## Hardware and Software Required

- Host Ubuntu machine
- sysmocom eUICC C2T
- HID Omnikey 3x21 reader
- USB cable (eUICC to host)
- lpac with BENCH markers enabled (real PC/SC mode, not socket mode)
- osmo-smdpp + nginx on port 8443 (classical TLS 1.3)
- Homebrew OpenSSL in LD_LIBRARY_PATH (same as Experiment 6 setup)

---

## Key Difference from Experiment 5 Setup

Experiment 5 used:
```bash
LPAC_APDU=socket ./build/lpac/src/lpac ...
```

Experiment 2 uses the real PC/SC path:
```bash
export LD_LIBRARY_PATH="/home/linuxbrew/.linuxbrew/opt/openssl/lib:${LD_LIBRARY_PATH:-}"
lpac profile download ...
# NO LPAC_APDU=socket
# lpac talks to the real eUICC via HID Omnikey
```

---

## Folder Structure

```
thesis_experiments/
│
├── exp2_classical_apdu_baseline/
│   ├── raw/
│   │   ├── session_001.log          # merged stdout+stderr per iteration
│   │   ├── session_002.log
│   │   ├── ...
│   │   ├── session_200.log
│   │   └── run_log.txt              # console copy from run_sessions.py
│   ├── processed/
│   │   ├── pcsc_model.json         # a, b from Experiment 1
│   │   ├── apdu_timings_raw.csv
│   │   ├── apdu_timings_net.csv     # after PC/SC subtraction where Lc is known
│   │   ├── summary_stats.csv
│   │   └── alpha_anchors.txt
│   ├── figures/
│   │   └── figure6_apdu_breakdown.png
│   ├── scripts/
│   │   ├── run_sessions.py          # driver (PC/SC, cooldown, disable+delete)
│   │   ├── analyse.py
│   │   └── payload_sizes_ref.json   # Lc per BENCH row; fill after APDU debug capture
│   ├── notes.md
│   └── README.md
```

---

## BENCH line format (actual lpac)

lpac prints **pipe-separated** lines on stderr (merged into session logs with stdout):

```
BENCH|<tag>|<name>|<duration_us>|<rv>
```

Examples:
```
BENCH|BF38|AuthenticateServer|3121000|0
BENCH|BF21|PrepareDownload|4075000|0
BENCH|BF36|LoadBPP_seg0|892000|0
BENCH|ES9P|/gsma/rsp2/es9plus/authenticateClient|150000|0
```

If your tree also emits `BENCH|ES10X|ES10_chunkN|...`, do **not** apply PC/SC subtraction twice to both ES10X chunks and the enclosing BF21/BF36 timing. `analyse.py` ignores `ES10X` rows by default and uses high-level BF* / ES9P rows only.

---

## Operations in a successful `lpac profile download`

These match `lpac/src/applet/profile/download.c`. There is **no BF30** and no `handleNotification` ES9+ call on the **success** path (`profile download` does not run the notification applets).

| BENCH tag | name (exact string) | Role |
|-----------|---------------------|------|
| BF2E | GetEuiccChallenge | Challenge |
| BF20 | GetEuiccInfo1 | EUICCInfo1 |
| ES9P | /gsma/rsp2/es9plus/initiateAuthentication | SM-DP+ round-trip |
| BF38 | AuthenticateServer | eUICC verifies server |
| ES9P | /gsma/rsp2/es9plus/authenticateClient | SM-DP+ round-trip; supplies smdpSigned2 material |
| BF21 | PrepareDownload | smdpSigned2 verify + ECDH keygen on eUICC |
| ES9P | /gsma/rsp2/es9plus/getBoundProfilePackage | SM-DP+ round-trip |
| BF36 | LoadBPP_seg0, LoadBPP_seg1, … | Load BPP segments |

Failure / cancel paths may add BF41 and cancelSession; success does not.

**α anchors (after PC/SC subtraction where Lc is known):**

- **T_eUICC(ECDSA_verify)** — use median **net** time for **BF38** (interpretation in thesis: dominated by chain + server signature verification on-card; not a single-ECDSA primitive).
- **T_eUICC(ECDH_keygen)** — BF21 blends ECDSA verify (smdpSigned2) and ECDH keygen. **Primary method:** `median(BF21_net) - T_smdpSigned2_verify`, where `T_smdpSigned2_verify` comes from a separate estimate (e.g. host `host_crypto_bench`, certificate-size arg, or a conservative bound from protocol analysis). **Do not** substitute Experiment 5’s software-eUICC BF21 deltas as the primary subtractor. Record any sanity check against Exp5 separately.

---

## Pre-Experiment Checklist

- [ ] sysmocom eUICC is connected and responsive (`pcsc_scan` shows card)
- [ ] HID Omnikey reader recognized
- [ ] No other process holding the PC/SC reader (close any open pySIM sessions)
- [ ] osmo-smdpp running on port 8443 with classical TLS 1.3 (ECDSA-P256 certificate, X25519 key exchange)
- [ ] nginx fronting osmo-smdpp on port 8443
- [ ] `LPAC_BENCH=1` and BENCH lines visible (see below)
- [ ] LD_LIBRARY_PATH set for Homebrew OpenSSL
- [ ] Same matching ID / profile can be re-provisioned after **disable + delete**

Confirm BENCH markers:
```bash
export LD_LIBRARY_PATH="/home/linuxbrew/.linuxbrew/opt/openssl/lib:${LD_LIBRARY_PATH:-}"
export LPAC_BENCH=1
lpac profile download -s testsmdpplus1.example.com:8443 -m <profile_id> 2>&1 | grep '^BENCH|'
```

---

## Procedure

### Step 1 — Payload sizes (optional but recommended for net times)

Fill `scripts/payload_sizes_ref.json` with Lc (command data length in bytes) per tag/name, from one run with `LPAC_APDU_DEBUG=1` or equivalent. Until then, `analyse.py` keeps `duration_net_us = duration_us` for rows without sizes and states this in `alpha_anchors.txt`.

### Step 2 — Run sessions

```bash
cd thesis_experiments/exp2_classical_apdu_baseline
../venv/bin/python scripts/run_sessions.py --iterations 200
# or: python3 scripts/run_sessions.py ...
```

The script:
- Runs `lpac profile download` with **PC/SC** (no `LPAC_APDU=socket`)
- Saves merged stdout+stderr to `raw/session_NNN.log`
- On **success**, parses the final JSON line (`type":"lpa"`, `message":"success`) for **iccid**, then runs `lpac profile disable <iccid>` and `lpac profile delete <iccid>`
- Cooldown 15 s every 50 iterations
- Logs failures and continues

### Step 3 — Analysis

```bash
python3 scripts/analyse.py \
  --raw-dir raw \
  --pcsc-model processed/pcsc_model.json \
  --payload-sizes scripts/payload_sizes_ref.json \
  --smdp2-verify-us <estimate_us>   # optional; for ECDH anchor line
```

Produces `processed/apdu_timings_*.csv`, `summary_stats.csv`, `alpha_anchors.txt`, and `figures/figure6_apdu_breakdown.png`.

### Step 4 — PC/SC model

Default model in `processed/pcsc_model.json` matches Experiment 1 extended regression:

`T_PCSC(n) = a + b*n` (µs) with `a ≈ 1073.75`, `b ≈ 62.30`.

---

## Data to Record

| Data Item | File |
|---|---|
| Per-session logs | `raw/session_*.log` |
| Console log | `raw/run_log.txt` |
| Raw / net tables | `processed/apdu_timings_raw.csv`, `apdu_timings_net.csv` |
| Summary | `processed/summary_stats.csv` |
| Anchors | `processed/alpha_anchors.txt` |
| Figure | `figures/figure6_apdu_breakdown.png` |

---

## How This Feeds Experiment 14

```
α_ECDSA = T_eUICC(ECDSA_verify) / T_STM32(ECDSA_verify)
α_ECDH  = T_eUICC(ECDH_keygen)  / T_STM32(ECDH_keygen)
```

T_STM32 from Experiment 7. Use **medians** for anchors on real silicon.

---

## Notes on Timing Stability

The real eUICC timing will have more variance than the software eUICC in Experiment 5. Expect USB jitter, occasional outliers, and mild thermal drift. Report **medians** for α anchors.

---

## Notes.md template

```markdown
# Experiment 2: Classical APDU Baseline Notes

**Date:**
**Status:** [ ] In Progress / [ ] Complete

## Setup
- eUICC: sysmocom C2T, firmware: ___
- Reader: HID Omnikey 3x21
- lpac: ___
- osmo-smdpp: 8443 (classical TLS 1.3)
- Iterations attempted: ___
- Failed iterations: ___

## PC/SC model
- Source: processed/pcsc_model.json (Experiment 1)

## Key medians (net, where corrected)
- BF2E, BF20, BF38, BF21, ES9P endpoints, BF36 segments: ___

## α anchors
- T_eUICC(ECDSA_verify) proxy (BF38 net median): ___ µs
- T_smdpSigned2_verify subtractor used for ECDH: ___ µs
- T_eUICC(ECDH_keygen): ___ µs
```

---

## README.md template

```markdown
# Experiment 2: Classical APDU Baseline

Classical full-session timings on **real** sysmocom eUICC via PC/SC.
Not Experiment 5 (software eUICC).

## Run
`python3 scripts/run_sessions.py` then `python3 scripts/analyse.py`

## Outputs
See `processed/` and `figures/`.
```
