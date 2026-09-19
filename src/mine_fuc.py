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

__version__ = "1.0.0"

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
        sys.exit(f"RandomX library not found: {LIB}")
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
    hv = int.from_bytes(h, "little")
    target = int(Decimal(DIFF1) / Decimal(str(difficulty)))
    return hv <= target


def share_diff(h: bytes) -> float:
    hv = int.from_bytes(h, "little")
    if hv == 0:
        return float("inf")
    return float(Decimal(DIFF1) / Decimal(hv))


class Miner:
    def __init__(self):
        self.rx = _load_randomx()
        print(f"BITFUC stratum miner v{__version__}", flush=True)
        print(f"loading RandomX from {LIB} ...", flush=True)
        self.cache = self.rx.randomx_alloc_cache(FLAGS)
        if not self.cache:
            sys.exit("randomx_alloc_cache failed")
        seed_buf = (c_ubyte * len(SEED)).from_buffer_copy(SEED)
        self.rx.randomx_init_cache(self.cache, seed_buf, len(SEED))
        self.vms = []
        for _ in range(THREADS):
            vm = self.rx.randomx_create_vm(FLAGS, self.cache, c_void_p(None))
            if not vm:
                sys.exit("randomx_create_vm failed")
            self.vms.append(vm)
        print(f"RandomX ready ({THREADS} thread(s), light mode)", flush=True)

        self.lock = threading.Lock()
        self.sock = None
        self.extranonce1 = None
        self.extranonce2_size = 4
        self.job = None
        self.job_gen = 0
        self.difficulty = 1e-7
        self.req_id = 1
        self.pending = {}
        self.accepted = 0
        self.rejected = 0
        self.hashes = 0
        self.stop = False

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
            for en2_i in range(thread_id, 0x1000000, THREADS):
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
                        print(
                            f"hashes={hcount} accepted={self.accepted} "
                            f"rejected={self.rejected} diff={d} job={job_id}",
                            flush=True,
                        )
                    if meets_diff(h, d):
                        en2_hex = extranonce2.hex()
                        ntime_hex = f"{ntime:08x}"
                        nonce_hex = f"{nonce:08x}"
                        sd = share_diff(h)
                        print(
                            f"SHARE job={job_id} nonce={nonce_hex} en2={en2_hex} "
                            f"localDiff={sd:.6e}",
                            flush=True,
                        )
                        with self.lock:
                            self.send(
                                "mining.submit",
                                [USER, job_id, en2_hex, ntime_hex, nonce_hex],
                                kind="submit",
                            )
                        time.sleep(0.2)

    def reader(self):
        buf = b""
        self.sock.settimeout(60.0)
        while not self.stop:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                print("disconnected", flush=True)
                self.stop = True
                return
            if not chunk:
                print("disconnected", flush=True)
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
                    with self.lock:
                        self.job = {
                            "job_id": p[0],
                            "prevhash": p[1],
                            "coinb1": p[2],
                            "coinb2": p[3],
                            "merkle": p[4],
                            "version": p[5],
                            "nbits": p[6],
                            "ntime": p[7],
                        }
                        self.job_gen += 1
                    print(f"job {p[0]} bits={p[6]} clean={p[8]}", flush=True)
                elif msg.get("method") == "mining.set_difficulty":
                    with self.lock:
                        self.difficulty = float(msg["params"][0])
                    print(f"difficulty -> {self.difficulty}", flush=True)
                elif msg.get("id") in self.pending:
                    kind = self.pending.pop(msg["id"])
                    if kind == "subscribe":
                        self.extranonce1 = msg["result"][1]
                        self.extranonce2_size = int(msg["result"][2])
                        print(
                            f"subscribed en1={self.extranonce1} "
                            f"en2size={self.extranonce2_size}",
                            flush=True,
                        )
                    elif kind == "authorize":
                        print(f"authorize -> {msg.get('result')}", flush=True)
                        if msg.get("error"):
                            print(f"authorize error: {msg['error']}", flush=True)
                    elif kind == "submit":
                        if msg.get("error"):
                            self.rejected += 1
                            print(f"REJECTED: {msg['error']}", flush=True)
                        elif msg.get("result") is True:
                            self.accepted += 1
                            print(f"SHARE ACCEPTED (total {self.accepted})", flush=True)
                        else:
                            self.rejected += 1
                            print(f"unexpected submit reply: {msg}", flush=True)

    def run(self):
        print(f"connecting {HOST}:{PORT} as {USER}", flush=True)
        self.sock = socket.create_connection((HOST, PORT), timeout=30)
        threading.Thread(target=self.reader, daemon=True).start()
        self.send("mining.subscribe", [f"bitfuc-miner/{__version__}"], kind="subscribe")
        time.sleep(0.4)
        self.send("mining.authorize", [USER, PASS], kind="authorize")
        time.sleep(0.4)
        workers = []
        for i, vm in enumerate(self.vms):
            t = threading.Thread(target=self.mine_worker, args=(vm, i), daemon=True)
            t.start()
            workers.append(t)
        try:
            while not self.stop:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nstopping...", flush=True)
            self.stop = True
        for t in workers:
            t.join(timeout=2)
        print(
            f"done accepted={self.accepted} rejected={self.rejected} hashes={self.hashes}",
            flush=True,
        )


def main():
    Miner().run()


if __name__ == "__main__":
    main()
