# Experiment 6: ECDH Ephemeral Key APDU Capture — HNDL Non-Coverage Proof

## Goal
Empirically demonstrate that PQ-TLS on the ES9+ channel does not protect the ECDH ephemeral public keys because they transit the eUICC-to-LPA APDU channel in plaintext. This transforms the formal verification result into a tangible, visually compelling empirical observation.

---

## Hardware and Software Required
- Host Ubuntu machine
- sysmocom eUICC C2T
- HID Omnikey 3x21 reader
- USB cable (eUICC to host)
- lpac (already running on host)
- osmo-smdpp + nginx on port 8444 (PQ-TLS already configured)
- Wireshark installed on Ubuntu

---

## Folder Structure

```
thesis_experiments/
│
├── exp1_pcsc_calibration/
│   └── (later)
│
├── exp2_classical_apdu_baseline/
│   └── (later)
│
├── exp5_suboperation_isolation/
│   └── (later)
│
├── exp6_ecdh_capture/
│   ├── raw/
│   │   ├── session_capture.pcapng        # full Wireshark capture file
│   │   └── session_capture.pcapng.notes  # your annotations during capture
│   ├── extracted/
│   │   ├── apdu_euiccsigned2.txt         # hex dump of euiccSigned2 APDU
│   │   ├── apdu_boundbody.txt            # hex dump of bind_body APDU
│   │   ├── otPK_EUICC_ECKA_bytes.txt     # extracted EC public key bytes
│   │   └── otPK_DP_ECKA_bytes.txt        # extracted EC public key bytes
│   ├── figures/
│   │   ├── panel_left_pqtls_handshake.png   # TLS handshake showing X25519MLKEM768
│   │   └── panel_right_ecdh_plaintext.png   # APDU showing EC key in plaintext
│   ├── notes.md                          # your observations during the experiment
│   └── README.md                         # experiment summary and findings
│
├── exp7_stm32_classical/
│   └── (after board arrives)
│
└── shared/
    ├── config/
    │   ├── nginx_classical.conf          # port 8443 config
    │   └── nginx_pqtls.conf              # port 8444 config
    └── scripts/
        └── (shared helper scripts)
```

---

## Pre-Experiment Checklist

Before starting, confirm all of these are working:

- [ ] nginx is running on port 8444 with ML-DSA-44 certificate and X25519MLKEM768
- [ ] lpac can successfully complete a provisioning session against port 8444
- [ ] Wireshark is installed (`sudo apt install wireshark`)
- [ ] You have permission to capture USB traffic (`sudo usermod -aG wireshark $USER`, then log out and back in)
- [ ] The HID Omnikey reader is connected and the eUICC is responsive

---

## Procedure

### Step 1 — Identify your USB interface in Wireshark

Open Wireshark. In the interface list you will see entries like `usbmon0`, `usbmon1`, `usbmon2`. The HID Omnikey reader will appear on one of these. To find the right one:

```bash
lsusb
# Look for the HID Omnikey entry, note the Bus number
# Bus 001 = usbmon1, Bus 002 = usbmon2, etc.
```

If `usbmon` interfaces do not appear, load the kernel module first:

```bash
sudo modprobe usbmon
```

---

### Step 2 — Enable the CCID dissector in Wireshark

In Wireshark go to: **Analyze → Enabled Protocols**, search for `CCID`, and make sure it is checked. This tells Wireshark to decode the raw USB packets as smart card APDU traffic so you can read the APDU payloads directly.

---

### Step 3 — Start the capture

In Wireshark, select the correct `usbmonX` interface and click the blue shark fin to start capturing. Do not run the lpac session yet.

Save the capture file immediately to:
```
thesis_experiments/exp6_ecdh_capture/raw/session_capture.pcapng
```

---

### Step 4 — Run one lpac provisioning session

In a terminal, run a single complete provisioning session against port 8444 (PQ-TLS):

```bash
lpac profile download \
  --server https://localhost:8444 \
  --activation-code <your_test_code>
```

Wait for the session to complete successfully. One session is enough — you only need one clean capture.

---

### Step 5 — Stop the capture and save

Stop the Wireshark capture. Make sure the file is saved to the `raw/` folder.

---

### Step 6 — Locate the TLS handshake in the capture

In Wireshark, filter for TLS traffic:

```
tls
```

Find the `ClientHello` and `ServerHello` packets from the lpac-to-nginx connection on port 8444. In the `ServerHello` you should see the negotiated cipher suite — look for `X25519MLKEM768` confirming PQ-TLS was active. Take a screenshot of this packet and save it as:

```
thesis_experiments/exp6_ecdh_capture/figures/panel_left_pqtls_handshake.png
```

---

