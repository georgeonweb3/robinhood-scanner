"""CLI: python3 -m scanner check <address> --chain robinhood [--json]"""
import argparse
import json
import sys

from .core import CHAINS, is_valid_address, scan_address

def _print_human(report):
    print(f"Address   {report.get('address')}")
    print(f"Chain     {report.get('chain_name', report.get('chain'))} (expected chainId {report.get('expected_chain_id')})")
    if report.get("explorer_url"):
        print(f"Explorer  {report['explorer_url']}")
    checks = report.get("checks", {})
    chain_c = checks.get("chain", {})
    if chain_c:
        print(f"ChainId   actual={chain_c.get('actual')} expected={chain_c.get('expected')} matches={chain_c.get('matches')}")
    dep = checks.get("deployment", {})
    if dep:
        print(f"Contract  is_contract={dep.get('is_contract')} size={dep.get('code_size_bytes')} proxy={dep.get('is_proxy_eip1967')} impl={dep.get('implementation')}")
    ver = checks.get("verification", {})
    if ver:
        print(f"Verified  status={ver.get('status')} - {ver.get('detail')}")
    ident = checks.get("identity", {})
    if ident and any(ident.values()):
        print(f"Token     name={ident.get('name')} symbol={ident.get('symbol')} decimals={ident.get('decimals')} totalSupply={ident.get('totalSupply')} owner={ident.get('owner')}")
    print("-" * 72)
    print(f"VERDICT   {report.get('verdict')}")
    for r in report.get("reasons", []):
        level = r.get("level", "info").upper()
        print(f"  [{level:7}] {r.get('code')}: {r.get('message')}")
    print()
    print("Note: CLEAR = nothing this scanner checks tripped. It is not a guarantee,")
    print("not an audit, and sellability is not proven here - test a small buy/sell yourself.")

def main(argv=None):
    parser = argparse.ArgumentParser(prog="scanner", description="Robinhood Chain Safety Scanner - read-only, never signs")
    sub = parser.add_subparsers(dest="cmd")
    p_check = sub.add_parser("check", help="check a contract address")
    p_check.add_argument("address", help="0x contract address")
    p_check.add_argument("--chain", default="robinhood", choices=["robinhood", "robinhood-testnet", "mainnet", "testnet"], help="chain (default robinhood)")
    p_check.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--version", action="store_true", help="print version")

    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        from . import __version__
        print(__version__)
        return 0
    if args.cmd != "check":
        parser.print_help()
        return 2
    if not is_valid_address(args.address):
        msg = f"invalid address: {args.address!r} - expected 0x + 40 hex chars"
        if args.json:
            print(json.dumps({"verdict": "UNKNOWN", "error": "invalid_address", "message": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 2
    # Normalize alias to canonical key for CHAINS lookup inside scan (it handles aliases via CHAINS dict)
    chain_key = args.chain
    report = scan_address(args.address, chain_key=chain_key)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_human(report)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
