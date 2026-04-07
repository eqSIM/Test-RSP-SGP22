# Experiment 2 notes

## Root cause (updated)

The **correct SGP.26 CI and DPauth chain for the sysmocom C2T already live in this repo**:

`pysim/smdpp-data/certs/CertificateIssuer/CERT_CI_ECDSA_NIST.der` has Subject Key Identifier `F5:41:72:BD:…:C3` = `f54172bdf98a95d65cbeb88a38a1c11d800a85c3`, the CI key ID the eUICC trusts. `CERT_S_SM_DPauth_ECDSA_NIST.der` is issued under that CI.

The failure mode is therefore almost certainly **not** “wrong golden certs,” but **which osmo-smdpp instance nginx is talking to** and **which `smdpp-data` tree it loads**:

1. **`osmo-smdpp.py` used `DATA_DIR = './smdpp-data'` (cwd-relative).** Starting the server from another working directory could point at a different or empty tree.
2. **`scripts/start_stack.sh` skipped starting smdpp if port 8000 was already taken.** Another project’s osmo-smdpp (e.g. virtual-rsp-2 with generated PKI) may have been bound there, so nginx still proxied to the **wrong** backend.

## Fix applied in this repo

- **`pysim/osmo-smdpp.py`:** `DATA_DIR` defaults to `os.path.abspath(os.path.join(dirname(__file__), 'smdpp-data'))`, independent of cwd. Optional override: **`SMDPP_DATA_DIR`**.
- **`scripts/start_stack.sh`:** exports **`SMDPP_DATA_DIR=$PWD/pysim/smdpp-data`** (this repo’s bundled certs). If **:8000** is already in use, it prints a **warning** instead of silently skipping—stop the other process and re-run.

## What to stop (concrete)

Only **one** process should serve ES9+ on **`127.0.0.1:8000`** for this bench: **pq-rsp-benchmarks** `pysim/osmo-smdpp.py` with bundled **`smdpp-data/certs/`**.

**Do stop** any other `osmo-smdpp.py` bound to 8000, especially:

- virtual-rsp / eqSIM copies using **`-c generated`** (generated CI ≠ firmware CI on real silicon).

Inspect and kill:

```bash
ss -tlnp | grep ':8000'
# Check cmdline + cwd, e.g.:
# tr '\0' ' ' < /proc/<PID>/cmdline; readlink -f /proc/<PID>/cwd
kill <PID>    # only if it is not pq-rsp-benchmarks/pysim/osmo-smdpp.py
```

Then from repo root: **`bash scripts/start_stack.sh`**. You should see  
`DATA_DIR=/home/.../pq-rsp-benchmarks/pysim/smdpp-data` in the script output.

**Do not** need to stop nginx on **8443/8444** unless you are reconfiguring TLS; nginx can keep proxying to the new backend on 8000.

## What you should do before re-running Exp2

1. Free **:8000** as above (or rely on `start_stack.sh` warning if something re-grabs it).
2. Run **`bash scripts/start_stack.sh`** from **pq-rsp-benchmarks** and confirm **`DATA_DIR=…/pysim/smdpp-data`**.
3. Re-run **`thesis_experiments/exp2_classical_apdu_baseline/scripts/run_sessions.py`**.
4. If download fails with **`install_failed_due_to_iccid_already_exists_on_euicc`**, the runner **removes that ICCID** (disable + delete) and **retries the same iteration** once automatically.
5. After a successful install, **`profile disable`** may return **“profile not in enabled state”** (RSP profile is installed but not the **enabled** profile). That is normal; **`profile delete`** still runs and recycles the slot.

You do **not** need to hunt for alternate certificate packages unless the failure persists **after** confirming the above.

## Partial data preserved

From 200 attempts (`processed/summary_stats.csv`), medians (net = raw until Lc table is filled):

| Step | Median |
|------|--------|
| BF2E GetEuiccChallenge | ~6.0 ms |
| BF20 GetEuiccInfo1 | ~41.4 ms |
| ES9P initiateAuthentication | ~4.5 ms |

## Status

Re-run the campaign after smdpp restart with bundled `smdpp-data`. Earlier “blocked until new certs” wording assumed a fundamental PKI mismatch; treat that as superseded unless a run still fails after the configuration fix.

See `plan2.md` for the original longer narrative and `results.md` for campaign summary.
