# Experiment 6: ECDH Ephemeral Key APDU Capture

**Date:** 2026-04-06  
**Status:** Complete

## Summary

During a PQ-TLS protected SGP.22 provisioning session, the ECDH ephemeral public keys `otPK.EUICC.ECKA` and `otPK.DP.ECKA` were observed in plaintext in the eUICC-to-LPA APDU traffic, confirming that PQ-TLS on the ES9+ channel does not protect the ECDH key agreement from an HNDL adversary with access to the local PC/SC interface.

## Setup

- **eUICC:** sysmocom C2T (EID `89049044900000000000000000116517`)
- **Reader:** HID Omnikey 3x21 (USB; `usbmon` not required when using `LPAC_APDU_DEBUG`)
- **lpac:** `2.3.0.r451.c0f585f30855` (from `lpac version`)
- **nginx:** `nginx/1.26.3` (PQ build under `nginx/pq_build/`)
- **OpenSSL (PQ TLS / libcurl for lpac):** OpenSSL 3.6.0 (Homebrew: `/home/linuxbrew/.linuxbrew/opt/openssl`)
- **TLS cipher suite (record layer):** `TLS_AES_256_GCM_SHA384`
- **TLS 1.3 key share (KEM):** `X25519MLKEM768` (confirmed via `openssl s_client -groups X25519MLKEM768`)
- **Peer signature (server cert):** `mldsa44`

## Key findings

- **otPK.EUICC.ECKA:** in PrepareDownload response (`BF21`); tag `5F49`; byte offset **30** within the APDU **Data** hex (start of `04||X||Y`). Raw APDU hex: `extracted/apdu_euiccsigned2.txt`
- **otPK.DP.ECKA:** in Load Bound Profile Package command (`BF36`); tag `5F49` (`smdpOtpk`); byte offset **51** within the APDU **Data** hex. Raw APDU hex: `extracted/apdu_boundbody.txt`
- **EC key format:** `04 || X || Y` (65 bytes, uncompressed P-256)

## Reproducing the capture

From repo root, with reader + stack (`scripts/start_stack.sh`) and only the benchmark osmo-smdpp on `:8000`:

```bash
export LPAC_BUILD="$PWD/lpac/build"
# lpac's curl uses system libssl unless OpenSSL 3.6+ is prepended:
export LD_LIBRARY_PATH="/home/linuxbrew/.linuxbrew/opt/openssl/lib:${LPAC_BUILD}:${LD_LIBRARY_PATH:-}"

# Remove test profile if present (same ICCID as UPP)
"$LPAC_BUILD/src/lpac" profile delete 89000123456789012341 2>/dev/null || true

LPAC_APDU_DEBUG=1 "$LPAC_BUILD/src/lpac" profile download \
  -s testsmdpplus1.example.com:8444 -m TS48v1_A \
  2>thesis_experiments/exp6_ecdh_capture/raw/apdu_debug.txt

python3 scripts/extract_keys.py
./.venv-bench/bin/python scripts/gen_figures.py
```

## Files

| Path | Description |
|------|-------------|
| `raw/apdu_debug.txt` | Full `LPAC_APDU_DEBUG` stderr for one PQ-TLS download |
| `extracted/apdu_euiccsigned2.txt` | `BF21` response APDU payload (hex) |
| `extracted/apdu_boundbody.txt` | `BF36` command APDU payload (hex) |
| `extracted/otPK_EUICC_ECKA_bytes.txt` | 130 hex chars, uncompressed point |
| `extracted/otPK_DP_ECKA_bytes.txt` | 130 hex chars, uncompressed point |
| `figures/panel_left_pqtls_handshake.png` | PQ-TLS facts (`openssl s_client`) |
| `figures/panel_right_ecdh_plaintext.png` | Hex dump of `BF21` with EUICC OTC key highlighted |
| `notes.md` | Capture notes and offsets |

## Scripts

- [`scripts/extract_keys.py`](../../scripts/extract_keys.py) — parse `apdu_debug.txt`, write `extracted/` + `notes.md`
- [`scripts/gen_figures.py`](../../scripts/gen_figures.py) — build both PNGs (requires `.venv-bench` for matplotlib)
