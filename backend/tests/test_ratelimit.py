import unittest

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


if __name__ == "__main__":
    unittest.main()
