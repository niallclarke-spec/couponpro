"""
Gold Morning Briefing Generator

Generates professional XAU/USD morning briefings for Telegram channels using:
- Twelve Data API for 15-min OHLC candles
- Computed Asian session metrics and pivot levels
- OpenAI for natural language generation
"""

import os
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY')
ASIAN_SESSION_START_HOUR = 0  # 00:00 UTC
ASIAN_SESSION_END_HOUR = 7    # 07:00 UTC
MIN_CANDLES_FOR_SESSION = 20  # Expect ~28 candles for 7 hours at 15-min interval
HISTORICAL_DAYS_FOR_AVERAGE = 10


@dataclass
class OHLC:
    """Open-High-Low-Close data"""
    open: float
    high: float
    low: float
    close: float
    
    @property
    def range(self) -> float:
        return self.high - self.low
    
    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2


@dataclass
class PivotLevels:
    """Classic pivot point levels"""
    pivot: float
    r1: float
    r2: float
    s1: float
    s2: float
    
    @classmethod
    def from_ohlc(cls, ohlc: OHLC) -> 'PivotLevels':
        pivot = (ohlc.high + ohlc.low + ohlc.close) / 3
        r1 = 2 * pivot - ohlc.low
        s1 = 2 * pivot - ohlc.high
        r2 = pivot + (ohlc.high - ohlc.low)
        s2 = pivot - (ohlc.high - ohlc.low)
        return cls(
            pivot=round(pivot, 2),
            r1=round(r1, 2),
            r2=round(r2, 2),
            s1=round(s1, 2),
            s2=round(s2, 2)
        )


@dataclass
class BriefingData:
    """All computed data for the morning briefing"""
    current_price: float
    asian_ohlc: OHLC
    yesterday_ohlc: OHLC
    pivots: PivotLevels
    range_classification: str  # tight, normal, expanded
    price_position: str  # near_high, near_low, mid_range
    avg_asian_range: float
    is_market_open: bool = True


def fetch_candles(symbol: str = "XAU/USD", interval: str = "15min", 
                  outputsize: int = 100) -> List[Dict]:
    """
    Fetch OHLC candles from Twelve Data API.
    Returns list of candles sorted oldest to newest.
    """
    if not TWELVE_DATA_API_KEY:
        logger.error("TWELVE_DATA_API_KEY not set")
        return []
    
    try:
        url = f"https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if data.get('status') == 'error':
            logger.error(f"Twelve Data API error: {data.get('message')}")
            return []
        
        values = data.get('values', [])
        if not values:
            logger.warning("No candles returned from Twelve Data")
            return []
        
        # Reverse to get oldest first
        return list(reversed(values))
        
    except requests.exceptions.Timeout:
        logger.warning("Twelve Data API request timed out")
        return []
    except Exception as e:
        logger.exception(f"Error fetching candles: {e}")
        return []


def parse_candle_datetime(datetime_str: str) -> datetime:
    """Parse Twelve Data datetime string to UTC datetime."""
    # Format: "2026-01-31 07:30:00"
    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def filter_asian_session_candles(candles: List[Dict], target_date: datetime) -> List[Dict]:
    """
    Filter candles to only those in the Asian session (00:00-07:00 UTC) 
    for the target date.
    """
    session_candles = []
    
    for candle in candles:
        try:
            dt = parse_candle_datetime(candle['datetime'])
            
            # Check if this candle is on the target date and within Asian session hours
            if (dt.date() == target_date.date() and 
                ASIAN_SESSION_START_HOUR <= dt.hour < ASIAN_SESSION_END_HOUR):
                session_candles.append(candle)
        except (KeyError, ValueError) as e:
            logger.warning(f"Error parsing candle: {e}")
            continue
    
    return session_candles


