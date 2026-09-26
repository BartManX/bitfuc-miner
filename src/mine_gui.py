#!/usr/bin/env python3
"""BITFUC miner GUI — wallet + pool/solo + start."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from mine_fuc import Miner, __version__, _app_dir

DEFAULT_HOST = "pool.miningcrypto.online"
POOL_PORT = 3073
SOLO_PORT = 3077
SETTINGS_NAME = "bitfuc-miner-gui.json"


def settings_path() -> str:
    return os.path.join(_app_dir(), SETTINGS_NAME)


class MinerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"BITFUC Miner {__version__}")
        self.minsize(520, 420)
        self.geometry("640x480")

        self.miner: Miner | None = None
        self._miner_thread: threading.Thread | None = None
        self._log_q: queue.Queue[str] = queue.Queue()
        self._hash_anchor = (0, time.time())
        self._running = False

        self.wallet_var = tk.StringVar()
        self.worker_var = tk.StringVar(value="worker1")
        self.mode_var = tk.StringVar(value="pool")
        self.threads_var = tk.IntVar(value=max(1, (os.cpu_count() or 4) // 2))
        self.status_var = tk.StringVar(value="Idle")
        self.stats_var = tk.StringVar(value="hashes 0 · accepted 0 · rejected 0 · 0 H/s")

        self._build()
        self._load_settings()
        self.after(200, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="BITFUC Miner", font=("Segoe UI", 16, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Wallet", width=10).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.wallet_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Worker", width=10).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.worker_var, width=18).pack(side=tk.LEFT)
        ttk.Label(row, text="Threads").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Spinbox(
            row, from_=1, to=64, textvariable=self.threads_var, width=6
        ).pack(side=tk.LEFT)

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Mode", width=10).pack(side=tk.LEFT)
        ttk.Radiobutton(
            row, text=f"Pool (:{POOL_PORT})", variable=self.mode_var, value="pool"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            row, text=f"Solo (:{SOLO_PORT})", variable=self.mode_var, value="solo"
        ).pack(side=tk.LEFT, padx=(12, 0))

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, **pad)
        self.start_btn = ttk.Button(row, text="Start mining", command=self._start)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(
            row, text="Stop", command=self._stop, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(row, textvariable=self.status_var).pack(side=tk.LEFT, padx=(16, 0))

        ttk.Label(frm, textvariable=self.stats_var).pack(anchor=tk.W, **pad)

        ttk.Label(frm, text="Log").pack(anchor=tk.W, padx=12)
        self.log = tk.Text(frm, height=14, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

    def _append_log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg.rstrip() + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _load_settings(self):
        try:
            with open(settings_path(), encoding="utf-8") as f:
                data = json.load(f)
            self.wallet_var.set(data.get("wallet", ""))
            self.worker_var.set(data.get("worker", "worker1"))
            self.mode_var.set(data.get("mode", "pool"))
            self.threads_var.set(int(data.get("threads", self.threads_var.get())))
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            pass

    def _save_settings(self):
        data = {
            "wallet": self.wallet_var.get().strip(),
            "worker": self.worker_var.get().strip() or "worker1",
            "mode": self.mode_var.get(),
            "threads": int(self.threads_var.get()),
        }
        try:
            with open(settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def _start(self):
        wallet = self.wallet_var.get().strip()
        if not wallet.startswith("fuc1") or len(wallet) < 20:
            messagebox.showerror("Wallet", "Enter a valid fuc1… wallet address.")
            return
        worker = self.worker_var.get().strip() or "worker1"
        user = f"{wallet}.{worker}"
        mode = self.mode_var.get()
        port = SOLO_PORT if mode == "solo" else POOL_PORT
        threads = max(1, int(self.threads_var.get()))
        self._save_settings()

        def log_cb(msg: str):
            self._log_q.put(msg)

        try:
            miner = Miner(
                host=DEFAULT_HOST,
                port=port,
                user=user,
                password="x",
                threads=threads,
                log=log_cb,
            )
        except Exception as e:
            messagebox.showerror("Miner", str(e))
            return

        self.miner = miner
        self._running = True
        self._hash_anchor = (0, time.time())
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"Mining ({mode}) → {DEFAULT_HOST}:{port}")

        def run():
            try:
                miner.start()
                while self._running and not miner.stop:
                    time.sleep(0.25)
            except Exception as e:
                self._log_q.put(f"error: {e}")
            finally:
                miner.request_stop()
                self._log_q.put("__STOPPED__")

        self._miner_thread = threading.Thread(target=run, daemon=True)
        self._miner_thread.start()
        self._append_log(f"Started {mode} mining as {user}")

    def _stop(self):
        self._running = False
        if self.miner:
            self.miner.request_stop()
        self.status_var.set("Stopping…")

    def _poll(self):
        while True:
            try:
                msg = self._log_q.get_nowait()
            except queue.Empty:
                break
            if msg == "__STOPPED__":
                self._running = False
                self.miner = None
                self.start_btn.configure(state=tk.NORMAL)
                self.stop_btn.configure(state=tk.DISABLED)
                self.status_var.set("Idle")
                self._append_log("Stopped.")
            else:
                self._append_log(msg)

        m = self.miner
        if m is not None:
            now = time.time()
            h0, t0 = self._hash_anchor
            dt = max(0.001, now - t0)
            rate = (m.hashes - h0) / dt
            if now - t0 >= 2.0:
                self._hash_anchor = (m.hashes, now)
            self.stats_var.set(
                f"hashes {m.hashes} · accepted {m.accepted} · "
                f"rejected {m.rejected} · {rate:.0f} H/s"
            )
        self.after(200, self._poll)

    def _on_close(self):
        self._save_settings()
        self._running = False
        if self.miner:
            self.miner.request_stop()
        self.destroy()


def main():
    app = MinerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
