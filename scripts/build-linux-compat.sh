#!/usr/bin/env bash
# Build Linux x64 release against Ubuntu 20.04 (glibc 2.31) so the
# PyInstaller binary runs on older hosts than Debian 13 / Ubuntu 24.04.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-1.0.1}"
OUT="bitfuc-miner-${VER}-linux-x64"
IMAGE=ubuntu:20.04

docker run --rm -v "$ROOT:/src" -w /src "$IMAGE" bash -lc "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv build-essential cmake >/dev/null
python3 -m pip install -q --upgrade pip
python3 -m pip install -q 'pyinstaller>=5,<7'

# Rebuild RandomX shared lib on this glibc
rm -rf /tmp/rxbuild && mkdir -p /tmp/rxbuild
# Existing librandomx.so is already old-glibc; rebuild shared from static if needed.
cmake -S /src/vendor/RandomX -B /tmp/rxbuild -DCMAKE_BUILD_TYPE=Release -DARCH=default
cmake --build /tmp/rxbuild -j\"\$(nproc)\" --target randomx
g++ -shared -o /src/src/librandomx.so -Wl,--whole-archive /tmp/rxbuild/librandomx.a -Wl,--no-whole-archive -lpthread -lstdc++
ls -la /src/src/librandomx.so
ldd /src/src/librandomx.so || true
objdump -T /src/src/librandomx.so | grep -o 'GLIBC_[0-9.]*' | sort -Vu | tail -5 || true


cd /src/src
rm -rf build dist
pyinstaller --noconfirm --clean mine_fuc.spec
mkdir -p \"/src/dist/${OUT}\"
cp -f dist/mine_fuc mine_fuc.py mine.sh librandomx.so \\
  \"/src/dist/${OUT}/\"
cp -f /src/README.md /src/LICENSE \"/src/dist/${OUT}/\"
cp -f LICENSE.RandomX \"/src/dist/${OUT}/\"
chmod +x \"/src/dist/${OUT}/mine_fuc\" \"/src/dist/${OUT}/mine.sh\" \"/src/dist/${OUT}/mine_fuc.py\"
ldd --version | head -1
objdump -T dist/mine_fuc 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -Vu | tail -5 || true
"

mkdir -p "$ROOT/releases"
tar -C "$ROOT/dist" -czf "$ROOT/releases/${OUT}.tar.gz" "$OUT"
cp -f "$ROOT/releases/${OUT}.tar.gz" "$ROOT/dist/"
ls -lh "$ROOT/releases/${OUT}.tar.gz"
echo "Built $OUT"
