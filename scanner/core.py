"""Robinhood Chain Safety Scanner - core.

Reuses Preflight's CLEAR / CAUTION / BLOCKED pattern and adds UNKNOWN
for transport failure, per rpc_failure_verdict_discipline:

- A failed RPC read (timeout, 403, malformed, unreachable) is evidence
  about the network, not about the address. It must NEVER be reported
  as BLOCKED / NOT_A_CONTRACT. It is UNKNOWN.
- A successful read that returns empty code ("0x") IS a verdict:
  BLOCKED / NOT_A_CONTRACT.
- Blockscout verification failure is "could not check" (unknown),
  distinct from "unverified" (checked, no verification found).

Stdlib only. Read-only RPC allowlist - no signing, no broadcasting.
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from .abi import dec_address, dec_string, dec_uint, encode_call

# ---------------------------------------------------------------- chains

@dataclass(frozen=True)
class Chain:
    key: str
    name: str
    chain_id: int
    rpcs: tuple
    explorer_api: str  # Blockscout API base, no trailing slash
    explorer_url: str

ROBINHOOD = Chain(
    key="robinhood",
    name="Robinhood Chain",
    chain_id=4663,
    rpcs=("https://rpc.mainnet.chain.robinhood.com",),
    explorer_api="https://robinhoodchain.blockscout.com/api",
    explorer_url="https://robinhoodchain.blockscout.com",
)
ROBINHOOD_TESTNET = Chain(
    key="robinhood-testnet",
    name="Robinhood Chain Testnet",
    chain_id=46630,
    rpcs=("https://rpc.testnet.chain.robinhood.com",),
    explorer_api="https://robinhoodchain.blockscout.com/api",
    explorer_url="https://robinhoodchain.blockscout.com",
)
CHAINS = {c.key: c for c in (ROBINHOOD, ROBINHOOD_TESTNET)}
# Friendly aliases
CHAINS["mainnet"] = ROBINHOOD
CHAINS["testnet"] = ROBINHOOD_TESTNET

EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

READ_ONLY_METHODS = {
    "eth_call", "eth_getCode", "eth_getStorageAt",
    "eth_blockNumber", "eth_chainId", "eth_gasPrice", "eth_getBalance",
}

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

def is_valid_address(addr) -> bool:
    return isinstance(addr, str) and bool(_ADDRESS_RE.match(addr.strip()))

def normalize_address(addr: str) -> str:
    return addr.strip().lower()

# ---------------------------------------------------------------- RPC

class Rpc:
    """Read-only JSON-RPC client with failover. Returns None on transport
    failure for simple getters, and {'__revert__'/'__error__'} for eth_call.
    That distinction is load-bearing: None = could not read, '0x' = read
    succeeded and came back empty."""

    def __init__(self, endpoints, user_agent="robinhood-scanner/0.1", timeout=15):
        self.endpoints = list(endpoints)
        self.user_agent = user_agent
        self.timeout = timeout
        self.errors = []

    def call(self, method, params):
        if method not in READ_ONLY_METHODS:
            raise ValueError(f"refusing non-read-only RPC method: {method}")
        last_err = None
        for ep in self.endpoints:
            try:
                payload = json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
                }).encode()
                req = urllib.request.Request(ep, data=payload, headers={
                    "Content-Type": "application/json",
                    "User-Agent": self.user_agent,
                })
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read()
                    j = json.loads(body)
                if "error" in j:
                    last_err = j["error"].get("message", str(j["error"])) if isinstance(j["error"], dict) else str(j["error"])
                    if method == "eth_call":
                        return {"__revert__": last_err}
                    return None
                return j.get("result")
            except Exception as e:
                last_err = str(e)
                self.errors.append(f"{ep}: {e}")
                continue
        if method == "eth_call":
            return {"__error__": last_err}
        return None

    def eth_call(self, to, data):
        return self.call("eth_call", [{"to": to, "data": data}, "latest"])

    def chain_id(self):
        res = self.call("eth_chainId", [])
        if isinstance(res, str) and res.startswith("0x"):
            try:
                return int(res, 16)
            except Exception:
                return None
        return None

# ---------------------------------------------------------------- Blockscout

def fetch_verification(address: str, chain: Chain, opener=None, timeout=12):
    """Attempt source verification via Blockscout API v2.

    Returns dict: {status: 'verified'|'unverified'|'unknown', detail: str, raw: ...}
    Any transport / parse failure -> 'unknown' (could not check), never
    promoted to 'unverified'.
    """
    url = f"{chain.explorer_api}/v2/smart-contracts/{address}"
    try:
        if opener is not None:
            data = opener(url)
            j = data if isinstance(data, dict) else json.loads(data)
        else:
            req = urllib.request.Request(url, headers={
                "User-Agent": "robinhood-scanner/0.1",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # 404 on Blockscout v2 for an address means no verified contract record.
        # But only treat as unverified if body positively looks like not-found;
        # conservative route: any HTTP error where we cannot parse a clear
        # not-verified signal stays unknown, except 404 which Blockscout uses
        # for unknown addresses - distributors check this empirically.
        # To stay honest per Preflight discipline, 404 -> unknown unless
        # caller overrides. We document this in the detail.
        if e.code == 404:
            return {"status": "unknown", "detail": f"Blockscout returned 404 for {address} - could not confirm verification status (address may be unverified or not indexed)", "source": url}
        return {"status": "unknown", "detail": f"Blockscout HTTP {e.code}: could not check verification", "source": url}
    except Exception as e:
        return {"status": "unknown", "detail": f"Blockscout unreachable: {e} - could not check verification", "source": url}

    # Parse Blockscout v2 shape: is_verified, name, etc.
    try:
        if isinstance(j, dict):
            if j.get("is_verified") is True:
                return {"status": "verified", "detail": "source verified on Blockscout", "name": j.get("name"), "source": url}
            if j.get("is_verified") is False:
                return {"status": "unverified", "detail": "Blockscout record exists but is_verified is false", "name": j.get("name"), "source": url}
            # Some responses nest or use different key - treat missing as unknown
            return {"status": "unknown", "detail": "Blockscout response did not carry a clear is_verified flag - could not check", "source": url}
    except Exception as e:
        return {"status": "unknown", "detail": f"Blockscout response unparseable: {e}", "source": url}
    return {"status": "unknown", "detail": "could not check verification", "source": url}

# ---------------------------------------------------------------- verdict

def _reason(code, level, message):
    return {"code": code, "level": level, "message": message}

def evaluate_verdict(checks: dict) -> tuple:
    """Pure function: checks dict -> (verdict, reasons).

    Verdicts: CLEAR / CAUTION / BLOCKED / UNKNOWN
    UNKNOWN wins when a critical transport read failed (rpc_ok is False
    or deployment.code_read_failed is True or chain_id check failed at
    transport level). UNKNOWN is not a negative verdict about the contract.
    """
    reasons = []
    deployment = checks.get("deployment", {}) or {}
    verification = checks.get("verification", {}) or {}
    identity = checks.get("identity", {}) or {}
    chain_check = checks.get("chain", {}) or {}

    # --- transport failure -> UNKNOWN (discipline: never BLOCKED) ---
    rpc_failed = False
    if checks.get("rpc_ok") is False:
        rpc_failed = True
    if deployment.get("code_read_failed"):
        rpc_failed = True
    if chain_check.get("transport_failed"):
        rpc_failed = True

    if rpc_failed:
        detail = checks.get("rpc_error") or deployment.get("error") or chain_check.get("error") or "RPC unreachable"
        reasons.append(_reason("RPC_UNREACHABLE", "unknown",
            f"RPC transport failed ({detail}) - the contract was NOT checked. "
            "This is evidence about the network/endpoint, not about this address. "
            "Re-run when the RPC path is healthy."))
        # Still surface any independent info we do have, but verdict stays UNKNOWN
        return "UNKNOWN", reasons

    # --- chainId mismatch (transport succeeded, wrong chain) ---
    if chain_check.get("matches") is False:
        reasons.append(_reason("CHAIN_ID_MISMATCH", "caution",
            f"RPC returned chainId {chain_check.get('actual')} but expected {chain_check.get('expected')} for {chain_check.get('name')} - endpoint may be pointing at the wrong chain, results should not be trusted as Robinhood data"))

    # --- no contract ---
    if deployment.get("is_contract") is False:
        reasons.append(_reason("NOT_A_CONTRACT", "block",
            "address has no contract code on this chain on a successful read (wrong address or wrong chain)"))
        return "BLOCKED", reasons

    if deployment.get("is_contract") is None:
        # No successful read and not flagged as transport failure above -
        # be conservative: UNKNOWN, not BLOCKED.
        reasons.append(_reason("DEPLOYMENT_UNKNOWN", "unknown",
            "deployment could not be determined - no successful eth_getCode read"))
        return "UNKNOWN", reasons

    # --- contract exists from here ---
    code_size = deployment.get("code_size_bytes")
    if code_size is not None:
        reasons.append(_reason("CONTRACT_EXISTS", "info",
            f"contract code exists ({code_size} bytes)"))

    if deployment.get("is_proxy_eip1967"):
        reasons.append(_reason("UPGRADEABLE_PROXY", "caution",
            f"upgradeable proxy (EIP-1967): implementation {deployment.get('implementation')} can be swapped after this check - re-verify at signing/trading time"))

    # verification
    vstatus = verification.get("status", "unknown")
    if vstatus == "verified":
        reasons.append(_reason("SOURCE_VERIFIED", "info", "source code verified on Blockscout"))
    elif vstatus == "unverified":
        reasons.append(_reason("UNVERIFIED_SOURCE", "caution",
            "source code is NOT verified on Blockscout - nobody outside the project can read what this contract does"))
    else:
        reasons.append(_reason("VERIFICATION_UNCHECKED", "caution",
            f"verification status could not be checked ({verification.get('detail', 'Blockscout unreachable')}) - treat as unverified until confirmed"))

    # identity / owner
    owner = identity.get("owner")
    if owner:
        if owner.lower() == ZERO_ADDRESS:
            reasons.append(_reason("OWNER_RENOUNCED", "info", "owner() is the zero address (ownership renounced or no owner)"))
        else:
            reasons.append(_reason("OWNER_PRESENT", "info", f"contract has an owner ({owner}) - check what the owner can change"))
    if identity.get("name") or identity.get("symbol"):
        reasons.append(_reason("TOKEN_IDENTITY", "info",
            f"token identity: {identity.get('name')} ({identity.get('symbol')}) decimals={identity.get('decimals')} totalSupply={identity.get('totalSupply')}"))
    else:
        reasons.append(_reason("NO_TOKEN_METADATA", "info",
            "no ERC20 name/symbol answered - may not be a standard ERC20, or metadata is on the implementation contract (proxy)"))

    # sellability - honest note, always info, never a fake honeypot verdict
    reasons.append(_reason("SELLABILITY_NOT_PROVEN", "info",
        "sellability / honeypot status is NOT proven by this scan: proving it needs a DEX router quote + eth_call buy/sell simulation against the actual pool, which depends on the token's pair and router. This scanner does not fake that verdict. Treat any token as unsellable until you test a small buy and sell on the DEX itself"))

    levels = {r["level"] for r in reasons}
    if "block" in levels:
        return "BLOCKED", reasons
    if "unknown" in levels:
        return "UNKNOWN", reasons
    if "caution" in levels:
        return "CAUTION", reasons
    return "CLEAR", reasons

# ---------------------------------------------------------------- probing

def _read_view(rpc, contract, sig, decoder):
    try:
        res = rpc.eth_call(contract, encode_call(sig))
    except Exception as e:
        return None
    if isinstance(res, dict):
        return None
    if res in (None, "0x"):
        return None
    return decoder(res)

def scan_address(address: str, chain_key: str = "robinhood", rpc=None, verification_fetcher=None) -> dict:
    """Run the full scan. Injectable rpc / verification_fetcher for tests."""
    if not is_valid_address(address):
        return {
            "schema": "robinhood-scanner/1",
            "address": address,
            "chain": chain_key,
            "verdict": "UNKNOWN",
            "reasons": [_reason("INVALID_ADDRESS", "unknown", "address is not a valid 0x + 40 hex character EVM address - nothing was checked")],
            "checks": {},
            "error": "invalid_address",
        }
    addr = normalize_address(address)
    chain = CHAINS.get(chain_key)
    if chain is None:
        return {
            "schema": "robinhood-scanner/1",
            "address": addr,
            "chain": chain_key,
            "verdict": "UNKNOWN",
            "reasons": [_reason("UNKNOWN_CHAIN", "unknown", f"unknown chain '{chain_key}' - supported: robinhood, robinhood-testnet")],
            "checks": {},
            "error": "unknown_chain",
        }

    if rpc is None:
        rpc = Rpc(chain.rpcs)

    checks = {}

    # 1. chainId verification
    actual_chain_id = None
    chain_transport_failed = False
    chain_error = None
    try:
        actual_chain_id = rpc.chain_id()
    except Exception as e:
        chain_transport_failed = True
        chain_error = str(e)
    if actual_chain_id is None:
        # chain_id() returns None only on transport failure (see Rpc.call)
        # Distinguish: if rpc has errors recorded, it's transport.
        # In mocked tests, a mock returning None also means transport failure.
        chain_transport_failed = True
        chain_error = chain_error or (rpc.errors[-1] if getattr(rpc, "errors", None) else "eth_chainId returned no result")
    checks["chain"] = {
        "name": chain.name,
        "expected": chain.chain_id,
        "actual": actual_chain_id,
        "matches": (actual_chain_id == chain.chain_id) if actual_chain_id is not None else None,
        "transport_failed": chain_transport_failed if actual_chain_id is None else False,
        "error": chain_error if actual_chain_id is None else None,
        "rpc_endpoint": chain.rpcs[0],
    }

    # If chainId transport failed, we cannot trust any further read -
    # still attempt getCode? Per discipline, verdict will be UNKNOWN anyway.
    # Short-circuit to UNKNOWN to avoid manufacturing other verdicts.
    if actual_chain_id is None:
        checks["deployment"] = {"is_contract": None, "code_read_failed": True, "error": chain_error}
        checks["verification"] = {"status": "unknown", "detail": "skipped - RPC unreachable"}
        checks["identity"] = {}
        checks["rpc_ok"] = False
        checks["rpc_error"] = f"eth_chainId transport failure: {chain_error}"
        verdict, reasons = evaluate_verdict(checks)
        return {
            "schema": "robinhood-scanner/1",
            "address": addr,
            "chain": chain.key,
            "chain_name": chain.name,
            "expected_chain_id": chain.chain_id,
            "verdict": verdict,
            "reasons": reasons,
            "checks": checks,
        }

    # 2. code exists / size
    code = None
    code_read_failed = False
    try:
        code = rpc.call("eth_getCode", [addr, "latest"])
    except Exception as e:
        code_read_failed = True
        code = None
    if not isinstance(code, str):
        code_read_failed = True
    code_hex = code[2:] if isinstance(code, str) else ""
    is_contract = None if code_read_failed else len(code_hex) > 0
    code_size = None if code_read_failed else len(code_hex) // 2

    # 3. proxy detection (only if contract exists)
    impl = None
    admin = None
    if is_contract:
        try:
            impl_raw = rpc.call("eth_getStorageAt", [addr, EIP1967_IMPL_SLOT, "latest"])
            if impl_raw and isinstance(impl_raw, str) and int(impl_raw, 16) != 0:
                impl = dec_address(impl_raw)
        except Exception:
            impl = None
        try:
            admin_raw = rpc.call("eth_getStorageAt", [addr, EIP1967_ADMIN_SLOT, "latest"])
            if admin_raw and isinstance(admin_raw, str) and int(admin_raw, 16) != 0:
                admin = dec_address(admin_raw)
        except Exception:
            admin = None

    checks["deployment"] = {
        "is_contract": is_contract,
        "code_read_failed": code_read_failed,
        "code_size_bytes": code_size,
        "is_proxy_eip1967": impl is not None,
        "implementation": impl,
        "proxy_admin": admin,
    }
    checks["rpc_ok"] = not code_read_failed
    if code_read_failed:
        checks["rpc_error"] = "eth_getCode transport failure - every RPC endpoint failed or returned malformed data"

    # 4. verification via Blockscout
    if verification_fetcher is not None:
        try:
            verification = verification_fetcher(addr, chain)
        except Exception as e:
            verification = {"status": "unknown", "detail": f"verification fetcher failed: {e}"}
    else:
        # Only attempt Blockscout if RPC succeeded - avoids long waits when offline
        if code_read_failed:
            verification = {"status": "unknown", "detail": "skipped - RPC failed"}
        else:
            verification = fetch_verification(addr, chain)
    checks["verification"] = verification

    # 5. ERC20 + owner probes (only if contract)
    identity = {"name": None, "symbol": None, "decimals": None, "totalSupply": None, "owner": None}
    if is_contract:
        identity["name"] = _read_view(rpc, addr, "name()", dec_string)
        identity["symbol"] = _read_view(rpc, addr, "symbol()", dec_string)
        identity["decimals"] = _read_view(rpc, addr, "decimals()", dec_uint)
        identity["totalSupply"] = _read_view(rpc, addr, "totalSupply()", dec_uint)
        # totalSupply as string for JSON safety (can exceed JS safe int, keep int in python json is fine)
        identity["owner"] = _read_view(rpc, addr, "owner()", dec_address)
    checks["identity"] = identity

    checks["sellability"] = {
        "proven": False,
        "note": "Not proven by this scan. Needs DEX router + pool simulation. See reason SELLABILITY_NOT_PROVEN.",
        "method_needed": "Find the token's DEX pair/router on Robinhood Chain, quote a small buy, eth_call simulate buy then sell, check round-trip - that flow is router-specific and not faked here.",
    }

    verdict, reasons = evaluate_verdict(checks)
    return {
        "schema": "robinhood-scanner/1",
        "address": addr,
        "chain": chain.key,
        "chain_name": chain.name,
        "expected_chain_id": chain.chain_id,
        "explorer_url": f"{chain.explorer_url}/address/{addr}",
        "verdict": verdict,
        "reasons": reasons,
        "checks": checks,
    }

