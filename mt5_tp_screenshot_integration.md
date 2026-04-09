# MT5 Screenshot for TP Win Messages — Implementation Guide

The TP pipeline is already fully built. This document covers only what needs to be added: the screenshot image generation and where it plugs into the existing code.

---

## How images enter the pipeline (the one hook point)

Every TP celebration (TP1, TP2, TP3) passes through this single function in `scheduler/messenger.py`:

```python
async def _generate_image_with_retry(
    self, signal_data: Dict, tp_level: int,
    max_attempts: int = 3, delay_ms: int = 200
) -> Optional[bytes]:
    trades    = self._build_trades_for_showcase(signal_data, tp_level)
    img_bytes = generate_trade_win_image(trades)   # ← THIS IS THE ONLY LINE TO CHANGE
    if img_bytes:
        return img_bytes
    return None
```

Whatever this function returns (PNG bytes or `None`) gets sent to Telegram via `send_photo_to_channel()`. If it returns `None`, the system falls back to text-only automatically — no other code needs to change.

**`signal_data` contains the full signal row:**

```python
{
    'id':            1234,
    'signal_type':   'BUY',        # or 'SELL'
    'pair':          'XAU/USD',
    'entry_price':   2750.00,
    'take_profit':   2755.00,      # TP1
    'take_profit_2': 2760.00,      # TP2 (may be None)
    'take_profit_3': 2765.00,      # TP3 (may be None)
    'posted_at':     '2026-03-11T13:45:00',
    ...
}
```

`tp_level` is `1`, `2`, or `3` — how many rows the image should show.

---

## Two options

| | Option B (Server-side replica) | Option A (Real MT5 screenshot) |
|---|---|---|
| **What it is** | Pillow draws a layout that looks like the MT5 History tab | Python bridge on the MT5 machine captures the actual terminal |
| **Infrastructure** | No new infrastructure | Python process running on Windows alongside MT5 |
| **Build time** | 1–2 days | 3–5 days |
| **Lot size / P&L** | 1-lot calculated P&L | Real P&L from the trade |
| **Start here?** | ✅ Yes | Phase 2 |

---

## Option B — Server-side MT5 replica (Pillow)

### Create `showcase/mt5_replica_generator.py`

This file produces PNG bytes styled as the MT5 History tab (dark background, column layout, green/red profit).

