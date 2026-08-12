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
    # SPREAD_PERCENT = 1.25% -> buy_price_wbtc = 61,000 * (1 - 0.0125) = 60,237.5 -> floor = 60237.5
    # SAVINGS_PERCENT = 0.25% -> safe_usdt = 12.2 * (1 - 0.0025) = 12.1695
    # raw_qty = 12.1695 / 60,237.5 = 0.000202025... -> floor(raw_qty * 100)/100 = 0.0

    db.insert_execution("exec_a", 0.0001, 60000.0, 6.0)
    db.insert_execution("exec_b", 0.0001, 62000.0, 6.2)

    mock_session = MagicMock()

    check_and_trade(db, mock_session, dry_run=True, spread_percent=1.25, savings_percent=0.25)

    # No REST order placed in DRY_RUN mode
    mock_session.place_order.assert_not_called()

    # Executions marked as processed
    pending = db.get_pending_executions()
    assert len(pending) == 0
    cleanup()


def test_check_and_trade_real_order():
    cleanup()
    db = DatabaseManager(TEST_DB)
    # Exec: 0.1 BTC @ 50,000 = 5000.0 USDT
    # Avg price = 50,000
    # SPREAD_PERCENT = 1.25% -> buy_price_wbtc = 50,000 * 0.9875 = 49,375.0 -> floor(val * 10)/10 = 49375.0
    # SAVINGS_PERCENT = 0.25% -> safe_usdt = 5000 * 0.9975 = 4987.5
    # raw_qty = 4987.5 / 49375 = 0.101012145... -> floor(val * 1e5)/1e5 = 0.10101
    db.insert_execution("exec_real", 0.1, 50000.0, 5000.0)

    mock_session = MagicMock()
    mock_session.place_order.return_value = {"retCode": 0, "result": {"orderId": "wbtc_order_123"}}

    check_and_trade(db, mock_session, dry_run=False, spread_percent=1.25, savings_percent=0.25)

    # REST place_order should be called once for WBTCUSDT
    mock_session.place_order.assert_called_once()
    kwargs = mock_session.place_order.call_args[1]
    assert kwargs["category"] == "spot"
    assert kwargs["symbol"] == "WBTCUSDT"
    assert kwargs["side"] == "Buy"
    assert kwargs["orderType"] == "Limit"
    assert kwargs["price"] == "49375.0"
    assert kwargs["qty"] == "0.10101"

    # Status updated in DB
    pending = db.get_pending_executions()
    assert len(pending) == 0
    cleanup()


def test_check_and_trade_amend_existing_order():
    cleanup()
    db = DatabaseManager(TEST_DB)
    # Exec: 0.1 BTC @ 50,000 = 5000.0 USDT
    # buy_price_wbtc = 49,375.0, qty_wbtc = 0.10101
    db.insert_execution("exec_amend", 0.1, 50000.0, 5000.0)

    mock_session = MagicMock()
    # Mock open order at price 49375.0 with existing qty 0.20000
    mock_session.get_open_orders.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "orderId": "existing_ord_999",
                    "side": "Buy",
                    "price": "49375.00",
                    "qty": "0.20000"
                }
            ]
        }
    }
    mock_session.amend_order.return_value = {"retCode": 0, "result": {"orderId": "existing_ord_999"}}

    check_and_trade(db, mock_session, dry_run=False, spread_percent=1.25, savings_percent=0.25)

    # Should call amend_order instead of place_order
    mock_session.place_order.assert_not_called()
    mock_session.amend_order.assert_called_once()
    kwargs = mock_session.amend_order.call_args[1]
    assert kwargs["category"] == "spot"
    assert kwargs["symbol"] == "WBTCUSDT"
    assert kwargs["orderId"] == "existing_ord_999"
    # new_qty = 0.20000 + 0.10101 = 0.30101
    assert kwargs["qty"] == "0.30101"

    # Status updated in DB
    pending = db.get_pending_executions()
    assert len(pending) == 0
    cleanup()


def test_sync_offline_executions_disabled():
    cleanup()
    db = DatabaseManager(TEST_DB)
    mock_session = MagicMock()
    mock_config = MagicMock()
    mock_config.sync_offline_history = False
    mock_config.sync_hours = 24.0

    from bot import sync_offline_executions
    sync_offline_executions(mock_session, db, config=mock_config)

    # get_executions should NOT be called when sync_offline_history is False
    mock_session.get_executions.assert_not_called()
    cleanup()


if __name__ == "__main__":
    test_db_manager()
    test_check_and_trade_below_threshold()
    test_check_and_trade_above_threshold_dry_run()
    test_check_and_trade_real_order()
    test_check_and_trade_amend_existing_order()
    test_sync_offline_executions_disabled()
    print("ALL TESTS PASSED SUCCESSFULLY!")
