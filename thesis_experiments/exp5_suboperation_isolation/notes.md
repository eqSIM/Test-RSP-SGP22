# Exp5 notes

## liboqs

- Version **0.15.0** (from `OQS_VERSION_*` in the liboqs source tree used for the build).
- Install prefix used: `$HOME/.local` (`CMAKE_PREFIX_PATH` for CMake, `PATH`/`PKG_CONFIG_PATH` as needed).

## Key numbers (200 iterations)

- `median BF21_us` config **(a) ECDH:** 494403.5 μs  
- `median BF21_us` config **(c) ML-KEM:** 494956.5 μs  
- **Median difference (c−a):** 553.0 μs — interpret as incremental BF21 cost when swapping ECDH keygen for ML-KEM-768 keygen (plus any fixed encoding differences), not a bare microbenchmark of `OQS_KEM_keypair` alone.

- Full `profile download` wall time medians: **(a)** ~11254 ms, **(c)** ~12018 ms — decaps/encaps and larger payloads dominate vs the sub-ms BF21 gap.

## Instrumentation

- BF21 timing is measured in **virtual-rsp-2** `lpac` (`es10b.c` / `bench.h`), not the separate `pq-rsp-benchmarks/lpac` tree (no socket APDU driver there).

## Limitations

- **Software eUICC on x86_64** — timing is an upper bound for “pure” keygen; a real eUICC would differ widely.
- BF21 RTT includes APDU framing and daemon work, not only scalar/KEM key generation.


## Interpretation

### BF21 difference (553 µs)
- Not a pure ML-KEM keygen microbenchmark
- Captures: ML-KEM keygen + 1119 extra encoding bytes
- Estimated encoding component: ~70 µs (at 62.3 µs/byte from Exp 1)
- Estimated pure keygen component: ~480 µs on x86_64 liboqs 0.15.0
- As fraction of BF21 total: 553/494404 = 0.11% — negligible at APDU level

### Full session difference (764 ms)
- BF21 contribution: 553 µs (0.07% of full session delta)
- Remaining ~211 ms: ML-KEM encaps at step 24b + larger bind_body payload
- Full session overhead of 764 ms on top of 11,254 ms = 6.8% increase
- On constrained silicon absolute times will differ but proportions should hold

### Paper claim
Config (c) protocol feasibility confirmed end-to-end.
BF21 incremental cost: 553 µs (upper bound, x86_64 software eUICC).
Full session overhead: ~764 ms (upper bound, x86_64 software eUICC).
STM32 Experiments 7-13 needed for eUICC-realistic projection.