### Step 7 — Locate the ECDH ephemeral public keys in the APDU traffic

In Wireshark, filter for CCID traffic on the USB interface:

```
ccid
```

You are looking for two specific APDU exchanges:

**Target 1 — euiccSigned2 (step 22)**
This is the `AuthenticateClient` exchange. The eUICC returns `euiccSigned2` which contains `otPK.EUICC.ECKA` — the eUICC's ephemeral EC public key. For P-256 this is an uncompressed EC point: a `04` prefix byte followed by 64 bytes (32 bytes X coordinate, 32 bytes Y coordinate), total 65 bytes.

**Target 2 — bind_body relay (step 26)**
This is within the `GetBoundProfilePackage` or `LoadBPP` exchange. The SM-DP+ relays `otPK.DP.ECKA` — the SM-DP+ ephemeral public key — to the eUICC. Same format: `04` prefix + 64 bytes.

For each target, note the byte offset in the APDU payload where the `04` prefix appears and copy the 65 bytes. Save them to:

```
thesis_experiments/exp6_ecdh_capture/extracted/otPK_EUICC_ECKA_bytes.txt
thesis_experiments/exp6_ecdh_capture/extracted/otPK_DP_ECKA_bytes.txt
```

Take an annotated screenshot of the APDU payload with the EC key bytes highlighted and save as:

```
thesis_experiments/exp6_ecdh_capture/figures/panel_right_ecdh_plaintext.png
```

---

### Step 8 — Write your notes

Open `thesis_experiments/exp6_ecdh_capture/notes.md` and record:

- The USB bus number used
- The TLS cipher suite confirmed in the ServerHello
- The byte offset of `otPK.EUICC.ECKA` in the euiccSigned2 APDU
- The byte offset of `otPK.DP.ECKA` in the bind_body APDU
- Whether the EC key bytes were visible without any decryption
- Any unexpected observations

---

## Data to Record

| Data Item | File Location |
|---|---|
| Full Wireshark capture | `raw/session_capture.pcapng` |
| TLS handshake screenshot (PQ-TLS confirmation) | `figures/panel_left_pqtls_handshake.png` |
| APDU plaintext screenshot (EC key visible) | `figures/panel_right_ecdh_plaintext.png` |
| otPK.EUICC.ECKA hex bytes | `extracted/otPK_EUICC_ECKA_bytes.txt` |
| otPK.DP.ECKA hex bytes | `extracted/otPK_DP_ECKA_bytes.txt` |
| Raw APDU hex dumps | `extracted/apdu_euiccsigned2.txt`, `extracted/apdu_boundbody.txt` |
| Observations and byte offsets | `notes.md` |

---

## Expected Output

A two-panel figure for Section VI-G of the paper:

**Left panel** — Wireshark TLS dissection showing the negotiated X25519MLKEM768 cipher suite, confirming PQ-TLS was active on the ES9+ channel during the session.

**Right panel** — Wireshark CCID dissection showing the APDU payload containing the EC public key bytes in plaintext on the local eUICC-to-LPA interface, during the same PQ-TLS protected session.

Together these two panels make the architectural argument visually undeniable: PQ-TLS is active on the network channel, yet the ECDH ephemeral keys bypass it entirely via the local APDU interface. This is Figure 8 in the revised paper, placed in the new Section VI-G.

---

## README.md Template

Create `thesis_experiments/exp6_ecdh_capture/README.md` with this structure:

```markdown
# Experiment 6: ECDH Ephemeral Key APDU Capture

**Date:** 
**Status:** [ ] In Progress / [ ] Complete

## Summary
One-sentence finding: During a PQ-TLS protected SGP.22 provisioning session,
the ECDH ephemeral public keys otPK.EUICC.ECKA and otPK.DP.ECKA were
observed in plaintext in the eUICC-to-LPA APDU traffic, confirming that
PQ-TLS on the ES9+ channel does not protect the ECDH key agreement from
an HNDL adversary with access to the local interface.

## Setup
- eUICC: sysmocom C2T, firmware version: ___
- Reader: HID Omnikey 3x21
- lpac version: ___
- nginx/openssl version: ___
- TLS cipher suite confirmed: ___

## Key Findings
- otPK.EUICC.ECKA location: APDU ___, byte offset ___
- otPK.DP.ECKA location: APDU ___, byte offset ___
- EC key format confirmed: 04 || X || Y (uncompressed P-256 point)

## Files
- raw/session_capture.pcapng
- figures/panel_left_pqtls_handshake.png
- figures/panel_right_ecdh_plaintext.png
- extracted/otPK_EUICC_ECKA_bytes.txt
- extracted/otPK_DP_ECKA_bytes.txt

## Paper Section
Section VI-G, Figure 8
```