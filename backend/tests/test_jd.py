import unittest

from services.jd import strip_html, _is_meaningful_company, _mentions_company, _extract_json


class StripHtmlTest(unittest.TestCase):
    def test_removes_tags_and_scripts(self):
        self.assertEqual(strip_html("<p>你好</p><script>alert(1)</script>"), "你好")

    def test_unescapes_entities(self):
        self.assertEqual(strip_html("&amp;"), "&")


class CompanyHeuristicTest(unittest.TestCase):
    def test_meaningful(self):
        self.assertTrue(_is_meaningful_company("米哈游"))

    def test_not_meaningful(self):
        for name in ("", "未知", "XX", "某公司", "保密", "n/a"):
            self.assertFalse(_is_meaningful_company(name), name)

    def test_mentions(self):
        self.assertTrue(_mentions_company("米哈游是一家游戏公司", "米哈游"))
        self.assertFalse(_mentions_company("这是一家游戏公司", "米哈游"))


class ExtractJsonTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_code_fence(self):
        self.assertEqual(_extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_surrounding_text(self):
        self.assertEqual(_extract_json('结果如下：{"a": 1} 完毕'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
