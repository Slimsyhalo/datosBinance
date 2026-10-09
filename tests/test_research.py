import datetime as dt
import unittest

import numpy as np
import pandas as pd

from quantdata.acquire import periods, plan
from quantdata.live import Book
from quantdata.research import candle_qa, features


class ResearchTests(unittest.TestCase):
    def test_plan_exact_boundary_no_daily_overlap(self):
        periods_out = list(periods(dt.date(2026, 5, 9), dt.date(2026, 10, 9), "klines"))
        self.assertEqual(periods_out[0], ("daily", "2026-05-09"))
        self.assertEqual(periods_out[-1], ("daily", "2026-10-08"))
        self.assertIn(("monthly", "2026-06"), periods_out)
        self.assertNotIn(("monthly", "2026-05"), periods_out)
        self.assertEqual(len(periods_out), 35)

    def make_grid(self):
        index = pd.date_range("2026-05-09", periods=300, freq="1min", tz="UTC")
        close = 100 + np.arange(300) * .1
        return pd.DataFrame({"open": close, "high": close+1, "low": close-1,
                             "close": close, "volume": 1., "quote_volume": close}, index=index)

    def test_future_changes_do_not_change_past_features(self):
        original = self.make_grid()
        revised = original.copy()
        revised.loc[revised.index[250:], ["open", "high", "low", "close", "quote_volume"]] *= 2
        a, b = features(original), features(revised)
        pd.testing.assert_frame_equal(a.iloc[:250], b.iloc[:250])

    def test_missing_bar_resets_indicators(self):
        grid = self.make_grid()
        grid.iloc[150] = np.nan
        result = features(grid)
        self.assertTrue(pd.isna(result.return_1m.iloc[151]))
        self.assertTrue(pd.isna(result.ema_20.iloc[169]))
        self.assertFalse(pd.isna(result.ema_20.iloc[170]))
        self.assertTrue(result.vwap_utc_day.iloc[:150].notna().all())
        self.assertTrue(result.vwap_utc_day.iloc[150:].isna().all())

    def test_future_missing_bar_does_not_mask_past_vwap(self):
        original = self.make_grid()
        revised = original.copy()
        revised.iloc[250] = np.nan
        a, b = features(original), features(revised)
        pd.testing.assert_frame_equal(a.iloc[:250], b.iloc[:250])

    def test_l2_bridge_gap_and_absolute_quantity(self):
        book = Book({"lastUpdateId": 100, "bids": [["99", "2"]], "asks": [["101", "3"]]})
        self.assertTrue(book.apply({"U": 99, "u": 101, "pu": 98, "b": [["99", "4"]], "a": []}))
        self.assertEqual(str(book.bids[next(iter(book.bids))]), "4")
        with self.assertRaises(ValueError):
            book.apply({"U": 103, "u": 104, "pu": 102, "b": [], "a": []})

    def test_l2_zero_removes_level(self):
        book = Book({"lastUpdateId": 100, "bids": [["99", "2"]], "asks": [["101", "3"]]})
        book.apply({"U": 100, "u": 101, "pu": 99, "b": [["99", "0"]], "a": []})
        self.assertEqual(book.bids, {})


if __name__ == "__main__":
    unittest.main()
