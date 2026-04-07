## What Happened and Why

The failure is a **certificate trust chain mismatch**, not a hardware or code problem. The sysmocom eUICC C2T has a specific CI root provisioned into its firmware — the SGP.26 test CI with key ID `f54172bdf98a95d65cbeb88a38a1c11d800a85c3` that we saw in the euiccInfo1 output on Day 1. The osmo-smdpp instance from virtual-rsp-2 generates its **own** CI certificates at setup time that are completely different from the SGP.26 test PKI. When the eUICC receives the DPauth certificate chain from virtual-rsp-2's osmo-smdpp it checks the issuer against its provisioned CI root, finds no match, and rejects at `initiateAuthentication`.

This is exactly the same reason the virtual-rsp-2 has its CI PKID patching logic in `test-all.sh` — but that patching modifies the **v-euicc C source** to trust whatever CI the test stack generated. It works for the software eUICC because that code can be recompiled. The real sysmocom eUICC cannot be recompiled.

---

## The Partial Data Is Still Useful

The three operations that did complete are not wasted:

| Operation | Median net | Value for paper |
|---|---|---|
| BF2E GetEuiccChallenge | ~6.0 ms | Challenge generation baseline |
| BF20 GetEuiccInfo1 | ~41.4 ms | Info retrieval baseline |
| ES9P initiateAuthentication | ~4.5 ms | ES9+ first round trip |

BF20 GetEuiccInfo1 at 41.4 ms is a real eUICC measurement. This can appear in Table 9 as confirmed ground-truth timing for the initial discovery steps even if the full session did not complete.

---

## Root Cause Diagnosis

You have two separate osmo-smdpp setups:

**Setup A — virtual-rsp-2 osmo-smdpp** (what you just ran against)
- Generates its own SGP.26-style test PKI at `pysim/smdpp-data/generated/`
- CI key ID changes every time `generate_smdpp_certs.py` is run
- Works perfectly with the software v-euicc-daemon (which gets recompiled with the matching PKID)
- Does NOT work with the real sysmocom eUICC (its CI root is fixed in firmware)

**Setup B — original osmo-smdpp** (what produced the original paper's 200 successful sessions)
- Must have been using certificates aligned with the SGP.26 test CI that the sysmocom eUICC trusts
- This is the setup that made Experiments 3 and 6 work with the real eUICC

---

## The Fix

You need to identify and restore the certificate setup that was working for the original paper. There are two paths:

**Path 1 — Use the original working osmo-smdpp setup (fastest)**

Check whether you have a separate osmo-smdpp installation outside virtual-rsp-2 that was used for the original paper benchmarks. This would have certificates signed by the SGP.26 test CI matching `f54172bdf98a95d65cbeb88a38a1c11d800a85c3`.

```bash
# Check if there is another osmo-smdpp instance or cert directory
find ~ -name "CERT_S_SM_DP_TLS_NIST.pem" 2>/dev/null
find ~ -name "smdpp.db" 2>/dev/null
# Look for a cert directory that has a CI cert matching the eUICC key ID
openssl x509 -inform DER -in <found_CI_cert> -noout -text | grep -A1 "Subject Key Identifier"
```

If you find it, point lpac at that osmo-smdpp instance (or start it on port 8443) and re-run.

**Path 2 — Generate SGP.26-aligned certificates for virtual-rsp-2**

This requires obtaining the SGP.26 test CI private key so you can re-issue the DPauth certificate signed by the CI root that the eUICC trusts. The GSMA SGP.26 test PKI private keys are available in the GSMA SGP.26 test tools package. If you have access to this package:

```bash
# Replace virtual-rsp-2's generated CI cert with the SGP.26 test CI
# Then re-issue DPauth signed by that CI
# Then rebuild v-euicc-daemon (CI PKID patch will update it)
```

---

## Recommended Action for Today

**Do Path 1 first.** Check whether the original working setup still exists on your machine. The original paper had 200 successful sessions, so somewhere on your machine there is an osmo-smdpp configuration that the sysmocom eUICC accepts. Finding it is a 15-minute search that avoids significant rework.

Run this search now:

```bash
# Find all smdpp certificate directories
find ~ -name "CERT_S_SM_DP_TLS_NIST*" 2>/dev/null
find ~ -name "CERT_S_SM_DP_AUTH*" 2>/dev/null

# Find all osmo-smdpp.py instances
find ~ -name "osmo-smdpp.py" 2>/dev/null

# Check git history if this is a git repo
# to see if there was a different cert setup previously
```

Tell me what you find and I will give you the exact next step. If the original setup still exists this is a 30-minute fix and Experiment 2 can be re-run today.

---

## What This Does Not Affect

Experiments 1, 5, and 6 are all still valid. Experiment 5 intentionally used the software eUICC so it is unaffected. Experiment 6 captured APDU traffic from a session that did complete — go back and check whether that session used the real eUICC or the software eUICC. If Experiment 6 completed a full session with the real eUICC, whatever osmo-smdpp instance it used is the one you need for Experiment 2.

---

## Update notes.md

```markdown
## Root Cause

Certificate trust chain mismatch. The sysmocom eUICC C2T trusts
CI key ID f54172bdf98a95d65cbeb88a38a1c11d800a85c3 (SGP.26 test CI).
virtual-rsp-2 osmo-smdpp generates its own CI certificates that do
not match this key ID. The eUICC rejects the DPauth chain at
initiateAuthentication.

## Fix Required
Identify the original osmo-smdpp setup that was used for the
original paper's 200 successful sessions. That setup has
certificates aligned with the eUICC's SGP.26 test CI.

## Partial Data Preserved
BF2E: 6.0 ms, BF20: 41.4 ms, ES9P initiate: 4.5 ms
These are real eUICC measurements and can appear in Table 9.

## Status
Blocked until certificate alignment is resolved.
```