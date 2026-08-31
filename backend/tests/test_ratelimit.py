import unittest
from unittest.mock import patch

from services.ratelimit import RateLimiter


class RateLimiterTest(unittest.TestCase):
    def test_allow_until_limit(self):
        r = RateLimiter()
        self.assertTrue(all(r.allow("k", 3) for _ in range(3)))
        self.assertFalse(r.allow("k", 3))

    def test_keys_are_isolated(self):
        r = RateLimiter()
        self.assertTrue(r.allow("a", 1))
        self.assertFalse(r.allow("a", 1))
        self.assertTrue(r.allow("b", 1))  # different key unaffected

    def test_window_rolls_over(self):
        # T-10: expired hits fall out of the window, allowing calls again.
        r = RateLimiter()
        with patch("services.ratelimit.time.time", return_value=1000.0):
            self.assertTrue(all(r.allow("k", 3) for _ in range(3)))
            self.assertFalse(r.allow("k", 3))
        # 61s later the whole window has expired.
        with patch("services.ratelimit.time.time", return_value=1061.0):
            self.assertTrue(r.allow("k", 3))

    def test_sweep_removes_expired_keys(self):
        # T-10: once the key table exceeds the threshold, a new call triggers
        # amortized cleanup of expired keys.
        r = RateLimiter()
        with patch("services.ratelimit.time.time", return_value=1000.0):
            for i in range(1025):  # over the 1024 sweep threshold
                r.allow(f"k{i}", 1)
        # New call at t=2000 sweeps every expired key.
        with patch("services.ratelimit.time.time", return_value=2000.0):
            r.allow("new", 1)
        self.assertEqual(len(r._hits), 1)
        self.assertIn("new", r._hits)


if __name__ == "__main__":
    unittest.main()
