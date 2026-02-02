"""
Trade Win Image Generator

Generates pixel-perfect MT5-style trade history images.
Matches Figma specs: 430x205px, SF Pro fonts (fallback to DejaVu Sans).

Data source: forex_signals table (Phase 1), MT4/MT5 API (Phase 2)
"""

import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Any
from PIL import Image, ImageDraw, ImageFont

from core.logging import get_logger

logger = get_logger(__name__)

CANVAS_WIDTH = 860
CANVAS_HEIGHT_BASE = 80  # Base height (padding top + bottom)
CANVAS_HEIGHT_PER_ROW = 124  # Height per trade row (2x original)
BACKGROUND_COLOR = "#000000"

COLOR_WHITE = "#FFFFFF"
COLOR_BLUE = "#4279EA"
COLOR_RED = "#EA4242"
COLOR_GRAY = "#B8B8B8"

CONTENT_LEFT = 32
CONTENT_TOP = 22
ROW_HEIGHT = 124

FONT_PATHS = {
    'medium': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'assets/fonts/SFProDisplay-Medium.ttf',
    ],
    'regular': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'assets/fonts/SFProText-Regular.ttf',
    ]
}


@dataclass
class TradeWinData:
    """Data for a single trade row."""
    pair: str
    direction: str
    lot_size: float
    entry_price: float
    exit_price: float
    profit: float
    timestamp: datetime
    
    @property
    def is_profit(self) -> bool:
        return self.profit >= 0
    
    @property
    def direction_lower(self) -> str:
        return self.direction.lower()
    
    @property
    def formatted_pair(self) -> str:
        return self.pair.replace("/", "").replace(" ", "").upper()
    
    @property
    def formatted_profit(self) -> str:
        return f"{abs(self.profit):,.2f}"
    
    @property
    def formatted_timestamp(self) -> str:
        return self.timestamp.strftime("%Y.%m.%d  %H:%M:%S")
    
    @property
    def formatted_lot(self) -> str:
        if self.lot_size == int(self.lot_size):
            return str(int(self.lot_size))
        return f"{self.lot_size:.2f}"


def _get_font(weight: str, size: int) -> Any:
    """Load font with fallback chain."""
    paths = FONT_PATHS.get(weight, FONT_PATHS['regular'])
    
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
    
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> Tuple[int, ...]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _draw_trade_row(
    draw: ImageDraw.ImageDraw,
    trade: TradeWinData,
    row_index: int,
    arrow_img: Optional[Image.Image] = None
) -> None:
    """Draw a single trade row at the specified index."""
    base_y = CONTENT_TOP + (row_index * ROW_HEIGHT)
    
    # 2x font sizes for high-res output
    font_pair = _get_font('medium', 40)
    font_direction = _get_font('regular', 38)
    font_small = _get_font('regular', 26)
    
    direction_color = COLOR_BLUE if trade.direction_lower == 'buy' else COLOR_RED
    profit_color = COLOR_BLUE if trade.is_profit else COLOR_RED
    
    # Row 1: Pair + direction/lot (left) | Profit (right)
    draw.text(
        (CONTENT_LEFT, base_y),
        trade.formatted_pair,
        font=font_pair,
        fill=_hex_to_rgb(COLOR_WHITE)
    )
    
    pair_bbox = draw.textbbox((CONTENT_LEFT, base_y), trade.formatted_pair, font=font_pair)
    pair_width = pair_bbox[2] - pair_bbox[0]
    
    direction_text = f"{trade.direction_lower} {trade.formatted_lot}"
    draw.text(
        (CONTENT_LEFT + pair_width + 12, base_y + 2),
        direction_text,
        font=font_direction,
        fill=_hex_to_rgb(direction_color)
    )
    
    # Row 2: Entry → Exit (left) | Timestamp (right)
    entry_y = base_y + 54
    entry_text = f"{trade.entry_price:.2f}"
    draw.text(
        (CONTENT_LEFT, entry_y),
        entry_text,
        font=font_small,
        fill=_hex_to_rgb(COLOR_GRAY)
    )
    
    entry_bbox = draw.textbbox((CONTENT_LEFT, entry_y), entry_text, font=font_small)
    entry_width = entry_bbox[2] - entry_bbox[0]
    entry_height = entry_bbox[3] - entry_bbox[1]
    
    # Draw centered arrow - calculate vertical center of text
    arrow_x = CONTENT_LEFT + entry_width + 12
    arrow_text = "→"
    arrow_bbox = draw.textbbox((0, 0), arrow_text, font=font_small)
    arrow_height = arrow_bbox[3] - arrow_bbox[1]
    # Center arrow vertically with entry price text
    arrow_y = entry_y + (entry_height - arrow_height) // 2
    
    draw.text(
        (arrow_x, arrow_y),
        arrow_text,
        font=font_small,
        fill=_hex_to_rgb(COLOR_GRAY)
    )
    
    arrow_width = arrow_bbox[2] - arrow_bbox[0]
    
    draw.text(
        (arrow_x + arrow_width + 12, entry_y),
        f"{trade.exit_price:.2f}",
        font=font_small,
        fill=_hex_to_rgb(COLOR_GRAY)
    )
    
    # Profit (right-aligned, row 1)
    profit_text = trade.formatted_profit
    profit_bbox = draw.textbbox((0, 0), profit_text, font=font_direction)
    profit_width = profit_bbox[2] - profit_bbox[0]
    profit_x = CANVAS_WIDTH - CONTENT_LEFT - profit_width
    
    draw.text(
        (profit_x, base_y + 2),
        profit_text,
        font=font_direction,
        fill=_hex_to_rgb(profit_color)
    )
    
    # Timestamp (right-aligned, row 2)
    timestamp_text = trade.formatted_timestamp
    timestamp_bbox = draw.textbbox((0, 0), timestamp_text, font=font_small)
    timestamp_width = timestamp_bbox[2] - timestamp_bbox[0]
    timestamp_x = CANVAS_WIDTH - CONTENT_LEFT - timestamp_width
    
    draw.text(
        (timestamp_x, entry_y),
        timestamp_text,
        font=font_small,
        fill=_hex_to_rgb(COLOR_GRAY)
    )


