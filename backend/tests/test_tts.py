import os
import tempfile
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from services.tts import clean_tts_text, synthesize_cached, _evict_cache_if_needed


class CleanTtsTextTest(unittest.TestCase):
    def test_strips_leading_stage_direction(self):
        self.assertEqual(clean_tts_text("（笑）抱歉抱歉，可能是网络问题"), "抱歉抱歉，可能是网络问题")

    def test_strips_inline_stage_direction(self):
        self.assertEqual(clean_tts_text("抱歉（笑）抱歉"), "抱歉抱歉")

    def test_strips_pause(self):
        self.assertEqual(clean_tts_text("（停顿）好的，我们继续"), "好的，我们继续")

    def test_keeps_real_parenthetical(self):
        self.assertEqual(clean_tts_text("（这个问题很好）我们继续"), "（这个问题很好）我们继续")

    def test_english_laugh(self):
        self.assertEqual(clean_tts_text("(laughs) 你好"), "你好")

    def test_only_stage_direction_becomes_empty(self):
        self.assertEqual(clean_tts_text("（笑）"), "")

    def test_empty_text(self):
        self.assertEqual(clean_tts_text(""), "")

    def test_no_stage_direction_passthrough(self):
        self.assertEqual(clean_tts_text("你好，请介绍一下自己"), "你好，请介绍一下自己")


class CacheTest(IsolatedAsyncioTestCase):
    async def test_cache_hit_and_miss(self):
        """T-3: first call synthesizes and writes the cache; the second call
        returns the cached bytes without calling iFlytek again."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.tts.settings.tts_cache_dir", tmp):
                synth = AsyncMock(return_value=b"audio-bytes")
                with patch("services.tts.synthesize", new=synth):
                    first = await synthesize_cached("你好", voice=None, speed=50)
                    second = await synthesize_cached("你好", voice=None, speed=50)
                self.assertEqual(first, b"audio-bytes")
                self.assertEqual(second, b"audio-bytes")
                self.assertEqual(synth.await_count, 1)  # second call was a hit

    def test_cache_eviction(self):
        """T-3: files beyond the cap are evicted oldest-first."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.tts.settings.tts_cache_dir", tmp):
                for i in range(1002):
                    p = os.path.join(tmp, f"key{i}.mp3")
                    with open(p, "wb") as f:
                        f.write(b"x")
                    os.utime(p, (i + 1, i + 1))  # distinct, increasing mtimes
                _evict_cache_if_needed()
                remaining = [n for n in os.listdir(tmp) if n.endswith(".mp3")]
                self.assertLessEqual(len(remaining), 1000)
                # the two oldest (key0, key1) were evicted
                self.assertNotIn("key0.mp3", remaining)
                self.assertNotIn("key1.mp3", remaining)


if __name__ == "__main__":
    unittest.main()
