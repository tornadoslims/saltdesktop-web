# runtime/cryptodash_fetcher.py
#
# Price Fetcher for CryptoDash.
# Fetches current prices and market data from the CoinGecko public API.

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

DashConfig = dict[str, Any]
PriceSnapshot = dict[str, Any]

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def fetch_prices(config: DashConfig) -> list[PriceSnapshot]:
    """Fetch current price snapshots for configured coins from CoinGecko.

    Calls /simple/price with market data fields (24h change, market cap,
    volume). Returns a list of PriceSnapshot dicts.

    Args:
        config: DashConfig with coins (list of CoinGecko IDs) and currency

    Returns:
        List of PriceSnapshot dicts with keys:
          coin_id, symbol, name, price, change_24h_pct,
          market_cap, volume_24h, fetched_at
    """
    coins: list[str] = config.get("coins", [])
    currency: str = config.get("currency", "usd").lower()
    timeout: int = int(config.get("timeout_seconds", 10))
    base_url: str = config.get("api_base_url", COINGECKO_BASE).rstrip("/")

    if not coins:
        return []

    ids_param = "%2C".join(coins)  # URL-encoded comma
    url = (
        f"{base_url}/simple/price"
        f"?ids={ids_param}"
        f"&vs_currencies={currency}"
        f"&include_market_cap=true"
        f"&include_24hr_vol=true"
        f"&include_24hr_change=true"
        f"&include_last_updated_at=true"
    )

    raw = _fetch(url, timeout)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse CoinGecko response: {e}\nBody: {raw[:500]}")

    fetched_at = datetime.now(timezone.utc).isoformat()
    snapshots: list[PriceSnapshot] = []

    for coin_id in coins:
        coin_data = data.get(coin_id)
        if not coin_data:
            continue  # coin not found in response, skip

        snapshot: PriceSnapshot = {
            "coin_id": coin_id,
            "symbol": coin_id,   # CoinGecko /simple/price doesn't return symbol; use id as fallback
            "name": coin_id.capitalize(),
            "price": float(coin_data.get(currency, 0)),
            "change_24h_pct": float(coin_data.get(f"{currency}_24h_change", 0)),
            "market_cap": float(coin_data.get(f"{currency}_market_cap", 0)),
            "volume_24h": float(coin_data.get(f"{currency}_24h_vol", 0)),
            "fetched_at": fetched_at,
        }
        snapshots.append(snapshot)

    return snapshots


def _fetch(url: str, timeout: int) -> str:
    """Fetch URL content via httpx (preferred) or curl fallback."""
    try:
        import httpx  # type: ignore
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except ImportError:
        pass
    except Exception as e:
        raise RuntimeError(f"httpx request failed: {e}")

    # curl fallback
    cmd = [
        "curl", "-s", "-f",
        "--max-time", str(timeout),
        "-H", "Accept: application/json",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"curl request timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("Neither httpx nor curl is available. Install httpx: pip install httpx")

    if result.returncode != 0:
        raise RuntimeError(
            f"curl failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    return result.stdout
