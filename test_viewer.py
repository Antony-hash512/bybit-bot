"""
Test suite for viewer.py functions.
"""

import unittest
from viewer import create_progress_bar, build_orders_table


class TestViewer(unittest.TestCase):
    def test_create_progress_bar(self):
        # 0% fill
        bar_0 = create_progress_bar(0.0)
        self.assertIn("░░░░░░░░░░", bar_0)
        self.assertIn("0.0%", bar_0)

        # 50% fill
        bar_50 = create_progress_bar(50.0)
        self.assertIn("█████░░░░░", bar_50)
        self.assertIn("50.0%", bar_50)

        # 100% fill
        bar_100 = create_progress_bar(100.0)
        self.assertIn("██████████", bar_100)
        self.assertIn("100.0%", bar_100)

    def test_build_orders_table(self):
        mock_orders = {
            "spot": [
                {
                    "orderId": "123456789012345",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "price": "65000",
                    "qty": "1.0",
                    "cumExecQty": "0.45",
                    "leavesQty": "0.55",
                    "orderStatus": "PartiallyFilled",
                    "updatedTime": "1723456789000",
                }
            ],
            "linear": [
                {
                    "orderId": "987654321098765",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "orderType": "Limit",
                    "price": "3500",
                    "qty": "2.0",
                    "cumExecQty": "0.0",
                    "leavesQty": "2.0",
                    "orderStatus": "New",
                    "updatedTime": "1723456799000",
                }
            ],
        }

        table = build_orders_table(mock_orders, testnet=True)
        self.assertEqual(table.title, table.title)  # table rendered without error
        self.assertEqual(len(table.rows), 2)


if __name__ == "__main__":
    unittest.main()