```python
"""
showcase/mt5_replica_generator.py

Generates a Pillow image styled as an MT5 History tab for TP win messages.
Called by scheduler/messenger.py → _generate_image_with_retry().
"""

import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional

from PIL import Image, ImageDraw, ImageFont

from showcase.profit_calculator import calculate_trade_profit


# ── Canvas ────────────────────────────────────────────────────────────────────
CANVAS_WIDTH     = 1400
ROW_HEIGHT       = 56
HEADER_HEIGHT    = 44
PAD_TOP          = 20
PAD_BOTTOM       = 20
PAD_SIDE         = 30

# ── Colors ────────────────────────────────────────────────────────────────────
BG              = (24, 24, 24)
HEADER_BG       = (38, 38, 38)
ROW_ALT_BG      = (30, 30, 30)
BORDER          = (55, 55, 55)
TEXT_WHITE      = (255, 255, 255)
TEXT_GRAY       = (170, 170, 170)
TEXT_BUY        = (66, 184, 131)    # green
TEXT_SELL       = (234, 66,  66)    # red
TEXT_PROFIT     = (66, 184, 131)
TEXT_LOSS       = (234, 66,  66)
HEADER_TEXT     = (130, 130, 130)
SUMMARY_BG      = (40, 40, 40)

# ── Column layout: (header, x_start, width, alignment) ───────────────────────
COLUMNS = [
    ('Time',    PAD_SIDE,           190, 'left'),
    ('Ticket',  PAD_SIDE + 200,      90, 'right'),
    ('Symbol',  PAD_SIDE + 300,     110, 'left'),
    ('Type',    PAD_SIDE + 420,      70, 'left'),
    ('Volume',  PAD_SIDE + 500,      80, 'right'),
    ('Open',    PAD_SIDE + 595,     105, 'right'),
    ('Close',   PAD_SIDE + 710,     105, 'right'),
    ('Profit',  PAD_SIDE + 830,     120, 'right'),
]

FONT_PATHS = {
    'bold':    ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                'assets/fonts/SFProDisplay-Medium.ttf'],
    'regular': ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                'assets/fonts/SFProText-Regular.ttf'],
    'mono':    ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
}


def _font(weight: str, size: int):
    for path in FONT_PATHS.get(weight, FONT_PATHS['regular']):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


@dataclass
class _Row:
    time:        str
    ticket:      str
    symbol:      str
    trade_type:  str   # 'buy' or 'sell'
    volume:      str
    open_price:  str
    close_price: str
    profit:      float


def _build_rows(signal_data: Dict[str, Any], tp_level: int) -> List[_Row]:
    entry     = float(signal_data['entry_price'])
    direction = signal_data.get('signal_type', 'BUY')
    symbol    = signal_data.get('pair', 'XAU/USD').replace('/', '')
    sig_id    = signal_data.get('id', 0)
    lot       = float(signal_data.get('lot_size', 1.0))

    tp_keys   = ['take_profit', 'take_profit_2', 'take_profit_3']
    rows      = []

    for i in range(tp_level):
        tp_raw = signal_data.get(tp_keys[i])
        if tp_raw is None:
            continue
        tp_price = float(tp_raw)

        result = calculate_trade_profit(
            entry_price=entry,
            exit_price=tp_price,
            direction=direction,
            lot_size=lot,
            include_commission=True
        )

        rows.append(_Row(
            time        = datetime.utcnow().strftime('%Y.%m.%d %H:%M:%S'),
            ticket      = f"#{100000 + (sig_id % 90000) + i}",
            symbol      = symbol,
            trade_type  = direction.lower(),
            volume      = f"{lot:.2f}",
            open_price  = f"{entry:.2f}",
            close_price = f"{tp_price:.2f}",
            profit      = result.net_profit,
        ))

    return rows


def generate_mt5_replica_image(signal_data: Dict[str, Any], tp_level: int) -> bytes:
    """
    Generate an MT5 History-tab style image for a TP win.

    Args:
        signal_data: Full signal row dict from forex_signals
        tp_level:    1, 2, or 3

    Returns:
        PNG bytes (empty bytes on failure)
    """
    rows = _build_rows(signal_data, tp_level)
    if not rows:
        return b''

    n      = len(rows)
    height = PAD_TOP + HEADER_HEIGHT + (n * ROW_HEIGHT) + 38 + PAD_BOTTOM  # 38 = summary bar

    img  = Image.new('RGB', (CANVAS_WIDTH, height), BG)
    draw = ImageDraw.Draw(img)

    fh   = _font('bold',    19)   # header font
    fr   = _font('regular', 22)   # regular cell
    fb   = _font('bold',    22)   # bold cell
    fm   = _font('mono',    20)   # monospace (prices, time)

    # ── Header row ─────────────────────────────────────────────────────────────
    hy = PAD_TOP
    draw.rectangle([0, hy, CANVAS_WIDTH, hy + HEADER_HEIGHT], fill=HEADER_BG)
    draw.line([(0, hy + HEADER_HEIGHT), (CANVAS_WIDTH, hy + HEADER_HEIGHT)], fill=BORDER, width=1)

    for col, x, w, align in COLUMNS:
        draw.text((x, hy + 13), col, font=fh, fill=HEADER_TEXT)

    # ── Data rows ──────────────────────────────────────────────────────────────
    for idx, row in enumerate(rows):
        ry     = PAD_TOP + HEADER_HEIGHT + idx * ROW_HEIGHT
        row_bg = ROW_ALT_BG if idx % 2 == 0 else BG
        draw.rectangle([0, ry, CANVAS_WIDTH, ry + ROW_HEIGHT], fill=row_bg)
        draw.line([(0, ry + ROW_HEIGHT), (CANVAS_WIDTH, ry + ROW_HEIGHT)], fill=BORDER, width=1)

        profit_color = TEXT_PROFIT if row.profit >= 0 else TEXT_LOSS
        type_color   = TEXT_BUY   if row.trade_type == 'buy' else TEXT_SELL
        profit_str   = ('+' if row.profit >= 0 else '') + f"{row.profit:.2f}"

        cells = [
            (row.time,        TEXT_GRAY,   fm),
            (row.ticket,      TEXT_GRAY,   fr),
            (row.symbol,      TEXT_WHITE,  fb),
            (row.trade_type,  type_color,  fb),
            (row.volume,      TEXT_GRAY,   fr),
            (row.open_price,  TEXT_GRAY,   fm),
            (row.close_price, TEXT_WHITE,  fm),
            (profit_str,      profit_color, fb),
        ]

        ty = ry + (ROW_HEIGHT - 22) // 2

        for (_, x, w, align), (text, color, font) in zip(COLUMNS, cells):
            if align == 'right':
                bbox = draw.textbbox((0, 0), text, font=font)
                tw   = bbox[2] - bbox[0]
                draw.text((x + w - tw, ty), text, font=font, fill=color)
            else:
                draw.text((x, ty), text, font=font, fill=color)

    # ── Summary bar ────────────────────────────────────────────────────────────
    sy    = PAD_TOP + HEADER_HEIGHT + n * ROW_HEIGHT
    total = sum(r.profit for r in rows)
    draw.rectangle([0, sy, CANVAS_WIDTH, sy + 38], fill=SUMMARY_BG)

    s_color = TEXT_PROFIT if total >= 0 else TEXT_LOSS
    s_str   = f"Total:  {'+' if total >= 0 else ''}{total:.2f}"
    draw.text((CANVAS_WIDTH - PAD_SIDE - 250, sy + 10), s_str, font=fb, fill=s_color)

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()
```

