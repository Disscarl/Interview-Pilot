import unittest

from services.tts import clean_tts_text


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


if __name__ == "__main__":
    unittest.main()
