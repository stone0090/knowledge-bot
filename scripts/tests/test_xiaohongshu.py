"""Offline tests for note images, identity, fallback and domain routing."""
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.parsers import url_reader as reader


NOTE_ID = "6ab2bd4f000000000a02270b"
PAGE = "https://www.xiaohongshu.com/explore/" + NOTE_ID


def page(note, desktop=False):
    state = ({"note": {"noteDetailMap": {NOTE_ID: {"note": note}}}} if desktop
             else {"noteData": {"data": {"noteData": note}}})
    return "<script>window.__INITIAL_STATE__=" + json.dumps(state) + "</script>"


class ImageTests(unittest.TestCase):
    def test_mobile_order_variants_dedup_and_string_preservation(self):
        html = page({"noteId": NOTE_ID, "title": "undefined", "desc": "正文",
                     "imageList": [
                         {"url": "http://cdn.example/1.jpg", "infoList": [
                             {"imageScene": "H5_PRV", "url": "http://cdn.example/thumb.jpg"},
                             {"imageScene": "H5_DTL", "url": "http://cdn.example/1.jpg"}]},
                         {"url": "//cdn.example/2.jpg"},
                         {"url": "http://cdn.example/1.jpg"},
                         {"url": "javascript:alert(1)"}]})
        html = html.replace('"desc": "正文"', '"unused": undefined, "desc": "正文"')
        result = reader._parse_xiaohongshu(html, PAGE, PAGE)
        self.assertIn("# undefined", result)
        self.assertIn("笔记图片（2 张）", result)
        self.assertLess(result.index("1.jpg"), result.index("2.jpg"))
        self.assertNotIn("thumb.jpg", result)
        self.assertNotIn("javascript:", result)
        self.assertNotIn("http://", result)

    def test_desktop_image_only_note(self):
        html = page({"noteId": NOTE_ID, "imageList": [
            {"urlDefault": "https://cdn.example/full.jpg"}]}, desktop=True)
        self.assertIn("full.jpg", reader._parse_xiaohongshu(html, PAGE, PAGE))

    def test_wrong_note_and_login_are_rejected(self):
        for html in ("<html>登录</html>", page({"noteId": "other", "desc": "推荐笔记"})):
            with self.assertRaises(ValueError):
                reader._parse_xiaohongshu(html, PAGE, PAGE)


class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_warns_about_missing_images(self):
        with patch.object(reader.httpx.AsyncClient, "get", AsyncMock(
            side_effect=httpx.ConnectError("offline"))), patch.object(
                reader, "_fetch_jina", AsyncMock(return_value="正文")):
            result = await reader._fetch_xiaohongshu(PAGE)
        self.assertIn("正文", result)
        self.assertIn("图片未能完整提取", result)

    async def test_domain_route_does_not_match_query_parameters(self):
        handler = AsyncMock(return_value="images")
        handler.__name__ = "xiaohongshu_test"
        pattern = reader._ROUTE_TABLE[0][0]
        with patch.object(reader, "_ROUTE_TABLE", [(pattern, handler)]), patch.object(
            reader, "_fetch_jina", AsyncMock(return_value="generic")):
            for host in ("xhslink.cn", "xhslink.com", "www.xiaohongshu.com"):
                self.assertEqual(await reader.fetch_url_as_markdown("https://" + host + "/a"), "images")
            for url in ("https://example.com/?u=xhslink.cn", "https://evilxhslink.cn/a"):
                self.assertEqual(await reader.fetch_url_as_markdown(url), "generic")


if __name__ == "__main__":
    unittest.main()
