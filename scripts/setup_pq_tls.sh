#!/usr/bin/env bash
# Optional: build liboqs + oqs-provider and wire PQ-TLS for tls_handshake_bench (PQ_TLS_PORT=8444).
# Default: print steps. Run: ./scripts/setup_pq_tls.sh --build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OQS_PREFIX="${OQS_PREFIX:-$ROOT/oqs-install}"
BUILD_DIR="${OQS_BUILD_DIR:-$ROOT/oqs-build}"

build() {
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  if [[ ! -d liboqs ]]; then
    git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git
  fi
  if [[ ! -d oqs-provider ]]; then
    git clone --depth 1 https://github.com/open-quantum-safe/oqs-provider.git
  fi
  cmake -S liboqs -B liboqs/build -DCMAKE_INSTALL_PREFIX="$OQS_PREFIX" -DCMAKE_BUILD_TYPE=Release
  cmake --build liboqs/build -j"$(nproc 2>/dev/null || echo 4)"
  cmake --install liboqs/build
  cmake -S oqs-provider -B oqs-provider/build \
    -DCMAKE_INSTALL_PREFIX="$OQS_PREFIX" \
    -DOPENSSL_ROOT_DIR="${OPENSSL_ROOT_DIR:-}" \
    -DCMAKE_PREFIX_PATH="$OQS_PREFIX"
  cmake --build oqs-provider/build -j"$(nproc 2>/dev/null || echo 4)"
  cmake --install oqs-provider/build
  echo "Installed liboqs + oqs-provider under $OQS_PREFIX"
  echo "Point OpenSSL 3.x at the provider, e.g.:"
  echo "  export OPENSSL_MODULES=$OQS_PREFIX/lib/ossl-modules"
  echo "  export LD_LIBRARY_PATH=$OQS_PREFIX/lib:\$LD_LIBRARY_PATH"
  echo "Then build or use an OpenSSL 3.x that loads oqs-provider (see oqs-provider README)."
}

usage() {
  cat <<EOF
PQ-TLS benchmark prep (ML-KEM / hybrid groups via oqs-provider).

1) Build (optional, long):  OQS_PREFIX=$OQS_PREFIX $0 --build
2) Copy nginx/nginx_pq.conf.example into nginx/nginx.conf as a second server { listen 8444 ssl; ... }
3) Generate DPtls certs with your PQ-capable openssl / org tooling; point ssl_certificate paths.
4) Run smdpp + nginx; then:
     export PQ_TLS_PORT=8444
     export OQS_OPENSSL=/path/to/openssl3-with-oqs
   and run benchmark/tls_handshake_bench.py

Classical TLS stays on :8443; PQ (or hybrid) on :8444 when configured.
EOF
}

if [[ "${1:-}" == "--build" ]]; then
  build
else
  usage
fi
