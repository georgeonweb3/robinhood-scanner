# docs/ - GitHub Pages source for the Robinhood Chain Safety Scanner

This `docs/` folder is the GitHub Pages source for the scanner. When
Pages is enabled on the `robinhood-scanner` repo with "deploy from a
branch -> main -> /docs", this folder becomes the public site:

- `index.html` - the scanner itself. ONE self-contained file: inline
  CSS, inline JS, no external assets, no CDN, no build step.
- `scan-core.js` - the canonical copy of the pure logic (validation,
  ABI decoding, verdict engine). It is NOT loaded by `index.html`
  (Pages must serve a single self-contained page), it exists so the
  logic can be unit-tested in Node.
- `test_verdict.mjs` - Node tests: `node docs/test_verdict.mjs`.
- `README-note.md` - this file.

## Why a browser version at all

The original scanner (`../scanner/core.py` + `../server.py`) needs a
running Python server. There is no free always-on server in this
setup, but GitHub Pages is free and static. So the scan was ported to
run entirely in the visitor's browser: the page makes read-only
JSON-RPC calls (`eth_chainId`, `eth_getCode`, `eth_getStorageAt`,
`eth_call`) directly from the visitor's device to the Robinhood Chain
RPC, and a verification lookup to Blockscout. No scanner server sits
in between, nothing is signed, nothing is broadcast.

## How the JS mirrors scanner/core.py

| Python (`scanner/`) | Browser (`docs/`) |
|---|---|
| `core.CHAINS` (4663 / 46630, RPC URLs, Blockscout base) | `CHAINS` in `scan-core.js` and inline in `index.html` |
| `core.is_valid_address` / `normalize_address` (`0x` + 40 hex) | same names in JS |
| `core.EIP1967_IMPL_SLOT` / `EIP1967_ADMIN_SLOT` | same constants in JS |
| `abi.dec_uint` / `dec_address` / `dec_string` | same names in JS; `decUint` returns a `BigInt` so `totalSupply` survives past 2^53 |
| `core.Rpc.call` (result / `__revert__` / transport `None`) | `rpcCall()` in `index.html` returns result / `{__revert__}` / `null` (or `{__error__}` for `eth_call`) |
| `core.fetch_verification` (Blockscout `/api/v2/smart-contracts/<addr>`) | `fetchVerification()` in `index.html`, same URL, same parsing of `is_verified` |
| view probes `owner()` `0x8da5cb5b`, `name()` `0x06fdde03`, `symbol()` `0x95d89b41`, `decimals()` `0x313ce567`, `totalSupply()` `0x18160ddd` | same selectors in `index.html` (`SELECTORS`) |
| `core.evaluate_verdict` -> CLEAR / CAUTION / BLOCKED / UNKNOWN | `evaluateVerdict()` in `scan-core.js`, duplicated inline in `index.html` |
| `SELLABILITY_NOT_PROVEN` reason in every full report | same, word for word. Sellability/honeypot status is never claimed as proven; that needs a DEX router buy/sell simulation against the actual pool |

Because `index.html` must be self-contained, the pure functions are
duplicated inline there. `scan-core.js` is the canonical copy: the
Node test imports it directly (no replication in the test). If the
verdict logic ever changes, change both copies and re-run
`node docs/test_verdict.mjs` (32 assertions: verified -> CLEAR,
no code -> BLOCKED, RPC failure -> UNKNOWN with `NOT_A_CONTRACT`
asserted absent, proxy -> CAUTION, Blockscout failure -> verification
unknown -> CAUTION, answered-unverified -> CAUTION, chainId mismatch
-> CAUTION, plus address validation and ABI decode checks).

## CORS / UNKNOWN handling (the honest part)

Verdict discipline (`rpc_failure_verdict_discipline`): a failed read
is evidence about the network, not about the contract.

- RPC unreachable, timed out, HTTP error, malformed response, or the
  `eth_chainId` check itself fails -> verdict **UNKNOWN** with reason
  `RPC_UNREACHABLE` ("the contract was NOT checked"). It is never
  dressed up as BLOCKED / NOT_A_CONTRACT. BLOCKED is issued only when
  `eth_getCode` succeeds and returns empty code.
- Blockscout lookup fails for ANY reason (network error, HTTP 403/404,
  unparseable body, or a browser CORS rejection, which surfaces as a
  thrown `TypeError: Failed to fetch`) -> verification status
  **unknown** ("could not check"), which the verdict engine reports as
  a CAUTION reason `VERIFICATION_UNCHECKED`. It is only ever reported
  as "unverified" when Blockscout actually answers and its record
  says `is_verified` is false.

What was actually checked from the build machine (2026-11-07, curl,
which is not a browser):

- Mainnet RPC `eth_chainId` answered `0x1237` = 4663 and testnet
  `0xb626` = 46630. Both RPC endpoints also answered a CORS
  preflight (OPTIONS with an `Origin` header) with
  `Access-Control-Allow-Origin: *`, `Allow-Methods: POST`,
  `Allow-Headers: content-type`. That is the behaviour a browser
  needs, so the RPC leg is expected to work from the published page.
  A real in-browser confirmation still only exists once the page is
  live and someone runs a scan on it.
- Blockscout's API returned HTTP 403 to this build machine (the same
  behaviour the Python scanner recorded when run from here), so
  Blockscout's browser/CORS behaviour could NOT be verified from
  here, one way or the other. On any visitor browser where that call
  fails, the page will show verification as "could not check" and the
  overall verdict as at most CAUTION. That is the designed behaviour,
  not a bug to paper over.

## Limits carried over from the Python version

- CLEAR = nothing this scanner checks tripped. Not a guarantee, not
  an audit.
- Sellability is NOT proven by this scan (see above).
- No keys, no signing, read-only RPC methods only.