def calculate_canvas_height(num_rows: int) -> int:
    """Calculate dynamic canvas height based on number of trade rows."""
    rows = max(1, min(num_rows, 3))  # Clamp between 1-3
    return CANVAS_HEIGHT_BASE + (rows * CANVAS_HEIGHT_PER_ROW)


def generate_trade_win_image(trades: List[TradeWinData]) -> bytes:
    """
    Generate a trade win showcase image with dynamic height.
    
    Args:
        trades: List of TradeWinData (max 3 rows visible)
        
    Returns:
        PNG image as bytes
    """
    num_rows = min(len(trades), 3)
    canvas_height = calculate_canvas_height(num_rows)
    
    img = Image.new('RGB', (CANVAS_WIDTH, canvas_height), _hex_to_rgb(BACKGROUND_COLOR))
    draw = ImageDraw.Draw(img)
    
    arrow_img = None
    arrow_path = os.path.join(os.path.dirname(__file__), 'arrow.png')
    if os.path.exists(arrow_path):
        try:
            arrow_img = Image.open(arrow_path).convert('RGBA')
        except Exception as e:
            logger.warning(f"Failed to load arrow image: {e}")
    
    for i, trade in enumerate(trades[:3]):
        _draw_trade_row(draw, trade, i, arrow_img)
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_single_trade_image(
    pair: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pips: float,
    lot_size: float = 1.0,
    timestamp: Optional[datetime] = None
) -> bytes:
    """
    Convenience function to generate image for a single trade.
    
    Calculates profit from pips (assuming XAU/USD: $1 per pip per lot).
    
    Args:
        pair: Trading pair (e.g., "XAU/USD")
        direction: "BUY" or "SELL"
        entry_price: Entry price
        exit_price: Exit/TP price
        pips: Pips gained/lost
        lot_size: Lot size (default 1.0)
        timestamp: Trade close time (default: now)
        
    Returns:
        PNG image as bytes
    """
    profit = pips * lot_size
    
    if timestamp is None:
        timestamp = datetime.utcnow()
    
    trade = TradeWinData(
        pair=pair,
        direction=direction,
        lot_size=lot_size,
        entry_price=entry_price,
        exit_price=exit_price,
        profit=profit,
        timestamp=timestamp
    )
    
    return generate_trade_win_image([trade])


if __name__ == '__main__':
    test_trades = [
        TradeWinData(
            pair="XAU/USD",
            direction="BUY",
            lot_size=1,
            entry_price=4624.94,
            exit_price=4635.18,
            profit=1024.00,
            timestamp=datetime(2026, 1, 14, 8, 46, 29)
        ),
        TradeWinData(
            pair="XAU/USD",
            direction="SELL",
            lot_size=1,
            entry_price=4650.00,
            exit_price=4640.50,
            profit=950.00,
            timestamp=datetime(2026, 1, 14, 10, 30, 15)
        ),
        TradeWinData(
            pair="XAU/USD",
            direction="BUY",
            lot_size=1,
            entry_price=4680.00,
            exit_price=4670.00,
            profit=-1000.00,
            timestamp=datetime(2026, 1, 14, 12, 15, 45)
        ),
    ]
    
    img_bytes = generate_trade_win_image(test_trades)
    
    with open('showcase/test_output.png', 'wb') as f:
        f.write(img_bytes)
    
    print(f"Generated test image: showcase/test_output.png ({len(img_bytes)} bytes)")