### Wire it in — change one line in `scheduler/messenger.py`

```python
# BEFORE
async def _generate_image_with_retry(self, signal_data, tp_level, max_attempts=3, delay_ms=200):
    trades    = self._build_trades_for_showcase(signal_data, tp_level)
    img_bytes = generate_trade_win_image(trades)
    ...

# AFTER
async def _generate_image_with_retry(self, signal_data, tp_level, max_attempts=3, delay_ms=200):
    from showcase.mt5_replica_generator import generate_mt5_replica_image
    img_bytes = generate_mt5_replica_image(signal_data, tp_level)
    if img_bytes:
        return img_bytes
    return None
```

That is the complete scope for Option B. Everything else (retry logic, `send_photo_to_channel`, cross-promo, message_id storage) is untouched.

### Profit formula used inside `generate_mt5_replica_image`

```
pips        = |exit_price − entry_price| × 10        (PIPS_MULTIPLIER = 10 on XAU/USD)
gross       = pips × $1.00 × lot_size                 (USD_PER_PIP_PER_LOT = 1.0)
commission  = $7.00 × lot_size                        (COMMISSION_PER_LOT = 7.0)
net_profit  = gross − commission                      ← displayed in image
```

Example: entry $2,750, TP1 $2,755, BUY, 1 lot → 50 pips → $50 gross − $7 = **$43.00 net**

Lot size defaults to `1.0` (hardcoded). To show real lot size, add a `lot_size FLOAT DEFAULT 1.0` column to `forex_signals` and it will be picked up automatically via `signal_data.get('lot_size', 1.0)`.

### Test it standalone

```python
# run from project root: python3 test_mt5_image.py
from showcase.mt5_replica_generator import generate_mt5_replica_image

signal_data = {
    'id':            99,
    'signal_type':   'BUY',
    'pair':          'XAU/USD',
    'entry_price':   2750.00,
    'take_profit':   2755.00,
    'take_profit_2': 2760.00,
    'take_profit_3': None,
}

for tp_level in [1, 2]:
    data = generate_mt5_replica_image(signal_data, tp_level)
    with open(f'test_tp{tp_level}.png', 'wb') as f:
        f.write(data)
    print(f'TP{tp_level}: {len(data):,} bytes → test_tp{tp_level}.png')
```

Open the output PNGs and confirm the layout before deploying.

---

## Option A — Real MT5 screenshot push

Use this as a Phase 2 upgrade. It requires a Python process running on the **Windows machine alongside MetaTrader 5**.

### How it works

```
MT5 machine (Windows)              EntryLab server
─────────────────────              ───────────────
mt5_bridge.py polls                POST /api/forex/tp-screenshot
closed positions every 5s    →     { signal_id, tp_number, image: <base64 PNG> }
captures terminal screenshot        decode → send_photo_to_channel() → Telegram
```

### MT5 bridge (`mt5_bridge.py` — runs on Windows)

