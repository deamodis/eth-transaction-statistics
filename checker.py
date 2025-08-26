#!/usr/bin/env python3
"""
Ethereum transaction stats with fixed EUR pricing (no external price APIs).

- ETH (normal + optional internal) → valued at FIXED_ETH_EUR_RATE.
- ERC-20 stablecoins (USDC/USDT) → valued at FIXED_USD_EUR_RATE.
- Prints Min / Median / Max with their tx hashes.
- Optional unified EUR view (ETH + stablecoins).
- No CoinGecko calls → no 429 errors.

Usage examples:
  python checker.py 0xADDRESS --exclude-zero
  python checker.py 0xADDRESS --exclude-zero --include-internal
  python checker.py 0xADDRESS --include-tokens --unified

Env:
  ETHERSCAN_API_KEY must be set (or present in .env).
"""

import os
import sys
import time
import argparse
import statistics
from typing import List, Dict, Sequence, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL")
PAGE_SIZE = int(os.getenv("PAGE_SIZE"))

# ===== Fixed snapshot rates (adjust as you like) =====
FIXED_ETH_EUR_RATE = 3659.00   # 1 ETH = 3659 EUR
FIXED_USD_EUR_RATE = 0.85      # 1 USD = 0.85 EUR

# Stablecoin contracts (Ethereum mainnet, lowercased) → decimals
STABLE_TOKENS: Dict[str, int] = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": 6,  # USDT
}

# ===== Fixed-rate converters (ignore timestamp/mode) =====
def eth_to_eur(value_eth: float, *_ignored) -> float:
    return value_eth * FIXED_ETH_EUR_RATE

def usd_to_eur(amount_usd: float, *_ignored) -> float:
    return amount_usd * FIXED_USD_EUR_RATE

# ===== Etherscan fetchers =====
def _paged_get(params_base: dict) -> List[dict]:
    page = 1
    items: List[dict] = []
    while True:
        params = dict(params_base)
        params.update({"page": page, "offset": PAGE_SIZE})
        r = requests.get(API_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        message = data.get("message")
        if status == "0" and message != "No transactions found":
            raise RuntimeError(f"Etherscan error: {message} | result={data.get('result')}")
        chunk = data.get("result", [])
        if not chunk:
            break
        items.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.21)  # be gentle with rate limits
    return items

def fetch_normal_txs(address: str, api_key: str, startblock=0, endblock=99999999, sort="asc") -> List[dict]:
    return _paged_get({
        "module": "account", "action": "txlist",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    })

def fetch_internal_txs(address: str, api_key: str, startblock=0, endblock=99999999, sort="asc") -> List[dict]:
    return _paged_get({
        "module": "account", "action": "txlistinternal",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    })

def fetch_token_txs(address: str, api_key: str, startblock=0, endblock=99999999, sort="asc") -> List[dict]:
    return _paged_get({
        "module": "account", "action": "tokentx",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    })

# ===== Utilities =====
def wei_to_eth(wei_str: str) -> float:
    return int(wei_str) / 10**18

def to_float_amount(raw: str, decimals: int) -> float:
    return int(raw) / (10 ** decimals)

