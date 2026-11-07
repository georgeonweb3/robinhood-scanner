# Robinhood Chain Safety Scanner

**Paste a contract. Get a verdict before you trade.**

Robinhood Chain went mainnet 1 July 2026, passed Base in daily active users in three weeks, and hit about $775M TVL. Then came the honeypot wave: tokens you could buy and never sell, unverified contracts, copycat tickers. The ecosystem's own builder map calls it out plainly: consumer-grade analytics and safety tooling is proven demand and underserved on this chain.

There are mature scanners on Base and BSC. On Robinhood Chain, retail traders were checking contracts by vibes. This scanner is the simple first check that was missing.

It reads the chain, checks the basics, and tells you in plain words: **CLEAR**, **CAUTION**, **BLOCKED**, or **UNKNOWN**, with every reason listed. It never signs anything. It never asks for a key. It just reads, checks, and shows its work.

**Use it in your browser, no install:** https://georgeonweb3.github.io/robinhood-scanner/ - the web version runs the same checks entirely in your browser (source in `docs/`), free basic scan.

Built by George Agbe, reusing the verdict pattern from Preflight (his BSC/Base mint precheck, CLEAR/CAUTION/BLOCKED with itemised reasons).

## What it checks

- **ChainId verification** - RPC must answer 4663 (mainnet) or 46630 (testnet). A mismatch is flagged, a transport failure is UNKNOWN.
- **Code exists / size** - is there actually a contract at that address, and how big is it?
- **EIP-1967 proxy detection** - if the code can be swapped by upgrading the implementation, you hear about it.
- **Source verification** - Blockscout API (`robinhoodchain.blockscout.com`). Verified, unverified, and "could not check" are three different answers and are never merged.
- **Owner** - `owner()` if present, including renounced (zero address).
- **ERC20 identity** - `name()`, `symbol()`, `decimals()`, `totalSupply()` if present.
- **Sellability note** - honest, every time (see limits below).

## What it does NOT prove

Sellability / honeypot status is **not** proven by this scan, and this scanner does not fake it.

Proving sellability needs the token's actual DEX pair and router, a quote, and an `eth_call` buy-then-sell simulation against that pool. That flow is router-specific. A bytecode scan alone cannot prove you can sell.

Every report carries this note as `SELLABILITY_NOT_PROVEN` (info level). Treat any token as unsellable until you test a small buy and a small sell yourself on the DEX.

A CLEAR verdict means: nothing this scanner checks tripped. It is not an audit, not a guarantee, and not financial advice.

## The UNKNOWN rule

This scanner follows RPC failure verdict discipline, learned the expensive way in Preflight:

- A failed RPC read (timeout, refused, 403, malformed) is evidence about the network, not about the address.
- It returns **UNKNOWN**: "the contract was not checked, re-run when the RPC is healthy."
- It never turns a failed read into BLOCKED, and never calls an address "not a contract" unless a successful read came back empty (`0x`, 0 bytes).

Same for Blockscout: unreachable means "could not check" (a caution), not "unverified".

## Run it

No dependencies. Pure Python 3.9+ stdlib. Nothing to pip install.

### CLI

```bash
cd robinhood-scanner
python3 -m scanner check 0xYourContractAddress --chain robinhood
python3 -m scanner check 0xYourContractAddress --chain robinhood --json
python3 -m scanner check 0xYourContractAddress --chain robinhood-testnet
```

Exit codes: 0 = check completed (BLOCKED is a completed check), 2 = invalid address / usage error.

### Web UI

```bash
python3 server.py --port 8097
# open http://127.0.0.1:8097/
```

- `/` - single-file UI: paste an address, pick a chain, get the verdict card plus raw JSON.
- `GET /api/check?address=0x...&chain=robinhood` - JSON API (also accepts POST with a JSON body).
- `GET /health` - `{"ok": true}`.

### Tests

```bash
python3 -m unittest discover -s tests -v
# 28 tests: address validation, Keccak selectors, chain config,
# verdict logic with mocked RPC, RPC failure -> UNKNOWN
```

See [DEMO.md](DEMO.md) for live results recorded on 2026-11-07, including what the RPC and Blockscout actually returned.

## Pricing

- **Free** - basic scan: chainId, code, proxy, verification, identity, owner, verdict. Enough to avoid the obvious traps.
- **Pro - $9/month** - unlimited scans, new-pool watch and alerts, scan history, priority RPC, Telegram bot access. For active Robinhood traders who scan dozens of contracts a week.

Why $9: one avoided honeypot pays for years of Pro. The free tier is the funnel, Pro is for the degens who live on the chain.

## How it was built

- `scanner/core.py` - chains, read-only RPC client (allowlist in code, no signing path), Blockscout verification, probing, pure verdict engine.
- `scanner/keccak.py` / `scanner/abi.py` - pure-Python Keccak-256 and minimal ABI helpers, reused from Preflight (stdlib only, `hashlib.sha3_256` would give wrong selectors).
- `scanner/cli.py` - human card + `--json` (schema `robinhood-scanner/1`).
- `server.py` + `index.html` - stdlib `http.server` UI and JSON API.

## License

MIT.

Built by [George Agbe](https://github.com/georgeonweb3), a Web3 builder working from a phone in Lagos.
