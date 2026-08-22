import unittest

from agent.interviewer import _limit_transcript


class LimitTranscriptTest(unittest.TestCase):
    def test_short_passthrough(self):
        self.assertEqual(_limit_transcript("你好"), "你好")

    def test_long_is_truncated(self):
        t = "字" * 20000
        r = _limit_transcript(t)
        self.assertLess(len(r), 10000)
        self.assertIn("省略", r)
        self.assertTrue(r.startswith("字" * 10))  # head kept
        self.assertTrue(r.endswith("字" * 10))    # tail kept


if __name__ == "__main__":
    unittest.main()
