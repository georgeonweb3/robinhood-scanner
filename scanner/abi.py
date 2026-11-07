"""Minimal ABI encode/decode - stdlib only, reused pattern from Preflight."""
from .keccak import selector

def encode_call(sig: str, args=None) -> str:
    args = args or []
    # Only no-arg calls needed for this scanner (name/symbol/decimals/totalSupply/owner)
    # Keep generic support for address/uint if extended later.
    data = selector(sig)
    inner = sig[sig.index("(") + 1:sig.rindex(")")] if "(" in sig else ""
    types = inner.split(",") if inner else []
    for t, v in zip(types, args):
        if t == "address":
            data += "000000000000000000000000" + v.lower().replace("0x", "")
        elif t.startswith("uint") or t.startswith("int"):
            data += "%064x" % int(v)
        elif t == "bool":
            data += "%064x" % (1 if v else 0)
        else:
            raise ValueError(f"unsupported arg type {t}")
    return "0x" + data

def dec_uint(hexdata):
    if not hexdata or hexdata == "0x":
        return None
    try:
        return int(hexdata[2:66], 16)
    except Exception:
        return None

def dec_address(hexdata):
    if not hexdata or len(hexdata) < 66:
        return None
    return "0x" + hexdata[26:66]

def dec_string(hexdata):
    if not hexdata or hexdata == "0x":
        return None
    try:
        raw = bytes.fromhex(hexdata[2:])
        if len(raw) >= 64:
            length = int.from_bytes(raw[32:64], "big")
            if 0 <= length <= 10000 and len(raw) >= 64 + length:
                return raw[64:64+length].decode("utf-8", "replace")
        return raw.rstrip(b"\x00").decode("utf-8", "replace")
    except Exception:
        return None
