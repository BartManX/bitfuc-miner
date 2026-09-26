# BITFUC Stratum Miner

CPU miner for **BITFUC (FUC)** — Bitcoin stratum + **RandomX** header PoW.

This is **not** XMRig / `rx/0`. Stock RandomX miners will not work.

**v1.1.0:** GUI — enter wallet, pick Pool or Solo, click Start.  
**v1.0.2:** Fixed duplicate-share rejects on job rebroadcasts.

## Quick start

### Windows (x64) — GUI

1. Unzip `bitfuc-miner-*-windows-x64.zip`
2. Run **`bitfuc-miner.exe`** (or `mine.bat`)
3. Paste your `fuc1…` wallet, choose **Pool** or **Solo**, set threads, **Start mining**

| Mode | Port |
|------|------|
| Pool (PPLNS) | `3073` |
| Solo | `3077` |

Host: `pool.miningcrypto.online`

CLI is still included as `mine_fuc.exe`.

Windows may need the **VC++ Redistributable** (x64) if the exe fails to load.

### Linux (x86_64)

```bash
tar xzf bitfuc-miner-*-linux-x64.tar.gz
cd bitfuc-miner-*-linux-x64
./mine.sh
```

GUI:

```bash
python3 mine_gui.py
```

Frozen `./mine_fuc` is built on Ubuntu 20.04 / glibc 2.31.

## Environment variables (CLI)

| Variable | Default | Meaning |
|----------|---------|---------|
| `STRATUM_HOST` | `pool.miningcrypto.online` | Pool host |
| `STRATUM_PORT` | `3073` | Stratum port (`3077` = solo) |
| `STRATUM_USER` | — | `fuc1….worker` |
| `STRATUM_PASS` | `x` | Password |
| `THREADS` | `1` | Mining threads |
| `LIBRANDOMX` | next to binary | Path to RandomX |

## Requirements

- Bundled `librandomx` (tevador/RandomX)
- Light-mode RandomX (~256 MiB)
- Key: `SHA256("BITFUC RandomX key v1")`

## License

Miner: MIT.  
RandomX: [BSD-style](https://github.com/tevador/RandomX/blob/LICENSE) (tevador/RandomX).
