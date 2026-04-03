# runtime/cryptodash_renderer.py

**Path:** `runtime/cryptodash_renderer.py`
**Purpose:** Dashboard renderer for CryptoDash. Renders a Rich terminal table with price, 24h%, market cap, volume, and sparkline.

## Functions

### `render_dashboard(snapshots, history, config) -> None`
Renders the dashboard to stdout using the Rich library. Columns: Coin, Price, 24h %, Market Cap, Volume 24h, Sparkline (optional). Falls back to plain-text rendering if Rich is not installed.

### `_sparkline(prices, width=10) -> str`
Generates an ASCII sparkline string using braille characters (`"........"` 8 levels). Uses the last `width` values from the price list.

### `_fmt_price(price, currency) -> str`
Formats price with appropriate precision ($67,432.00 for large, $0.004521 for small).

### `_fmt_large(value) -> str`
Formats large numbers: $1.23B, $456.78M, $12.34K.

### `_fmt_change(pct) -> tuple[str, str]`
Returns formatted change string with arrow and Rich color style (green for positive, red for negative).

### `_render_plain(snapshots, history, config) -> None`
Fallback plain-text renderer when Rich is not available.
