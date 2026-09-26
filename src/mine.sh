#!/usr/bin/env bash
cd "$(dirname "$0")"
export STRATUM_HOST="${STRATUM_HOST:-pool.miningcrypto.online}"
export STRATUM_PORT="${STRATUM_PORT:-3073}"
export STRATUM_USER="${STRATUM_USER:-fuc1qnt4kydw9hdlkpe243fxja4tuehhfvnyalxq0wc.worker1}"
export STRATUM_PASS="${STRATUM_PASS:-x}"
export THREADS="${THREADS:-1}"

# Prefer system Python + librandomx.so — works on older glibc hosts where the
# frozen PyInstaller binary may fail (needs GLIBC from the build machine).
if command -v python3 >/dev/null 2>&1 && [[ -f ./mine_fuc.py ]]; then
  exec python3 mine_fuc.py
fi
if [[ -x ./mine_fuc ]]; then
  exec ./mine_fuc
fi
echo "error: need python3 or ./mine_fuc" >&2
exit 1
