# MT5 Screenshot Integration for TP Win Messages
### Complete Developer Reference — EntryLab Platform

---

## Table of Contents

1. [What We Are Building](#1-what-we-are-building)
2. [Current System Architecture](#2-current-system-architecture)
3. [Complete TP Win Pipeline — Step by Step](#3-complete-tp-win-pipeline--step-by-step)
4. [The Dollar Profit Calculation](#4-the-dollar-profit-calculation)
5. [Current Image Generation (Pillow Showcase Card)](#5-current-image-generation-pillow-showcase-card)
6. [How Images Are Attached to Telegram Messages](#6-how-images-are-attached-to-telegram-messages)
7. [Database Schema — Signal Row Fields](#7-database-schema--signal-row-fields)
8. [Two Implementation Options](#8-two-implementation-options)
9. [Option B — Server-Side MT5 Replica (Recommended First)](#9-option-b--server-side-mt5-replica-recommended-first)
10. [Option A — Real MT5 Screenshot Push](#10-option-a--real-mt5-screenshot-push)
11. [Dollar Amount Overlay on Screenshots](#11-dollar-amount-overlay-on-screenshots)
12. [Complete File Change List](#12-complete-file-change-list)
13. [Testing Checklist](#13-testing-checklist)

---

## 1. What We Are Building

Every time a gold (XAU/USD) trade hits a Take Profit level (TP1, TP2, or TP3), the platform:

1. Detects the price hit
2. Sends a **celebration message** to the VIP Telegram channel
3. **Currently**: the message is accompanied by a programmatically-drawn "showcase card" (Pillow PNG)
4. **After this feature**: the showcase card is replaced (or supplemented) by an image that looks like a real MT5 terminal trade history screenshot, showing the actual trade details and profit

The message also gets forwarded to the **FREE channel** as part of the cross-promo system (see Section 3).

---

## 2. Current System Architecture

### Key Files and Their Roles

```
forex_signals.py                     ← Price monitoring + TP/SL hit detection
scheduler/monitor.py                 ← Processes hit events, triggers messages + cross-promo
scheduler/messenger.py               ← Generates text, calls image gen, sends to Telegram
showcase/trade_win_generator.py      ← Pillow image renderer (current showcase card)
showcase/profit_calculator.py        ← Pips and $ profit calculations for images
core/pip_calculator.py               ← Single source of truth for all pip math
core/telegram_sender.py              ← send_photo_to_channel() — actual Telegram send
domains/crosspromo/service.py        ← Forwards TP messages to FREE channel
domains/crosspromo/repo.py           ← Cross-promo job queue (PostgreSQL)
db.py                                ← All database queries (signals, TP message IDs)
bots/core/milestone_tracker.py       ← Generates TP celebration text messages
```

### Runtime Flow Diagram

```
┌─────────────────────┐     every 30s    ┌──────────────────────────┐
│   forex_signals.py  │ ──────────────── │  Fetch current XAU/USD   │
│  monitor_active_    │                  │  price (Twelve Data API) │
│  signals()          │                  └──────────────────────────┘
└──────────┬──────────┘
           │  TP1/TP2/TP3 price reached
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Atomic DB update:                                              │
│  • SET tp1_hit = TRUE  (or tp2_hit / tp3_hit)                   │
│  • SET tp1_hit_at = NOW()                                       │
│  • CLOSE signal if single-TP or final TP (status = 'won')       │
└──────────────────────────────────┬──────────────────────────────┘
                                   │  returns update event dict
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  scheduler/monitor.py → _process_signal_update(update)           │
│                                                                   │
│  if event == 'tp1_hit':  messenger.send_tp1_celebration(...)     │
│  if event == 'tp2_hit':  messenger.send_tp2_celebration(...)     │
│  if event == 'tp3_hit':  messenger.send_tp3_celebration(...)     │
└──────────────────────────────────┬───────────────────────────────┘
                                   │  calls messenger
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  scheduler/messenger.py → send_tpX_celebration()                 │
│                                                                   │
│  1. Generate text (milestone_tracker.generate_tpX_celebration()) │
│  2. Generate image (_generate_image_with_retry(signal_data, X))  │
│     └─ calls generate_trade_win_image(trades) → PNG bytes        │
│  3. Send: send_photo_to_channel(photo=bytes, caption=text)       │
│     └─ falls back to text-only if image fails after 3 retries    │
│  4. Returns: message_id (Telegram message ID)                    │
└──────────────────────────────────┬───────────────────────────────┘
                                   │  message_id stored in DB
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  db.update_tp_message_id(signal_id, tp_number, message_id)       │
│  → stores in forex_signals.tp1_message_id / tp2_message_id / tp3 │
└──────────────────────────────────┬───────────────────────────────┘
                                   │  cross-promo trigger
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  domains/crosspromo/service.py → trigger_tp_crosspromo()         │
│  → enqueues job to FORWARD the TP message to FREE channel        │
│  → job executor also calls forward_message() + promo text        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Complete TP Win Pipeline — Step by Step

### Step 1: Price Detection (`forex_signals.py`)

The file `forex_signals.py` contains `ForexSignalEngine.monitor_active_signals()`. It runs every 30 seconds, fetches the current XAU/USD price, and checks every open signal against its TP levels.

```python
# forex_signals.py — monitor_active_signals()

# For each open signal:
tp1 = float(signal['take_profit'])
tp2 = float(signal.get('take_profit_2') or 0)
tp3 = float(signal.get('take_profit_3') or 0)

tp1_hit = signal.get('tp1_hit', False)
tp2_hit = signal.get('tp2_hit', False)
tp3_hit = signal.get('tp3_hit', False)

tp1_pct = signal.get('tp1_percentage') or 50   # % of position closed at TP1
tp2_pct = signal.get('tp2_percentage') or 30
tp3_pct = signal.get('tp3_percentage') or 20

# BUY signal TP1 detection:
if not tp1_hit and current_price >= tp1:
    pips = round((tp1 - entry) * PIPS_MULTIPLIER, 1)
    remaining = (tp2_pct if has_tp2 else 0) + (tp3_pct if has_tp3 else 0)
    update_tp_hit(signal_id, 1, tenant_id=self.tenant_id)   # DB: tp1_hit=TRUE
    updates.append({
        'id': signal_id,
        'event': 'tp1_hit',
        'pips': pips,
        'percentage': tp1_pct,
        'remaining': remaining   # % of position still open toward TP2/TP3
    })

# TP2 detected only after TP1 is already marked hit:
if has_tp2 and tp1_hit and not tp2_hit and current_price >= tp2:
    pips = round((tp2 - entry) * PIPS_MULTIPLIER, 1)
    remaining = tp3_pct if has_tp3 else 0
    update_tp_hit(signal_id, 2, tenant_id=self.tenant_id)
    updates.append({'id': signal_id, 'event': 'tp2_hit', 'pips': pips, 'remaining': remaining})

# TP3 detected only after TP2 is already marked hit:
if has_tp3 and tp2_hit and not tp3_hit and current_price >= tp3:
    pips = round((tp3 - entry) * PIPS_MULTIPLIER, 1)
    update_tp_hit(signal_id, 3, tenant_id=self.tenant_id)
    update_forex_signal_status(signal_id, 'won', ...)   # Signal fully closed
    updates.append({'id': signal_id, 'event': 'tp3_hit', 'status': 'won', 'pips': pips})
```

The same logic exists for SELL signals with reversed comparisons (`current_price <= tp1`, etc.).

---

### Step 2: Event Processing (`scheduler/monitor.py`)

`SignalMonitor._process_signal_update(update)` handles each event:

```python
# scheduler/monitor.py — _process_signal_update()

elif event == 'tp1_hit':
    remaining = update.get('remaining', 0)
    posted_at = matching_signal.get('posted_at')

    # Send TP1 celebration message (with image)
    tp1_message_id = await self.messenger.send_tp1_celebration(
        signal_type, pips, remaining, posted_at, matching_signal
    )

    # If portion still riding to TP2: move stop loss to TP1 price
    if remaining > 0 and matching_signal:
        tp1_price = float(matching_signal.get('take_profit', 0))
        db.update_effective_sl(signal_id, tp1_price, tenant_id=self.tenant_id)

    # Store TP1 message ID in DB (needed for cross-promo forwarding)
    if tp1_message_id and matching_signal:
        db.update_tp_message_id(signal_id, 1, tp1_message_id, tenant_id=self.tenant_id)

        # Trigger cross-promo: forward signal + TP1 to FREE channel
        signal_message_id = matching_signal.get('telegram_message_id')
        trigger_tp_crosspromo(
            tenant_id=self.tenant_id,
            signal_id=signal_id,
            tp_number=1,
            signal_message_id=signal_message_id,  # original signal post
            tp_message_id=tp1_message_id,          # TP1 celebration message
            pips_secured=pips
        )

# TP2 and TP3 follow the exact same pattern
```

---

### Step 3: Message + Image Generation (`scheduler/messenger.py`)

```python
# scheduler/messenger.py — send_tp1_celebration()

async def send_tp1_celebration(
    self,
    signal_type: str,
    pips: float,
    remaining: float,
    posted_at: Optional[str] = None,
    signal_data: Optional[Dict[str, Any]] = None   # ← full signal row from DB
) -> Optional[int]:                                  # returns Telegram message_id
    
    # 1. Generate celebration text
    message = self.milestone_tracker.generate_tp1_celebration(
        signal_type, pips, remaining, posted_at
    )
    # Returns HTML like:
    # "🎉 <b>TP1 HIT!</b>\n\n+50.00 pips secured! 💰\n⏱️ Hit in 47 minutes\n\n..."

    # 2. Generate image + send (with text fallback)
    success, message_id = await self._send_tp_celebration_combined(
        message=message,
        signal_data=signal_data,
        tp_level=1
    )

    return message_id  # stored in DB as tp1_message_id
```

```python
# scheduler/messenger.py — _send_tp_celebration_combined()

async def _send_tp_celebration_combined(
    self, message: str, signal_data: Optional[Dict], tp_level: int,
    channel_type: str = 'vip'
) -> Tuple[bool, Optional[int]]:

    if signal_data:
        # Try to generate the showcase image (3 retries, 200ms between each)
        img_bytes = await self._generate_image_with_retry(signal_data, tp_level)

        if img_bytes:
            # Send photo with celebration text as caption
            result = await send_photo_to_channel(
                tenant_id=self.tenant_id,
                bot_role='signal_bot',
                photo=img_bytes,          # PNG bytes
                caption=message,          # HTML celebration text
                channel_type=channel_type # 'vip'
            )
            if result.success:
                return True, result.message_id

    # Fallback: text only
    result = await send_to_channel(self.tenant_id, 'signal_bot', message, channel_type=channel_type)
    return result.success, result.message_id if result.success else None
```

```python
# scheduler/messenger.py — _generate_image_with_retry()
# THIS IS THE FUNCTION TO CHANGE FOR MT5 SCREENSHOTS

async def _generate_image_with_retry(
    self, signal_data: Dict, tp_level: int,
    max_attempts: int = 3, delay_ms: int = 200
) -> Optional[bytes]:

    # Build list of TradeWinData objects (one per TP hit up to current level)
    trades = self._build_trades_for_showcase(signal_data, tp_level)
    if not trades:
        return None

    for attempt in range(1, max_attempts + 1):
        try:
            img_bytes = generate_trade_win_image(trades)  # ← Pillow render
            if img_bytes:
                return img_bytes
        except Exception as e:
            logger.warning(f"Image gen attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            await asyncio.sleep(delay_ms / 1000.0)

    return None  # all attempts failed → text-only fallback
```

```python
# scheduler/messenger.py — _build_trades_for_showcase()

def _build_trades_for_showcase(self, signal_data: Dict, tp_level: int) -> List[TradeWinData]:
    entry_price = float(signal_data.get('entry_price', 0))
    direction   = signal_data.get('signal_type', 'BUY')
    pair        = signal_data.get('pair', 'XAU/USD')

    tp_prices = [
        signal_data.get('take_profit'),      # TP1
        signal_data.get('take_profit_2'),    # TP2
        signal_data.get('take_profit_3')     # TP3
    ]

    trades = []
    for i in range(tp_level):          # tp_level=1 → [TP1], tp_level=2 → [TP1, TP2], etc.
        tp_price = tp_prices[i]
        if tp_price is None:
            continue
        tp_price = float(tp_price)

        profit_calc = calculate_trade_profit(
            entry_price=entry_price,
            exit_price=tp_price,
            direction=direction,
            lot_size=1.0,              # hardcoded — see Section 4
            include_commission=True
        )

        trade = TradeWinData(
            pair=pair,
            direction=direction,
            lot_size=1.0,
            entry_price=entry_price,
            exit_price=tp_price,
            profit=profit_calc.net_profit,   # e.g. 43.00
            timestamp=datetime.utcnow()
        )
        trades.append(trade)

    return trades
```

---

### Step 4: Final Telegram Delivery (`core/telegram_sender.py`)

```python
# core/telegram_sender.py — send_photo_to_channel()

async def send_photo_to_channel(
    tenant_id: str,
    bot_role: str,
    photo: Union[bytes, io.BytesIO, str],
    caption: Optional[str] = None,
    parse_mode: str = 'HTML',
    channel_type: str = 'default'   # 'vip' or 'free'
) -> SendResult:

    # 1. Resolve bot token from DB (60-second TTL cache)
    connection = _resolve_bot_connection(tenant_id, bot_role)

    # 2. Determine channel ID ('vip' or 'free')
    if channel_type == 'vip':
        chat_id = connection.vip_channel_id
    elif channel_type == 'free':
        chat_id = connection.free_channel_id

    # 3. Delegate to send_photo()
    return await send_photo(tenant_id, bot_role, chat_id, photo, caption, parse_mode)


async def send_photo(
    tenant_id, bot_role, chat_id, photo, caption=None, parse_mode='HTML', ...
) -> SendResult:

    bot = Bot(token=connection.token)  # short-lived instance per send

    # Wrap bytes in BytesIO with filename
    if isinstance(photo, bytes):
        photo_file = io.BytesIO(photo)
        photo_file.name = 'trade_win.png'
        input_file = InputFile(photo_file)

    sent = await bot.send_photo(
        chat_id=chat_id,
        photo=input_file,
        caption=caption,
        parse_mode=parse_mode if caption else None
    )

    return SendResult(success=True, message_id=sent.message_id)
```

---

### Step 5: Cross-Promo Forwarding (`domains/crosspromo/service.py`)

After TP1, TP2, and TP3 hits, the Telegram message is **forwarded** from the VIP channel to the FREE channel. This is handled by the cross-promo system:

```
TP1 hit → enqueue job: forward_tp1_sequence
  └─ forward original signal message VIP→FREE
  └─ forward TP1 celebration message VIP→FREE
  └─ send AI-generated promo text to FREE channel
  └─ start 30-minute countdown before finish

TP2 hit → enqueue job: forward_tp_update (tp_number=2)
  └─ forward TP2 message VIP→FREE
  └─ reset the 30-minute finish countdown

TP3 hit → enqueue job: forward_tp_update (tp_number=3)
  └─ forward TP3 message VIP→FREE
  └─ send AI hype message to FREE channel
  └─ finish cross-promo immediately
  └─ trigger Hype Bot flow chain
```

The `tp1_message_id`, `tp2_message_id`, `tp3_message_id` values stored in the DB are what the cross-promo system uses to know which Telegram message to forward. **If an image is sent as a photo+caption, the returned `message_id` is still a regular Telegram message ID and is forwarded the same way.**

---

## 4. The Dollar Profit Calculation

### Constants (`core/pip_calculator.py`)

This is the single source of truth for all pip math. **All other files import from here.**

```python
# core/pip_calculator.py

PIP_VALUE           = 0.10    # $0.10 price movement = 1 pip on XAU/USD
PIPS_MULTIPLIER     = 10      # price_diff_in_dollars × 10 = pips
USD_PER_PIP_PER_LOT = 1.0    # $1.00 profit per pip per standard lot (1 lot = 100 oz gold)
COMMISSION_PER_LOT  = 7.0    # $7.00 round-turn commission per lot (fixed)
```

### Why these numbers?

- **Gold (XAU/USD)** is quoted in USD per troy ounce
- A standard lot = 100 oz
- A $0.10 price move on 100 oz = $10.00 value per lot
- But the platform's `USD_PER_PIP_PER_LOT = 1.0` (not $10.00) — this reflects the internal lot sizing convention used by EntryLab signals
- So: 1 pip = $0.10 price move → $1.00 profit per lot per pip

### The pip calculation

```python
# core/pip_calculator.py — calculate_pips()

def calculate_pips(entry_price: float, exit_price: float, direction: str) -> float:
    if direction.upper() == "BUY":
        return round((exit_price - entry_price) * PIPS_MULTIPLIER, 1)
    else:  # SELL
        return round((entry_price - exit_price) * PIPS_MULTIPLIER, 1)

# Example BUY:  entry=2750.00, exit=2755.00
#   pips = (2755.00 - 2750.00) × 10 = 50.0 pips

# Example SELL: entry=2755.00, exit=2750.00
#   pips = (2755.00 - 2750.00) × 10 = 50.0 pips  (also profit for SELL)
```

### The dollar profit calculation

```python
# showcase/profit_calculator.py — calculate_trade_profit()

def calculate_trade_profit(
    entry_price: float,
    exit_price: float,
    direction: str,
    lot_size: float = 1.0,
    include_commission: bool = True
) -> TradeProfit:

    pips          = calculate_pips(entry_price, exit_price, direction)
    gross_profit  = pips * USD_PER_PIP_PER_LOT * lot_size   # pips × $1.00 × lots
    commission    = COMMISSION_PER_LOT * lot_size if include_commission else 0
    net_profit    = gross_profit - commission

    # Result fields:
    # .pips         = 50.0
    # .gross_profit = 50.0  ($50.00)
    # .commission   = 7.0   ($7.00)
    # .net_profit   = 43.0  ($43.00) ← this is what is displayed
```

### Worked example (BUY, TP1)

| Field | Calculation | Result |
|---|---|---|
| Entry price | — | $2,750.00 |
| TP1 exit price | — | $2,755.00 |
| Price diff | $2,755.00 − $2,750.00 | $5.00 |
| Pips | $5.00 × 10 | 50 pips |
| Gross profit (1 lot) | 50 pips × $1.00/pip | $50.00 |
| Commission | $7.00 per lot | −$7.00 |
| **Net profit displayed** | — | **$43.00** |

### Important: lot size is hardcoded to 1.0

The current system always calculates for 1 standard lot. The MT5 screenshot (if real) will show the trader's **actual** lot size and real P&L. To show real lot profit in the replica, you would need to:

1. Add a `lot_size FLOAT DEFAULT 1.0` column to `forex_signals`
2. Store the configured lot size when creating a signal
3. Pass `lot_size=signal['lot_size']` to `calculate_trade_profit()`

---

## 5. Current Image Generation (Pillow Showcase Card)

### File: `showcase/trade_win_generator.py`

```python
CANVAS_WIDTH          = 1200        # high-DPI pixel width
CANVAS_HEIGHT_BASE    = 112         # top + bottom padding
CANVAS_HEIGHT_PER_ROW = 174         # height per trade row
BACKGROUND_COLOR      = "#000000"   # black background
COLOR_WHITE           = "#FFFFFF"
COLOR_BLUE            = "#4279EA"   # BUY direction, profit
COLOR_RED             = "#EA4242"   # SELL direction, loss
COLOR_GRAY            = "#B8B8B8"   # prices, timestamps
```

### The `TradeWinData` dataclass (one row per TP hit)

```python
@dataclass
class TradeWinData:
    pair:         str       # e.g. "XAU/USD"
    direction:    str       # "BUY" or "SELL"
    lot_size:     float     # e.g. 1.0
    entry_price:  float     # e.g. 2750.00
    exit_price:   float     # e.g. 2755.00 (TP price)
    profit:       float     # net profit, e.g. 43.00
    timestamp:    datetime  # UTC time of close

    # Computed properties:
    # .formatted_pair     → "XAUUSD" (no slash, uppercase)
    # .formatted_profit   → "43.00"
    # .formatted_lot      → "1" (or "0.50")
    # .formatted_timestamp → "2026.03.11  14:32:17"
    # .is_profit          → True if profit >= 0
    # .direction_lower    → "buy" or "sell"
```

### What each row draws (`_draw_trade_row`)

Each row has two lines:

**Line 1 (top):**
- Left: `XAUUSD` (pair, bold white, font size 56)
- Left: `buy 1` or `sell 1` (direction + lot, colored blue/red, font size 53)
- Right: `43.00` (profit, colored blue/red, font size 53)

**Line 2 (below):**
- Left: `2750.00 → 2755.00` (entry → exit with arrow, gray, font size 36)
- Right: `2026.03.11  14:32:17` (UTC timestamp, gray, font size 36)

### The full render function

```python
def generate_trade_win_image(trades: List[TradeWinData]) -> bytes:
    num_rows     = min(len(trades), 3)
    canvas_height = CANVAS_HEIGHT_BASE + (num_rows * CANVAS_HEIGHT_PER_ROW)
    # e.g. TP1=1 row: height=286px. TP3=3 rows: height=634px

    img  = Image.new('RGB', (1200, canvas_height), (0, 0, 0))   # black bg
    draw = ImageDraw.Draw(img)

    for i, trade in enumerate(trades[:3]):
        _draw_trade_row(draw, trade, i)   # draws at y = 30 + (i × 174)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()   # PNG bytes
```

### Font loading

```python
FONT_PATHS = {
    'medium':  ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                'assets/fonts/SFProDisplay-Medium.ttf'],
    'regular': ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                'assets/fonts/SFProText-Regular.ttf']
}
# Falls back to ImageFont.load_default() if neither path exists
```

---

## 6. How Images Are Attached to Telegram Messages

### The send function: `send_photo_to_channel()`

```python
# core/telegram_sender.py

async def send_photo(
    tenant_id: str,
    bot_role: str,        # "signal_bot"
    chat_id: str,         # Telegram channel ID (negative number for channels)
    photo: Union[bytes, io.BytesIO, str],
    caption: Optional[str] = None,
    parse_mode: str = 'HTML',
    disable_notification: bool = False
) -> SendResult:

    connection = _resolve_bot_connection(tenant_id, bot_role)
    bot        = Bot(token=connection.token)

    # Accepts bytes directly — wraps in BytesIO automatically
    if isinstance(photo, bytes):
        photo_file      = io.BytesIO(photo)
        photo_file.name = 'trade_win.png'
        input_file      = InputFile(photo_file)
    elif isinstance(photo, io.BytesIO):
        photo.name = 'trade_win.png'
        input_file = InputFile(photo)
    else:
        input_file = photo  # file path string

    sent = await bot.send_photo(
        chat_id=chat_id,
        photo=input_file,
        caption=caption,
        parse_mode=parse_mode if caption else None,
        disable_notification=disable_notification
    )

    return SendResult(success=True, message_id=sent.message_id)
```

### Credential resolution (60s TTL cache)

The function `_resolve_bot_connection(tenant_id, 'signal_bot')` fetches bot credentials from the `tenant_bot_connections` DB table. It is cached in memory for 60 seconds to avoid hammering the DB during message bursts.

```python
@dataclass
class BotConnection:
    tenant_id:      str
    bot_role:       str
    token:          str   # Telegram bot token
    vip_channel_id: Optional[str]   # e.g. "-1001234567890"
    free_channel_id: Optional[str]
    bot_username:   Optional[str]
    resolved_at:    float  # time.time()
```

### Telegram photo constraints

| Constraint | Limit | Notes |
|---|---|---|
| Max file size | 10 MB | Pillow PNG is ~100 KB — no issue |
| Max caption length | 1,024 characters | TP messages are well under this |
| Caption parse_mode | HTML or Markdown | Platform uses HTML throughout |
| `message_id` on success | Always returned | Stored in DB for cross-promo forwarding |

### The `SendResult` dataclass

```python
@dataclass
class SendResult:
    success:    bool
    message_id: Optional[int] = None   # Telegram message ID on success
    error:      Optional[str] = None
    error_code: Optional[int] = None
```

---

## 7. Database Schema — Signal Row Fields

The full `forex_signals` table row used during TP celebrations:

```sql
-- Core signal fields (all available in signal_data dict passed to messenger)
id                   SERIAL PRIMARY KEY
tenant_id            VARCHAR(100)
signal_type          VARCHAR(10)          -- 'BUY' or 'SELL'
pair                 VARCHAR(20)          -- 'XAU/USD'
entry_price          DECIMAL(10,2)
take_profit          DECIMAL(10,2)        -- TP1
take_profit_2        DECIMAL(10,2)        -- TP2 (nullable)
take_profit_3        DECIMAL(10,2)        -- TP3 (nullable)
stop_loss            DECIMAL(10,2)
effective_sl         DECIMAL(10,2)        -- current stop loss (may differ from original)
tp1_percentage       INTEGER              -- % of position closed at TP1 (default 50)
tp2_percentage       INTEGER              -- % closed at TP2 (default 30)
tp3_percentage       INTEGER              -- % closed at TP3 (default 20)
posted_at            TIMESTAMP            -- when signal was posted to Telegram
status               VARCHAR(20)          -- 'pending', 'won', 'lost', 'expired'
result_pips          DECIMAL(10,2)        -- final pips on close

-- TP tracking
tp1_hit              BOOLEAN DEFAULT FALSE
tp2_hit              BOOLEAN DEFAULT FALSE
tp3_hit              BOOLEAN DEFAULT FALSE
tp1_hit_at           TIMESTAMP
tp2_hit_at           TIMESTAMP
tp3_hit_at           TIMESTAMP

-- Telegram message IDs
telegram_message_id  BIGINT               -- original signal post message ID
tp1_message_id       BIGINT               -- TP1 celebration message ID (for cross-promo)
tp2_message_id       BIGINT               -- TP2 celebration message ID
tp3_message_id       BIGINT               -- TP3 celebration message ID
```

**Fields NOT yet in the schema that you may need to add:**

```sql
-- For real lot size support (Option A real P&L):
lot_size             FLOAT DEFAULT 1.0

-- For MT5 bridge matching (Option A):
mt5_ticket_id        BIGINT               -- MT5 trade ticket number
```

---

## 8. Two Implementation Options

### Option A — Real MT5 Screenshot (pushed from MT5 machine)

A Python bridge running on the same Windows machine as MetaTrader 5 captures the History tab when a trade closes and POSTs it to a new server endpoint.

**Requires:** A Python process running on the MT5 machine with the `MetaTrader5` pip package.

**Best for:** Showing the real MT5 terminal screenshot with authentic ticket numbers, real lot size, and actual P&L.

### Option B — Server-Side MT5 Replica (Pillow, no MT5 connection)

The existing Pillow image generator is redesigned to look like an MT5 History tab — same dark layout, same column structure — using data already in the signal row.

**Requires:** Only changes to `showcase/` — no new infrastructure.

**Best for:** Getting the visual immediately without any MT5 connectivity.

---

## 9. Option B — Server-Side MT5 Replica (Recommended First)

### What to build

Create a new file `showcase/mt5_replica_generator.py` that generates a Pillow image styled to look like the MT5 History tab.

**MT5 History tab columns to replicate:**

| Column | Data source | Example |
|---|---|---|
| Time | `datetime.utcnow()` | `2026.03.11 14:32:17` |
| Ticket | `signal.id` (or a fake ticket starting at `#100000`) | `#100234` |
| Symbol | `signal['pair'].replace('/', '')` | `XAUUSD` |
| Type | `signal['signal_type'].lower()` | `buy` |
| Volume | `1.00` (hardcoded until lot_size column added) | `1.00` |
| Open Price | `signal['entry_price']` | `2750.00` |
| Close Price | `signal['take_profit']` (for TP1) | `2755.00` |
| Profit | `calculate_trade_profit(...)` | `43.00` |

### New file: `showcase/mt5_replica_generator.py`

```python
"""
MT5 Replica Image Generator

Generates an image styled to match the MetaTrader 5 History tab.
Used as the TP win celebration image in place of the simple showcase card.

Data comes entirely from the signal row in forex_signals — no MT5 connection needed.
"""

import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

from PIL import Image, ImageDraw, ImageFont

from showcase.profit_calculator import calculate_trade_profit
from core.pip_calculator import calculate_pips


# ── Canvas dimensions ───────────────────────────────────────────────────────
CANVAS_WIDTH          = 1400      # wider to fit all columns
ROW_HEIGHT            = 52        # height per trade row
HEADER_HEIGHT         = 40        # column header row
PADDING_TOP           = 20
PADDING_BOTTOM        = 20
PADDING_SIDE          = 30

# ── MT5 colors ───────────────────────────────────────────────────────────────
BG_COLOR              = (24, 24, 24)       # #181818 dark gray
HEADER_BG             = (40, 40, 40)       # #282828 slightly lighter
ROW_ALT_BG            = (32, 32, 32)       # alternating row bg
BORDER_COLOR          = (60, 60, 60)       # subtle grid lines
TEXT_WHITE            = (255, 255, 255)
TEXT_GRAY             = (180, 180, 180)
TEXT_BUY              = (66, 184, 131)     # green #42B883
TEXT_SELL             = (234, 66, 66)      # red #EA4242
TEXT_PROFIT           = (66, 184, 131)     # green
TEXT_LOSS             = (234, 66, 66)      # red
HEADER_TEXT           = (140, 140, 140)    # muted gray for column headers

# ── Column layout (x position, width, alignment) ─────────────────────────────
COLUMNS = [
    ('Time',        PADDING_SIDE,         180, 'left'),
    ('Ticket',      PADDING_SIDE + 190,   90,  'right'),
    ('Symbol',      PADDING_SIDE + 290,   100, 'left'),
    ('Type',        PADDING_SIDE + 400,   70,  'left'),
    ('Volume',      PADDING_SIDE + 480,   80,  'right'),
    ('Open',        PADDING_SIDE + 570,   100, 'right'),
    ('Close',       PADDING_SIDE + 680,   100, 'right'),
    ('Profit',      PADDING_SIDE + 790,   110, 'right'),
]

FONT_PATHS = {
    'bold':    ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                'assets/fonts/SFProDisplay-Medium.ttf'],
    'regular': ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                'assets/fonts/SFProText-Regular.ttf'],
    'mono':    ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
}


@dataclass
class MT5TradeRow:
    time:       str      # "2026.03.11 14:32:17"
    ticket:     str      # "#100234"
    symbol:     str      # "XAUUSD"
    trade_type: str      # "buy" or "sell"
    volume:     str      # "1.00"
    open_price: str      # "2750.00"
    close_price: str     # "2755.00"
    profit:     float    # 43.00 (positive = win)


def _get_font(weight: str, size: int):
    paths = FONT_PATHS.get(weight, FONT_PATHS['regular'])
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def _build_rows_from_signal(signal_data: Dict[str, Any], tp_level: int) -> List[MT5TradeRow]:
    """Build MT5 trade rows from signal data."""
    entry_price = float(signal_data.get('entry_price', 0))
    direction   = signal_data.get('signal_type', 'BUY')
    pair        = signal_data.get('pair', 'XAU/USD').replace('/', '')  # XAUUSD
    signal_id   = signal_data.get('id', 0)
    base_ticket = 100000 + (signal_id % 90000)   # fake ticket number from signal ID

    tp_prices = [
        signal_data.get('take_profit'),      # TP1
        signal_data.get('take_profit_2'),    # TP2
        signal_data.get('take_profit_3'),    # TP3
    ]

    rows = []
    for i in range(tp_level):
        tp_price = tp_prices[i]
        if tp_price is None:
            continue
        tp_price = float(tp_price)

        profit_calc = calculate_trade_profit(
            entry_price=entry_price,
            exit_price=tp_price,
            direction=direction,
            lot_size=signal_data.get('lot_size', 1.0),  # use real lot_size if column exists
            include_commission=True
        )

        rows.append(MT5TradeRow(
            time        = datetime.utcnow().strftime('%Y.%m.%d %H:%M:%S'),
            ticket      = f"#{base_ticket + i}",
            symbol      = pair,
            trade_type  = direction.lower(),
            volume      = f"{signal_data.get('lot_size', 1.0):.2f}",
            open_price  = f"{entry_price:.2f}",
            close_price = f"{tp_price:.2f}",
            profit      = profit_calc.net_profit
        ))

    return rows


def generate_mt5_replica_image(signal_data: Dict[str, Any], tp_level: int) -> bytes:
    """
    Generate a Pillow image styled as an MT5 History tab.

    Args:
        signal_data: Full signal row dict from forex_signals table
        tp_level:    1, 2, or 3 — how many TP rows to show

    Returns:
        PNG bytes
    """
    rows = _build_rows_from_signal(signal_data, tp_level)
    if not rows:
        return b''

    num_rows     = len(rows)
    canvas_height = PADDING_TOP + HEADER_HEIGHT + (num_rows * ROW_HEIGHT) + PADDING_BOTTOM

    img  = Image.new('RGB', (CANVAS_WIDTH, canvas_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_header  = _get_font('bold',    18)
    font_regular = _get_font('regular', 22)
    font_bold    = _get_font('bold',    22)
    font_mono    = _get_font('mono',    20)

    # ── Draw header row ───────────────────────────────────────────────────────
    header_y = PADDING_TOP
    draw.rectangle([0, header_y, CANVAS_WIDTH, header_y + HEADER_HEIGHT], fill=HEADER_BG)

    for col_name, x, width, align in COLUMNS:
        draw.text((x, header_y + 12), col_name, font=font_header, fill=HEADER_TEXT)

    # Header bottom border
    draw.line([(0, header_y + HEADER_HEIGHT), (CANVAS_WIDTH, header_y + HEADER_HEIGHT)],
              fill=BORDER_COLOR, width=1)

    # ── Draw data rows ─────────────────────────────────────────────────────────
    for row_idx, row in enumerate(rows):
        row_y  = PADDING_TOP + HEADER_HEIGHT + (row_idx * ROW_HEIGHT)
        row_bg = ROW_ALT_BG if row_idx % 2 == 0 else BG_COLOR
        draw.rectangle([0, row_y, CANVAS_WIDTH, row_y + ROW_HEIGHT], fill=row_bg)

        # Row border
        draw.line([(0, row_y + ROW_HEIGHT), (CANVAS_WIDTH, row_y + ROW_HEIGHT)],
                  fill=BORDER_COLOR, width=1)

        profit_color = TEXT_PROFIT if row.profit >= 0 else TEXT_LOSS
        type_color   = TEXT_BUY if row.trade_type == 'buy' else TEXT_SELL

        profit_str   = f"+{row.profit:.2f}" if row.profit >= 0 else f"{row.profit:.2f}"

        row_data = [
            (row.time,                TEXT_GRAY,     font_mono),
            (row.ticket,              TEXT_GRAY,     font_regular),
            (row.symbol,              TEXT_WHITE,    font_bold),
            (row.trade_type,          type_color,    font_bold),
            (row.volume,              TEXT_GRAY,     font_regular),
            (row.open_price,          TEXT_GRAY,     font_mono),
            (row.close_price,         TEXT_WHITE,    font_mono),
            (profit_str,              profit_color,  font_bold),
        ]

        text_y = row_y + (ROW_HEIGHT - 22) // 2   # vertically centered

        for (col_name, x, width, align), (text, color, font) in zip(COLUMNS, row_data):
            if align == 'right':
                bbox  = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                draw.text((x + width - text_w, text_y), text, font=font, fill=color)
            else:
                draw.text((x, text_y), text, font=font, fill=color)

    # ── Summary bar ───────────────────────────────────────────────────────────
    total_profit = sum(r.profit for r in rows)
    summary_y    = PADDING_TOP + HEADER_HEIGHT + (num_rows * ROW_HEIGHT)
    draw.rectangle([0, summary_y, CANVAS_WIDTH, summary_y + 35], fill=HEADER_BG)

    summary_color = TEXT_PROFIT if total_profit >= 0 else TEXT_LOSS
    summary_str   = f"Total: {'+' if total_profit >= 0 else ''}{total_profit:.2f}"
    draw.text((CANVAS_WIDTH - PADDING_SIDE - 200, summary_y + 9),
              summary_str, font=font_bold, fill=summary_color)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()
```

### Wire it in — change one function in `messenger.py`

```python
# scheduler/messenger.py — _generate_image_with_retry()
# CHANGE THIS:

async def _generate_image_with_retry(
    self, signal_data: Dict, tp_level: int,
    max_attempts: int = 3, delay_ms: int = 200
) -> Optional[bytes]:

    # ── BEFORE (current) ──────────────────────────────────────────────────────
    from showcase.trade_win_generator import generate_trade_win_image, TradeWinData
    trades    = self._build_trades_for_showcase(signal_data, tp_level)
    img_bytes = generate_trade_win_image(trades)

    # ── AFTER (swap to MT5 replica) ───────────────────────────────────────────
    from showcase.mt5_replica_generator import generate_mt5_replica_image
    img_bytes = generate_mt5_replica_image(signal_data, tp_level)

    # ─────────────────────────────────────────────────────────────────────────
    # Return type (bytes) is identical. Nothing else in the chain changes.
    # Retry logic and text-only fallback work exactly the same.
    
    if img_bytes:
        return img_bytes
    return None
```

**That is the only code change needed for Option B.** All TP1, TP2, and TP3 celebrations are automatically covered because they all call `_generate_image_with_retry()`.

---

## 10. Option A — Real MT5 Screenshot Push

This approach requires a Python process running on the **same Windows machine as MetaTrader 5**.

### Architecture

```
┌──────────────────────────────┐       HTTPS POST         ┌───────────────────────────────┐
│  Windows machine with MT5    │  ──────────────────────►  │  EntryLab server              │
│                              │                            │                               │
│  mt5_bridge.py               │  {                         │  POST /api/forex/tp-screenshot│
│  ├─ Connects to MT5 API      │    "tenant_id": "...",     │  ├─ Decode base64 PNG         │
│  ├─ Polls closed positions   │    "signal_id": 1234,      │  ├─ Get celebration text      │
│  ├─ Takes screenshot of      │    "tp_number": 1,         │  ├─ send_photo_to_channel()   │
│  │   History tab             │    "image": "<base64>",    │  └─ Return message_id         │
│  └─ POSTs to platform        │    "pips": 50.0,           │                               │
│                              │    "net_profit": 43.00     │                               │
└──────────────────────────────┘  }                         └───────────────────────────────┘
```

### MT5 Python bridge (`mt5_bridge.py` — runs on Windows machine)

```python
"""
MT5 Screenshot Bridge

Runs on the Windows machine alongside MetaTrader 5.
Detects closed positions and sends screenshots to the EntryLab server.

Requirements (Windows):
    pip install MetaTrader5 pywin32 Pillow requests
"""

import MetaTrader5 as mt5
import win32gui
import win32con
import win32ui
from PIL import Image
import io
import base64
import requests
import time
import json

# ── Config ────────────────────────────────────────────────────────────────────
PLATFORM_URL  = "https://your-entrylab-domain.com/api/forex/tp-screenshot"
TENANT_ID     = "entrylab"
API_SECRET    = "your-hmac-secret"   # shared secret for authentication
POLL_INTERVAL = 5   # seconds between position checks

# Map MT5 ticket → signal_id (populated when signals are posted)
# Stored in a local JSON file updated by the platform via a webhook
TICKET_MAP_FILE = "ticket_map.json"

# Track which tickets we have already sent screenshots for
sent_tickets = set()


def load_ticket_map():
    """Load the MT5 ticket → signal_id mapping from file."""
    try:
        with open(TICKET_MAP_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def take_mt5_history_screenshot() -> bytes:
    """
    Capture a screenshot of the MT5 terminal window.
    Returns PNG bytes.
    """
    # Find MT5 window by title
    hwnd = win32gui.FindWindow(None, "MetaTrader 5")
    if not hwnd:
        raise RuntimeError("MT5 window not found")

    # Get window dimensions
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width  = right - left
    height = bottom - top

    # Capture the window
    hwnd_dc    = win32gui.GetWindowDC(hwnd)
    mfc_dc     = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc    = mfc_dc.CreateCompatibleDC()
    save_bitmap = win32ui.CreateBitmap()
    save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(save_bitmap)
    save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

    # Convert to PIL Image → PNG bytes
    bmp_info = save_bitmap.GetInfo()
    bmp_str  = save_bitmap.GetBitmapBits(True)
    img      = Image.frombuffer(
        'RGB', (bmp_info['bmWidth'], bmp_info['bmHeight']),
        bmp_str, 'raw', 'BGRX', 0, 1
    )

    # Cleanup Windows GDI
    win32gui.DeleteObject(save_bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    # Save as PNG
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def send_screenshot_to_platform(
    signal_id: int,
    tp_number: int,
    img_bytes: bytes,
    pips: float,
    net_profit: float
) -> bool:
    """POST screenshot to EntryLab server."""
    payload = {
        "tenant_id":  TENANT_ID,
        "signal_id":  signal_id,
        "tp_number":  tp_number,
        "image":      base64.b64encode(img_bytes).decode('utf-8'),
        "pips":       pips,
        "net_profit": net_profit,
    }

    # Simple HMAC authentication header
    import hmac, hashlib
    body_bytes = json.dumps(payload).encode()
    sig = hmac.new(API_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()

    resp = requests.post(
        PLATFORM_URL,
        json=payload,
        headers={
            'X-Signature': sig,
            'Content-Type': 'application/json'
        },
        timeout=10
    )
    return resp.status_code == 200


def calculate_tp_number(ticket_info: dict) -> int:
    """
    Determine which TP number was hit based on ticket info.
    
    The simplest approach: the platform sends the tp_number when it creates
    partial close orders. Store tp_number in the ticket_map alongside signal_id.
    """
    return ticket_info.get('tp_number', 1)


def poll_closed_positions():
    """Main polling loop."""
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    print(f"MT5 bridge running. Polling every {POLL_INTERVAL}s...")

    while True:
        ticket_map = load_ticket_map()

        # Get deals from history (last 24 hours)
        from_date = time.time() - 86400
        deals = mt5.history_deals_get(from_date, time.time())

        if deals:
            for deal in deals:
                ticket = str(deal.ticket)
                if ticket in sent_tickets:
                    continue
                if ticket not in ticket_map:
                    continue   # not one of our signals

                # This is a deal we care about
                signal_id  = ticket_map[ticket]['signal_id']
                tp_number  = ticket_map[ticket].get('tp_number', 1)
                pips       = abs(deal.profit / deal.volume) if deal.volume else 0
                net_profit = deal.profit

                try:
                    img_bytes = take_mt5_history_screenshot()
                    success   = send_screenshot_to_platform(
                        signal_id, tp_number, img_bytes, pips, net_profit
                    )
                    if success:
                        sent_tickets.add(ticket)
                        print(f"Sent TP{tp_number} screenshot for signal #{signal_id}")
                    else:
                        print(f"Failed to send screenshot for ticket {ticket}")
                except Exception as e:
                    print(f"Error processing ticket {ticket}: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    poll_closed_positions()
```

### New server endpoint (`server.py`)

Add this to the server's routing and handler dispatch:

```python
# server.py — add to routing table
# In the route dispatch section, add:
('/api/forex/tp-screenshot', 'POST'): handle_tp_screenshot_post,


# New handler function (add to forex-related handlers or a new file):
def handle_tp_screenshot_post(handler):
    """
    Receive an MT5 screenshot and send it as the TP celebration photo.
    Called by the MT5 bridge running on the Windows machine.
    """
    import base64
    import asyncio
    import hmac
    import hashlib
    import json

    # ── Auth ─────────────────────────────────────────────────────────────────
    body_bytes = handler.request_body   # raw bytes
    sig_header = handler.headers.get('X-Signature', '')
    api_secret = os.environ.get('MT5_BRIDGE_SECRET', '')

    expected_sig = hmac.new(api_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig_header, expected_sig):
        handler.send_response(401)
        handler.end_headers()
        return

    # ── Parse payload ─────────────────────────────────────────────────────────
    data      = json.loads(body_bytes)
    tenant_id = data['tenant_id']
    signal_id = int(data['signal_id'])
    tp_number = int(data['tp_number'])      # 1, 2, or 3
    img_bytes = base64.b64decode(data['image'])
    pips      = float(data.get('pips', 0))

    # ── Get signal from DB ────────────────────────────────────────────────────
    import db as db_module
    signal = db_module.get_forex_signal_by_id(signal_id, tenant_id)
    if not signal:
        handler.send_response(404)
        handler.end_headers()
        return

    # ── Build celebration text ────────────────────────────────────────────────
    from bots.core.milestone_tracker import milestone_tracker
    signal_type = signal['signal_type']
    posted_at   = signal.get('posted_at')

    if isinstance(posted_at, datetime):
        posted_at = posted_at.isoformat()

    if tp_number == 1:
        has_tp2 = bool(signal.get('take_profit_2'))
        has_tp3 = bool(signal.get('take_profit_3'))
        remaining = ((signal.get('tp2_percentage') or 30) if has_tp2 else 0) + \
                    ((signal.get('tp3_percentage') or 20) if has_tp3 else 0)
        caption = milestone_tracker.generate_tp1_celebration(signal_type, pips, remaining, posted_at)
    elif tp_number == 2:
        tp1_price = float(signal.get('take_profit', 0))
        has_tp3   = bool(signal.get('take_profit_3'))
        remaining = (signal.get('tp3_percentage') or 20) if has_tp3 else 0
        caption   = milestone_tracker.generate_tp2_celebration(signal_type, pips, tp1_price, remaining, posted_at)
    else:  # tp_number == 3
        caption = milestone_tracker.generate_tp3_celebration(signal_type, pips, posted_at)

    # ── Optionally add profit badge overlay ───────────────────────────────────
    # (see Section 11 for add_profit_badge() implementation)
    # net_profit = float(data.get('net_profit', 0))
    # img_bytes  = add_profit_badge(img_bytes, net_profit)

    # ── Send photo to Telegram ────────────────────────────────────────────────
    from core.telegram_sender import send_photo_to_channel, SIGNAL_BOT

    result = asyncio.run(send_photo_to_channel(
        tenant_id    = tenant_id,
        bot_role     = SIGNAL_BOT,
        photo        = img_bytes,
        caption      = caption,
        channel_type = 'vip'
    ))

    if result.success:
        # Store message ID for cross-promo forwarding
        db_module.update_tp_message_id(signal_id, tp_number, result.message_id, tenant_id=tenant_id)

        # Trigger cross-promo (same as monitor.py does after normal TP hits)
        from domains.crosspromo.service import trigger_tp_crosspromo
        signal_message_id = signal.get('telegram_message_id')
        if signal_message_id:
            trigger_tp_crosspromo(
                tenant_id        = tenant_id,
                signal_id        = signal_id,
                tp_number        = tp_number,
                signal_message_id = signal_message_id,
                tp_message_id    = result.message_id,
                pips_secured     = pips
            )

        _send_json(handler, 200, {'ok': True, 'message_id': result.message_id})
    else:
        _send_json(handler, 500, {'ok': False, 'error': result.error})
```

### DB changes for Option A

```sql
-- Add to forex_signals (run once, server auto-migrates on startup)
ALTER TABLE forex_signals ADD COLUMN IF NOT EXISTS mt5_ticket_id BIGINT;
ALTER TABLE forex_signals ADD COLUMN IF NOT EXISTS lot_size FLOAT DEFAULT 1.0;

-- Add to db.py auto-migration section:
if 'mt5_ticket_id' not in existing_columns:
    cursor.execute("ALTER TABLE forex_signals ADD COLUMN mt5_ticket_id BIGINT")
if 'lot_size' not in existing_columns:
    cursor.execute("ALTER TABLE forex_signals ADD COLUMN lot_size FLOAT DEFAULT 1.0")
```

### Ticket map: linking MT5 tickets to signal IDs

When the platform posts a signal and gets back a Telegram `message_id`, it should also store the MT5 ticket number. This means:

1. The signal generator needs to know the MT5 ticket it placed (this comes from your MT5 EA or position manager)
2. Store it: `UPDATE forex_signals SET mt5_ticket_id = %s WHERE id = %s`
3. The bridge reads `ticket_map.json` which is regenerated by the server whenever a new signal is created:

```python
# Called from signal creation endpoint — writes ticket map for bridge to read
def write_ticket_map_for_bridge(tenant_id: str):
    """Generate ticket_map.json for the MT5 bridge."""
    import json
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, mt5_ticket_id, tp1_percentage, tp2_percentage, tp3_percentage,
               tp1_hit, tp2_hit, tp3_hit
        FROM forex_signals
        WHERE tenant_id = %s AND status = 'pending' AND mt5_ticket_id IS NOT NULL
    """, (tenant_id,))
    rows = cur.fetchall()

    ticket_map = {}
    for row in rows:
        signal_id, ticket_id, tp1_pct, tp2_pct, tp3_pct, tp1_hit, tp2_hit, tp3_hit = row
        if not ticket_id:
            continue
        # Determine which TP is next
        if not tp1_hit:
            tp_number = 1
        elif not tp2_hit:
            tp_number = 2
        else:
            tp_number = 3
        ticket_map[str(ticket_id)] = {'signal_id': signal_id, 'tp_number': tp_number}

    with open('ticket_map.json', 'w') as f:
        json.dump(ticket_map, f)
```

---

## 11. Dollar Amount Overlay on Screenshots

If you receive a real MT5 screenshot (Option A) and want to brand it with the calculated profit badge:

```python
# utils/image_overlay.py  (new file)

from PIL import Image, ImageDraw, ImageFont
import io
import os

FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'assets/fonts/SFProDisplay-Medium.ttf',
]


def _get_bold_font(size: int):
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def add_profit_badge(img_bytes: bytes, net_profit: float) -> bytes:
    """
    Stamp a branded profit badge onto an image (e.g., real MT5 screenshot).

    Places a semi-transparent green pill with the profit amount
    in the bottom-right corner of the image.

    Args:
        img_bytes:   PNG bytes of the original image
        net_profit:  Net profit in dollars (positive = profit)

    Returns:
        PNG bytes of the image with the badge overlaid
    """
    img  = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Format the profit text
    badge_text = f"+${net_profit:,.2f}" if net_profit >= 0 else f"-${abs(net_profit):,.2f}"

    font = _get_bold_font(52)

    # Measure text
    bbox  = draw.textbbox((0, 0), badge_text, font=font)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]

    # Position: bottom-right, 24px from edge
    x = img.width  - tw - 36
    y = img.height - th - 28

    # Background pill (semi-transparent green for profit, red for loss)
    pill_color = (16, 185, 129, 210) if net_profit >= 0 else (234, 66, 66, 210)
    draw.rounded_rectangle(
        [x - 16, y - 10, x + tw + 16, y + th + 10],
        radius=12,
        fill=pill_color
    )

    # Profit text (white)
    draw.text((x, y), badge_text, font=font, fill=(255, 255, 255, 255))

    # Convert back to RGB PNG
    out = io.BytesIO()
    img.convert('RGB').save(out, format='PNG', optimize=True)
    return out.getvalue()


def add_entrylab_watermark(img_bytes: bytes, text: str = "EntryLab") -> bytes:
    """
    Add a small bottom-left watermark to an image.
    """
    img  = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font = _get_bold_font(28)

    draw.text((20, img.height - 40), text, font=font, fill=(255, 255, 255, 120))

    out = io.BytesIO()
    img.convert('RGB').save(out, format='PNG')
    return out.getvalue()
```

**Usage in the server endpoint (Option A):**

```python
from showcase.profit_calculator import calculate_trade_profit

net_profit = calculate_trade_profit(
    entry_price        = float(signal['entry_price']),
    exit_price         = float(signal['take_profit']),   # TP1 for tp_number=1
    direction          = signal['signal_type'],
    lot_size           = float(signal.get('lot_size', 1.0)),
    include_commission = True
).net_profit

img_bytes = add_profit_badge(img_bytes, net_profit)  # overlay before sending
```

---

## 12. Complete File Change List

### Option B — Server-side MT5 Replica

| File | Action | Details |
|---|---|---|
| `showcase/mt5_replica_generator.py` | **CREATE** | New Pillow renderer with MT5 History tab styling |
| `scheduler/messenger.py` | **EDIT** | In `_generate_image_with_retry()`: replace `generate_trade_win_image()` call with `generate_mt5_replica_image()` |

That is the complete scope for Option B. Two files. The rest of the system (credential resolution, send_photo, cross-promo, retry logic) is unchanged.

---

### Option A — Real MT5 Screenshot (in addition to Option B or standalone)

| File | Action | Details |
|---|---|---|
| `mt5_bridge.py` | **CREATE** | Python process running on MT5 Windows machine |
| `utils/image_overlay.py` | **CREATE** | `add_profit_badge()` function |
| `server.py` | **EDIT** | Add route + `handle_tp_screenshot_post()` handler |
| `db.py` | **EDIT** | Add `mt5_ticket_id` and `lot_size` to auto-migration block |
| `ticket_map.json` | **CREATE** (auto) | Generated by server, read by bridge |

**New environment variable needed:**

```bash
MT5_BRIDGE_SECRET=<random 32-char string>   # shared HMAC secret between bridge and server
```

---

### Summary of signal data dict available in `messenger.py`

When `messenger.send_tp1_celebration(signal_type, pips, remaining, posted_at, signal_data)` is called, `signal_data` is the full row from `db.get_forex_signal_by_id()`. Fields available:

```python
signal_data = {
    'id':               1234,
    'tenant_id':        'entrylab',
    'signal_type':      'BUY',          # or 'SELL'
    'pair':             'XAU/USD',
    'entry_price':      2750.00,
    'take_profit':      2755.00,         # TP1
    'take_profit_2':    2760.00,         # TP2 (may be None)
    'take_profit_3':    2765.00,         # TP3 (may be None)
    'stop_loss':        2745.00,
    'effective_sl':     2750.00,         # current SL (may differ from original)
    'tp1_percentage':   50,
    'tp2_percentage':   30,
    'tp3_percentage':   20,
    'tp1_hit':          True,
    'tp2_hit':          False,
    'tp3_hit':          False,
    'tp1_hit_at':       '2026-03-11T14:32:17',
    'tp1_message_id':   98765432,        # Telegram msg ID of TP1 celebration
    'telegram_message_id': 98765400,     # Telegram msg ID of original signal post
    'posted_at':        '2026-03-11T13:45:00',
    'status':           'pending',
    'result_pips':      None,            # filled on close
    # (lot_size and mt5_ticket_id after schema migration)
}
```

---

## 13. Testing Checklist

### Option B (Pillow replica)

1. **Standalone test** — run directly to verify image output:
   ```python
   # test_replica.py
   from showcase.mt5_replica_generator import generate_mt5_replica_image

   signal_data = {
       'id': 99, 'signal_type': 'BUY', 'pair': 'XAU/USD',
       'entry_price': 2750.00, 'take_profit': 2755.00,
       'take_profit_2': 2760.00, 'take_profit_3': None,
   }

   for tp_level in [1, 2]:
       img = generate_mt5_replica_image(signal_data, tp_level)
       with open(f'test_tp{tp_level}.png', 'wb') as f:
           f.write(img)
       print(f"TP{tp_level}: {len(img)} bytes → test_tp{tp_level}.png")
   ```

2. **Visual review** — open `test_tp1.png` and `test_tp2.png`, confirm layout matches MT5 style

3. **Live test** — trigger a manual TP celebration by temporarily lowering a signal's TP price in the DB to below current price, confirm photo appears in Telegram VIP channel

4. **Fallback test** — temporarily break `generate_mt5_replica_image()` (raise an exception), confirm the text-only fallback fires and the message still appears

### Option A (MT5 bridge)

1. **Test bridge locally** — run `mt5_bridge.py` and use `requests` to mock a closed position deal in `mt5.history_deals_get()`

2. **Test endpoint** — `curl` the `/api/forex/tp-screenshot` endpoint with a sample base64 PNG and signal_id

3. **End-to-end** — place a manual MT5 trade at the exact TP price, confirm screenshot flows to Telegram

4. **HMAC auth** — confirm a request with an invalid `X-Signature` gets a 401

---

## Key Constants Quick Reference

| Constant | File | Value | Meaning |
|---|---|---|---|
| `PIPS_MULTIPLIER` | `core/pip_calculator.py` | `10` | `$0.10` move = 1 pip |
| `USD_PER_PIP_PER_LOT` | `core/pip_calculator.py` | `$1.00` | Profit per pip per lot |
| `COMMISSION_PER_LOT` | `core/pip_calculator.py` | `$7.00` | Commission per lot |
| `max_attempts` | `scheduler/messenger.py` | `3` | Image gen retries |
| `delay_ms` | `scheduler/messenger.py` | `200ms` | Retry delay |
| `CACHE_TTL_SECONDS` | `core/telegram_sender.py` | `60s` | Bot credential cache |
| `CANVAS_WIDTH` | `showcase/trade_win_generator.py` | `1200px` | High-DPI output |
| `POLL_INTERVAL` | `mt5_bridge.py` (new) | `5s` | MT5 position poll |

---

*Internal developer reference — EntryLab Platform — March 2026*
