"""Archive inline Markdown images next to Raw notes before saving references."""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit, urljoin

import httpx

from app.config import settings
from app.parsers.url_reader import FetchError
from app.vault.collection import root

IMAGE = re.compile(r'!\[[^\]\n]*\]\(\s*(?:<(?P<angle>https?://[^>]+)>|(?P<plain>https?://[^\s)]+))(?:\s+["\'][^\n]*?["\'])?\s*\)')
MAX_IMAGE = 20 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024


def image_urls(text):
    return list(dict.fromkeys(m.group('angle') or m.group('plain') for m in IMAGE.finditer(text)))


def _extension(data):
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data[:6] in (b'GIF87a', b'GIF89a'): return '.gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return '.webp'
    if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'): return '.avif'
    raise ValueError('unsupported_image')


async def _public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username:
        raise ValueError('invalid_image_url')
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('private_image_url')


async def download_images(text, source):
    """All downloads finish before writing any vault files; failures are retryable."""
    urls = image_urls(text)
    if not urls: return {}
    if len(urls) > 100: raise ValueError('too_many_images')
    result = {}; total = 0
    headers = {'User-Agent': 'Mozilla/5.0'}
    if source.startswith(('https://', 'http://')):
        host = urlsplit(source).hostname or ''
        # XHS CDN rejects its own short-link host as Referer.
        if host in ('xhslink.cn', 'xhslink.com') or host.endswith('.xiaohongshu.com') or host == 'xiaohongshu.com':
            headers['Referer'] = 'https://www.xiaohongshu.com/'
        else:
            headers['Referer'] = str(httpx.URL(source))
    try:
        async with httpx.AsyncClient(timeout=30, proxy=settings.http_proxy or None) as client:
            for original in urls:
                url = original
                for redirect in range(6):
                    await _public_url(url)
                    async with client.stream('GET', url, headers=headers) as response:
                        if response.is_redirect:
                            url = urljoin(url, response.headers['location'])
                            continue
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk); total += len(chunk)
                            if len(data) > MAX_IMAGE or total > MAX_TOTAL:
                                raise ValueError('image_size_limit')
                        payload = bytes(data)
                        result[original] = (payload, _extension(payload))
                        break
                else:
                    raise ValueError('too_many_image_redirects')
        return result
    except (httpx.HTTPError, ValueError, OSError, KeyError) as exc:
        raise FetchError('image_archive_failed', '图片下载失败，原始消息已保留；重试时会重新获取页面和图片链接。') from exc


def save_images(text, note_path, downloads):
    """Called under vault write gate. Content hashes deduplicate image bytes."""
    folder = Path(note_path).parent / '_assets'
    replacements = {}; paths = []
    for url, (payload, suffix) in downloads.items():
        rel = folder / (hashlib.sha256(payload).hexdigest() + suffix)
        target = root() / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.tmp')
            temporary.write_bytes(payload)
            os.replace(temporary, target)
        replacements[url] = '_assets/' + target.name
        paths.append(str(rel))
    # Also localize the adjacent explicit links emitted by the XHS reader.
    for url in sorted(replacements, key=len, reverse=True):
        text = text.replace('(<'+url+'>)', '(<'+replacements[url]+'>)')
    def replace(match):
        url = match.group('angle') or match.group('plain')
        return match.group().replace(url, replacements[url], 1) if url in replacements else match.group()
    return IMAGE.sub(replace, text), list(dict.fromkeys(paths))
