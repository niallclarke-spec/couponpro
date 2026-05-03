"""
Live macro data fetcher for Markus voice morning/EoD posts.

Pulls XAU/USD spot price from metals-api.com so the AI has real ground truth
to anchor its narrative around (prevents hallucinated prices).
"""
import os
from typing import Optional
from datetime import datetime, timedelta

import urllib.request
import urllib.parse
import json

from core.logging import get_logger

logger = get_logger(__name__)

METALS_API_BASE = "https://metals-api.com/api"


def _fetch_json(url: str, timeout: float = 6.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"metals-api fetch failed for {url.split('?')[0]}: {e}")
        return None


XAU_PRICE_MIN = 500.0
XAU_PRICE_MAX = 20000.0


def _xau_usd_from_response(data: dict) -> Optional[float]:
    """metals-api returns rates as USD-per-base; if base=USD, XAU rate = XAU/USD ratio.

    Convention: rate is "1 USD = N XAU", so price-per-ounce in USD = 1 / rate.
    Returns None if the inverted price is outside a sane band — guards against
    provider convention changes that would produce absurd posts.
    """
    if not data or not data.get("success", True):
        return None
    rates = data.get("rates") or {}
    xau = rates.get("XAU")
    if not xau or xau <= 0:
        return None
    spot = round(1.0 / float(xau), 2)
    if spot < XAU_PRICE_MIN or spot > XAU_PRICE_MAX:
        logger.warning(f"XAU/USD spot {spot} out of sane band [{XAU_PRICE_MIN}, {XAU_PRICE_MAX}], rejecting")
        return None
    return spot


def fetch_xau_context() -> Optional[str]:
    """Build a 'LIVE CONTEXT' string for Markus morning macro prompts.

    Returns formatted string with current XAU/USD spot and 24h change %, or
    None if the API is unavailable. Caller must handle None gracefully.
    """
    api_key = os.environ.get("METALS_API_KEY")
    if not api_key:
        logger.warning("METALS_API_KEY not set, skipping XAU context fetch")
        return None

    latest_url = f"{METALS_API_BASE}/latest?access_key={api_key}&base=USD&symbols=XAU"
    latest = _fetch_json(latest_url)
    spot = _xau_usd_from_response(latest)
    if spot is None:
        logger.warning("Could not extract XAU/USD spot from metals-api response")
        return None

    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    hist_url = f"{METALS_API_BASE}/{yesterday}?access_key={api_key}&base=USD&symbols=XAU"
    hist = _fetch_json(hist_url)
    prev = _xau_usd_from_response(hist)

    lines = [f"LIVE MARKET DATA (real, fetched just now):",
             f"- XAU/USD spot: {spot:.2f}"]
    if prev and abs(spot - prev) > 0.01:
        change_pct = ((spot - prev) / prev) * 100.0
        direction = "up" if change_pct >= 0 else "down"
        lines.append(f"- 24h change: {direction} {abs(change_pct):.2f}% (from {prev:.2f})")

    logger.info(f"Fetched XAU/USD context: spot={spot}, prev={prev}")
    return "\n".join(lines)
