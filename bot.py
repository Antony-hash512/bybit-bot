"""
Bybit Reactive Hedge Trading Bot (Fire and Forget)
Monitors Sell executions on BTCUSDT, aggregates volume (min 6.0 USDT limit),
and places counter Limit Buy orders on WBTCUSDT.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import math
from pathlib import Path
import sqlite3
import sys
import threading

from logging.handlers import RotatingFileHandler

from pybit.unified_trading import HTTP, WebSocket

from config import Config, load_config

# Configure logging (console + rotating log file)
file_handler = RotatingFileHandler(
    "bot.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[stream_handler, file_handler],
)
logger = logging.getLogger("bybit_bot.hedge")


class DatabaseManager:
    """SQLite Database Manager for hedge bot execution tracking."""

    def __init__(self, db_path: str = "hedge_bot.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._lock, self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    exec_id TEXT PRIMARY KEY,
                    exec_qty REAL NOT NULL,
                    exec_price REAL NOT NULL,
                    exec_value_usdt REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def insert_execution(
        self, exec_id: str, exec_qty: float, exec_price: float, exec_value_usdt: float
    ) -> bool:
        """Insert execution with status='pending'. Returns True if inserted, False if duplicate."""
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO executions (exec_id, exec_qty, exec_price, exec_value_usdt, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (exec_id, exec_qty, exec_price, exec_value_usdt),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_executions(self) -> list[dict]:
        """Fetch all executions with status='pending'."""
        with self._lock, self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT exec_id, exec_qty, exec_price, exec_value_usdt
                FROM executions
                WHERE status = 'pending'
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def mark_as_processed(self, exec_ids: list[str]) -> None:
        """Update status to 'processed' for the given list of execution IDs."""
        if not exec_ids:
            return
        with self._lock, self.get_connection() as conn:
            placeholders = ",".join("?" for _ in exec_ids)
            conn.execute(
                f"UPDATE executions SET status = 'processed' WHERE exec_id IN ({placeholders})",
                exec_ids,
            )
            conn.commit()


def get_symbol_precision(session: HTTP, symbol: str = "WBTCUSDT") -> tuple[int, int]:
    """
    Fetch price and quantity precision for a given spot symbol from Bybit.
    Returns (price_precision, qty_precision).
    """
    try:
        res = session.get_instruments_info(category="spot", symbol=symbol)
        if res.get("retCode") == 0 and res.get("result", {}).get("list"):
            info = res["result"]["list"][0]
            price_filter = info.get("priceFilter", {})
            lot_filter = info.get("lotSizeFilter", {})

            tick_size = price_filter.get("tickSize", "0.01")
            base_precision = lot_filter.get("basePrecision", "0.0001")

            def count_decimals(val_str: str) -> int:
                if "." in val_str:
                    return len(val_str.rstrip("0").split(".")[1])
                return 0

            price_prec = count_decimals(tick_size)
            qty_prec = count_decimals(base_precision)
            return price_prec, qty_prec
    except Exception as e:
        logger.warning(f"Failed to fetch symbol precision for {symbol}, using fallback (2, 5): {e}")

    return 2, 5


trade_lock = threading.Lock()


def check_and_trade(
    db: DatabaseManager,
    session: HTTP,
    config: Config | None = None,
    dry_run: bool | None = None,
    spread_percent: float | None = None,
    savings_percent: float | None = None,
) -> None:
    """
    Checks DB for pending executions. If total value >= 6.0 USDT:
    - Calculates weighted average sell price.
    - Calculates buy_price_wbtc = avg_sell_price * (1 - SPREAD_PERCENT / 100).
    - Calculates safe_usdt = total_pending_usdt * (1 - SAVINGS_PERCENT / 100).
    - Calculates qty_wbtc = safe_usdt / buy_price_wbtc.
    - Floors buy_price_wbtc and qty_wbtc to 2 decimal places using math.floor(val * 100) / 100.
    - Places limit Buy order on WBTCUSDT (if dry_run is False).
    - Updates execution statuses in DB from 'pending' to 'processed'.
    """
    with trade_lock:
        if config is None:
            config = load_config()

        is_dry_run = config.dry_run if dry_run is None else dry_run
        spread_pct = config.spread_percent if spread_percent is None else spread_percent
        savings_pct = config.savings_percent if savings_percent is None else savings_percent

        pending = db.get_pending_executions()
        if not pending:
            return

        total_pending_usdt = sum(float(x["exec_value_usdt"]) for x in pending)

        if total_pending_usdt < 6.0:
            logger.info(
                f"Pending volume: {total_pending_usdt:.2f} USDT (< 6.0 USDT threshold). "
                f"Accumulated {len(pending)} execution(s). Waiting for more trades."
            )
            return

        total_pending_qty = sum(float(x["exec_qty"]) for x in pending)
        if total_pending_qty <= 0:
            logger.warning("Invalid total pending quantity <= 0. Skipping trade calculation.")
            return

        avg_sell_price = total_pending_usdt / total_pending_qty
        raw_buy_price = avg_sell_price * (1.0 - spread_pct / 100.0)
        safe_usdt = total_pending_usdt * (1.0 - savings_pct / 100.0)
        raw_qty = safe_usdt / raw_buy_price if raw_buy_price > 0 else 0.0

        # Strict floor rounding: price (1 decimal: math.floor(val * 10) / 10), qty (5 decimals: math.floor(val * 100000) / 100000)
        buy_price_wbtc = math.floor(round(raw_buy_price, 8) * 10) / 10.0
        qty_wbtc = math.floor(round(raw_qty, 8) * 100000) / 100000.0

        formatted_price = f"{buy_price_wbtc:.1f}"
        formatted_qty = f"{qty_wbtc:.5f}"

        # Check for existing open Buy order at the exact same price (to 1 decimal place)
        existing_order = None
        try:
            open_orders_resp = session.get_open_orders(category="spot", symbol="WBTCUSDT")
            if open_orders_resp.get("retCode") == 0:
                orders_list = open_orders_resp.get("result", {}).get("list", [])
                for ord_item in orders_list:
                    ord_side = ord_item.get("side", "").lower()
                    if ord_side == "buy":
                        try:
                            ord_price = float(ord_item.get("price", 0))
                            ord_price_floored = math.floor(round(ord_price, 8) * 10) / 10.0
                            if ord_price_floored == buy_price_wbtc:
                                existing_order = ord_item
                                break
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            logger.warning(f"Could not fetch open orders for WBTCUSDT: {e}")

        if existing_order:
            order_id = existing_order.get("orderId", "N/A")
            try:
                curr_qty = float(existing_order.get("qty", 0.0))
            except (ValueError, TypeError):
                curr_qty = 0.0

            raw_new_qty = curr_qty + qty_wbtc
            new_qty = math.floor(round(raw_new_qty, 8) * 100000) / 100000.0
            formatted_new_qty = f"{new_qty:.5f}"

            if is_dry_run:
                logger.info(
                    f"DRY_RUN: Увеличил бы объем существующего ордера [{order_id}] с {curr_qty:.5f} до {formatted_new_qty} по цене {formatted_price}"
                )
            else:
                try:
                    resp = session.amend_order(
                        category="spot",
                        symbol="WBTCUSDT",
                        orderId=order_id,
                        qty=formatted_new_qty,
                    )
                    ret_code = resp.get("retCode", -1)
                    ret_msg = resp.get("retMsg", "")
                    if ret_code == 0:
                        logger.info(
                            f"Увеличил объем существующего ордера [{order_id}] до [{formatted_new_qty}] по цене {formatted_price}"
                        )
                    else:
                        logger.error(f"Failed to amend order [{order_id}]: [{ret_code}] {ret_msg}")
                        return
                except Exception as e:
                    logger.error(f"Error amending WBTCUSDT order [{order_id}] via REST API: {e}")
                    return
        else:
            if is_dry_run:
                logger.info(
                    f"DRY_RUN: Выставил бы ордер Buy WBTCUSDT на сумму {safe_usdt:.2f} USDT "
                    f"по цене {formatted_price} (Qty: {formatted_qty}, Avg Sell Price: {avg_sell_price:.2f}, "
                    f"Spread: {spread_pct}%, Savings: {savings_pct}%)"
                )
            else:
                try:
                    resp = session.place_order(
                        category="spot",
                        symbol="WBTCUSDT",
                        side="Buy",
                        orderType="Limit",
                        price=formatted_price,
                        qty=formatted_qty,
                        timeInForce="GTC",
                    )
                    ret_code = resp.get("retCode", -1)
                    ret_msg = resp.get("retMsg", "")
                    if ret_code == 0:
                        order_id = resp.get("result", {}).get("orderId", "N/A")
                        logger.info(
                            f"ORDER PLACED SUCCESSFULLY [ID: {order_id}]: Buy WBTCUSDT price={formatted_price}, qty={formatted_qty}"
                        )
                    else:
                        logger.error(f"Failed to place order: [{ret_code}] {ret_msg}")
                        return
                except Exception as e:
                    logger.error(f"Error placing WBTCUSDT order via REST API: {e}")
                    return

        exec_ids = [x["exec_id"] for x in pending]
        db.mark_as_processed(exec_ids)
        logger.info(f"Updated status of {len(exec_ids)} execution(s) to 'processed' in DB.")


def sync_offline_executions(session: HTTP, db: DatabaseManager, config: Config | None = None) -> None:
    """
    Fetch BTCUSDT execution history for the last 24 hours via REST API before WS connection.
    Filter Sell orders and insert new executions into DB as 'pending'.
    Triggers check_and_trade afterwards.
    """
    logger.info("Starting offline REST execution sync for BTCUSDT (last 24 hours)...")
    start_time_ms = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
    cursor = None
    new_count = 0

    while True:
        kwargs = {
            "category": "spot",
            "symbol": "BTCUSDT",
            "startTime": start_time_ms,
            "limit": 100,
        }
        if cursor:
            kwargs["cursor"] = cursor

        try:
            resp = session.get_executions(**kwargs)
            ret_code = resp.get("retCode", -1)
            if ret_code != 0:
                logger.error(f"REST execution sync error [{ret_code}]: {resp.get('retMsg')}")
                break

            result = resp.get("result", {})
            executions = result.get("list", [])

            for item in executions:
                side = item.get("side", "")
                if side.lower() == "sell":
                    exec_id = str(item.get("execId", ""))
                    exec_qty = float(item.get("execQty", 0.0))
                    exec_price = float(item.get("execPrice", 0.0))
                    exec_value = float(item.get("execValue", 0.0)) or (exec_qty * exec_price)

                    if exec_id and exec_qty > 0 and exec_price > 0:
                        inserted = db.insert_execution(exec_id, exec_qty, exec_price, exec_value)
                        if inserted:
                            new_count += 1

            cursor = result.get("nextPageCursor")
            if not cursor:
                break
        except Exception as e:
            logger.error(f"Failed to fetch execution history during REST sync: {e}")
            break

    logger.info(f"REST sync complete. Inserted {new_count} new pending execution(s).")
    check_and_trade(db, session, config=config)


def make_ws_callback(db: DatabaseManager, session: HTTP, config: Config | None = None):
    def handle_ws_message(msg: dict) -> None:
        try:
            topic = msg.get("topic", "")
            if topic != "execution":
                return

            data = msg.get("data", [])
            if not isinstance(data, list):
                data = [data]

            for item in data:
                symbol = item.get("symbol", "")
                side = item.get("side", "")
                if symbol == "BTCUSDT" and side.lower() == "sell":
                    exec_id = str(item.get("execId", ""))
                    exec_qty = float(item.get("execQty", 0.0))
                    exec_price = float(item.get("execPrice", 0.0))
                    exec_value = float(item.get("execValue", 0.0)) or (exec_qty * exec_price)

                    if exec_id and exec_qty > 0 and exec_price > 0:
                        inserted = db.insert_execution(exec_id, exec_qty, exec_price, exec_value)
                        if inserted:
                            logger.info(
                                f"WS Event: Captured BTCUSDT Sell Execution {exec_id} "
                                f"(qty={exec_qty}, price={exec_price}, usdt={exec_value:.2f})"
                            )

            check_and_trade(db, session, config=config)
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)

    return handle_ws_message


async def async_main():
    config = load_config()

    logger.info("=" * 60)
    logger.info("Starting Bybit Reactive Hedge Bot")
    logger.info(f"DRY_RUN mode: {config.dry_run}")
    logger.info(f"Spread Percent: {config.spread_percent}% | Savings Percent: {config.savings_percent}%")
    logger.info("=" * 60)

    if not config.api_key or not config.api_secret or config.api_secret == "your_api_secret_here":
        logger.error("API credentials not properly configured in .env file!")
        sys.exit(1)

    logger.info(f"Operating Mode: {'TESTNET' if config.testnet else 'MAINNET'}")

    db_filename = "hedge_bot_testnet.db" if config.testnet else "hedge_bot.db"
    logger.info(f"Using database file: {db_filename}")
    db = DatabaseManager(db_filename)

    session = HTTP(
        testnet=config.testnet,
        api_key=config.api_key,
        api_secret=config.api_secret,
        rsa_authentication=config.rsa_authentication,
    )

    # 1. Offline REST API Sync
    sync_offline_executions(session, db, config=config)

    # 2. WebSocket Real-time Connection
    logger.info("Connecting to Bybit Private WebSocket execution stream...")
    ws = WebSocket(
        testnet=config.testnet,
        api_key=config.api_key,
        api_secret=config.api_secret,
        rsa_authentication=config.rsa_authentication,
        channel_type="private",
    )

    callback = make_ws_callback(db, session, config=config)
    ws.execution_stream(callback=callback)
    logger.info("Subscribed to 'execution' WebSocket stream. Listening for BTCUSDT Sell events...")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received. Stopping bot...")
    finally:
        try:
            ws.exit()
            logger.info("WebSocket connection closed cleanly.")
        except Exception as e:
            logger.warning(f"Error closing WebSocket: {e}")


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Bot exited.")


if __name__ == "__main__":
    main()
