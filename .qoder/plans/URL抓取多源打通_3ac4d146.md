# URL 抓取多源打通

## 现状分析

当前 `app/parsers/url_reader.py` 只有 Jina Reader 一条路径（19 行），所有 URL 无差别走 `https://r.jina.ai/`。问题：
- 微信公众号：触发人机验证，存入"环境异常"垃圾页面
- 视频链接（YouTube/B站）：Jina Reader 只能拿到页面 HTML，拿不到字幕/内容
- 推特/X：国内网络限制 + 反爬，Jina Reader 大概率失败
- 无质量检测：抓到验证页/空页面也照样走 LLM 编译 + 存入 Vault

## Task 1: 重构 url_reader.py — 域名路由 + 质量检测

将 `app/parsers/url_reader.py` 从单一 Jina Reader 改为**多策略路由器**：

```python
# 路由表（按域名匹配）
ROUTE_TABLE = [
    (r"mp\.weixin\.qq\.com",        _fetch_wechat),
    (r"(youtube\.com|youtu\.be)",    _fetch_video_subtitle),
    (r"(bilibili\.com|b23\.tv)",     _fetch_video_subtitle),
    (r"(x\.com|twitter\.com)",       _fetch_twitter),
    (r".*",                          _fetch_jina),     # 兜底
]
```

每个策略函数返回 markdown 文本，失败抛 `FetchError(reason, hint)`。

新增 `_check_quality(text)` 函数：检测返回内容是否含 CAPTCHA/验证/空白等标志词，不合格时抛异常而非静默写入 Vault。

涉及文件：`app/parsers/url_reader.py`（重写）

## Task 2: yt-dlp 集成 — 视频字幕提取

安装 `yt-dlp`（pip 包），新增 `_fetch_video_subtitle()` 策略：

```python
async def _fetch_video_subtitle(url: str) -> str:
    # yt-dlp --write-auto-subs --skip-download --sub-lang zh,en --print-to-file subtitle
    # 支持 YouTube / B站 / 1800+ 站点
```

- 优先取中文字幕，fallback 英文自动字幕
- 同时提取视频标题、时长、描述作为上下文
- 需要代理时走 `--proxy http://127.0.0.1:7890`
- 新增依赖：`requirements.txt` 加 `yt-dlp`

涉及文件：`app/parsers/url_reader.py`、`requirements.txt`

## Task 3: 微信公众号 — 前置拦截 + 降级提示

`_fetch_wechat()` 策略：

```python
async def _fetch_wechat(url: str) -> str:
    # 方案 A: 先尝试 Jina Reader（极少数文章能通过）
    # 方案 B: 若检测到 CAPTCHA → 抛 FetchError:
    #   "微信公众号反爬限制，请复制文章正文，以文本方式重新发送"
```

这是已知无法自动化的域名（文章里也说"Agent Reach 管不到"），给出清晰的降级指引比静默存垃圾好得多。

涉及文件：`app/parsers/url_reader.py`

## Task 4: Twitter/X — Jina Reader 尝试 + 降级

推特抓取目前没有免费稳定的 Python 方案（xreach 是 Node.js CLI，需要 cookie 配置）。一期策略：

```python
async def _fetch_twitter(url: str) -> str:
    # 1. 先尝试 Jina Reader（部分推文能抓到）
    # 2. 质量检测：若内容为空/登录页 → 抛 FetchError:
    #   "X/Twitter 内容抓取受限，请复制推文正文以文本方式发送"
```

todo.md M11 已规划 xreach 集成，此处先做好路由占位 + 降级提示。

涉及文件：`app/parsers/url_reader.py`

## Task 5: 错误传递 — ingest 层感知抓取失败

当前 `ingest.py` 对 `parse_any()` 的异常只有通用 catch。需要让抓取失败的**友好提示**能传递到飞书回复：

- 新增 `FetchError` 异常类（含 `reason` + `user_hint` 字段）
- `ingest()` 捕获 `FetchError` 时，用 `user_hint` 回复用户，而非笼统的"整理失败"
- `dispatcher.py` 的 `_handle_message` 里也同步处理

涉及文件：`app/parsers/url_reader.py`（定义异常）、`app/handlers/ingest.py`、`app/handlers/dispatcher.py`

## Task 6: 文档 + 测试同步

- `docs/todo.md`：优化项"抓取降级逻辑"标完成，M11 更新说明一期已做的占位
- `.env.example`：如需新增环境变量（如 `HTTP_PROXY`）同步更新
- 跑 `scripts/test_url_ingest.py` 验证各类 URL：
  - 普通网页（sspai.com 等）
  - 微信公众号 → 预期拿到友好提示
  - YouTube 链接 → 预期拿到字幕
  - Twitter 链接 → 预期 Jina 尝试 + 降级提示

涉及文件：`docs/todo.md`、`.env.example`、`scripts/test_url_ingest.py`
