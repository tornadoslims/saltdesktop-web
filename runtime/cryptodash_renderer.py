# runtime/cryptodash_renderer.py
#
# Dashboard Renderer for CryptoDash.
# Renders a Rich terminal table with price, 24h%, market cap, volume, sparkline.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DashConfig = dict[str, Any]
PriceSnapshot = dict[str, Any]

# Braille-based sparkline characters (8 levels)
SPARKS = "▁▂▃▄▅▆▇█"


def _sparkline(prices: list[float], width: int = 10) -> str:
    """Generate an ASCII sparkline string from a list of price values.

    Args:
        prices: List of price floats (oldest first)
        width:  Number of characters in the output sparkline

    Returns:
        A string of spark characters, or '—' if insufficient data.
    """
    if len(prices) < 2:
        return "—"

    # Use last `width` values
    values = prices[-width:]
    lo, hi = min(values), max(values)

    if hi == lo:
        # Flat line — all same value
        return SPARKS[3] * len(values)

    def to_spark(v: float) -> str:
        idx = int((v - lo) / (hi - lo) * (len(SPARKS) - 1))
        return SPARKS[idx]

    return "".join(to_spark(v) for v in values)


def _fmt_price(price: float, currency: str) -> str:
    symbol = "$" if currency == "usd" else currency.upper() + " "
    if price >= 1000:
        return f"{symbol}{price:,.2f}"
    elif price >= 1:
        return f"{symbol}{price:.4f}"
    else:
        return f"{symbol}{price:.6f}"


def _fmt_large(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.2f}"


def _fmt_change(pct: float) -> tuple[str, str]:
    """Returns (formatted string, Rich color style)."""
    arrow = "▲" if pct >= 0 else "▼"
    style = "green" if pct >= 0 else "red"
    return f"{arrow} {abs(pct):.2f}%", style


def render_dashboard(
    snapshots: list[PriceSnapshot],
    history: dict[str, list[PriceSnapshot]],
    config: DashConfig,
) -> None:
    """Render the CryptoDash terminal dashboard using Rich.

    Prints a formatted table to stdout with columns:
      Coin | Price | 24h% | Market Cap | Volume 24h | Sparkline

    Args:
        snapshots: Current price snapshots from Price Fetcher
        history:   Full coin history dict from History Store
        config:    DashConfig with currency, show_sparkline, title
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
        from rich.text import Text
    except ImportError:
        _render_plain(snapshots, history, config)
        return

    currency: str = config.get("currency", "usd").lower()
    show_sparkline: bool = config.get("show_sparkline", True)
    title: str = config.get("title", "CryptoDash")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    console = Console()

    table = Table(
        title=f"[bold cyan]{title}[/bold cyan]  [dim]{now}[/dim]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="bright_black",
        pad_edge=True,
    )

    table.add_column("Coin", style="bold", min_width=12)
    table.add_column("Price", justify="right", min_width=14)
    table.add_column("24h %", justify="right", min_width=10)
    table.add_column("Market Cap", justify="right", min_width=12)
    table.add_column("Volume 24h", justify="right", min_width=12)
    if show_sparkline:
        table.add_column("Sparkline", justify="left", min_width=12)

    for snap in snapshots:
        coin_id: str = snap.get("coin_id", "?")
        name: str = snap.get("name", coin_id.capitalize())
        price: float = snap.get("price", 0.0)
        change: float = snap.get("change_24h_pct", 0.0)
        market_cap: float = snap.get("market_cap", 0.0)
        volume: float = snap.get("volume_24h", 0.0)

        change_str, change_style = _fmt_change(change)
        change_text = Text(change_str, style=change_style)

        coin_label = f"[bold]{name}[/bold]\n[dim]{coin_id}[/dim]"

        row = [
            coin_label,
            _fmt_price(price, currency),
            change_text,
            _fmt_large(market_cap),
            _fmt_large(volume),
        ]

        if show_sparkline:
            coin_history = history.get(coin_id, [])
            prices_over_time = [s.get("price", 0.0) for s in coin_history]
            spark = _sparkline(prices_over_time)
            spark_style = "green" if change >= 0 else "red"
            row.append(Text(spark, style=spark_style))

        table.add_row(*row)

    console.print()
    console.print(table)
    console.print()


def _render_plain(
    snapshots: list[PriceSnapshot],
    history: dict[str, list[PriceSnapshot]],
    config: DashConfig,
) -> None:
    """Fallback plain-text renderer when Rich is not installed."""
    currency = config.get("currency", "usd").lower()
    show_sparkline = config.get("show_sparkline", True)
    title = config.get("title", "CryptoDash")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"\n{'='*60}")
    print(f"  {title}  —  {now}")
    print(f"{'='*60}")
    header = f"{'Coin':<14} {'Price':>14} {'24h%':>10} {'Mkt Cap':>12} {'Volume':>12}"
    if show_sparkline:
        header += f"  {'Spark':<12}"
    print(header)
    print("-" * (len(header) + 2))

    for snap in snapshots:
        coin_id = snap.get("coin_id", "?")
        price = snap.get("price", 0.0)
        change = snap.get("change_24h_pct", 0.0)
        market_cap = snap.get("market_cap", 0.0)
        volume = snap.get("volume_24h", 0.0)
        arrow = "+" if change >= 0 else "-"

        row = (
            f"{coin_id:<14} "
            f"{_fmt_price(price, currency):>14} "
            f"{arrow}{abs(change):.2f}%{' ':>4} "
            f"{_fmt_large(market_cap):>12} "
            f"{_fmt_large(volume):>12}"
        )
        if show_sparkline:
            coin_history = history.get(coin_id, [])
            prices_over_time = [s.get("price", 0.0) for s in coin_history]
            row += f"  {_sparkline(prices_over_time)}"
        print(row)

    print()
