import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from app.config import settings
from app.vault import images
from scripts.repair_xhs_images import repair_text

JPEG = b'\xff\xd8\xff' + b'test image'
URL = 'https://cdn.example/image!signed'
TEXT = '正文\n![图片 1](<'+URL+'>)\n[图片 1 链接](<'+URL+'>)'

class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_dedup_validation_and_local_links(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, content=JPEG)
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch.object(images, '_public_url'), patch.object(images.httpx, 'AsyncClient', return_value=client):
            files = await images.download_images(TEXT+'\n'+TEXT, 'https://xhslink.cn/o/example')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers['referer'], 'https://www.xiaohongshu.com/')
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings, 'vault_path', tmp):
            local, paths = images.save_images(TEXT, 'Raw/2026/10/note.md', files)
            self.assertEqual(len(paths), 1)
            self.assertEqual((Path(tmp)/paths[0]).read_bytes(), JPEG)
            self.assertNotIn(URL, local)
            self.assertIn('_assets/', local)
            self.assertEqual(images.save_images(TEXT, 'Raw/2026/10/renamed.md', files), (local, paths))
            repaired = repair_text(TEXT+'\n我的修改', TEXT, local)
            self.assertIn('我的修改', repaired)
            self.assertNotIn(URL, repaired)
            self.assertEqual(repair_text(repaired, TEXT, local), repaired)

    async def test_html_403_and_oversize_fail_before_any_vault_write(self):
        for status, content, size in [(403, b'Forbidden', 100), (200, b'<html>login', 100), (200, JPEG, 2)]:
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, content=content)))
            with patch.object(images, '_public_url'), patch.object(images.httpx, 'AsyncClient', return_value=client), patch.object(images, 'MAX_IMAGE', size):
                with self.assertRaises(images.FetchError): await images.download_images(TEXT, 'https://example.com')

    async def test_redirect_destination_is_validated(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(302, headers={'location':'http://127.0.0.1/private'})))
        with patch.object(images, '_public_url', side_effect=[None, ValueError('private')]), patch.object(images.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(images.FetchError): await images.download_images(TEXT, 'https://example.com')

    def test_plain_and_titled_markdown_and_local_skipping(self):
        self.assertEqual(images.image_urls('![a](https://cdn.example/a.png "title") ![local](_assets/a.png)'), ['https://cdn.example/a.png'])

if __name__ == '__main__': unittest.main()
