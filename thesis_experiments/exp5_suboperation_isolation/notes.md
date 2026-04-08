# Exp5 notes

## liboqs

- Version **0.15.0** (from `OQS_VERSION_*` in the liboqs source tree used for the build).
- Install prefix used: `$HOME/.local` (`CMAKE_PREFIX_PATH` for CMake, `PATH`/`PKG_CONFIG_PATH` as needed).

## Key numbers (200 iterations each, 2026-04-08 rerun)

- `median BF21_us` config **(a) ECDH:** 495191.5 μs  
- `median BF21_us` config **(c) ML-KEM:** 495002.5 μs  
- **Median difference (c−a):** −189.0 μs — within measurement noise (σ ≈ 2400–3900 μs); the BF21 cost is statistically indistinguishable between the two configurations on x86_64, consistent with sub-ms keygen for both algorithms on modern hardware.

- Full `profile download` wall time medians: **(a)** ~11264 ms, **(c)** ~12005 ms — delta ~741 ms at session level, driven by ML-KEM encaps/decaps and the larger ES9+ bound_body payload.

## Instrumentation

- BF21 timing is measured in **virtual-rsp-2** `lpac` (`es10b.c` / `bench.h`), not the separate `pq-rsp-benchmarks/lpac` tree (no socket APDU driver there).

## Limitations

- **Software eUICC on x86_64** — timing is an upper bound for “pure” keygen; a real eUICC would differ widely.
- BF21 RTT includes APDU framing and daemon work, not only scalar/KEM key generation.


## Interpretation

### BF21 difference (−189 µs, within noise)
- Not a pure ML-KEM keygen microbenchmark
- BF21 RTT dominated by socket/APDU framing overhead (~495 ms); actual keygen is sub-ms on x86_64
- Measured delta (−189 µs) is within 1σ of both distributions (σ_a ≈ 2387 µs, σ_c ≈ 3937 µs)
- Conclusion: BF21 incremental cost of ML-KEM-768 vs ECDH P-256 is **statistically negligible** on x86_64 software eUICC
- As fraction of BF21 total: |−189| / 495192 = 0.04% — negligible at APDU level

### Full session difference (~741 ms)
- BF21 contribution: negligible (within noise)
- Full session overhead of 741 ms on top of 11,264 ms = 6.6% increase
- Driven by ML-KEM encaps/decaps + larger BPP payload from expanded key material
- On constrained silicon absolute times will differ but proportions should hold

### Paper claim
Config (c) protocol feasibility confirmed end-to-end (200/200 successful downloads).
BF21 incremental cost: statistically negligible on x86_64 software eUICC (within σ).
Full session overhead: ~741 ms (6.6%) — upper bound for x86_64 software eUICC.
STM32 Experiments 7-13 needed for eUICC-realistic projection.

## v-euicc crash fix (2026-04-08)

During the 2026-04-07 rerun, v-euicc-daemon crashed at iteration 36 of config (c).
Root cause: `apdu_handle_connect()` called `euicc_state_init()` (which does `memset(state, 0)`)
without first freeing existing heap allocations from the prior session. In ML-KEM mode
the per-session heap allocations are large (euicc_otpk 1184B + euicc_otsk 2400B +
smdp_otpk 1088B = 4672B per session vs 162B for ECDH), causing heap corruption after
~35 sessions. Fix: add `euicc_state_reset(state)` before `euicc_state_init(state)` in
`apdu_handle_connect()` in `v-euicc/src/apdu_handler.c`.