```python
"""
mt5_bridge.py — runs on the Windows machine alongside MetaTrader 5.

Install:  pip install MetaTrader5 pywin32 Pillow requests
Run:      python mt5_bridge.py
"""

import MetaTrader5 as mt5
import win32gui, win32con, win32ui
from PIL import Image
import io, base64, requests, time, json, hmac, hashlib

PLATFORM_URL  = "https://your-domain.com/api/forex/tp-screenshot"
TENANT_ID     = "entrylab"
API_SECRET    = "your-shared-hmac-secret"   # same value as MT5_BRIDGE_SECRET on server
POLL_INTERVAL = 5   # seconds
TICKET_MAP    = "ticket_map.json"  # written by server, maps mt5_ticket → {signal_id, tp_number}

sent = set()   # tickets already processed this session


def load_map():
    try:
        return json.load(open(TICKET_MAP))
    except FileNotFoundError:
        return {}


def screenshot_mt5_window() -> bytes:
    hwnd = win32gui.FindWindow(None, "MetaTrader 5")
    if not hwnd:
        raise RuntimeError("MT5 window not found")
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t

    dc     = win32gui.GetWindowDC(hwnd)
    mdc    = win32ui.CreateDCFromHandle(dc)
    sdc    = mdc.CreateCompatibleDC()
    bmp    = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w, h)
    sdc.SelectObject(bmp)
    sdc.BitBlt((0, 0), (w, h), mdc, (0, 0), win32con.SRCCOPY)

    info = bmp.GetInfo()
    data = bmp.GetBitmapBits(True)
    img  = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']), data, 'raw', 'BGRX', 0, 1)

    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC(); mdc.DeleteDC()
    win32gui.ReleaseDC(hwnd, dc)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def post_screenshot(signal_id, tp_number, img_bytes, pips, net_profit):
    payload = {
        "tenant_id":  TENANT_ID,
        "signal_id":  signal_id,
        "tp_number":  tp_number,
        "image":      base64.b64encode(img_bytes).decode(),
        "pips":       pips,
        "net_profit": net_profit,
    }
    body = json.dumps(payload).encode()
    sig  = hmac.new(API_SECRET.encode(), body, hashlib.sha256).hexdigest()
    r    = requests.post(PLATFORM_URL, data=body,
                         headers={'X-Signature': sig, 'Content-Type': 'application/json'},
                         timeout=15)
    return r.status_code == 200


def run():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    print(f"Bridge running — polling every {POLL_INTERVAL}s")

    while True:
        tmap  = load_map()
        deals = mt5.history_deals_get(time.time() - 86400, time.time()) or []

        for deal in deals:
            key = str(deal.ticket)
            if key in sent or key not in tmap:
                continue
            info       = tmap[key]
            signal_id  = info['signal_id']
            tp_number  = info.get('tp_number', 1)
            net_profit = deal.profit
            pips       = abs(deal.profit / deal.volume) if deal.volume else 0

            try:
                img = screenshot_mt5_window()
                if post_screenshot(signal_id, tp_number, img, pips, net_profit):
                    sent.add(key)
                    print(f"TP{tp_number} screenshot sent — signal #{signal_id}")
            except Exception as e:
                print(f"Error on ticket {key}: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    run()
```

### New server endpoint — add to `server.py`

Add the route to the routing table alongside other forex routes:

```python
('/api/forex/tp-screenshot', 'POST'): handle_tp_screenshot_post,
```

Handler function:

```python
def handle_tp_screenshot_post(handler):
    import base64, asyncio, hmac, hashlib, json

    body      = handler.request_body
    sig       = handler.headers.get('X-Signature', '')
    secret    = os.environ.get('MT5_BRIDGE_SECRET', '')
    expected  = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected):
        handler.send_response(401); handler.end_headers(); return

    data      = json.loads(body)
    tenant_id = data['tenant_id']
    signal_id = int(data['signal_id'])
    tp_number = int(data['tp_number'])
    img_bytes = base64.b64decode(data['image'])
    pips      = float(data.get('pips', 0))

    signal = db.get_forex_signal_by_id(signal_id, tenant_id)
    if not signal:
        handler.send_response(404); handler.end_headers(); return

    # Build celebration text (same text the scheduler generates)
    from bots.core.milestone_tracker import milestone_tracker
    sig_type  = signal['signal_type']
    posted_at = signal.get('posted_at')
    if hasattr(posted_at, 'isoformat'):
        posted_at = posted_at.isoformat()

    if tp_number == 1:
        has_tp2   = bool(signal.get('take_profit_2'))
        has_tp3   = bool(signal.get('take_profit_3'))
        remaining = ((signal.get('tp2_percentage') or 30) if has_tp2 else 0) + \
                    ((signal.get('tp3_percentage') or 20) if has_tp3 else 0)
        caption = milestone_tracker.generate_tp1_celebration(sig_type, pips, remaining, posted_at)
    elif tp_number == 2:
        remaining = (signal.get('tp3_percentage') or 20) if signal.get('take_profit_3') else 0
        caption   = milestone_tracker.generate_tp2_celebration(
                        sig_type, pips, float(signal['take_profit']), remaining, posted_at)
    else:
        caption = milestone_tracker.generate_tp3_celebration(sig_type, pips, posted_at)

    # Optionally overlay a profit badge (see next section)
    # img_bytes = add_profit_badge(img_bytes, float(data.get('net_profit', 0)))

    from core.telegram_sender import send_photo_to_channel, SIGNAL_BOT
    result = asyncio.run(send_photo_to_channel(
        tenant_id=tenant_id, bot_role=SIGNAL_BOT,
        photo=img_bytes, caption=caption, channel_type='vip'
    ))

    if result.success:
        db.update_tp_message_id(signal_id, tp_number, result.message_id, tenant_id=tenant_id)
        _send_json(handler, 200, {'ok': True, 'message_id': result.message_id})
    else:
        _send_json(handler, 500, {'ok': False, 'error': result.error})
```

