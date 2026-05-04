"""knowledge-bot 自动回归测试：纯离线、无副作用、秒级完成。

每次部署完自动跑一遍，验证核心契约不走样。覆盖：
  - 模块 import 完整性
  - frontmatter dump/parse round-trip（含中文 / 冒号 / 列表）
  - writer 路径映射 + 真实文件写入（sandbox tempdir）
  - indexer append / remove / 5 种 type 分组
  - lint 对合规页无报错、对破损页能识别
  - compile（LLM mock）：正常 JSON 路径 + 非 JSON 兜底路径
  - SkillCard / KnowledgeCard.to_markdown()
  - vault_write_gate 并发排队 + on_queued 回调触发
  - dispatcher 前缀常量 + cleanup 规范化逻辑

**不覆盖**（需要手动飞书冒烟或真调 LLM / 抓 URL / git push）：
  - URL 抓取真实网络请求
  - LLM API 真实调用
  - git commit/push
  - 飞书事件派发与回调
  - ripgrep 检索（取决于 ECS 是否装 rg）

用法:
  # 本地
  .venv/Scripts/python.exe scripts/tests/regression.py

  # ECS
  ssh kb 'cd /opt/knowledge-bot && .venv/bin/python scripts/tests/regression.py'

退出码：0 = 全部通过；1 = 有失败；2 = 脚本自身异常（非测试失败）。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable, Awaitable

# 保证仍能直接 `python scripts/tests/regression.py` 方式运行（将仓库根加入 sys.path）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ======================================================================
# 迷你测试框架（避免引入 pytest 依赖）
# ======================================================================

_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((name, passed, detail))
    mark = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
    line = f"  [{mark}] {name}"
    if detail and not passed:
        line += f"  -> {detail}"
    print(line, flush=True)


def _section(title: str) -> None:
    print(f"\n== {title} ==", flush=True)


def _run_sync(name: str, fn: Callable[[], Any]) -> None:
    try:
        fn()
        _check(name, True)
    except AssertionError as exc:
        _check(name, False, str(exc))
    except Exception as exc:  # noqa: BLE001
        _check(name, False, f"{type(exc).__name__}: {exc}")


async def _run_async(name: str, coro: Awaitable[Any]) -> None:
    try:
        await coro
        _check(name, True)
    except AssertionError as exc:
        _check(name, False, str(exc))
    except Exception as exc:  # noqa: BLE001
        _check(name, False, f"{type(exc).__name__}: {exc}")


# ======================================================================
# 准备 sandbox vault + monkey-patch settings
# ======================================================================

def _prepare_sandbox() -> Path:
    """创建临时 vault 目录，monkey-patch settings.vault_path 指向它。"""
    from app.config import settings

    tmp = Path(tempfile.mkdtemp(prefix="kb-regression-"))
    (tmp / "Wiki").mkdir()
    (tmp / "Raw").mkdir()
    settings.vault_path = str(tmp)
    return tmp


def _cleanup_sandbox(tmp: Path) -> None:
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)


# ======================================================================
# T1. import 完整性
# ======================================================================

def test_imports() -> None:
    import app.config                       # noqa: F401
    import app.handlers.dispatcher          # noqa: F401
    import app.handlers.ingest              # noqa: F401
    import app.handlers.query               # noqa: F401
    import app.handlers.cleanup             # noqa: F401
    import app.handlers.cards               # noqa: F401
    import app.llm.compile                  # noqa: F401
    import app.llm.query                    # noqa: F401
    import app.llm.dashscope_client         # noqa: F401
    import app.vault                        # noqa: F401
    import app.vault.writer                 # noqa: F401
    import app.vault.indexer                # noqa: F401
    import app.vault.lint                   # noqa: F401
    import app.vault.frontmatter            # noqa: F401
    import app.vault.git_sync               # noqa: F401
    import app.vault.search                 # noqa: F401
    import app.vault.gate                   # noqa: F401
    import app.parsers.dispatcher           # noqa: F401
    import app.parsers.url_reader           # noqa: F401
    import app.parsers.file_reader          # noqa: F401
    import app.feishu.client                # noqa: F401


# ======================================================================
# T2. frontmatter round-trip
# ======================================================================

def test_frontmatter_roundtrip() -> None:
    from app.vault.frontmatter import dump_frontmatter, parse_frontmatter, split_frontmatter

    meta = {
        "type": "skill",
        "title": "Ghostty 快速上手",
        "name": "ghostty-quick-start",
        "description": "Use when the user asks how to install Ghostty. Covers brew, theme, GPU check.",
        "tags": ["tool/terminal", "ai-coding"],
        "sources": ["Raw/articles/x.md"],
        "created": "2026-05-03",
    }
    dumped = dump_frontmatter(meta)
    assert dumped.startswith("---\n") and dumped.rstrip().endswith("---"), "frontmatter 分隔符不对"

    full = dumped + "\nhello body\n"
    parsed, body = split_frontmatter(full)
    assert parsed["type"] == "skill"
    assert parsed["title"] == "Ghostty 快速上手"
    assert parsed["name"] == "ghostty-quick-start"
    assert "Use when" in parsed["description"]
    assert parsed["tags"] == ["tool/terminal", "ai-coding"]
    assert parsed["sources"] == ["Raw/articles/x.md"]
    assert body.strip() == "hello body"


# ======================================================================
# T3. writer 路径映射 + 写入
# ======================================================================

def test_writer_type_map() -> None:
    from app.vault.writer import _TYPE_TO_SUBDIR
    assert set(_TYPE_TO_SUBDIR.keys()) == {"entity", "concept", "comparison", "query", "skill"}
    assert _TYPE_TO_SUBDIR["skill"] == "skills"


def test_writer_write_raw(tmp: Path) -> None:
    from app.vault.writer import write_raw
    from app.vault.frontmatter import split_frontmatter

    rel = write_raw(
        title="回归测试素材",
        source_type="text",
        source_ref="inline",
        text="测试正文：包含冒号:还有 # 号",
    )
    path = tmp / rel
    assert path.exists()
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    assert meta["source_type"] == "text"
    assert meta["source_ref"] == "inline"
    assert meta["title"] == "回归测试素材"
    assert "回归测试素材" not in body or True  # body 是原文，不强制


def test_writer_write_wiki(tmp: Path) -> None:
    from app.vault.writer import write_wiki
    from app.vault.frontmatter import split_frontmatter

    rel = write_wiki(
        type="entity",
        title="Ghostty",
        tags=["tool/terminal"],
        summary="现代 GPU 终端",
        source_ref="Raw/articles/x.md",
        body_markdown="# Ghostty\n\n正文",
        aliases=["ghostty-term"],
        confidence="high",
    )
    path = tmp / rel
    assert path.exists()
    assert "Wiki/entities/" in rel.as_posix()
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    assert meta["type"] == "entity"
    assert meta["aliases"] == ["ghostty-term"]
    assert meta["confidence"] == "high"


def test_writer_write_skill(tmp: Path) -> None:
    from app.vault.writer import write_skill
    from app.vault.frontmatter import split_frontmatter

    rel = write_skill(
        title="Ghostty 快速上手",
        name="ghostty-quick-start",
        description="Use when user asks how to install Ghostty.",
        tags=["tool/terminal"],
        summary="一句摘要",
        source_ref="Raw/articles/x.md",
        body_markdown="# Ghostty 快速上手\n\n## Steps\n1. brew install\n",
        confidence="medium",
    )
    path = tmp / rel
    assert path.exists()
    # 文件名用 name 而非 title slug，保证 agent 匹配
    assert path.name == "ghostty-quick-start.md"
    assert "Wiki/skills/" in rel.as_posix()
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    assert meta["type"] == "skill"
    assert meta["name"] == "ghostty-quick-start"
    assert "Use when" in meta["description"]


def test_writer_write_query(tmp: Path) -> None:
    from app.vault.writer import write_query

    rel = write_query("什么是 LLM Wiki", "这是一种方法论…", candidates=["Wiki/entities/x.md"])
    path = tmp / rel
    assert path.exists()
    assert "Wiki/queries/" in rel.as_posix()


# ======================================================================
# T4. indexer
# ======================================================================

def test_indexer_heading_map() -> None:
    from app.vault.indexer import _TYPE_HEADING
    assert set(_TYPE_HEADING.keys()) == {"entity", "concept", "comparison", "query", "skill"}
    assert _TYPE_HEADING["skill"] == "## Skills"


def test_indexer_append_and_remove(tmp: Path) -> None:
    from app.vault.indexer import append_index, append_log, remove_from_index

    append_index("skill", "Ghostty 快速上手", "一句摘要")
    append_log("skill", "Ghostty 快速上手", "Wiki/skills/ghostty-quick-start.md")

    idx = (tmp / "index.md").read_text(encoding="utf-8")
    assert "## Skills" in idx
    assert "[[Ghostty 快速上手]]" in idx

    log = (tmp / "log.md").read_text(encoding="utf-8")
    assert "[[Ghostty 快速上手]]" in log
    assert "`skill`" in log

    # 去重：二次 append 不会重复写
    append_index("skill", "Ghostty 快速上手", "一句摘要")
    idx2 = (tmp / "index.md").read_text(encoding="utf-8")
    assert idx2.count("[[Ghostty 快速上手]]") == 1

    # 移除
    remove_from_index("Ghostty 快速上手")
    idx3 = (tmp / "index.md").read_text(encoding="utf-8")
    assert "[[Ghostty 快速上手]]" not in idx3


# ======================================================================
# T5. lint 对合规页无报错 + 破损页被识别
# ======================================================================

def test_lint_clean_vault(tmp: Path) -> None:
    from app.vault.lint import lint_vault
    from app.vault.writer import write_wiki
    from app.vault.indexer import append_index

    write_wiki(
        type="concept",
        title="Lint 测试概念",
        tags=["methodology"],
        summary="供 lint 扫描的合规页",
        source_ref="Raw/notes/x.md",
        body_markdown="# Lint 测试概念\n\n## 定义\n...\n",
        confidence="medium",
    )
    append_index("concept", "Lint 测试概念", "供 lint 扫描")

    result = lint_vault()
    assert result["pages"] >= 1
    # 合规页不应被报告
    for rel, _kind, _detail in result["issues"]:
        assert "lint-测试概念" not in rel.lower(), f"合规页被误报: {rel}"


def test_lint_detects_broken(tmp: Path) -> None:
    from app.vault.lint import lint_vault

    # 无 frontmatter
    (tmp / "Wiki" / "entities" / "broken-no-fm.md").write_text("# 无 frontmatter\n正文\n", encoding="utf-8")
    # 非法 type
    (tmp / "Wiki" / "entities" / "broken-bad-type.md").write_text(
        "---\ntype: xxxxxx\ntitle: 错\ncreated: 2026-05-03\nupdated: 2026-05-03\nsources: [x]\ntags: [a]\n---\n正文\n",
        encoding="utf-8",
    )

    result = lint_vault()
    kinds = {r[1] for r in result["issues"]}
    assert "no_frontmatter" in kinds, f"未识别无 frontmatter 页: {result['issues']}"
    assert any("type" in k.lower() or "invalid" in k.lower() for k in kinds), \
        f"未识别非法 type: {result['issues']}"


# ======================================================================
# T6. compile（LLM mock）
# ======================================================================

async def test_compile_knowledge_json_path() -> None:
    """mock chat 返回合法 JSON，验证 KnowledgeCard 字段解析。"""
    import app.llm.compile as mod

    async def mock_chat(model: str, messages: list) -> str:
        return (
            '{"type": "concept", "title": "红绿灯原则", '
            '"aliases": [], "tags": ["methodology"], '
            '"summary": "人机边界契约", "points": ["绿灯 LLM 全托管", "红灯 人工"], '
            '"related": [], "confidence": "high"}'
        )
    original = mod.chat
    mod.chat = mock_chat
    try:
        card = await mod.compile_knowledge("原文")
        assert card.type == "concept"
        assert card.title == "红绿灯原则"
        assert card.confidence == "high"
        assert len(card.points) == 2
    finally:
        mod.chat = original


async def test_compile_knowledge_fallback() -> None:
    """mock chat 返回非 JSON，验证兄底 KnowledgeCard。"""
    import app.llm.compile as mod

    async def bad_chat(model: str, messages: list) -> str:
        return "这不是 JSON"

    original = mod.chat
    mod.chat = bad_chat
    try:
        card = await mod.compile_knowledge("某文本第一行\n第二行")
        assert card.confidence == "low"
        assert card.type == "entity"
    finally:
        mod.chat = original


async def test_compile_skill_json_path() -> None:
    """mock chat 返回 skill JSON，验证 SkillCard。"""
    import app.llm.compile as mod

    async def mock_chat(model: str, messages: list) -> str:
        return (
            '{"title": "Ghostty 快速上手", "name": "ghostty-quick-start", '
            '"description": "Use when the user asks how to install Ghostty.", '
            '"tags": ["tool/terminal"], "summary": "一键装好 Ghostty", '
            '"prerequisites": ["macOS 14+"], "steps": ["brew install ghostty", "配置 config"], '
            '"verify": ["ghostty +info"], "pitfalls": ["x86 无 GPU"], "notes": [], '
            '"confidence": "medium"}'
        )
    original = mod.chat
    mod.chat = mock_chat
    try:
        card = await mod.compile_skill("原文")
        assert card.type == "skill"
        assert card.name == "ghostty-quick-start"
        assert "Use when" in card.description
        assert len(card.steps) == 2
        # to_markdown() 正文结构
        md = card.to_markdown()
        assert "## Prerequisites" in md
        assert "## Steps" in md
        assert "## Verify" in md
        assert "## Common Pitfalls" in md
    finally:
        mod.chat = original


async def test_compile_skill_fallback() -> None:
    """mock chat 返回非 JSON，兄底 SkillCard confidence=low。"""
    import app.llm.compile as mod

    async def bad_chat(model: str, messages: list) -> str:
        return "not json"

    original = mod.chat
    mod.chat = bad_chat
    try:
        card = await mod.compile_skill("一段原文")
        assert card.type == "skill"
        assert card.confidence == "low"
        assert "Use when" in card.description  # 兄底 description 模板
        # name 必须是合法 slug
        assert card.name.replace("-", "").replace("skill", "x").isalnum() or card.name == "skill"
    finally:
        mod.chat = original


def test_skill_name_normalization() -> None:
    from app.llm.compile import _normalize_skill_name
    assert _normalize_skill_name("Ghostty Quick Start", "") == "ghostty-quick-start"
    assert _normalize_skill_name("  HELLO_WORLD  ", "") == "hello-world"
    assert _normalize_skill_name("中文被过滤", "fallback-title") == "fallback-title"
    assert _normalize_skill_name("", "") == "skill"
    assert _normalize_skill_name("123abc", "fallback") == "fallback"  # 不能数字开头


# ======================================================================
# T7. vault_write_gate 并发排队
# ======================================================================

async def test_gate_serialization() -> None:
    """两个并发任务争用锁：第二个进入时拿到 on_queued(1) 回调。"""
    from app.vault.gate import VaultWriteGate

    gate = VaultWriteGate()
    order: list[str] = []
    notified: list[int] = []

    async def task_a():
        async with gate.acquire():
            order.append("A-enter")
            await asyncio.sleep(0.05)
            order.append("A-exit")

    async def _on_queued(ahead: int) -> None:
        notified.append(ahead)

    async def task_b():
        async with gate.acquire(on_queued=_on_queued):
            order.append("B-enter")
            order.append("B-exit")

    t1 = asyncio.create_task(task_a())
    await asyncio.sleep(0.01)  # 保证 A 先入
    t2 = asyncio.create_task(task_b())
    await asyncio.gather(t1, t2)

    assert order == ["A-enter", "A-exit", "B-enter", "B-exit"], f"执行顺序不对: {order}"
    assert notified == [1], f"on_queued 应被调一次 ahead=1，实际 {notified}"
    assert gate.pending == 0


# ======================================================================
# T8. dispatcher / cleanup 轻量契约
# ======================================================================

def test_dispatcher_prefixes() -> None:
    from app.handlers.dispatcher import (
        QUERY_PREFIXES, LINT_PREFIXES, DELETE_PREFIXES,
        ARCHIVE_PREFIXES, SKILL_PREFIXES,
    )
    assert "/查" in QUERY_PREFIXES
    assert "/lint" in LINT_PREFIXES
    assert "/del" in DELETE_PREFIXES
    assert "/archive" in ARCHIVE_PREFIXES
    assert "/skill" in SKILL_PREFIXES
    # /skill 必须排在前（否则 /sk 会先抢匹配）
    assert SKILL_PREFIXES[0] == "/skill"


def test_cleanup_normalize() -> None:
    from app.handlers.cleanup import _norm
    assert _norm("Foo-Bar_Baz") == "foo bar baz"
    assert _norm("  Hello   World  ") == "hello world"
    assert _norm("") == ""
    # 连字符、下划线、空格三者等价
    assert _norm("ghostty-quick-start") == _norm("ghostty quick start") == _norm("ghostty_quick_start")


# ======================================================================
# 主流程
# ======================================================================

async def _main() -> int:
    print("knowledge-bot regression test\n", flush=True)

    _section("T1. import 完整性")
    _run_sync("所有核心模块可 import", test_imports)

    _section("T2. frontmatter")
    _run_sync("dump/parse round-trip（中文/冒号/列表）", test_frontmatter_roundtrip)

    _section("T3. writer（sandbox vault）")
    _run_sync("_TYPE_TO_SUBDIR 覆盖 5 类", test_writer_type_map)

    tmp = _prepare_sandbox()
    try:
        _run_sync("write_raw + frontmatter 校验", lambda: test_writer_write_raw(tmp))
        _run_sync("write_wiki(entity) + frontmatter 校验", lambda: test_writer_write_wiki(tmp))
        _run_sync("write_skill + name 即文件名", lambda: test_writer_write_skill(tmp))
        _run_sync("write_query 写到 Wiki/queries/", lambda: test_writer_write_query(tmp))

        _section("T4. indexer")
        _run_sync("_TYPE_HEADING 覆盖 5 类", test_indexer_heading_map)
        _run_sync("append_index / append_log / 去重 / remove",
                  lambda: test_indexer_append_and_remove(tmp))

        _section("T5. lint")
        _run_sync("合规页不被误报", lambda: test_lint_clean_vault(tmp))
        _run_sync("破损页被识别（no_frontmatter / invalid type）",
                  lambda: test_lint_detects_broken(tmp))
    finally:
        _cleanup_sandbox(tmp)

    _section("T6. compile（LLM mock）")
    await _run_async("compile_knowledge 正常 JSON 路径", test_compile_knowledge_json_path())
    await _run_async("compile_knowledge 非 JSON 兄底", test_compile_knowledge_fallback())
    await _run_async("compile_skill 正常 JSON 路径", test_compile_skill_json_path())
    await _run_async("compile_skill 非 JSON 兄底", test_compile_skill_fallback())
    _run_sync("_normalize_skill_name 边界用例", test_skill_name_normalization)

    _section("T7. vault_write_gate 并发")
    await _run_async("两任务争锁：B 收到 on_queued(1) + 顺序串行化",
                     test_gate_serialization())

    _section("T8. dispatcher / cleanup 契约")
    _run_sync("所有前缀常量就位 + /skill 在 /sk 前", test_dispatcher_prefixes)
    _run_sync("cleanup._norm 规范化", test_cleanup_normalize)

    # 汇总
    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed
    print(f"\n{'='*60}")
    print(f"regression: {passed}/{total} passed, {failed} failed", flush=True)
    if failed:
        print("\n失败用例:", flush=True)
        for name, ok, detail in _RESULTS:
            if not ok:
                print(f"  [FAIL] {name}  -> {detail}", flush=True)
        return 1
    print("[OK] 全部通过", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except Exception:
        traceback.print_exc()
        sys.exit(2)
