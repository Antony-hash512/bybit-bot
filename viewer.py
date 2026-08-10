"""
Bybit Open Orders Viewer script.
Fetches and displays active (unfilled / partially filled) orders across pairs and categories,
showing execution progress for each order.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from pybit.unified_trading import HTTP
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import load_config

# Set up standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("bybit_bot.viewer")

console = Console()


def create_progress_bar(percentage: float, width: int = 10) -> str:
    """Generate a visual ASCII progress bar for order fill percentage."""
    percentage = max(0.0, min(100.0, percentage))
    filled_len = int(round(width * percentage / 100.0))
    empty_len = width - filled_len
    bar = "█" * filled_len + "░" * empty_len
    return f"[{bar}] {percentage:5.1f}%"


def fetch_open_orders_for_category(
    session: HTTP, category: str, settle_coin: str | None = None
) -> list[dict[str, Any]]:
    """
    Fetch all open / partially filled orders for a specific category using pagination.
    Handles required settleCoin for linear and inverse categories.
    """
    if settle_coin:
        settle_coins = [settle_coin]
    elif category == "linear":
        settle_coins = ["USDT", "USDC"]
    elif category == "inverse":
        settle_coins = ["BTC", "ETH", "USDT"]
    else:
        settle_coins = [None]  # spot or other

    all_orders: list[dict[str, Any]] = []

    for coin in settle_coins:
        cursor: str | None = None
        while True:
            kwargs: dict[str, Any] = {"category": category, "limit": 50, "openOnly": 0}
            if coin:
                kwargs["settleCoin"] = coin
            if cursor:
                kwargs["cursor"] = cursor

            response = session.get_open_orders(**kwargs)
            ret_code = response.get("retCode", -1)
            if ret_code != 0:
                msg = response.get("retMsg", "Unknown error")
                logger.error(
                    f"Error fetching open orders for category '{category}' (settleCoin={coin}): [{ret_code}] {msg}"
                )
                raise RuntimeError(f"Bybit API Error ({ret_code}): {msg}")

            result = response.get("result", {})
            order_list = result.get("list", [])
            all_orders.extend(order_list)

            cursor = result.get("nextPageCursor")
            if not cursor:
                break

    return all_orders


async def get_all_open_orders(
    session: HTTP, categories: list[str], settle_coin: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Fetch open orders across all specified categories concurrently/asynchronously."""
    results: dict[str, list[dict[str, Any]]] = {}

    for cat in categories:
        try:
            cat_orders = await asyncio.to_thread(
                fetch_open_orders_for_category, session, cat, settle_coin
            )
            results[cat] = cat_orders
        except Exception as e:
            logger.warning(f"Could not fetch orders for category '{cat}': {e}")
            results[cat] = []

    return results


def build_orders_table(
    all_orders: dict[str, list[dict[str, Any]]], testnet: bool
) -> Table:
    """Build a styled rich Table summarizing all open orders and their fill progress."""
    env_label = "TESTNET" if testnet else "MAINNET"
    table = Table(
        title=f"🚀 Bybit Open Orders ({env_label}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )

    table.add_column("Category", style="dim", justify="center")
    table.add_column("Symbol", style="bold yellow")
    table.add_column("Side", justify="center")
    table.add_column("Order ID", style="dim")
    table.add_column("Type", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Total Qty", justify="right")
    table.add_column("Filled Qty", justify="right")
    table.add_column("Remaining Qty", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Progress", justify="left")
    table.add_column("Updated", style="dim", justify="center")

    total_orders = 0
    partially_filled_count = 0

    for category, orders in all_orders.items():
        for order in orders:
            total_orders += 1

            symbol = order.get("symbol", "N/A")
            side = order.get("side", "N/A")
            side_text = (
                Text("BUY", style="bold green")
                if side.upper() == "BUY"
                else Text("SELL", style="bold red")
                if side.upper() == "SELL"
                else Text(side)
            )

            order_id = order.get("orderId", "N/A")
            # Truncate order_id for display if too long
            short_id = order_id[:8] + "..." if len(order_id) > 12 else order_id

            order_type = order.get("orderType", "N/A")
            price = order.get("price", "0")

            qty = float(order.get("qty", 0.0))
            cum_exec_qty = float(order.get("cumExecQty", 0.0))
            leaves_qty = float(order.get("leavesQty", 0.0))

            progress_pct = (cum_exec_qty / qty * 100.0) if qty > 0 else 0.0

            order_status = order.get("orderStatus", "N/A")
            if order_status == "PartiallyFilled":
                status_text = Text(order_status, style="bold yellow")
                partially_filled_count += 1
            elif order_status in ("New", "Untriggered"):
                status_text = Text(order_status, style="cyan")
            else:
                status_text = Text(order_status)

            progress_bar = create_progress_bar(progress_pct)
            if progress_pct == 100.0:
                progress_display = Text(progress_bar, style="green")
            elif progress_pct > 0.0:
                progress_display = Text(progress_bar, style="yellow")
            else:
                progress_display = Text(progress_bar, style="dim white")

            updated_ms = int(order.get("updatedTime", 0))
            if updated_ms:
                updated_str = datetime.fromtimestamp(
                    updated_ms / 1000.0, tz=timezone.utc
                ).strftime("%H:%M:%S")
            else:
                updated_str = "N/A"

            table.add_row(
                category,
                symbol,
                side_text,
                short_id,
                order_type,
                price,
                f"{qty:g}",
                f"{cum_exec_qty:g}",
                f"{leaves_qty:g}",
                status_text,
                progress_display,
                updated_str,
            )

    if total_orders == 0:
        table.add_row(
            "-",
            "No open orders found",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
        )

    return table


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bybit Open Orders & Progress Viewer"
    )
    parser.add_argument(
        "-c",
        "--category",
        type=str,
        help="Specify trading category (e.g. spot, linear, inverse). Overrides config.",
    )
    parser.add_argument(
        "-s",
        "--settle-coin",
        type=str,
        help="Specify settlement coin for linear/inverse categories (e.g. USDT, USDC, BTC).",
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="Continuously watch and refresh open orders display.",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds when watch mode is enabled (default: 5).",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use Bybit Testnet regardless of .env settings.",
    )

    args = parser.parse_args()
    config = load_config()

    testnet = args.testnet or config.testnet
    categories = [args.category] if args.category else config.categories

    if not config.api_key or not config.api_secret or config.api_secret == "your_api_secret_here":
        console.print(
            Panel.fit(
                "[bold red]⚠️  API credentials not configured![/bold red]\n"
                "Please edit the [yellow].env[/yellow] file and set valid [bold]BYBIT_API_KEY[/bold] and [bold]BYBIT_API_SECRET[/bold].",
                title="Configuration Error",
                border_style="red",
            )
        )

    session = HTTP(
        testnet=testnet,
        api_key=config.api_key,
        api_secret=config.api_secret,
        rsa_authentication=config.rsa_authentication,
    )

    if args.watch:
        console.print(f"[bold cyan]Starting live viewer (refreshing every {args.interval}s, press Ctrl+C to exit)...[/bold cyan]")
        try:
            with Live(console=console, refresh_per_second=1) as live:
                while True:
                    all_orders = await get_all_open_orders(
                        session, categories, args.settle_coin
                    )
                    table = build_orders_table(all_orders, testnet)
                    live.update(table)
                    await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Viewer stopped.[/yellow]")
    else:
        all_orders = await get_all_open_orders(
            session, categories, args.settle_coin
        )
        table = build_orders_table(all_orders, testnet)
        console.print(table)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
