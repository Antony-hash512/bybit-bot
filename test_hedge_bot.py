import sqlite3
# standalone tests
from unittest.mock import MagicMock
import os
import shutil

from bot import DatabaseManager, check_and_trade, get_symbol_precision

TEST_DB = "test_hedge_bot.db"


def cleanup():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_db_manager():
    cleanup()
    db = DatabaseManager(TEST_DB)

    # 1. Insert execution
    inserted = db.insert_execution("exec_1", 0.0001, 60000.0, 6.0)
    assert inserted is True

    # 2. Insert duplicate execution
    inserted_dup = db.insert_execution("exec_1", 0.0001, 60000.0, 6.0)
    assert inserted_dup is False

    # 3. Get pending
    pending = db.get_pending_executions()
    assert len(pending) == 1
    assert pending[0]["exec_id"] == "exec_1"
    assert pending[0]["exec_value_usdt"] == 6.0

    # 4. Mark as processed
    db.mark_as_processed(["exec_1"])
    pending_after = db.get_pending_executions()
    assert len(pending_after) == 0

    cleanup()


def test_check_and_trade_below_threshold():
    cleanup()
    db = DatabaseManager(TEST_DB)
    # Total value = 3.0 USDT (< 6.0 limit)
    db.insert_execution("exec_sub", 0.00005, 60000.0, 3.0)

    mock_session = MagicMock()
    check_and_trade(db, mock_session, dry_run=True)

    # Should remain pending
    pending = db.get_pending_executions()
    assert len(pending) == 1
    cleanup()


def test_check_and_trade_above_threshold_dry_run():
    cleanup()
    db = DatabaseManager(TEST_DB)
    # Execution 1: 0.0001 BTC @ 60,000 = 6.0 USDT
    # Execution 2: 0.0001 BTC @ 62,000 = 6.2 USDT
    # Total USDT = 12.2, Total Qty = 0.0002
    # Avg price = 12.2 / 0.0002 = 61,000
    # buy_price_wbtc = 61,000 * 0.95 = 57,950
    # safe_usdt = 12.2 * 0.99 = 12.078
    # qty_wbtc = 12.078 / 57,950 = ~0.00020842

    db.insert_execution("exec_a", 0.0001, 60000.0, 6.0)
    db.insert_execution("exec_b", 0.0001, 62000.0, 6.2)

    mock_session = MagicMock()
    mock_session.get_instruments_info.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "priceFilter": {"tickSize": "0.01"},
                    "lotSizeFilter": {"basePrecision": "0.00001"}
                }
            ]
        }
    }

    check_and_trade(db, mock_session, dry_run=True)

    # No REST order placed in DRY_RUN mode
    mock_session.place_order.assert_not_called()

    # Executions marked as processed
    pending = db.get_pending_executions()
    assert len(pending) == 0
    cleanup()


def test_check_and_trade_real_order():
    cleanup()
    db = DatabaseManager(TEST_DB)
    db.insert_execution("exec_real", 0.0002, 50000.0, 10.0)

    mock_session = MagicMock()
    mock_session.get_instruments_info.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "priceFilter": {"tickSize": "0.01"},
                    "lotSizeFilter": {"basePrecision": "0.00001"}
                }
            ]
        }
    }
    mock_session.place_order.return_value = {"retCode": 0, "result": {"orderId": "wbtc_order_123"}}

    check_and_trade(db, mock_session, dry_run=False)

    # REST place_order should be called once for WBTCUSDT
    mock_session.place_order.assert_called_once()
    kwargs = mock_session.place_order.call_args[1]
    assert kwargs["category"] == "spot"
    assert kwargs["symbol"] == "WBTCUSDT"
    assert kwargs["side"] == "Buy"
    assert kwargs["orderType"] == "Limit"

    # Status updated in DB
    pending = db.get_pending_executions()
    assert len(pending) == 0
    cleanup()


if __name__ == "__main__":
    test_db_manager()
    test_check_and_trade_below_threshold()
    test_check_and_trade_above_threshold_dry_run()
    test_check_and_trade_real_order()
    print("ALL TESTS PASSED SUCCESSFULLY!")
