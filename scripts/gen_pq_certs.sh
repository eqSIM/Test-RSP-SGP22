#!/usr/bin/env bash
# Generate ML-DSA-44 leaf cert + key for nginx :8444 (OpenSSL 3.0+ with ML-DSA).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/nginx/ssl_pq"
# Prefer Homebrew OpenSSL 3.6+ if present (matches ML-DSA / ML-KEM support in this project)
OPENSSL_BIN="${OPENSSL:-$(command -v openssl)}"
if [[ -x /home/linuxbrew/.linuxbrew/opt/openssl/bin/openssl ]]; then
  OPENSSL_BIN="/home/linuxbrew/.linuxbrew/opt/openssl/bin/openssl"
fi

mkdir -p "$OUT"
CN="${PQ_TLS_CN:-testsmdpplus1.example.com}"

echo "Using: $OPENSSL_BIN"
"$OPENSSL_BIN" version

"$OPENSSL_BIN" genpkey -algorithm MLDSA44 -out "$OUT/dptls.key"
chmod 600 "$OUT/dptls.key"

"$OPENSSL_BIN" req -new -x509 -key "$OUT/dptls.key" -out "$OUT/dptls.pem" -days 3650 \
  -subj "/CN=${CN}" \
  -addext "subjectAltName=DNS:${CN}"

echo "Wrote $OUT/dptls.pem and $OUT/dptls.key"
