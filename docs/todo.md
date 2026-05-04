# 待办

> 方法论：[llm-wiki-method.md](llm-wiki-method.md) · 运行契约：ECS `/opt/vault/SCHEMA.md`（参考 [vault-seed/schema-template.md](vault-seed/schema-template.md)）

一期 LLM Wiki 重构已全部交付✅：`compile.py` 分路 / `writer.py` 新 frontmatter / `indexer.py` 自动维护 / `lint.py` + `/lint` / `/archive` + `/del` / `/skill` 沉淀。

## 二期

- [ ] **M4** PDF / PPT / Excel / Word / 图片 OCR（markitdown + `im:resource` 权限）
- [ ] **M6** Wiki 双向链接 `[[wikilink]]`
- [ ] **M8** 多模态智能路由（按场景选模，让预留的模型变量生效）

## 三期

- [ ] **M11** RSS / Reddit / Exa 语义搜索
- [ ] **M12** 飞书周报（基于 log.md 自动汇总）

## 优化项

- [ ] 检索关键词抽取（当前 `/查` 把整句当 keyword，命中率低）
- [ ] `/查` 回填 “保留 / 丢弃” 飞书按钮（当前默认异步保留，无 UI 开关）
