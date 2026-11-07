// test_verdict.mjs - Node tests for the browser scanner's pure logic.
//
// Run:  node docs/test_verdict.mjs
//
// This test IMPORTS the real verdict code from ./scan-core.js (no
// replication): docs/index.html carries an inline duplicate of the same
// functions because it must be one self-contained file for GitHub Pages,
// and scan-core.js is the canonical copy these tests exercise. If you
// change the verdict logic, change both copies and re-run this file.

import {
  CHAINS,
  EIP1967_IMPL_SLOT,
  isValidAddress,
  normalizeAddress,
  decUint,
  decAddress,
  decString,
  evaluateVerdict,
} from "./scan-core.js";

let passed = 0;
let failed = 0;

function check(name, cond, extra) {
  if (cond) {
    passed++;
    console.log("ok   - " + name);
  } else {
    failed++;
    console.log("FAIL - " + name + (extra !== undefined ? " :: " + JSON.stringify(extra) : ""));
  }
}

function codes(result) {
  return result.reasons.map((r) => r.code);
}

function baseChecks(overrides) {
  const base = {
    rpc_ok: true,
    chain: { name: "Robinhood Chain", expected: 4663, actual: 4663, matches: true, transport_failed: false, error: null },
    deployment: { is_contract: true, code_read_failed: false, code_size_bytes: 4200, is_proxy_eip1967: false, implementation: null, proxy_admin: null },
    verification: { status: "verified", detail: "source verified on Blockscout" },
    identity: { name: "TestToken", symbol: "TST", decimals: 18, totalSupply: "1000000", owner: "0x1111111111111111111111111111111111111111" },
  };
  return Object.assign(base, overrides || {});
}

// ---------------------------------------------------------------- validation
check("valid address accepted", isValidAddress("0x1111111111111111111111111111111111111111") === true);
check("checksummed address accepted", isValidAddress("0xAbCdEf0123456789aBcDeF0123456789AbCdEf01") === true);
check("short address rejected", isValidAddress("0x1234") === false);
check("missing 0x rejected", isValidAddress("1111111111111111111111111111111111111111") === false);
check("non-hex rejected", isValidAddress("0xZZZZ111111111111111111111111111111111111") === false);
check("non-string rejected", isValidAddress(null) === false && isValidAddress(42) === false);
check("normalize lowercases + trims", normalizeAddress(" 0xABCDEF0123456789ABCDEF0123456789ABCDEF01 ") === "0xabcdef0123456789abcdef0123456789abcdef01");

// ---------------------------------------------------------------- ABI decode
function abiEncodeString(s) {
  const bytes = new TextEncoder().encode(s);
  const word = (n) => n.toString(16).padStart(64, "0");
  let hex = "0x" + word(32) + word(bytes.length);
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  while ((hex.length - 2) % 64 !== 0) hex += "00";
  return hex;
}
check("ABI string decode (dynamic)", decString(abiEncodeString("TestToken")) === "TestToken");
check("ABI string decode (empty result)", decString("0x") === null);
check("ABI uint decode small", decUint("0x" + (18).toString(16).padStart(64, "0")) === 18n);
check("ABI uint decode big (totalSupply > 2^53)",
  decUint("0x" + (123456789012345678901234567890n).toString(16).padStart(64, "0")) === 123456789012345678901234567890n);
check("ABI address decode from storage word",
  decAddress("0x" + "0".repeat(24) + "2222222222222222222222222222222222222222") === "0x2222222222222222222222222222222222222222");
check("EIP-1967 impl slot matches the Python constant",
  EIP1967_IMPL_SLOT === "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc");
check("chain config: mainnet 4663, testnet 46630",
  CHAINS["robinhood"].chainId === 4663 && CHAINS["robinhood-testnet"].chainId === 46630);

// ------------------------------------------------- 1. verified token -> CLEAR
{
  const r = evaluateVerdict(baseChecks());
  check("verified token -> CLEAR", r.verdict === "CLEAR", r);
  check("CLEAR report carries SELLABILITY_NOT_PROVEN", codes(r).includes("SELLABILITY_NOT_PROVEN"));
  check("CLEAR report carries SOURCE_VERIFIED", codes(r).includes("SOURCE_VERIFIED"));
}

// ------------------------------------------------- 2. no code -> BLOCKED
{
  const checks = baseChecks({
    deployment: { is_contract: false, code_read_failed: false, code_size_bytes: 0, is_proxy_eip1967: false, implementation: null, proxy_admin: null },
  });
  const r = evaluateVerdict(checks);
  check("no code on successful read -> BLOCKED", r.verdict === "BLOCKED", r);
  check("BLOCKED reason is NOT_A_CONTRACT", codes(r).includes("NOT_A_CONTRACT"));
}

