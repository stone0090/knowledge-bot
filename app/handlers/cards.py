"""回复卡片生成。"""
from __future__ import annotations


def build_ingest_card(
    title: str,
    summary: str,
    tags: list[str],
    vault_path: str,
    mirror_url: str | None = None,
) -> dict:
    """投喂成功后的卡片回复。

    - vault_path：写入 ECS Vault 的相对路径（如 Wiki/entities/xxx.md）作为真相源引用。
    - mirror_url：飞书云盘镜像链接，best-effort；缺失时按钮不显示。
    """
    tag_md = " ".join(f"`{t}`" for t in tags) if tags else "-"
    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**摘要**\n{summary}"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**标签**: {tag_md}"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**Vault 路径**\n`{vault_path}`"}},
    ]
    if mirror_url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "打开飞书镜像"},
                    "type": "primary",
                    "url": mirror_url,
                },
            ],
        })
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📥 已收录: {title}"},
            "template": "green",
        },
        "elements": elements,
    }


def build_answer_card(question: str, answer_md: str, vault_path: str | None = None) -> dict:
    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": answer_md}},
    ]
    if vault_path:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"📒 已回填：`{vault_path}`"}}
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🔎 {question[:30]}"},
            "template": "blue",
        },
        "elements": elements,
    }
