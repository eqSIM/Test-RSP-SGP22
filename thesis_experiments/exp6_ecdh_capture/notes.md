# Experiment 6 — capture notes

**Date:** 2026-04-06

## TLS / host

- ES9+ target during capture: `testsmdpplus1.example.com:8444` (PQ-TLS)
- On this host, lpac requires Homebrew OpenSSL in `LD_LIBRARY_PATH` for ML-KEM handshake, e.g.:
  `export LD_LIBRARY_PATH=/home/linuxbrew/.linuxbrew/opt/openssl/lib:$LPAC_BUILD:$LD_LIBRARY_PATH`

## APDU sources (from `raw/apdu_debug.txt`)

| Item | Description |
|------|-------------|
| PrepareDownload response | First RX line with `BF21` containing `euiccOtpk` (tag `5F49`) |
| Load BPP / Initialise SC | First TX line with `BF36` containing SM-DP+ `smdpOtpk` (tag `5F49`) |

## Byte offsets (within the **Data:** hex field only)

- **otPK.EUICC.ECKA** — start of uncompressed point (`04`): hex character offset **60** (byte offset 30)
- **otPK.DP.ECKA** — start of uncompressed point (`04`): hex character offset **102** (byte offset 51)

## Keys (130 hex chars = 65 bytes, format `04 || X || Y`)

### otPK.EUICC.ECKA
```
04471d371ca66b715adad96fbb08ff2388102234ac824c38b280a02254706513738a8e032d3b955045763786a56ff3f045c9ae20c62ddf32a37a98e5a2f06f04b7
```

### otPK.DP.ECKA
```
040200e1d3c97b9ed5e99a7d6bcc99d677858cd153a5e9dff25ed743aaee7a57ff96175cc9fb6cd6ceac3ff3cff5b54e9f8029e35908111927234933b5117e9b53
```

## Observation

Both ephemeral ECDH public keys are visible in the PC/SC APDU hex without decryption, while ES9+ uses PQ-TLS (`X25519MLKEM768`) on the network path.


---

# Experiment 6 — Findings and Insights

## Core Finding
Both ECDH ephemeral public keys were recovered in plaintext from PC/SC APDU traffic during an active PQ-TLS session, empirically confirming the ProVerif formal verification result that configuration (b) provides no HNDL protection at the application layer.

## Key Data Points
- `otPK.EUICC.ECKA` located in BF21 (PrepareDownload response), tag `5F49`, byte offset 30
- `otPK.DP.ECKA` located in BF36 (Load BPP), tag `5F49`, byte offset 51
- Both are valid uncompressed P-256 points (`04 || X || Y`, 65 bytes each)
- ES9+ channel confirmed using X25519MLKEM768 during the same session
- No decryption required to extract either key

## Architectural Insight
The result visually separates two distinct channels that are easy to conflate when reading the protocol spec. PQ-TLS protects the ES9+ network segment between LPA and SM-DP+. The ECDH key exchange happens on the ES10c APDU segment between eUICC and LPA, which is a local PC/SC interface that never enters the TLS tunnel. An HNDL adversary does not need to break or bypass PQ-TLS at all — they observe the local USB traffic to harvest both public keys and apply the Shor oracle offline.

## Formal Verification Connection
This empirical observation directly validates the ProVerif quantum attacker result. In the formal model, the Shor oracle fires on public keys visible on the public channel. This experiment shows those keys are literally visible as plaintext bytes in the APDU stream on the local interface. The gap between the formal model and physical reality is zero for this finding.

## What This Means for the Paper
Configuration (b) must not be described as an HNDL mitigation for session key confidentiality anywhere in the paper. The current Section IV-B text and Section VII-B Phase 1 description both need the correction drafted earlier. The word "HNDL" should only appear in association with configuration (b) when explicitly stating it does not close the HNDL window. The only honest framing for configuration (b) is: it hardens the ES9+ transport channel and establishes server-side PQC infrastructure, but the ECDH key exchange remains exposed on the local interface.

## Unexpected Observations
None. The result was exactly as the formal model predicted. This is itself notable — the symbolic ProVerif model accurately predicted a real physical observation with no discrepancy. It reinforces the validity of the formal methodology.

## Limitations of This Finding
The capture was performed on a PC/SC testbed where the eUICC-to-LPA channel is a USB interface accessible to the host. On a production smartphone, the ES10c channel is an internal bus between the eUICC and the application processor. Physical access to that internal bus requires either a compromised OS, a rogue LPA application, or hardware-level interception. The threat is therefore more realistic on IoT M2M devices where the local interface may be more exposed than on a locked-down smartphone. This nuance is worth one sentence in Section VII-C limitations.

---