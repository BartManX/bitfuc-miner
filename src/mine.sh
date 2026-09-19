#!/usr/bin/env bash
cd "$(dirname "$0")"
export STRATUM_HOST="${STRATUM_HOST:-66.94.115.118}"
export STRATUM_PORT="${STRATUM_PORT:-3073}"
export STRATUM_USER="${STRATUM_USER:-fuc1qnt4kydw9hdlkpe243fxja4tuehhfvnyalxq0wc.worker1}"
export STRATUM_PASS="${STRATUM_PASS:-x}"
export THREADS="${THREADS:-1}"
if [[ -x ./mine_fuc ]]; then
  exec ./mine_fuc
fi
exec python3 mine_fuc.py
