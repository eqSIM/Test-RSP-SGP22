#!/usr/bin/env bash
# Build nginx linked against OpenSSL 3.6+ (ML-DSA / ML-KEM TLS) so :8444 PQ server works.
# System nginx (Ubuntu) is often OpenSSL 3.0.13 without PQ — use this binary for benchmarks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENSSL_ROOT="${OPENSSL_ROOT:-/home/linuxbrew/.linuxbrew/opt/openssl}"
SRC_DIR="${ROOT}/nginx/nginx-source"
PREFIX="${ROOT}/nginx/pq_build"
NGINX_VER="${NGINX_VER:-1.26.3}"

if [[ ! -d "$OPENSSL_ROOT/include/openssl" ]]; then
  echo "Set OPENSSL_ROOT to an OpenSSL 3.5+ install (e.g. Homebrew: /home/linuxbrew/.linuxbrew/opt/openssl)" >&2
  exit 1
fi

mkdir -p "$SRC_DIR"
cd "$SRC_DIR"
TAR="nginx-${NGINX_VER}.tar.gz"
if [[ ! -f "$TAR" ]]; then
  echo "Downloading nginx ${NGINX_VER}..."
  curl -fsSL -o "$TAR" "https://nginx.org/download/${TAR}"
fi
rm -rf "nginx-${NGINX_VER}"
tar -xzf "$TAR"
cd "nginx-${NGINX_VER}"

export PKG_CONFIG_PATH="${OPENSSL_ROOT}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

./configure \
  --prefix="$PREFIX" \
  --with-http_ssl_module \
  --with-cc-opt="-I${OPENSSL_ROOT}/include -O2" \
  --with-ld-opt="-L${OPENSSL_ROOT}/lib -Wl,-rpath,${OPENSSL_ROOT}/lib"

make -j"$(nproc 2>/dev/null || echo 4)"
make install

echo "Installed PQ-capable nginx: $PREFIX/sbin/nginx"
"$PREFIX/sbin/nginx" -V
