#!/usr/bin/env python3
"""
BITFUC (FUC) stratum miner — Bitcoin-style jobs + RandomX header PoW.

Requires librandomx next to this script (or set LIBRANDOMX):
  Linux:   librandomx.so
  Windows: librandomx.dll

Env overrides:
  STRATUM_HOST  STRATUM_PORT  STRATUM_USER  STRATUM_PASS  LIBRANDOMX  THREADS
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time
from ctypes import (
    CDLL,
    c_size_t,
    c_ubyte,
    c_uint,
    c_void_p,
    create_string_buffer,
)
from decimal import Decimal

__version__ = "1.1.0"

# BITFUC RandomX key = SHA256("BITFUC RandomX key v1")
SEED = bytes.fromhex(
    "6fbd63b9ec831b1139a2359e833910012713d006830986f8abdd0dfcd104b291"
)
# HARD_AES | JIT | ARGON2  (light mode — no FULL_MEM)
FLAGS = 2 | 8 | 96
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000

HOST = os.environ.get("STRATUM_HOST", "pool.miningcrypto.online")
PORT = int(os.environ.get("STRATUM_PORT", "3073"))
USER = os.environ.get(
    "STRATUM_USER",
    "fuc1qnt4kydw9hdlkpe243fxja4tuehhfvnyalxq0wc.worker1",
)
PASS = os.environ.get("STRATUM_PASS", "x")
THREADS = max(1, int(os.environ.get("THREADS", "1")))


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _default_lib() -> str:
    name = "librandomx.dll" if (os.name == "nt" or sys.platform.startswith("win")) else "librandomx.so"
    candidates = []
    # PyInstaller bundle extract dir
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, name))
    candidates.append(os.path.join(_app_dir(), name))
    candidates.append(os.path.join(os.getcwd(), name))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


LIB = os.environ.get("LIBRANDOMX", _default_lib())


def _load_randomx():
    if not os.path.isfile(LIB):
        raise FileNotFoundError(f"RandomX library not found: {LIB}")
    rx = CDLL(LIB)
    rx.randomx_alloc_cache.restype = c_void_p
    rx.randomx_alloc_cache.argtypes = [c_uint]
    rx.randomx_init_cache.argtypes = [c_void_p, c_void_p, c_size_t]
    rx.randomx_create_vm.restype = c_void_p
    rx.randomx_create_vm.argtypes = [c_uint, c_void_p, c_void_p]
    rx.randomx_calculate_hash.argtypes = [c_void_p, c_void_p, c_size_t, c_void_p]
    rx.randomx_destroy_vm.argtypes = [c_void_p]
    rx.randomx_release_cache.argtypes = [c_void_p]
    return rx


def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def stratum_prevhash_to_header(prevhash_hex: str) -> bytes:
    # Miningcore sends ReverseByteOrder(prev); header needs each 4-byte word byte-swapped.
    b = bytes.fromhex(prevhash_hex)
    return b"".join(b[i : i + 4][::-1] for i in range(0, 32, 4))


def build_header(j, en1: str, extranonce2: bytes, ntime: int, nonce: int) -> bytes:
    coinbase = (
        bytes.fromhex(j["coinb1"])
        + bytes.fromhex(en1)
        + extranonce2
        + bytes.fromhex(j["coinb2"])
    )
    merkle = sha256d(coinbase)
    for branch in j["merkle"]:
        merkle = sha256d(merkle + bytes.fromhex(branch))
    return (
        struct.pack("<I", int(j["version"], 16))
        + stratum_prevhash_to_header(j["prevhash"])
        + merkle
        + struct.pack("<I", ntime)
        + struct.pack("<I", int(j["nbits"], 16))
        + struct.pack("<I", nonce)
    )


def meets_diff(h: bytes, difficulty: float) -> bool:
    if difficulty is None or difficulty <= 0:
        return False
    hv = int.from_bytes(h, "little")
    target = int(Decimal(DIFF1) / Decimal(str(difficulty)))
    return hv <= target


def share_diff(h: bytes) -> float:
    hv = int.from_bytes(h, "little")
    if hv == 0:
        return float("inf")
    return float(Decimal(DIFF1) / Decimal(hv))


class Miner:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        threads: int | None = None,
        log=None,
    ):
        self.host = host or HOST
        self.port = int(port if port is not None else PORT)
        self.user = user or USER
        self.password = password if password is not None else PASS
        self.threads = max(1, int(threads if threads is not None else THREADS))
        self._log = log or (lambda msg: print(msg, flush=True))

        self.rx = _load_randomx()
        self._log(f"BITFUC stratum miner v{__version__}")
        self._log(f"loading RandomX from {LIB} ...")
        self.cache = self.rx.randomx_alloc_cache(FLAGS)
        if not self.cache:
            raise RuntimeError("randomx_alloc_cache failed")
        seed_buf = (c_ubyte * len(SEED)).from_buffer_copy(SEED)
        self.rx.randomx_init_cache(self.cache, seed_buf, len(SEED))
        self.vms = []
        for _ in range(self.threads):
            vm = self.rx.randomx_create_vm(FLAGS, self.cache, c_void_p(None))
            if not vm:
                raise RuntimeError("randomx_create_vm failed")
            self.vms.append(vm)
        self._log(f"RandomX ready ({self.threads} thread(s), light mode)")

        self.lock = threading.Lock()
        self.sock = None
        self.extranonce1 = None
        self.extranonce2_size = 4
        self.job = None
        self.job_gen = 0
        self.difficulty = 1e-7
        self.req_id = 1
        self.pending = {}
        # Pool dupe-checks en1+en2+ntime+nonce per job. We also key without job_id so
        # a template rebroadcast (new job_id, same work) cannot resubmit the same nonces.
        self.submitted: set[tuple[str, str, str]] = set()
        self.accepted = 0
        self.rejected = 0
        self.duplicates_skipped = 0
        self.hashes = 0
        self.stop = False
        self._workers: list[threading.Thread] = []

    @staticmethod
    def _job_fingerprint(j: dict) -> tuple:
        """Block template identity (not job_id)."""
        return (
            j.get("prevhash"),
            j.get("coinb1"),
            j.get("coinb2"),
            tuple(j.get("merkle") or ()),
            j.get("version"),
            j.get("nbits"),
            j.get("ntime"),
        )

    def rxhash(self, vm, data: bytes) -> bytes:
        inp = (c_ubyte * len(data)).from_buffer_copy(data)
        out = (c_ubyte * 32)()
        self.rx.randomx_calculate_hash(vm, inp, len(data), out)
        return bytes(out)

    def send(self, method, params, kind=None):
        rid = self.req_id
        self.req_id += 1
        if kind:
            self.pending[rid] = kind
        self.sock.sendall(
            (json.dumps({"id": rid, "method": method, "params": params}) + "\n").encode()
        )
        return rid

    def mine_worker(self, vm, thread_id: int):
        while not self.stop:
            with self.lock:
                j = self.job
                d = self.difficulty
                en1 = self.extranonce1
                en2sz = self.extranonce2_size
                gen = self.job_gen
            if not j or not en1:
                time.sleep(0.05)
                continue
            ntime = int(j["ntime"], 16)
            job_id = j["job_id"]
            # Partition extranonce2 space across threads
            for en2_i in range(thread_id, 0x1000000, self.threads):
                if self.stop:
                    return
                with self.lock:
                    if self.job_gen != gen:
                        break
                extranonce2 = en2_i.to_bytes(en2sz, "big")
                for nonce in range(0, 0x1000000):
                    if self.stop:
                        return
                    with self.lock:
                        if self.job_gen != gen:
                            break
                    header = build_header(j, en1, extranonce2, ntime, nonce)
                    h = self.rxhash(vm, header)
                    with self.lock:
                        self.hashes += 1
                        hcount = self.hashes
                    if hcount % 100 == 0 and thread_id == 0:
                        self._log(
                            f"hashes={hcount} accepted={self.accepted} "
                            f"rejected={self.rejected} dup_skip={self.duplicates_skipped} "
                            f"diff={d} job={job_id}"
                        )
                    if meets_diff(h, d):
                        en2_hex = extranonce2.hex()
                        ntime_hex = f"{ntime:08x}"
                        nonce_hex = f"{nonce:08x}"
                        key = (en2_hex, ntime_hex, nonce_hex)
                        with self.lock:
                            if key in self.submitted:
                                self.duplicates_skipped += 1
                                continue
                            self.submitted.add(key)
                            if len(self.submitted) > 50000:
                                self.submitted.clear()
                                self.submitted.add(key)
                            # Prefer latest job_id (rebroadcast may change id without new work)
                            submit_job_id = (
                                self.job["job_id"] if self.job else job_id
                            )
                        sd = share_diff(h)
                        self._log(
                            f"SHARE job={submit_job_id} nonce={nonce_hex} en2={en2_hex} "
                            f"localDiff={sd:.6e}"
                        )
                        with self.lock:
                            self.send(
                                "mining.submit",
                                [self.user, submit_job_id, en2_hex, ntime_hex, nonce_hex],
                                kind="submit",
                            )
                else:
                    continue
                break  # job_gen changed — restart outer while with new job

    def reader(self):
        buf = b""
        self.sock.settimeout(60.0)
        while not self.stop:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                self._log("disconnected")
                self.stop = True
                return
            if not chunk:
                self._log("disconnected")
                self.stop = True
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line:
                    continue
                msg = json.loads(line.decode())
                if msg.get("method") == "mining.notify":
                    p = msg["params"]
                    new_job = {
                        "job_id": p[0],
                        "prevhash": p[1],
                        "coinb1": p[2],
                        "coinb2": p[3],
                        "merkle": p[4],
                        "version": p[5],
                        "nbits": p[6],
                        "ntime": p[7],
                    }
                    with self.lock:
                        old = self.job
                        work_changed = (
                            old is None
                            or self._job_fingerprint(old) != self._job_fingerprint(new_job)
                        )
                        self.job = new_job
                        # Only restart nonce search when the template actually changes.
                        # Miningcore rebroadcasts assign a new job_id for the same work;
                        # resetting on that caused duplicate share rejects.
                        if work_changed:
                            self.job_gen += 1
                            self.submitted.clear()
                    self._log(
                        f"job {p[0]} bits={p[6]} clean={p[8] if len(p) > 8 else '?'} "
                        f"work_changed={work_changed}"
                    )
                elif msg.get("method") == "mining.set_difficulty":
                    with self.lock:
                        self.difficulty = float(msg["params"][0])
                    self._log(f"difficulty -> {self.difficulty}")
                elif msg.get("id") in self.pending:
                    kind = self.pending.pop(msg["id"])
                    if kind == "subscribe":
                        self.extranonce1 = msg["result"][1]
                        self.extranonce2_size = int(msg["result"][2])
                        self._log(
                            f"subscribed en1={self.extranonce1} "
                            f"en2size={self.extranonce2_size}"
                        )
                    elif kind == "authorize":
                        self._log(f"authorize -> {msg.get('result')}")
                        if msg.get("error"):
                            self._log(f"authorize error: {msg['error']}")
                    elif kind == "submit":
                        if msg.get("error"):
                            self.rejected += 1
                            self._log(f"REJECTED: {msg['error']}")
                        elif msg.get("result") is True:
                            self.accepted += 1
                            self._log(f"SHARE ACCEPTED (total {self.accepted})")
                        else:
                            self.rejected += 1
                            self._log(f"unexpected submit reply: {msg}")

    def start(self):
        """Connect and start mining threads (non-blocking)."""
        self.stop = False
        self._log(f"connecting {self.host}:{self.port} as {self.user}")
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        threading.Thread(target=self.reader, daemon=True).start()
        self.send(
            "mining.subscribe",
            [f"bitfuc-miner/{__version__}"],
            kind="subscribe",
        )
        time.sleep(0.4)
        self.send("mining.authorize", [self.user, self.password], kind="authorize")
        time.sleep(0.4)
        self._workers = []
        for i, vm in enumerate(self.vms):
            t = threading.Thread(target=self.mine_worker, args=(vm, i), daemon=True)
            t.start()
            self._workers.append(t)

    def request_stop(self):
        self.stop = True
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass

    def run(self):
        self.start()
        try:
            while not self.stop:
                time.sleep(1)
        except KeyboardInterrupt:
            self._log("stopping...")
            self.request_stop()
        for t in self._workers:
            t.join(timeout=2)
        self._log(
            f"done accepted={self.accepted} rejected={self.rejected} "
            f"dup_skip={self.duplicates_skipped} hashes={self.hashes}"
        )


def main():
    try:
        Miner().run()
    except Exception as e:
        print(f"error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