### Add `MT5_BRIDGE_SECRET` environment variable

Set it on the server as a random string (32+ chars). The same value goes into `API_SECRET` in `mt5_bridge.py` on the Windows machine.

### Linking MT5 tickets to signal IDs

The bridge needs to know which MT5 ticket corresponds to which signal. The simplest approach:

1. Add `mt5_ticket_id BIGINT` column to `forex_signals`
2. After placing a trade in MT5, update the signal row with the ticket number
3. The server regenerates `ticket_map.json` whenever a signal is created or updated
4. The bridge reads `ticket_map.json` to look up the signal on each closed deal

---

## Optional: Profit badge overlay on real screenshots

If the real MT5 screenshot doesn't clearly show the profit (or you want consistent branding), stamp it with a Pillow badge:

```python
# utils/image_overlay.py

from PIL import Image, ImageDraw, ImageFont
import io, os

def add_profit_badge(img_bytes: bytes, net_profit: float) -> bytes:
    """Overlay a branded profit badge on the bottom-right of an image."""
    img  = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    draw = ImageDraw.Draw(img)

    text = ('+' if net_profit >= 0 else '') + f'${abs(net_profit):,.2f}'

    font_paths = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                  'assets/fonts/SFProDisplay-Medium.ttf']
    font = None
    for p in font_paths:
        if os.path.exists(p):
            try: font = ImageFont.truetype(p, 52); break
            except: pass
    if not font:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    x    = img.width  - tw - 36
    y    = img.height - th - 28

    fill = (16, 185, 129, 210) if net_profit >= 0 else (234, 66, 66, 210)
    draw.rounded_rectangle([x-14, y-10, x+tw+14, y+th+10], radius=12, fill=fill)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    out = io.BytesIO()
    img.convert('RGB').save(out, format='PNG', optimize=True)
    return out.getvalue()
```

Usage in the server endpoint (after decoding the base64 image, before calling `send_photo_to_channel`):

```python
from utils.image_overlay import add_profit_badge
from showcase.profit_calculator import calculate_trade_profit

net_profit = calculate_trade_profit(
    entry_price=float(signal['entry_price']),
    exit_price=float(signal['take_profit']),   # use take_profit_2/3 for tp_number 2/3
    direction=signal['signal_type'],
    lot_size=float(signal.get('lot_size', 1.0)),
    include_commission=True
).net_profit

img_bytes = add_profit_badge(img_bytes, net_profit)
```

---

## File summary

### Option B (Pillow replica) — 2 file changes

| File | Action |
|---|---|
| `showcase/mt5_replica_generator.py` | **Create** — full Pillow renderer above |
| `scheduler/messenger.py` | **Edit** — swap one import + one function call in `_generate_image_with_retry()` |

### Option A (Real MT5 push) — additional files

| File | Action |
|---|---|
| `mt5_bridge.py` | **Create** — runs on Windows machine |
| `server.py` | **Edit** — add route + `handle_tp_screenshot_post()` handler |
| `utils/image_overlay.py` | **Create** (optional) — profit badge overlay |
| `db.py` | **Edit** — add `mt5_ticket_id BIGINT` to auto-migration block |

---

*EntryLab Platform — March 2026*
