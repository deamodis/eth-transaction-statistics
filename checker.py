# eth_stats.py
import os
import time
from typing import List, Dict, Sequence, Tuple, Optional, Literal

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "https://api.etherscan.io/api")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "10000"))

# ===== Fixed snapshot rates (adjust as you like) =====
FIXED_ETH_EUR_RATE = float(os.getenv("FIXED_ETH_EUR_RATE", "3659.00"))  # 1 ETH = 3659 EUR
FIXED_USD_EUR_RATE = float(os.getenv("FIXED_USD_EUR_RATE", "0.85"))     # 1 USD = 0.85 EUR

# Stablecoin contracts (Ethereum mainnet, lowercased) → decimals
STABLE_TOKENS: Dict[str, int] = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": 6,  # USDT
}

# ===== Fixed-rate converters =====
def eth_to_eur(value_eth: float) -> float:
    return value_eth * FIXED_ETH_EUR_RATE

def usd_to_eur(amount_usd: float) -> float:
    return amount_usd * FIXED_USD_EUR_RATE

# ===== Utilities =====
def wei_to_eth(wei_str: str) -> float:
    return int(wei_str) / 10**18

def to_float_amount(raw: str, decimals: int) -> float:
    return int(raw) / (10 ** decimals)

def _median_with_indices(values: Sequence[float]) -> Tuple[float, List[int]]:
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
    if not values:
        return None
    n = len(values)
    min_idx = min(range(n), key=lambda i: values[i])
    max_idx = max(range(n), key=lambda i: values[i])
    med_val, med_indices = _median_with_indices(values)
    return {
        "count": n,
        "min": {"value": values[min_idx], "hash": hashes[min_idx]},
        "median": {"value": med_val, "hashes": [hashes[i] for i in med_indices]},
        "max": {"value": values[max_idx], "hash": hashes[max_idx]},
    }

# ===== Etherscan fetchers =====
def _paged_get(params_base: dict, api_url: str, page_size: int, pause_s: float) -> List[dict]:
    page = 1
    items: List[dict] = []
    while True:
        params = dict(params_base)
        params.update({"page": page, "offset": page_size})
        r = requests.get(api_url, params=params, timeout=30)
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
        if len(chunk) < page_size:
            break
        page += 1
        if pause_s:
            time.sleep(pause_s)  # be gentle with rate limits
    return items

def fetch_normal_txs(address: str, api_key: str, api_url: str, startblock=0, endblock=99999999, sort="asc",
                     page_size: int = PAGE_SIZE, pause_s: float = 0.21) -> List[dict]:
    return _paged_get({
        "module": "account", "action": "txlist",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    }, api_url, page_size, pause_s)

def fetch_internal_txs(address: str, api_key: str, api_url: str, startblock=0, endblock=99999999, sort="asc",
                       page_size: int = PAGE_SIZE, pause_s: float = 0.21) -> List[dict]:
    return _paged_get({
        "module": "account", "action": "txlistinternal",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    }, api_url, page_size, pause_s)

def fetch_token_txs(address: str, api_key: str, api_url: str, startblock=0, endblock=99999999, sort="asc",
                    page_size: int = PAGE_SIZE, pause_s: float = 0.21) -> List[dict]:
    return _paged_get({
        "module": "account", "action": "tokentx",
        "address": address, "startblock": startblock, "endblock": endblock,
        "sort": sort, "apikey": api_key
    }, api_url, page_size, pause_s)

# ===== Public API for your web app =====
class ComputeOptions(Tuple):
    """Use a simple dict-like options object instead if you prefer Pydantic in FastAPI."""
    pass

def compute_address_stats(
    address: str,
    *,
    api_key: Optional[str] = None,
    include_internal: bool = False,
    include_tokens: bool = False,
    exclude_zero_eth: bool = False,
    unified: bool = False,
    startblock: int = 0,
    endblock: int = 9_9999_999,
    sort: Literal["asc", "desc"] = "asc",
    api_url: str = API_URL,
    page_size: int = PAGE_SIZE,
    pause_s: float = 0.21,
) -> Dict:
    """
    Returns a JSON-serializable dict with ETH / stablecoin / unified stats.
    Does not print or parse CLI args — safe to call from a web handler.
    """
    api_key = api_key or os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY missing")

    # ---- ETH (normal + optional internal) ----
    normal = fetch_normal_txs(address, api_key, api_url, startblock, endblock, sort, page_size, pause_s)
    internal = fetch_internal_txs(address, api_key, api_url, startblock, endblock, sort, page_size, pause_s) if include_internal else []

    eth_vals_eth: List[float] = []
    eth_vals_eur: List[float] = []
    eth_hashes: List[str] = []

    for tx in normal:
        v_eth = wei_to_eth(tx["value"])
        if exclude_zero_eth and v_eth == 0:
            continue
        eth_vals_eth.append(v_eth)
        eth_vals_eur.append(eth_to_eur(v_eth))
        eth_hashes.append(tx["hash"])

    if include_internal:
        for tx in internal:
            v_eth = wei_to_eth(tx["value"])
            if exclude_zero_eth and v_eth == 0:
                continue
            eth_vals_eth.append(v_eth)
            eth_vals_eur.append(eth_to_eur(v_eth))
            eth_hashes.append(tx["hash"])

    out: Dict[str, Dict] = {
        "params": {
            "address": address,
            "startblock": startblock,
            "endblock": endblock,
            "sort": sort,
            "include_internal": include_internal,
            "include_tokens": include_tokens,
            "unified": unified,
            "exclude_zero_eth": exclude_zero_eth,
            "rates": {
                "ETH_EUR": FIXED_ETH_EUR_RATE,
                "USD_EUR": FIXED_USD_EUR_RATE,
            },
        },
        "eth": {
            "raw_eth_amounts": eth_vals_eth,   # keep if you want ETH-denominated stats on client
            "eur_stats": stats_with_hash(eth_vals_eur, eth_hashes),
        },
    }

    # ---- Stablecoins (USDC/USDT only) ----
    token_eur_vals: List[float] = []
    token_hashes: List[str] = []
    if include_tokens:
        tokens = fetch_token_txs(address, api_key, api_url, startblock, endblock, sort, page_size, pause_s)
        for t in tokens:
            raw = int(t["value"])
            if raw == 0:
                continue
            contract = t["contractAddress"].lower()
            if contract not in STABLE_TOKENS:
                continue
            decimals = STABLE_TOKENS[contract]
            amount_usd = to_float_amount(t["value"], decimals)
            eur_val = usd_to_eur(amount_usd)
            token_eur_vals.append(eur_val)
            token_hashes.append(t["hash"])

        out["stablecoins"] = {
            "eur_stats": stats_with_hash(token_eur_vals, token_hashes),
        }
    else:
        out["stablecoins"] = {"eur_stats": None}

    # ---- Unified EUR view ----
    if unified:
        unified_vals: List[float] = []
        unified_hashes: List[str] = []
        if eth_vals_eur:
            unified_vals += eth_vals_eur
            unified_hashes += eth_hashes
        if token_eur_vals:
            unified_vals += token_eur_vals
            unified_hashes += token_hashes
        out["unified"] = {"eur_stats": stats_with_hash(unified_vals, unified_hashes)}
    else:
        out["unified"] = {"eur_stats": None}

    return out