// --------------------------------------- 3. RPC failure -> UNKNOWN, never BLOCKED
{
  const checks = baseChecks({
    rpc_ok: false,
    rpc_error: "eth_chainId transport failure: Failed to fetch",
    chain: { name: "Robinhood Chain", expected: 4663, actual: null, matches: null, transport_failed: true, error: "Failed to fetch" },
    deployment: { is_contract: null, code_read_failed: true, code_size_bytes: null, is_proxy_eip1967: false, implementation: null, proxy_admin: null, error: "Failed to fetch" },
  });
  const r = evaluateVerdict(checks);
  check("RPC failure -> UNKNOWN", r.verdict === "UNKNOWN", r);
  check("RPC failure reason is RPC_UNREACHABLE", codes(r).includes("RPC_UNREACHABLE"));
  check("RPC failure: NOT_A_CONTRACT absent (transport is not a verdict)", !codes(r).includes("NOT_A_CONTRACT"));
  check("RPC failure: verdict is not BLOCKED", r.verdict !== "BLOCKED");
}
{
  // getCode-only failure (chainId succeeded, code read failed) is also UNKNOWN.
  const checks = baseChecks({
    rpc_ok: false,
    rpc_error: "eth_getCode transport failure",
    deployment: { is_contract: null, code_read_failed: true, code_size_bytes: null, is_proxy_eip1967: false, implementation: null, proxy_admin: null },
  });
  const r = evaluateVerdict(checks);
  check("getCode failure -> UNKNOWN, NOT_A_CONTRACT absent", r.verdict === "UNKNOWN" && !codes(r).includes("NOT_A_CONTRACT"), r);
}
{
  // Deployment undetermined without a successful read -> UNKNOWN.
  const checks = baseChecks({
    deployment: { is_contract: null, code_read_failed: false, code_size_bytes: null, is_proxy_eip1967: false, implementation: null, proxy_admin: null },
  });
  const r = evaluateVerdict(checks);
  check("deployment undetermined -> UNKNOWN", r.verdict === "UNKNOWN" && codes(r).includes("DEPLOYMENT_UNKNOWN"), r);
}

// ------------------------------------------------- 4. proxy -> CAUTION
{
  const checks = baseChecks({
    deployment: { is_contract: true, code_read_failed: false, code_size_bytes: 900, is_proxy_eip1967: true, implementation: "0x3333333333333333333333333333333333333333", proxy_admin: null },
  });
  const r = evaluateVerdict(checks);
  check("upgradeable proxy (verified) -> CAUTION", r.verdict === "CAUTION", r);
  check("proxy reason is UPGRADEABLE_PROXY", codes(r).includes("UPGRADEABLE_PROXY"));
}

// --------------------------- 5. Blockscout failure -> verification unknown -> CAUTION
{
  // This is the checks object the browser scan builds when the Blockscout
  // fetch throws (network error or CORS): status unknown, never unverified.
  const checks = baseChecks({
    verification: { status: "unknown", detail: "Blockscout unreachable: Failed to fetch - could not check verification" },
  });
  const r = evaluateVerdict(checks);
  check("Blockscout failure -> CAUTION (not CLEAR, not unverified-block)", r.verdict === "CAUTION", r);
  check("Blockscout failure reason is VERIFICATION_UNCHECKED", codes(r).includes("VERIFICATION_UNCHECKED"));
  check("Blockscout failure does NOT claim UNVERIFIED_SOURCE", !codes(r).includes("UNVERIFIED_SOURCE"));
}

// --------------------------------- 6. Blockscout answered unverified -> CAUTION
{
  const checks = baseChecks({
    verification: { status: "unverified", detail: "Blockscout record exists but is_verified is false" },
  });
  const r = evaluateVerdict(checks);
  check("answered unverified -> CAUTION with UNVERIFIED_SOURCE",
    r.verdict === "CAUTION" && codes(r).includes("UNVERIFIED_SOURCE"), r);
}

// --------------------------------- 7. chainId mismatch -> CAUTION flag, no fake verdict
{
  const checks = baseChecks({
    chain: { name: "Robinhood Chain", expected: 4663, actual: 1, matches: false, transport_failed: false, error: null },
  });
  const r = evaluateVerdict(checks);
  check("chainId mismatch -> CAUTION with CHAIN_ID_MISMATCH",
    r.verdict === "CAUTION" && codes(r).includes("CHAIN_ID_MISMATCH"), r);
}

console.log("\n" + passed + " passed, " + failed + " failed");
if (failed > 0) process.exit(1);
