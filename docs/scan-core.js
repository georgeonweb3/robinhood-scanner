// scan-core.js - pure logic for the Robinhood Chain Safety Scanner (browser build).
//
// This module is a faithful JavaScript port of the pure functions in
// ../scanner/core.py (validation + verdict engine) and ../scanner/abi.py
// (ABI decoding). It contains NO network code, so it can be unit-tested
// in Node (see test_verdict.mjs).
//
// docs/index.html is a single self-contained file (GitHub Pages, no
// external assets), so it carries an inline DUPLICATE of these same
// functions. Keep the two copies in sync: any change here must be
// mirrored in the inline <script> in index.html.
//
// Verdict discipline (rpc_failure_verdict_discipline):
// - A failed RPC/transport read is UNKNOWN, never BLOCKED.
// - BLOCKED / NOT_A_CONTRACT only on a SUCCESSFUL read returning no code.
// - Blockscout failure is verification "unknown" (could not check),
//   never "unverified".

export const CHAINS = {
  "robinhood": {
    key: "robinhood",
    name: "Robinhood Chain",
    chainId: 4663,
    rpc: "https://rpc.mainnet.chain.robinhood.com",
    explorerUrl: "https://robinhoodchain.blockscout.com",
    blockscoutApi: "https://robinhoodchain.blockscout.com/api",
  },
  "robinhood-testnet": {
    key: "robinhood-testnet",
    name: "Robinhood Chain Testnet",
    chainId: 46630,
    rpc: "https://rpc.testnet.chain.robinhood.com",
    explorerUrl: "https://robinhoodchain.blockscout.com",
    blockscoutApi: "https://robinhoodchain.blockscout.com/api",
  },
};

export const EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc";
export const EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103";
export const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";

const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

export function isValidAddress(addr) {
  return typeof addr === "string" && ADDRESS_RE.test(addr.trim());
}

export function normalizeAddress(addr) {
  return addr.trim().toLowerCase();
}

// ---------------------------------------------------------------- ABI decode
// Mirrors scanner/abi.py. Input is a 0x-prefixed hex string (or null).

export function decUint(hexdata) {
  if (!hexdata || hexdata === "0x") return null;
  try {
    // First 32-byte word. BigInt: totalSupply can exceed Number.MAX_SAFE_INTEGER.
    return BigInt("0x" + hexdata.slice(2, 66));
  } catch (e) {
    return null;
  }
}

export function decAddress(hexdata) {
  if (!hexdata || hexdata.length < 66) return null;
  return "0x" + hexdata.slice(26, 66).toLowerCase();
}

export function decString(hexdata) {
  if (!hexdata || hexdata === "0x") return null;
  try {
    const hex = hexdata.slice(2);
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    if (bytes.length >= 64) {
      // ABI dynamic string: word 1 = offset, word 2 = length, then bytes.
      // Mirrors the Python decoder, which reads the length from word 2.
      let length = 0n;
      for (let i = 32; i < 64; i++) length = (length << 8n) | BigInt(bytes[i]);
      if (length >= 0n && length <= 10000n && bytes.length >= 64 + Number(length)) {
        return new TextDecoder("utf-8", { fatal: false }).decode(bytes.slice(64, 64 + Number(length)));
      }
    }
    // Fallback (e.g. bytes32-style): strip trailing zero bytes and decode.
    let end = bytes.length;
    while (end > 0 && bytes[end - 1] === 0) end--;
    return new TextDecoder("utf-8", { fatal: false }).decode(bytes.slice(0, end));
  } catch (e) {
    return null;
  }
}

// ---------------------------------------------------------------- verdict
// Mirrors evaluate_verdict() in scanner/core.py.
// Input: a checks object of the same shape the Python scanner builds:
//   {
//     rpc_ok: bool,
//     rpc_error: string?,
//     chain:      { name, expected, actual, matches, transport_failed, error },
//     deployment: { is_contract, code_read_failed, code_size_bytes,
//                   is_proxy_eip1967, implementation, proxy_admin, error },
//     verification: { status: 'verified'|'unverified'|'unknown', detail },
//     identity:   { name, symbol, decimals, totalSupply, owner }
//   }
// Output: { verdict, reasons: [{code, level, message}] }

function reason(code, level, message) {
  return { code, level, message };
}

