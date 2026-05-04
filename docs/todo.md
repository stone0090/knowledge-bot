# 待办

> 方法论：[llm-wiki-method.md](llm-wiki-method.md) · 运行契约：ECS `/opt/vault/SCHEMA.md`（参考 [vault-seed/schema-template.md](vault-seed/schema-template.md)）

## 一期剩余（LLM Wiki 重构）

- [ ] **M10** `/查` 结果一键保存到 `Wiki/queries/`（卡片「保存到 Wiki」按钮）
- [ ] **M9a** `compile.py` 按 `type`（entity / concept）分路 System Prompt
- [ ] **M9b** `writer.py` 按 type 分路径 + 新 frontmatter（type/created/updated/sources/confidence/contested）
- [ ] **M9c** `indexer.py` 自动维护 `index.md` / `log.md`（每次 ingest 追加）
- [ ] **M9d** `lint.py` + 飞书 `/lint` 命令（孤儿页、frontmatter 缺失、stale 检测）

## 二期

- [ ] **M4** PDF / PPT / Excel / Word / 图片 OCR（markitdown + `im:resource` 权限）
- [ ] **M6** Wiki 双向链接 `[[wikilink]]`
- [ ] **M8** 多模态智能路由（按场景选模，让预留的模型变量生效）

## 三期

- [ ] **M11** RSS / Reddit / Exa 语义搜索
- [ ] **M12** 飞书周报（基于 log.md 自动汇总）

## 优化项

- [ ] 检索关键词抽取（当前 `/查` 把整句当 keyword，命中率低）
