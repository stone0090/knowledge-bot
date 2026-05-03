---
name: add-url-source
description: Standard workflow for adding a new URL fetch source (e.g. RSS, Reddit, 小红书) to knowledge-bot. Covers anti-crawl research, fetcher implementation in url_reader.py, route registration, local testing, ECS deployment, and cross-doc updates. Use when the user asks to support a new website/platform for URL ingestion.
---

# 新增 URL 抓取源

为 knowledge-bot 添加新的 URL 内容源的标准化交付流程。已按此流程交付：微信公众号、yt-dlp 视频、Twitter/X。

## 工作流（六步）

### 1. 调研：目标平台反爬与可用工具

动手写代码前先搞清楚三件事：

| 问题 | 方法 |
|------|------|
| 目标页面是否需要 JS 渲染？ | `curl -s <url> | head -100` 看 HTML 里有没有正文 |
| 有没有现成轮子？ | 搜 PyPI / GitHub（优先纯 Python 库，避免二进制依赖） |
| ECS CentOS 7.6 能跑吗？ | 注意 glibc 2.17 限制（url-md 踩过此坑），优先 pip 安装或纯 Python |

**决策优先级**：纯 Python 实现 > pip 包 > 系统二进制 > Playwright（太重，最后兜底）

### 2. 实现 fetcher 函数

在 `app/parsers/url_reader.py` 中新增一个 `async def _fetch_xxx(url: str) -> str` 函数。

**必须遵循的模式**（参考 `_fetch_wechat` / `_fetch_video_subtitle`）：

```python
async def _fetch_xxx(url: str) -> str:
    """一句话说明抓什么、用什么技术。"""
    logger.info("XXX 抓取: {}", url)
    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, proxy=_httpx_proxy(),
        ) as client:
            r = await client.get(url, headers=_XXX_HEADERS)
    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
        raise FetchError(
            reason=f"XXX 网络异常: {type(exc).__name__}",
            user_hint="XXX 抓取超时，请复制正文以文本方式发送。",
        ) from exc

    # ... 解析逻辑 ...

    _check_quality(result, url)   # ← 必须调用质量检测
    return result
```

**关键约束**：
- 用 `httpx.AsyncClient`（项目已有依赖），**带 `proxy=_httpx_proxy()`**
- 异常统一抛 `FetchError(reason=..., user_hint=...)`，`user_hint` 是给飞书用户看的中文提示
- 结尾必须调 `_check_quality()` 做内容质量兜底
- 新增 pip 依赖写入 `requirements.txt`

### 3. 注册域名路由

在文件底部的 `_ROUTE_TABLE` 列表中添加一条：

```python
_ROUTE_TABLE: list[tuple[re.Pattern, Callable[[str], Awaitable[str]]]] = [
    (re.compile(r"mp\.weixin\.qq\.com"),                 _fetch_wechat),
    (re.compile(r"(youtube\.com|youtu\.be)"),             _fetch_video_subtitle),
    (re.compile(r"(bilibili\.com|b23\.tv|bili\d+\.cn)"),  _fetch_video_subtitle),
    (re.compile(r"(x\.com|twitter\.com)"),                _fetch_twitter),
    # ↑ 已有路由
    (re.compile(r"新域名正则"),                            _fetch_xxx),  # 新增
]
```

**注意**：路由按顺序匹配，第一个命中即停止。专用路由放前面，通用兜底 `_fetch_jina` 在函数末尾。

### 4. 本地测试

用已有的测试脚本模式验证：

```bash
# 在项目根目录
python -c "
import asyncio
from app.parsers.url_reader import fetch_url_as_markdown

async def main():
    text = await fetch_url_as_markdown('https://目标URL')
    print(f'长度: {len(text)} 字符')
    print(text[:500])

asyncio.run(main())
"
```

检查项：
- [ ] 正文提取完整（非空、非反爬页面）
- [ ] 标题 / 作者 / 来源等元信息正确
- [ ] `_check_quality` 未误报
- [ ] 不存在的 URL 或反爬页面能抛出友好 `FetchError`

### 5. 部署到 ECS

```bash
bash scripts/deploy/deploy_to_ecs.sh update
```

部署后在飞书里实际发一条目标 URL 做冒烟测试。

### 6. 更新文档（三处必改）

| 文档 | 改什么 |
|------|--------|
| `docs/architecture.md` | 抓取分层表新增一行（工具 / 覆盖 / 状态） |
| `README.md` §技术栈 | 技术栈表新增一行 |
| `docs/todo.md` | M11 里程碑更新进度 |

如有新 pip 依赖，还需同步 `requirements.txt` 和 `docs/setup.md`（如有安装说明）。

## 反模式

- ❌ 依赖无 Linux 预编译的二进制工具（ECS 是 CentOS 7.6，glibc 2.17）
- ❌ 忘记 `proxy=_httpx_proxy()`（ECS 访问海外服务需要代理）
- ❌ `user_hint` 写英文或技术术语（用户是飞书聊天场景，要中文友好提示）
- ❌ 不调 `_check_quality()`（空内容 / 反爬页面会静默返回垃圾）
- ❌ 改了代码不更新文档（至少三处：architecture / README / todo）
