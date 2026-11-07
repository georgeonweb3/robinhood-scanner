# DEMO - Live checks recorded 2026-11-07

Everything below is what actually happened when the commands were run
from this VM on Sat 2026-11-07 (Africa/Lagos). Nothing is invented.
Where a service failed, the failure is shown and how the scanner
handled it.

## 1. Unit tests

```bash
python3 -m unittest discover -s tests -v
# Ran 28 tests in 0.013s - OK
```

Coverage: address validation (7), chain config (2), Keccak known
selectors (2), RPC allowlist refusal (1), verdict logic with mocked
checks (9, including code-read-failure never becomes BLOCKED), full
scan with mocked RPC (7, including RPC failure -> UNKNOWN and zero
address handling).

## 2. Live RPC - Robinhood mainnet, zero address

Command:

```bash
python3 -m scanner check 0x0000000000000000000000000000000000000000 --chain robinhood --json
```

Actual outcome:

- RPC `https://rpc.mainnet.chain.robinhood.com` was **reachable**.
- `eth_chainId` returned **4663**, matches expected 4663: `matches=true`, `transport_failed=false`.
- `eth_getCode` for the zero address succeeded and returned empty: `is_contract=false`, `code_size_bytes=0`, `code_read_failed=false`.
- Verdict: **BLOCKED** - `NOT_A_CONTRACT: address has no contract code on this chain on a successful read`. This is the correct use of BLOCKED: the read succeeded, the answer was empty. It is not a transport failure dressed up as a verdict.
- Blockscout: `GET https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x000...0` returned **HTTP 403** from this VM. Scanner recorded `verification.status = "unknown"`, detail "Blockscout HTTP 403: could not check verification". It did **not** call the contract unverified. For a NOT_A_CONTRACT verdict this does not change the outcome; for a real contract it would surface as a `VERIFICATION_UNCHECKED` caution.

Human output (same check, no `--json`):

```text
Address   0x0000000000000000000000000000000000000000
Chain     Robinhood Chain (expected chainId 4663)
ChainId   actual=4663 expected=4663 matches=True
Contract  is_contract=False size=0 proxy=False impl=None
Verified  status=unknown - Blockscout HTTP 403: could not check verification
------------------------------------------------------------------------
VERDICT   BLOCKED
  [BLOCK  ] NOT_A_CONTRACT: address has no contract code on this chain on a successful read (wrong address or wrong chain)
```

## 3. Live RPC - Robinhood testnet, zero address

```bash
python3 -m scanner check 0x0000000000000000000000000000000000000000 --chain robinhood-testnet --json
```

Actual outcome:

- RPC `https://rpc.testnet.chain.robinhood.com` was **reachable**.
- `eth_chainId` returned **46630**, matches expected 46630.
- `eth_getCode` succeeded, empty: `is_contract=false`, 0 bytes.
- Verdict: **BLOCKED / NOT_A_CONTRACT** (same reasoning as mainnet).
- Blockscout this time: "Remote end closed connection without response" - recorded as `unknown` / could not check, same honest handling, different transport error.

## 4. UNKNOWN handling - simulated RPC failure (live run, bad endpoint)

To prove the discipline end to end, the scanner was run in-process
against an unreachable endpoint (`https://127.0.0.1:9/unreachable`):

```text
verdict: UNKNOWN
RPC_UNREACHABLE: RPC transport failed (eth_chainId transport failure:
  ... Connection refused) - the contract was NOT checked. This is
  evidence about the network/endpoint, not about this address.
  Re-run when the RPC path is healthy.
chain check: actual=None, matches=None, transport_failed=True
```

No BLOCKED, no NOT_A_CONTRACT. A failed network never becomes a
verdict about a contract. The same path is covered by unit tests
`test_scan_unknown_on_rpc_failure` and
`test_scan_unknown_on_code_read_failure`.

## 5. Invalid address handling

```bash
python3 -m scanner check 0x123 --chain robinhood
# stderr: invalid address: '0x123' - expected 0x + 40 hex chars
# exit code: 2

python3 -m scanner check 0x123 --chain robinhood --json
# {"verdict": "UNKNOWN", "error": "invalid_address", ...}
# exit code: 2
```

## 6. Web server - live smoke test

```bash
python3 server.py --port 8097 --host 127.0.0.1
curl http://127.0.0.1:8097/            # 200, 3612 bytes, the UI
curl http://127.0.0.1:8097/health      # {"ok": true, "service": "robinhood-scanner"}
curl "http://127.0.0.1:8097/api/check?address=0x000...0&chain=robinhood"
# 200, same BLOCKED / NOT_A_CONTRACT report as the CLI, chainId 4663 matched
curl "http://127.0.0.1:8097/api/check?address=0x123&chain=robinhood"
# 400, {"verdict": "UNKNOWN", "error": "invalid_address", ...}
```

Server was stopped after the smoke test.

## Honest limits shown by this demo

- No real token contract was scanned live in this demo: the zero
  address was the control (the task allowed any address, including
  zero address handling). The mocked-RPC tests cover the
  contract-exists / token-identity / CLEAR and CAUTION paths with a
  fake ERC20 (`TestToken` / `TEST`, 18 decimals). A first live token
  scan is a 1-command follow-up once George picks a Robinhood token
  he wants checked.
- Blockscout verification could not be confirmed from this VM
  (403 / dropped connection on both attempts). The scanner's
  "could not check" path is therefore not theoretical - it is what
  a user on a similar network will actually see, and it is reported
  as a caution, never as "unverified".
- Sellability was not tested and is not claimed. See README.