export function evaluateVerdict(checks) {
  const reasons = [];
  const deployment = checks.deployment || {};
  const verification = checks.verification || {};
  const identity = checks.identity || {};
  const chainCheck = checks.chain || {};

  // --- transport failure -> UNKNOWN (discipline: never BLOCKED) ---
  let rpcFailed = false;
  if (checks.rpc_ok === false) rpcFailed = true;
  if (deployment.code_read_failed) rpcFailed = true;
  if (chainCheck.transport_failed) rpcFailed = true;

  if (rpcFailed) {
    const detail = checks.rpc_error || deployment.error || chainCheck.error || "RPC unreachable";
    reasons.push(reason("RPC_UNREACHABLE", "unknown",
      "RPC transport failed (" + detail + ") - the contract was NOT checked. " +
      "This is evidence about the network/endpoint, not about this address. " +
      "Re-run when the RPC path is healthy."));
    return { verdict: "UNKNOWN", reasons };
  }

  // --- chainId mismatch (transport succeeded, wrong chain) ---
  if (chainCheck.matches === false) {
    reasons.push(reason("CHAIN_ID_MISMATCH", "caution",
      "RPC returned chainId " + chainCheck.actual + " but expected " + chainCheck.expected +
      " for " + chainCheck.name + " - endpoint may be pointing at the wrong chain, " +
      "results should not be trusted as Robinhood data"));
  }

  // --- no contract (only reachable on a successful read) ---
  if (deployment.is_contract === false) {
    reasons.push(reason("NOT_A_CONTRACT", "block",
      "address has no contract code on this chain on a successful read (wrong address or wrong chain)"));
    return { verdict: "BLOCKED", reasons };
  }

  if (deployment.is_contract === null || deployment.is_contract === undefined) {
    reasons.push(reason("DEPLOYMENT_UNKNOWN", "unknown",
      "deployment could not be determined - no successful eth_getCode read"));
    return { verdict: "UNKNOWN", reasons };
  }

  // --- contract exists from here ---
  if (deployment.code_size_bytes !== null && deployment.code_size_bytes !== undefined) {
    reasons.push(reason("CONTRACT_EXISTS", "info",
      "contract code exists (" + deployment.code_size_bytes + " bytes)"));
  }

  if (deployment.is_proxy_eip1967) {
    reasons.push(reason("UPGRADEABLE_PROXY", "caution",
      "upgradeable proxy (EIP-1967): implementation " + deployment.implementation +
      " can be swapped after this check - re-verify at signing/trading time"));
  }

  // verification
  const vstatus = verification.status || "unknown";
  if (vstatus === "verified") {
    reasons.push(reason("SOURCE_VERIFIED", "info", "source code verified on Blockscout"));
  } else if (vstatus === "unverified") {
    reasons.push(reason("UNVERIFIED_SOURCE", "caution",
      "source code is NOT verified on Blockscout - nobody outside the project can read what this contract does"));
  } else {
    reasons.push(reason("VERIFICATION_UNCHECKED", "caution",
      "verification status could not be checked (" + (verification.detail || "Blockscout unreachable") + ") - treat as unverified until confirmed"));
  }

  // identity / owner
  const owner = identity.owner;
  if (owner) {
    if (String(owner).toLowerCase() === ZERO_ADDRESS) {
      reasons.push(reason("OWNER_RENOUNCED", "info", "owner() is the zero address (ownership renounced or no owner)"));
    } else {
      reasons.push(reason("OWNER_PRESENT", "info", "contract has an owner (" + owner + ") - check what the owner can change"));
    }
  }
  if (identity.name || identity.symbol) {
    reasons.push(reason("TOKEN_IDENTITY", "info",
      "token identity: " + identity.name + " (" + identity.symbol + ") decimals=" +
      identity.decimals + " totalSupply=" + identity.totalSupply));
  } else {
    reasons.push(reason("NO_TOKEN_METADATA", "info",
      "no ERC20 name/symbol answered - may not be a standard ERC20, or metadata is on the implementation contract (proxy)"));
  }

  // sellability - honest note, always info, never a fake honeypot verdict
  reasons.push(reason("SELLABILITY_NOT_PROVEN", "info",
    "sellability / honeypot status is NOT proven by this scan: proving it needs a DEX router quote + eth_call buy/sell simulation against the actual pool, which depends on the token's pair and router. This scanner does not fake that verdict. Treat any token as unsellable until you test a small buy and sell on the DEX itself"));

  const levels = new Set(reasons.map((r) => r.level));
  if (levels.has("block")) return { verdict: "BLOCKED", reasons };
  if (levels.has("unknown")) return { verdict: "UNKNOWN", reasons };
  if (levels.has("caution")) return { verdict: "CAUTION", reasons };
  return { verdict: "CLEAR", reasons };
}