def aggregate_to_ohlc(candles: List[Dict]) -> Optional[OHLC]:
    """Aggregate multiple candles into a single OHLC."""
    if not candles:
        return None
    
    try:
        opens = [float(c['open']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        return OHLC(
            open=opens[0],  # First candle's open
            high=max(highs),
            low=min(lows),
            close=closes[-1]  # Last candle's close
        )
    except (KeyError, ValueError, IndexError) as e:
        logger.error(f"Error aggregating candles: {e}")
        return None


def get_yesterday_ohlc(candles: List[Dict]) -> Optional[OHLC]:
    """
    Get the most recent trading day's OHLC from candles.
    Scans back up to 7 days to handle weekends and holidays (e.g., Monday needs Friday's data).
    """
    now_utc = datetime.now(timezone.utc)
    
    # Try each day going back, looking for one with trading data
    for day_offset in range(1, 8):  # Check up to 7 days back
        target_date = now_utc - timedelta(days=day_offset)
        
        day_candles = []
        for candle in candles:
            try:
                dt = parse_candle_datetime(candle['datetime'])
                if dt.date() == target_date.date():
                    day_candles.append(candle)
            except (KeyError, ValueError):
                continue
        
        # If we found candles for this day, use them
        if day_candles:
            logger.debug(f"Using OHLC from {target_date.date()} ({len(day_candles)} candles)")
            return aggregate_to_ohlc(day_candles)
    
    logger.warning("Could not find any trading day data in the past 7 days")
    return None


def compute_historical_avg_range(days: int = HISTORICAL_DAYS_FOR_AVERAGE) -> float:
    """
    Compute average Asian session range over the past N trading days.
    Returns 0 if unable to compute.
    """
    # Fetch more candles to cover historical period
    candles = fetch_candles(outputsize=days * 100)
    if not candles:
        return 0.0
    
    daily_ranges = []
    now_utc = datetime.now(timezone.utc)
    
    for day_offset in range(1, days + 3):  # Extra days to account for weekends
        target_date = now_utc - timedelta(days=day_offset)
        
        # Skip weekends
        if target_date.weekday() >= 5:
            continue
        
        session_candles = filter_asian_session_candles(candles, target_date)
        if len(session_candles) >= MIN_CANDLES_FOR_SESSION // 2:
            ohlc = aggregate_to_ohlc(session_candles)
            if ohlc and ohlc.range > 0:
                daily_ranges.append(ohlc.range)
        
        if len(daily_ranges) >= days:
            break
    
    if not daily_ranges:
        return 0.0
    
    return sum(daily_ranges) / len(daily_ranges)


def classify_range(current_range: float, avg_range: float) -> str:
    """
    Classify the current range as tight, normal, or expanded
    relative to the historical average.
    """
    if avg_range <= 0:
        return "normal"
    
    ratio = current_range / avg_range
    
    if ratio < 0.7:
        return "tight"
    elif ratio > 1.3:
        return "expanded"
    else:
        return "normal"


def determine_price_position(current_price: float, ohlc: OHLC) -> str:
    """
    Determine if price is near the session high, low, or mid-range.
    Within 20% of the range from high/low = near that level.
    """
    if ohlc.range <= 0:
        return "mid_range"
    
    threshold = ohlc.range * 0.2
    
    if current_price >= ohlc.high - threshold:
        return "near_high"
    elif current_price <= ohlc.low + threshold:
        return "near_low"
    else:
        return "mid_range"


def compute_briefing_data() -> Optional[BriefingData]:
    """
    Compute all data needed for the morning briefing.
    Returns None if essential data is unavailable.
    """
    logger.info("Computing morning briefing data from Twelve Data...")
    
    # Fetch recent candles (enough for today + yesterday)
    candles = fetch_candles(outputsize=200)
    if not candles:
        logger.warning("No candles available for briefing")
        return None
    
    now_utc = datetime.now(timezone.utc)
    
    # Get Asian session OHLC for today
    asian_candles = filter_asian_session_candles(candles, now_utc)
    
    # Check if market is likely closed (weekend or no recent candles)
    is_market_open = len(asian_candles) >= MIN_CANDLES_FOR_SESSION // 2
    
    if not is_market_open:
        logger.info("Market appears closed or limited data - using fallback")
        # Try to use yesterday's data for display
        asian_candles = []
        for day_offset in range(1, 4):
            target = now_utc - timedelta(days=day_offset)
            if target.weekday() < 5:  # Weekday
                asian_candles = filter_asian_session_candles(candles, target)
                if asian_candles:
                    break
    
    asian_ohlc = aggregate_to_ohlc(asian_candles)
    if not asian_ohlc:
        logger.warning("Could not compute Asian session OHLC")
        return None
    
    # Get yesterday's OHLC for pivot calculations
    yesterday_ohlc = get_yesterday_ohlc(candles)
    if not yesterday_ohlc:
        logger.warning("Could not compute yesterday's OHLC")
        return None
    
    # Current price is the latest candle's close
    try:
        current_price = float(candles[-1]['close'])
    except (KeyError, ValueError, IndexError):
        current_price = asian_ohlc.close
    
    # Compute pivot levels
    pivots = PivotLevels.from_ohlc(yesterday_ohlc)
    
    # Compute historical average range
    avg_range = compute_historical_avg_range()
    
    # Classify today's range
    range_class = classify_range(asian_ohlc.range, avg_range)
    
    # Determine price position
    price_pos = determine_price_position(current_price, asian_ohlc)
    
    logger.info(f"Briefing data computed: price=${current_price:.2f}, "
                f"range={range_class}, position={price_pos}")
    
    return BriefingData(
        current_price=round(current_price, 2),
        asian_ohlc=asian_ohlc,
        yesterday_ohlc=yesterday_ohlc,
        pivots=pivots,
        range_classification=range_class,
        price_position=price_pos,
        avg_asian_range=avg_range,
        is_market_open=is_market_open
    )


def generate_ai_briefing(data: BriefingData) -> Optional[str]:
    """
    Use OpenAI to generate a natural-sounding briefing from computed data.
    """
    from openai import OpenAI
    
    try:
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        
        if not api_key:
            logger.warning("OpenAI credentials not available")
            return None
        
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        
        # Build context for the AI
        range_desc = {
            "tight": "a tight, consolidating",
            "normal": "a normal",
            "expanded": "an expanded, volatile"
        }.get(data.range_classification, "a normal")
        
        position_desc = {
            "near_high": "pressing the Asian highs",
            "near_low": "holding near the Asian lows", 
            "mid_range": "trading mid-range"
        }.get(data.price_position, "trading mid-range")
        
        market_status = "" if data.is_market_open else " (Note: using last available session data as markets may be closed)"
        
        prompt = f"""Write a professional morning briefing for gold traders on Telegram.

MARKET DATA:
- Current XAU/USD price: ${data.current_price:.2f}
- Asian session: {range_desc} range of ${data.asian_ohlc.range:.2f}
- Asian High: ${data.asian_ohlc.high:.2f}, Asian Low: ${data.asian_ohlc.low:.2f}
- Price is currently {position_desc}
- Yesterday's close: ${data.yesterday_ohlc.close:.2f}
- Yesterday's range: ${data.yesterday_ohlc.range:.2f}{market_status}

KEY LEVELS (Classic Pivots):
- Resistance: R1 = ${data.pivots.r1:.2f}, R2 = ${data.pivots.r2:.2f}
- Support: S1 = ${data.pivots.s1:.2f}, S2 = ${data.pivots.s2:.2f}
- Pivot: ${data.pivots.pivot:.2f}

REQUIREMENTS:
1. Start with: 🌅 <b>GOLD MORNING OUTLOOK</b> (HTML bold, on its own line)
2. Add "XAU/USD" on the next line
3. Write a "Market:" line (1-2 sentences about overnight session + current structure)
4. List "Key Levels:" with Support and Resistance on separate lines
5. Write a confident "Outlook:" line - sound assured that clear setups will emerge at these levels, without predicting direction
6. End with "Stay tuned for signals" or similar CTA
7. Use HTML formatting (<b> for bold) - NO markdown
8. Keep total message under 700 characters
9. Sound like a confident professional trader writing to their community
10. Reference the actual numbers provided

EXAMPLE FORMAT:
🌅 <b>GOLD MORNING OUTLOOK</b>
XAU/USD

<b>Market:</b> Gold traded in a tight range overnight, consolidating around $2785. Price pressing Asian highs with momentum building.

<b>Key Levels:</b>
• Support: $2778 / $2765
• Resistance: $2792 / $2805

<b>Outlook:</b> Clean setups expected as price approaches key levels. The structure is clear — opportunities will present themselves.

Stay tuned for signals. 📊

Write ONLY the briefing message:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        
        message = response.choices[0].message.content.strip()
        
        # Validate response
        if len(message) < 100 or len(message) > 1000:
            logger.warning(f"AI response invalid length: {len(message)}")
            return None
        
        if "GOLD" not in message.upper() or "Key Levels" not in message:
            logger.warning("AI response missing required elements")
            return None
        
        return message
        
    except Exception as e:
        logger.warning(f"AI briefing generation failed: {e}")
        return None


def build_template_briefing(data: BriefingData) -> str:
    """
    Build a deterministic template briefing when AI is unavailable.
    """
    range_desc = {
        "tight": "in a tight range",
        "normal": "within a normal range",
        "expanded": "with expanded volatility"
    }.get(data.range_classification, "within a normal range")
    
    position_desc = {
        "near_high": "pressing the session highs",
        "near_low": "holding near session lows",
        "mid_range": "trading mid-range"
    }.get(data.price_position, "trading mid-range")
    
    return f"""🌅 <b>GOLD MORNING OUTLOOK</b>
XAU/USD

<b>Market:</b> Gold traded {range_desc} overnight at ${data.current_price:.0f}, {position_desc}.

<b>Key Levels:</b>
• Support: ${data.pivots.s1:.0f} / ${data.pivots.s2:.0f}
• Resistance: ${data.pivots.r1:.0f} / ${data.pivots.r2:.0f}

<b>Outlook:</b> Clean setups expected as price approaches key levels. The structure is clear.

Stay tuned for signals. 📊"""


def build_fallback_briefing() -> str:
    """
    Static fallback when no data is available.
    """
    return """🌅 <b>GOLD MORNING OUTLOOK</b>
XAU/USD

Markets are warming up for the session ahead. Key levels are in play and setups will emerge.

Stay tuned for signals. 📊"""


def generate_morning_briefing(tenant_id: str = "default") -> str:
    """
    Main entry point: Generate the complete morning briefing.
    Tries AI first, falls back to template, then to static message.
    """
    logger.info(f"Generating morning briefing for tenant: {tenant_id}")
    
    # Step 1: Compute market data
    data = compute_briefing_data()
    
    if not data:
        logger.warning(f"Could not compute briefing data for {tenant_id}, using fallback")
        return build_fallback_briefing()
    
    # Step 2: Try AI generation
    ai_message = generate_ai_briefing(data)
    
    if ai_message:
        logger.info(f"Generated AI briefing for {tenant_id}")
        return ai_message
    
    # Step 3: Fall back to template with computed data
    logger.info(f"Using template briefing for {tenant_id}")
    return build_template_briefing(data)


if __name__ == "__main__":
    # Test the briefing generator
    logging.basicConfig(level=logging.INFO)
    print(generate_morning_briefing("test"))