def _median_with_indices(values: Sequence[float]) -> Tuple[float, List[int]]:
    """Return (median_value, indices_used). Even count -> two indices."""
    n = len(values)
    ord_idx = sorted(range(n), key=lambda i: values[i])
    if n % 2 == 1:
        mid = ord_idx[n // 2]
        return values[mid], [mid]
    else:
        lo = ord_idx[n // 2 - 1]
        hi = ord_idx[n // 2]
        return (values[lo] + values[hi]) / 2.0, [lo, hi]

def stats_with_hash(values: Sequence[float], hashes: Sequence[str]):
    """Compute Min/Median/Max and return values with hashes."""
    if not values:
        return None
    n = len(values)
    min_idx = min(range(n), key=lambda i: values[i])
    max_idx = max(range(n), key=lambda i: values[i])
    med_val, med_indices = _median_with_indices(values)
    return {
        "count": n,
        "min": (values[min_idx], hashes[min_idx]),
        "median": (med_val, [hashes[i] for i in med_indices]),
        "max": (values[max_idx], hashes[max_idx]),
    }

def print_transactions_higher_than(txs: Sequence[float], amount: float, hashes: Sequence[str]):
    a = 0

    if len(txs) != len(hashes):
        raise ValueError("txs and hashes must have the same length")
    for value, h in zip(txs, hashes):
        if value > amount:
            a = a + 1

            print(f"{value} -> {h}")

    print(f"Total: {a} of { len(txs) }")

def print_stats_with_hash(title: str, values: Sequence[float], hashes: Sequence[str], unit: str = "€", decimals: int = 2):
    if not values:
        print(f"\n=== {title} ===\nNo values.")
        return
    st = stats_with_hash(values, hashes)
    print(f"\n=== {title} ===")
    print(f"Count: {st['count']}")
    fmt = (lambda v: f"{unit}{v:.{decimals}f}") if unit else (lambda v: f"{v:.6f}")
    v_min, h_min = st["min"]
    v_med, h_meds = st["median"]
    v_max, h_max = st["max"]
    print(f"Min: {fmt(v_min)} | hash: {h_min}")
    if len(h_meds) == 1:
        print(f"Median: {fmt(v_med)} | hash: {h_meds[0]}")
    else:
        # even sample → median is average of two middle txs
        print(f"Median: {fmt(v_med)} | hashes: {h_meds[0]} & {h_meds[1]}")
    print(f"Max: {fmt(v_max)} | hash: {h_max}")

def print_stats_simple(title: str, values: List[float], unit: str = "", decimals: int = 6):
    """Stats without hashes (for ETH-in-ETH if you want both)."""
    if not values:
        print(f"\n=== {title} ===\nNo values.")
        return
    _min = min(values)
    _max = max(values)
    med = statistics.median(values)
    print(f"\n=== {title} ===")
    print(f"Count: {len(values)}")
    if unit:
        print(f"Min: {unit}{_min:.2f}")
        print(f"Median: {unit}{med:.2f}")
        print(f"Max: {unit}{_max:.2f}")
    else:
        print(f"Min: { _min:.{decimals}f}")
        print(f"Median: { med:.{decimals}f}")
        print(f"Max: { _max:.{decimals}f}")

# ===== Main =====
def main():
    parser = argparse.ArgumentParser(description="Compute ETH & stablecoin transfer stats (EUR, fixed rates)")
    parser.add_argument("address", help="Ethereum address (0x...)")
    parser.add_argument("--exclude-zero", action="store_true", help="Exclude zero-value ETH txs")
    parser.add_argument("--include-internal", action="store_true", help="Include internal ETH txs")
    parser.add_argument("--include-tokens", action="store_true", help="Include ERC-20 stablecoin transfers (USDC/USDT)")
    parser.add_argument("--unified", action="store_true", help="Also print a unified EUR view (ETH+stablecoins)")
    parser.add_argument("--startblock", type=int, default=0)
    parser.add_argument("--endblock", type=int, default=99999999)
    parser.add_argument("--descending", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        print("ERROR: Please set ETHERSCAN_API_KEY.", file=sys.stderr)
        sys.exit(1)

    sort = "desc" if args.descending else "asc"
    addr = args.address

    print(f"Fetching for {addr} (blocks {args.startblock}-{args.endblock}, sort {sort}) ...")

    # ---- ETH (normal + optional internal) ----
    normal = fetch_normal_txs(addr, api_key, args.startblock, args.endblock, sort)
    internal = fetch_internal_txs(addr, api_key, args.startblock, args.endblock, sort) if args.include_internal else []

    eth_vals_eth: List[float] = []
    eth_vals_eur: List[float] = []
    eth_hashes: List[str] = []

    # Normal ETH txs
    for tx in normal:
        v_eth = wei_to_eth(tx["value"])
        if args.exclude_zero and v_eth == 0:
            continue
        eth_vals_eth.append(v_eth)
        eth_vals_eur.append(eth_to_eur(v_eth))
        eth_hashes.append(tx["hash"])

    # Internal ETH txs (optional)
    if args.include_internal:
        for tx in internal:
            v_eth = wei_to_eth(tx["value"])
            if args.exclude_zero and v_eth == 0:
                continue
            eth_vals_eth.append(v_eth)
            eth_vals_eur.append(eth_to_eur(v_eth))
            eth_hashes.append(tx["hash"])

    # Print ETH stats (ETH & EUR) + hashes for EUR
    if eth_vals_eth:
        print_stats_simple("ETH Transaction Amounts (ETH)", eth_vals_eth, unit="", decimals=6)
        print_stats_with_hash("ETH Transaction Amounts (EUR) + hashes", eth_vals_eur, eth_hashes, unit="€", decimals=2)
    else:
        print("\n=== ETH Transaction Amounts (ETH) ===\nNo values.")
        print("\n=== ETH Transaction Amounts (EUR) + hashes ===\nNo values.")

    # ---- Stablecoins (USDC/USDT only) ----
    token_eur_vals: List[float] = []
    token_hashes: List[str] = []
    if args.include_tokens:
        tokens = fetch_token_txs(addr, api_key, args.startblock, args.endblock, sort)
        for t in tokens:
            raw = int(t["value"])
            if raw == 0:
                continue
            contract = t["contractAddress"].lower()
            if contract not in STABLE_TOKENS:
                # Skip non-stable tokens to avoid price lookups
                continue
            decimals = STABLE_TOKENS[contract]
            amount_usd = to_float_amount(t["value"], decimals)   # ~ USD amount
            eur_val = usd_to_eur(amount_usd)
            token_eur_vals.append(eur_val)
            token_hashes.append(t["hash"])

        print_stats_with_hash("Stablecoin Transfers (EUR, USDC/USDT) + hashes",
                              token_eur_vals, token_hashes, unit="€", decimals=2)

        print(len(token_eur_vals))
        print_transactions_higher_than(amount = 6000, txs = token_eur_vals, hashes = token_hashes)

    # ---- Unified EUR view ----
    if args.unified:
        unified_vals = []
        unified_hashes = []
        if eth_vals_eur:
            unified_vals += eth_vals_eur
            unified_hashes += eth_hashes
        if token_eur_vals:
            unified_vals += token_eur_vals
            unified_hashes += token_hashes
        print_stats_with_hash("Unified Value Moved (EUR) — ETH + Stablecoins + hashes",
                              unified_vals, unified_hashes, unit="€", decimals=2)

if __name__ == "__main__":
    main()
