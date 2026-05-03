"""URL 抓取：按域名路由到最佳策略，带质量检测。

策略路由表：
  mp.weixin.qq.com       → 内置 HTTP + BeautifulSoup（微信反爬需模拟浏览器 UA）
  youtube / youtu.be     → yt-dlp（字幕提取）
  bilibili / b23.tv      → yt-dlp（字幕提取）
  x.com / twitter.com    → Jina Reader 尝试 + 降级提示
  *（兜底）              → Jina Reader
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Awaitable

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from markdownify import markdownify as md

from app.config import settings


# ---------------------------------------------------------------------------
# FetchError — 带用户友好提示的抓取异常
# ---------------------------------------------------------------------------

class FetchError(Exception):
    """URL 抓取失败，携带面向用户的提示。"""

    def __init__(self, reason: str, user_hint: str) -> None:
        self.reason = reason
        self.user_hint = user_hint
        super().__init__(reason)


# ---------------------------------------------------------------------------
# 质量检测
# ---------------------------------------------------------------------------

_BAD_MARKERS = [
    "环境异常",
    "完成验证后即可继续访问",
    "CAPTCHA",
    "请完成安全验证",
    "Access Denied",
    "Just a moment...",          # Cloudflare challenge
    "Enable JavaScript and cookies",
]

_MIN_CONTENT_LENGTH = 80  # 有效内容最低字符数


def _check_quality(text: str, url: str) -> None:
    """检测抓取内容质量，不合格直接抛 FetchError。"""
    stripped = text.strip()
    if len(stripped) < _MIN_CONTENT_LENGTH:
        raise FetchError(
            reason=f"内容过短（{len(stripped)} 字符）",
            user_hint="抓取到的内容几乎为空，可能被反爬拦截。请复制正文以文本方式重新发送。",
        )
    for marker in _BAD_MARKERS:
        if marker.lower() in stripped.lower():
            raise FetchError(
                reason=f"检测到反爬标志: {marker}",
                user_hint="该页面触发了反爬验证，无法自动抓取。请复制正文以文本方式重新发送。",
            )


# ---------------------------------------------------------------------------
# 策略：Jina Reader（通用网页）
# ---------------------------------------------------------------------------

JINA_READER = "https://r.jina.ai/"


def _httpx_proxy() -> str | None:
    """返回 httpx 代理地址，未配置则 None。"""
    return settings.http_proxy or None


async def _fetch_jina(url: str) -> str:
    """通用网页抓取：Jina AI Reader。"""
    target = JINA_READER + url
    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, proxy=_httpx_proxy(),
        ) as client:
            r = await client.get(target, headers={"Accept": "text/plain"})
    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
        raise FetchError(
            reason=f"Jina Reader 网络异常: {type(exc).__name__}",
            user_hint="网页抓取服务连接超时（可能是网络限制）。请复制正文以文本方式发送。",
        ) from exc
    if r.status_code != 200:
        raise FetchError(
            reason=f"Jina Reader HTTP {r.status_code}",
            user_hint=f"网页抓取失败（HTTP {r.status_code}）。请检查链接是否可访问，或复制正文以文本方式发送。",
        )
    _check_quality(r.text, url)
    return r.text


# ---------------------------------------------------------------------------
# 策略：微信公众号（内置 HTTP + BeautifulSoup，参考 url-md weixin 适配器）
# ---------------------------------------------------------------------------

_WECHAT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def _fetch_wechat(url: str) -> str:
    """微信公众号抓取：httpx + BeautifulSoup + markdownify。

    核心逻辑参考 url-md (Rust) weixin adapter：
    1. 带桌面 UA 请求页面 HTML（永久链 /s/* 不需要 JS 渲染）
    2. 解析 #js_content 提取正文
    3. 恢复图片 data-src → src
    4. 转为 Markdown
    """
    logger.info("微信公众号内置抓取: {}", url)
    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, proxy=_httpx_proxy(),
        ) as client:
            r = await client.get(url, headers=_WECHAT_HEADERS)
    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
        raise FetchError(
            reason=f"微信请求网络异常: {type(exc).__name__}",
            user_hint="微信文章抓取超时，请稍后重试或复制正文以文本方式发送。",
        ) from exc

    if r.status_code != 200:
        raise FetchError(
            reason=f"微信 HTTP {r.status_code}",
            user_hint=f"微信文章请求失败（HTTP {r.status_code}），请复制正文以文本方式发送。",
        )

    html = r.text

    # 检测反爬拦截（页面不含正文容器）
    if 'id="js_content"' not in html:
        raise FetchError(
            reason="未找到 #js_content，可能是反爬拦截页",
            user_hint="微信公众号文章触发了反爬验证，无法自动抓取。\n请复制文章正文，以文本方式重新发送。",
        )

    soup = BeautifulSoup(html, "html.parser")

    # 提取元信息
    title_el = soup.select_one("h1#activity-name")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        og = soup.select_one('meta[property="og:title"]')
        title = og["content"].strip() if og and og.get("content") else "未知标题"

    author_el = soup.select_one("#js_author_name") or soup.select_one("#js_name")
    author = author_el.get_text(strip=True) if author_el else ""

    pub_el = soup.select_one("#publish_time")
    pub_time = pub_el.get_text(strip=True) if pub_el else ""

    # 提取正文 HTML 并恢复图片（微信防盗链用 data-src）
    content_el = soup.select_one("#js_content")
    if not content_el:
        raise FetchError(
            reason="#js_content 为空",
            user_hint="微信文章正文为空，请复制正文以文本方式发送。",
        )

    # data-src → src（微信图片懒加载）
    for img in content_el.find_all("img"):
        data_src = img.get("data-src")
        if data_src and not img.get("src"):
            img["src"] = data_src

    # HTML → Markdown
    body_md = md(
        str(content_el),
        heading_style="ATX",
        strip=["script", "style", "iframe"],
    ).strip()

    # 组装最终 Markdown
    parts = [f"# {title}", ""]
    if author:
        parts.append(f"**作者**: {author}")
    if pub_time:
        parts.append(f"**发布时间**: {pub_time}")
    parts += [f"**来源**: {url}", "", "---", "", body_md]

    result = "\n".join(parts)
    _check_quality(result, url)
    return result


# ---------------------------------------------------------------------------
# 策略：yt-dlp（视频字幕提取）
# ---------------------------------------------------------------------------

async def _fetch_video_subtitle(url: str) -> str:
    """视频字幕提取：yt-dlp（YouTube / B站 / 1800+ 站点）。"""
    yt_dlp_bin = shutil.which("yt-dlp")
    if not yt_dlp_bin:
        raise FetchError(
            reason="yt-dlp 未安装",
            user_hint="视频字幕提取需要 yt-dlp，请运行 pip install yt-dlp 安装。",
        )

    # 第一步：获取视频元数据（标题、描述、时长）
    logger.info("yt-dlp 提取视频信息: {}", url)
    try:
        meta_proc = await asyncio.create_subprocess_exec(
            yt_dlp_bin, "--dump-json", "--no-download",
            "--no-playlist",
            *(["--proxy", settings.http_proxy] if settings.http_proxy else []),
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        meta_out, meta_err = await asyncio.wait_for(meta_proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        raise FetchError(
            reason="yt-dlp 元数据获取超时",
            user_hint="视频信息获取超时，请检查网络或稍后重试。",
        )

    if meta_proc.returncode != 0:
        err = meta_err.decode("utf-8", errors="replace").strip()
        logger.warning("yt-dlp meta 失败: {}", err)
        # fallback 到 Jina Reader
        logger.info("yt-dlp 失败，尝试 Jina Reader fallback")
        return await _fetch_jina(url)

    try:
        meta = json.loads(meta_out.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return await _fetch_jina(url)

    title = meta.get("title", "未知标题")
    duration = meta.get("duration")
    uploader = meta.get("uploader", "")
    description = meta.get("description", "")

    # 第二步：提取字幕
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_path = Path(tmpdir) / "sub"
        try:
            sub_proc = await asyncio.create_subprocess_exec(
                yt_dlp_bin,
                "--write-auto-subs", "--write-subs",
                "--sub-lang", "zh,zh-Hans,zh-CN,en",
                "--sub-format", "vtt/srt/best",
                "--skip-download",
                "--no-playlist",
                *(["--proxy", settings.http_proxy] if settings.http_proxy else []),
                "-o", str(sub_path),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(sub_proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            logger.warning("yt-dlp 字幕提取超时")

        # 查找字幕文件（优先中文）
        subtitle_text = ""
        sub_files = sorted(Path(tmpdir).glob("sub*.*"))
        for pref in ["zh", "zh-Hans", "zh-CN", "en"]:
            for sf in sub_files:
                if pref in sf.name:
                    subtitle_text = sf.read_text(encoding="utf-8", errors="replace")
                    break
            if subtitle_text:
                break
        if not subtitle_text and sub_files:
            subtitle_text = sub_files[0].read_text(encoding="utf-8", errors="replace")

        # 清洗 VTT/SRT 字幕格式为纯文本
        if subtitle_text:
            subtitle_text = _clean_subtitle(subtitle_text)

    # 组装输出
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "未知"
    parts = [
        f"# {title}",
        "",
        f"**来源**: {url}",
        f"**作者**: {uploader}" if uploader else "",
        f"**时长**: {duration_str}",
        "",
    ]
    if description and len(description) < 2000:
        parts += ["## 视频简介", "", description, ""]
    if subtitle_text:
        parts += ["## 字幕内容", "", subtitle_text]
    else:
        parts += ["## 字幕内容", "", "（未找到可用字幕）"]
        if description:
            parts += ["", "---", "", "注：以上为视频描述，字幕不可用。"]

    result = "\n".join(parts)
    if len(result.strip()) < _MIN_CONTENT_LENGTH and not subtitle_text:
        # 没有字幕也没有描述，试试 Jina Reader
        logger.info("yt-dlp 无字幕可用，尝试 Jina Reader fallback")
        return await _fetch_jina(url)
    return result


def _clean_subtitle(raw: str) -> str:
    """清洗 VTT/SRT 字幕为纯文本，去重复行。"""
    lines = raw.splitlines()
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        line = line.strip()
        # 跳过 VTT header / 时间戳 / 序号
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d+$", line):  # SRT 序号
            continue
        if re.match(r"[\d:.,\-> ]+$", line):  # 时间戳行
            continue
        # 去 HTML 标签
        line = re.sub(r"<[^>]+>", "", line)
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# 策略：Twitter/X（Jina Reader 尝试 + 降级）
# ---------------------------------------------------------------------------

async def _fetch_twitter(url: str) -> str:
    """Twitter/X 抓取：先尝试 Jina Reader，失败给降级提示。"""
    try:
        text = await _fetch_jina(url)
        return text
    except FetchError:
        raise FetchError(
            reason="Twitter/X 内容抓取受限",
            user_hint=(
                "X/Twitter 内容抓取受限（反爬 + 网络限制）。\n"
                "请复制推文正文，以文本方式重新发送。"
            ),
        )


# ---------------------------------------------------------------------------
# 域名路由表
# ---------------------------------------------------------------------------

_ROUTE_TABLE: list[tuple[re.Pattern, Callable[[str], Awaitable[str]]]] = [
    (re.compile(r"mp\.weixin\.qq\.com"),                 _fetch_wechat),
    (re.compile(r"(youtube\.com|youtu\.be)"),             _fetch_video_subtitle),
    (re.compile(r"(bilibili\.com|b23\.tv|bili\d+\.cn)"),  _fetch_video_subtitle),
    (re.compile(r"(x\.com|twitter\.com)"),                _fetch_twitter),
]


async def fetch_url_as_markdown(url: str) -> str:
    """按域名路由到最佳抓取策略，带质量检测。"""
    for pattern, handler in _ROUTE_TABLE:
        if pattern.search(url):
            logger.info("URL 路由: {} → {}", url[:80], handler.__name__)
            return await handler(url)
    # 兜底：Jina Reader
    logger.info("URL 路由: {} → _fetch_jina（兜底）", url[:80])
    return await _fetch_jina(url)
