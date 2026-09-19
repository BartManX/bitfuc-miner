# BITFUC Stratum Miner

CPU miner for **BITFUC (FUC)** pools that speak Bitcoin stratum with **RandomX** proof-of-work on the 80-byte block header.

This is **not** XMRig / `rx/0`. Stock RandomX miners will not work.

## Quick start

### Linux (x86_64)

```bash
tar xzf bitfuc-miner-*-linux-x64.tar.gz
cd bitfuc-miner-*-linux-x64
./mine_fuc
```

Or with Python:

```bash
python3 mine_fuc.py
```

### Windows (x64)

1. Install [Python 3](https://www.python.org/downloads/) (check “Add to PATH”).
2. Unzip `bitfuc-miner-*-windows-x64.zip`
3. Edit `mine.bat` if you need a different wallet, then double-click it.

Or from cmd:

```bat
set STRATUM_HOST=pool.miningcrypto.online
set STRATUM_PORT=3073
set STRATUM_USER=YOUR_FUC_ADDRESS.worker1
set STRATUM_PASS=x
python mine_fuc.py
```

Windows needs the **VC++ Redistributable** (x64) if `librandomx.dll` fails to load.

## Default pool

| Setting | Value |
|--------|--------|
| Stratum | `stratum+tcp://pool.miningcrypto.online:3073` |
| Algorithm | BitfucRandomX |
| Password | `x` |

Set `STRATUM_USER` to your `fuc1…` address (optional `.workername`).

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `STRATUM_HOST` | `pool.miningcrypto.online` | Pool host |
| `STRATUM_PORT` | `3073` | Stratum port |
| `STRATUM_USER` | pool example wallet | Login / wallet |
| `STRATUM_PASS` | `x` | Password |
| `THREADS` | `1` | Mining threads |
| `LIBRANDOMX` | `./librandomx.so` or `.dll` | Path to RandomX |

## Requirements

- Bundled `librandomx` (tevador/RandomX, shared library)
- Light-mode RandomX (~256 MiB)
- Fixed key: `SHA256("BITFUC RandomX key v1")`

## License

Miner script: MIT.  
RandomX: [BSD-style license](https://github.com/tevador/RandomX/blob/master/LICENSE) (tevador/RandomX).
