"""Robinhood Chain Safety Scanner."""
__version__ = "0.1.0"
from .core import CHAINS, is_valid_address, scan_address, evaluate_verdict
__all__ = ["CHAINS", "is_valid_address", "scan_address", "evaluate_verdict", "__version__"]
