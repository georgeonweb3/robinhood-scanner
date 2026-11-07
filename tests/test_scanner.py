"""Unit tests for Robinhood Chain Safety Scanner.

Run: python3 -m unittest discover -s tests -v
Stdlib unittest only. No network in these tests - RPC is mocked.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scanner.core import (
    CHAINS, Rpc, evaluate_verdict, is_valid_address, scan_address,
)
from scanner.keccak import selector, selftest as keccak_selftest
from scanner.abi import encode_call, dec_uint

VALID = "0x0000000000000000000000000000000000000001"
VALID2 = "0xA79E2C85D5456Fa3d9115d86398896a390159D1c"

# --- Mock RPCs -------------------------------------------------------

class MockRpcOk:
    """Simulates a healthy RPC: chainId matches, contract exists, verified token."""
    def __init__(self, chain_id=4663, code="0x6080604052348015600e575f80fd5b50"):
        self._chain_id = chain_id
        self._code = code
        self.errors = []
    def chain_id(self):
        return self._chain_id
    def call(self, method, params):
        if method == "eth_chainId":
            return hex(self._chain_id)
        if method == "eth_getCode":
            return self._code
        if method == "eth_getStorageAt":
            return "0x" + "0" * 64
        return None
    def eth_call(self, to, data):
        # name() selector 06fdde03, symbol() 95d89b41, decimals() 313ce567,
        # totalSupply() 18160ddd, owner() 8da5cb5b
        if data.startswith("0x06fdde03"):
            # ABI string "TestToken"
            name = b"TestToken"
            return "0x" + ("%064x" % 32) + ("%064x" % len(name)) + name.hex().ljust(64, "0")
        if data.startswith("0x95d89b41"):
            sym = b"TEST"
            return "0x" + ("%064x" % 32) + ("%064x" % len(sym)) + sym.hex().ljust(64, "0")
        if data.startswith("0x313ce567"):
            return "0x" + ("%064x" % 18)
        if data.startswith("0x18160ddd"):
            return "0x" + ("%064x" % 1000000)
        if data.startswith("0x8da5cb5b"):
            return "0x" + "0" * 24 + "0000000000000000000000000000000000000000"
        return "0x"

class MockRpcNoContract:
    def __init__(self):
        self.errors = []
    def chain_id(self):
        return 4663
    def call(self, method, params):
        if method == "eth_getCode":
            return "0x"
        if method == "eth_getStorageAt":
            return "0x" + "0" * 64
        return None
    def eth_call(self, to, data):
        return "0x"

class MockRpcFail:
    """Every transport read fails - chain_id None, getCode None."""
    def __init__(self):
        self.errors = ["https://rpc.mainnet.chain.robinhood.com: simulated timeout"]
    def chain_id(self):
        return None
    def call(self, method, params):
        return None
    def eth_call(self, to, data):
        return {"__error__": "simulated transport failure"}

class MockRpcCodeFailOnly:
    """ChainId ok, but getCode fails at transport level."""
    def __init__(self):
        self.errors = ["getCode timeout"]
    def chain_id(self):
        return 4663
    def call(self, method, params):
        if method == "eth_getCode":
            return None
        if method == "eth_getStorageAt":
            return "0x" + "0" * 64
        return None
    def eth_call(self, to, data):
        return "0x"

def verified_fetcher(addr, chain):
    return {"status": "verified", "detail": "source verified on Blockscout (mock)"}

def unverified_fetcher(addr, chain):
    return {"status": "unverified", "detail": "not verified (mock)"}

def unknown_fetcher(addr, chain):
    return {"status": "unknown", "detail": "Blockscout unreachable (mock) - could not check"}

# --- Tests -----------------------------------------------------------

class TestAddressValidation(unittest.TestCase):
    def test_valid_lowercase(self):
        self.assertTrue(is_valid_address("0x0000000000000000000000000000000000000001"))
    def test_valid_checksum(self):
        self.assertTrue(is_valid_address(VALID2))
    def test_invalid_short(self):
        self.assertFalse(is_valid_address("0x123"))
    def test_invalid_no_prefix(self):
        self.assertFalse(is_valid_address("0000000000000000000000000000000000000001"))
    def test_invalid_non_hex(self):
        self.assertFalse(is_valid_address("0xZZZZ000000000000000000000000000000000001"))
    def test_invalid_empty(self):
        self.assertFalse(is_valid_address(""))
        self.assertFalse(is_valid_address(None))
    def test_zero_address_is_valid_format(self):
        self.assertTrue(is_valid_address("0x0000000000000000000000000000000000000000"))

class TestKeccak(unittest.TestCase):
    def test_selftest(self):
        self.assertTrue(keccak_selftest())
    def test_known_selectors(self):
        self.assertEqual(selector("name()"), "06fdde03")
        self.assertEqual(selector("symbol()"), "95d89b41")
        self.assertEqual(selector("owner()"), "8da5cb5b")
        self.assertEqual(selector("totalSupply()"), "18160ddd")

class TestChains(unittest.TestCase):
    def test_robinhood_mainnet(self):
        c = CHAINS["robinhood"]
        self.assertEqual(c.chain_id, 4663)
        self.assertIn("rpc.mainnet.chain.robinhood.com", c.rpcs[0])
    def test_robinhood_testnet(self):
        c = CHAINS["robinhood-testnet"]
        self.assertEqual(c.chain_id, 46630)
        self.assertIn("rpc.testnet.chain.robinhood.com", c.rpcs[0])

class TestVerdictLogic(unittest.TestCase):
    def _base_checks(self):
        return {
            "rpc_ok": True,
            "chain": {"expected": 4663, "actual": 4663, "matches": True, "transport_failed": False},
            "deployment": {"is_contract": True, "code_read_failed": False, "code_size_bytes": 5000, "is_proxy_eip1967": False, "implementation": None},
            "verification": {"status": "verified", "detail": "ok"},
            "identity": {"name": "Test", "symbol": "TEST", "decimals": 18, "totalSupply": 1000, "owner": "0x0000000000000000000000000000000000000000"},
        }
    def test_clear_when_verified_not_proxy(self):
        verdict, reasons = evaluate_verdict(self._base_checks())
        self.assertEqual(verdict, "CLEAR")
    def test_caution_when_unverified(self):
        checks = self._base_checks()
        checks["verification"] = {"status": "unverified", "detail": "not verified"}
        verdict, _ = evaluate_verdict(checks)
        self.assertEqual(verdict, "CAUTION")
    def test_caution_when_verification_unknown(self):
        checks = self._base_checks()
        checks["verification"] = {"status": "unknown", "detail": "could not check"}
        verdict, reasons = evaluate_verdict(checks)
        self.assertEqual(verdict, "CAUTION")
        self.assertTrue(any(r["code"] == "VERIFICATION_UNCHECKED" for r in reasons))
    def test_caution_when_proxy(self):
        checks = self._base_checks()
        checks["deployment"]["is_proxy_eip1967"] = True
        checks["deployment"]["implementation"] = VALID
        verdict, _ = evaluate_verdict(checks)
        self.assertEqual(verdict, "CAUTION")
    def test_blocked_when_no_contract(self):
        checks = self._base_checks()
        checks["deployment"]["is_contract"] = False
        checks["deployment"]["code_size_bytes"] = 0
        verdict, reasons = evaluate_verdict(checks)
        self.assertEqual(verdict, "BLOCKED")
        self.assertTrue(any(r["code"] == "NOT_A_CONTRACT" for r in reasons))
    def test_unknown_when_rpc_failed_flag(self):
        checks = self._base_checks()
        checks["rpc_ok"] = False
        checks["rpc_error"] = "timeout"
        verdict, _ = evaluate_verdict(checks)
        self.assertEqual(verdict, "UNKNOWN")
    def test_unknown_when_code_read_failed_never_blocked(self):
        # Core discipline: failed code read must NOT become BLOCKED / NOT_A_CONTRACT
        checks = self._base_checks()
        checks["deployment"]["code_read_failed"] = True
        checks["deployment"]["is_contract"] = None
        verdict, reasons = evaluate_verdict(checks)
        self.assertEqual(verdict, "UNKNOWN")
        self.assertFalse(any(r["code"] == "NOT_A_CONTRACT" for r in reasons))
    def test_unknown_when_chain_transport_failed(self):
        checks = self._base_checks()
        checks["chain"]["transport_failed"] = True
        verdict, _ = evaluate_verdict(checks)
        self.assertEqual(verdict, "UNKNOWN")
    def test_sellability_note_always_present_and_info_only(self):
        checks = self._base_checks()
        verdict, reasons = evaluate_verdict(checks)
        sell = [r for r in reasons if r["code"] == "SELLABILITY_NOT_PROVEN"]
        self.assertEqual(len(sell), 1)
        self.assertEqual(sell[0]["level"], "info")
        # Info alone must not block a CLEAR
        self.assertEqual(verdict, "CLEAR")

class TestScanWithMocks(unittest.TestCase):
    def test_scan_clear_with_mock_ok_and_verified(self):
        report = scan_address(VALID, chain_key="robinhood", rpc=MockRpcOk(), verification_fetcher=verified_fetcher)
        self.assertEqual(report["verdict"], "CLEAR")
        self.assertEqual(report["checks"]["identity"]["name"], "TestToken")
        self.assertEqual(report["checks"]["identity"]["symbol"], "TEST")
        self.assertEqual(report["checks"]["identity"]["decimals"], 18)
    def test_scan_caution_unverified(self):
        report = scan_address(VALID, chain_key="robinhood", rpc=MockRpcOk(), verification_fetcher=unverified_fetcher)
        self.assertEqual(report["verdict"], "CAUTION")
    def test_scan_blocked_no_contract(self):
        report = scan_address(VALID, chain_key="robinhood", rpc=MockRpcNoContract(), verification_fetcher=verified_fetcher)
        self.assertEqual(report["verdict"], "BLOCKED")
    def test_scan_unknown_on_rpc_failure(self):
        report = scan_address(VALID, chain_key="robinhood", rpc=MockRpcFail(), verification_fetcher=verified_fetcher)
        self.assertEqual(report["verdict"], "UNKNOWN")
        self.assertFalse(any(r["code"] == "NOT_A_CONTRACT" for r in report["reasons"]))
    def test_scan_unknown_on_code_read_failure(self):
        report = scan_address(VALID, chain_key="robinhood", rpc=MockRpcCodeFailOnly(), verification_fetcher=verified_fetcher)
        self.assertEqual(report["verdict"], "UNKNOWN")
    def test_scan_invalid_address(self):
        report = scan_address("0x123", chain_key="robinhood", rpc=MockRpcOk(), verification_fetcher=verified_fetcher)
        self.assertEqual(report["verdict"], "UNKNOWN")
        self.assertEqual(report.get("error"), "invalid_address")
    def test_scan_zero_address_handling_no_contract(self):
        # Zero address with a healthy RPC that returns 0x code -> BLOCKED (not a contract), not a crash
        report = scan_address("0x0000000000000000000000000000000000000000", chain_key="robinhood", rpc=MockRpcNoContract(), verification_fetcher=unknown_fetcher)
        self.assertEqual(report["verdict"], "BLOCKED")

class TestRpcAllowlist(unittest.TestCase):
    def test_rpc_refuses_non_readonly(self):
        rpc = Rpc(["https://example.invalid"])
        with self.assertRaises(ValueError):
            rpc.call("eth_sendTransaction", [])

if __name__ == "__main__":
    unittest.main()
