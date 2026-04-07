# Experiment 5 — Sub-operation isolation (BF21 PrepareDownload)

## What was measured

- **Config (a):** virtual-rsp-2 with **ECDH P-256** one-time key in BF21 (baseline).
- **Config (c):** same stack with **ML-KEM-768** keypair in BF21 (liboqs), SM-DP+ encapsulation in `getBoundProfilePackage`, v-euicc decapsulation in BF23.
- **Metric:** `BENCH|BF21|PrepareDownload|<us>|…` from instrumented **virtual-rsp-2** `lpac` (`LPAC_BENCH=1`, `LPAC_APDU=socket`), plus wall time per `profile download`.

## Results (n=200 each)

| Series | Median BF21 RTT (μs) | Notes |
|--------|----------------------|--------|
| (a) ECDH | 494403.5 | see `processed/ecdh_keygen_latency.txt` |
| (c) ML-KEM | 494956.5 | see `processed/mlkem_keygen_latency.txt` |
| **Median delta (c−a)** | **553.0 μs** | incremental BF21 cost vs ECDH path |

Full-session wall time (median): (a) ≈ 11254 ms, (c) ≈ 12018 ms — ML-KEM stack is slower end-to-end; BF21 delta alone does not capture BF23 encaps/decaps and Python work.

## Dependencies

- **liboqs** built/installed with CMake prefix e.g. `$HOME/.local` (version used: **0.15.0**).
- **liboqs-python** in `virtual-rsp-2/pysim/venv`.
- Rebuild `virtual-rsp-2` with `-DCMAKE_PREFIX_PATH=$HOME/.local` so `find_package(liboqs)` resolves.

## Patches (saved from `virtual-rsp-2` git tree)

- `patches/v_euicc_mlkem_patch.diff` — v-euicc + lpac bench hooks (`v-euicc/`, `lpac/euicc/`).
- `patches/osmo_smdpp_mlkem_patch.diff` — `pysim/osmo-smdpp.py`.

## Reproduce

1. Build/install liboqs; rebuild virtual-rsp-2 with `CMAKE_PREFIX_PATH` pointing at the install prefix.
2. **Config (a) (ECDH BF21):** `export VRSP_BF21_MODE=ecdh`, then `scripts/start_vrsp_stack.sh`. Run `python3 scripts/run_sessions.py --config a --iterations 200`. `scripts/stop_vrsp_stack.sh`.
3. **Config (c) (ML-KEM BF21):** `export VRSP_BF21_MODE=mlkem` (or unset), start stack again, then `python3 scripts/run_sessions.py --config c --iterations 200`. Stop stack.
   - Or one shot: `scripts/run_exp5_full_rerun.sh` (archives existing `raw/*.csv` first).
4. Analysis: `python3 scripts/analyse.py` (for plots, use a venv with **matplotlib**, e.g. `python3 -m venv .venv && .venv/bin/pip install matplotlib && .venv/bin/python scripts/analyse.py`).

`VIRTUAL_RSP2` overrides the virtual-rsp-2 tree if not at `/home/jhubuntu/projects/virtual-rsp-2`.

## Figures (`figures/`)

| File | Role |
|------|------|
| `suboperation_timing_comparison.png` | **Figure A** — BF21 RTT violins (a) vs (c); annotations stress near-overlap at full scale. |
| `fig_b_bf21_paired_difference.png` | **Figure B** — paired Δ BF21 per iteration, \(BF21(c)_i - BF21(a)_i\). |
| `fig_c_fullsession_wall_time.png` | **Figure C** — full `profile download` wall time (ms), session-level overhead. |

## Caveat

Measurements are on a **software v-euicc (x86_64)** and host-side SM-DP+; absolute μs values are not representative of smartcard-class secure elements.
