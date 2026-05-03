"""YAML Frontmatter 极简读写（避免引入 PyYAML 依赖）。

只支持当前项目实际用到的字段类型：字符串、字符串数组、整数、ISO 日期时间。
不支持嵌套对象、多行字符串、复杂 YAML 特性。
"""
from __future__ import annotations

from typing import Any

_DELIM = "---"


def _escape_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # 需要加引号：含冒号 / 井号 / 以特殊字符开头
    needs_quote = (
        ":" in s
        or "#" in s
        or s.startswith(("-", "?", "!", "&", "*", "[", "{", "|", ">"))
        or s.strip() != s
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _unescape_scalar(s: str) -> Any:
    s = s.strip()
    if not s:
        return ""
    if s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        try:
            return int(s)
        except ValueError:
            return s
    return s


def dump_frontmatter(meta: dict[str, Any]) -> str:
    """把 dict 序列化为 frontmatter 块（含上下 `---` 分隔符，末尾带换行）。"""
    lines = [_DELIM]
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{key}: []")
            else:
                items = ", ".join(_escape_scalar(x) for x in value)
                lines.append(f"{key}: [{items}]")
        else:
            lines.append(f"{key}: {_escape_scalar(value)}")
    lines.append(_DELIM)
    lines.append("")
    return "\n".join(lines)


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """把 md 文件内容拆为 (meta, body)；不存在 frontmatter 则返回 ({}, content)。"""
    if not content.startswith(_DELIM):
        return {}, content
    rest = content[len(_DELIM):].lstrip("\r\n")
    end = rest.find("\n" + _DELIM)
    if end == -1:
        return {}, content
    block = rest[:end]
    body = rest[end + len("\n" + _DELIM):].lstrip("\r\n")
    return parse_frontmatter(block), body


def parse_frontmatter(block: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [_unescape_scalar(x) for x in _split_list(inner)]
        else:
            meta[key] = _unescape_scalar(value)
    return meta


def _split_list(inner: str) -> list[str]:
    """按逗号切分，尊重双引号内的逗号。"""
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in inner:
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
        elif ch == "," and not in_quote:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]
