# 待办清单（TODO）

> 所有"已规划但还没写进代码"的事项集中在此。文档里不再分散用 🚧 / TODO 标记，统一回链到本文件。

## 一、代码 / 里程碑

### 存储层迁移（M13 / M14 / M15 / M16）· 优先级最高

本组为「飞书主存储 → ECS Vault 主存储 + 飞书只读镜像」的架构升级，需在 M9 编译器 MVP 之前落地（否则 M9 会继续写飞书，给後续增加迁移成本）。技术方案见 [技术方案.md §二](技术方案.md)。

- [ ] **M15 收尾** 飞书开放平台删掉 `bitable:app` 权限（代码已完成，仅差权限清理）
- [ ] **M16** 移动端 Obsidian 接入验证
  - 桌面 Obsidian + `obsidian-git` 插件 clone `kb:/opt/vault-bare.git`（或完整 `ssh://root@121.196.26.127:4500/opt/vault-bare.git`）读写
  - iOS Working Copy + Obsidian / Android MGit + Obsidian 实际跨端写入验证
  - 冲突规则文档化：LLM 只写 `Wiki/`、人工笔记只入 `Raw/notes/` 和 `notes/`（新建目录）

### 一期剩余（M9 / M10 / M16）

- [ ] **M16** 移动端 Obsidian 接入验证
- [ ] **M9** `SCHEMA.md` 编译器 MVP
  - 在 `/opt/vault/SCHEMA.md` 落人机契约（随 M13 一起初始化）
  - 改 [`app/llm/compile.py`](../app/llm/compile.py) 的 prompt，按 SCHEMA 输出“实体 / 概念”两类页
  - 改 [`app/handlers/ingest.py`](../app/handlers/ingest.py) 的 `_write_wiki`：在 M13 落地后改为写 `/opt/vault/Wiki/*/页名.md`不再写飞书（镜像走 M14）
  - 追加 `/opt/vault/Wiki/index.md` 与 `/opt/vault/Wiki/log.md` 条目
- [ ] **M10** `/查` 结果回填 `/opt/vault/Wiki/queries/`
  - 卡片加「保存到 Wiki」按钮
  - 命中该按钮时将 Q&A 写入 `/opt/vault/Wiki/queries/YYYYMMDD-{slug}.md`，触发 git push + 飞书镜像

### 二期（M4 / M6 / M8）

- [ ] **M4** PDF / PPT / Excel / Word / 图片 OCR
  - 启用 `requirements-phase2.txt`（`markitdown`）
  - 放开飞书权限 `im:resource`
- [ ] **M6** Wiki 子目录拆分 + 双向链接
  - 物理目录：`/opt/vault/Wiki/{entities,concepts,comparisons,queries}/`（M13 初始化时已预建，本里程碑专注「编译器将正确分发」）
  - 页面互链用 `[[wikilink]]`
- [ ] **M8** 多模态智能路由接入
  - 在 `app/llm/` 下新增 `router.py`，按 `ParsedContent.source_type` + 后缀 + 字数打分选模
  - 让 `DASHSCOPE_MODEL_COMPILE_{TEXT|LONG|VISION|CODE|DEEP}` 与 `DASHSCOPE_MODEL_QUERY_{FAST|DEEP|LONG|VISION}` 真正生效

### 一期已落地的多源抓取（M11 部分）

- [x] 视频字幕：`yt-dlp`（YouTube / B站）已集成到 url_reader.py
- [x] 微信公众号：内置 Python 实现（httpx + BeautifulSoup + markdownify），模拟 UA 拦截反爬
- [x] Twitter/X：Jina Reader 尝试 + 友好降级提示

### 三期待做（M11 剩余 / M12）

- [ ] **M11（剩余）** 多源抓取扩展
  - 待做：RSS 订阅抓取
  - 待做：Reddit / Exa 全网语义搜索（需代理）
- [ ] **M12** Wiki lint + 周报
  - 扫"矛盾 / 过时 / 孤儿页 / 索引缺口"四类
  - APScheduler 周期触发 → 飞书周报卡片推送

## 二、优化项（未排期，随手可做）

- [ ] **检索关键词抽取**：当前 `/查` 把整句当 keyword 走 ripgrep，自然问题命中率低。下一步做 LLM 关键词抽取后再扫 vault。
- [x] **抓取降级逻辑**（已落地）：url_reader.py 重构为域名路由 + 质量检测 + FetchError 友好提示；微信公众号内置 Python 实现、视频 yt-dlp、Twitter Jina+降级、通用 Jina Reader 兜底
- [x] **环境变量统一清理**（已随 M13/M14/M15 落地）：config.py / .env.example / .env 已同步

## 三、测试 / 运维

- [ ] 手造 `im.message.receive_v1` 事件 POST `/feishu/event`，验证整条 webhook 路由（已在 [feishu-setup.md §5.1](feishu-setup.md) 标注）
- [ ] PDF 文件投喂压测（二期启动后再做）
- [ ] `.env` 迁到阿里云 KMS / 参数仓储（上 ECS 之后）

## 四、文档维护约定

- 本文件作为**单一待办源**，其它文档遇到"未做"的事只写一句"详见 [todo.md](todo.md)"，避免散落
- 完成一项就把该项整行挪到本文件末尾的「已完成归档」区（带完成日期）
- 每新增一条外部参考，同步更新 [外部参考/外部参考目录.md](外部参考/外部参考目录.md) 的"被引用于"列

## 已完成归档

- [x] 2026-05-03 · **M7** ECS 部署：`deploy_to_ecs.sh` 一键部署 + Nginx HTTPS 9443 + acme.sh ZeroSSL 证书 + 飞书事件回调验证通过 + mihomo 代理 + 多环境配置拆分（local.env / ecs.env / .env.secrets）
- [x] 2026-05-03 · **M11（部分）** URL 多源抓取：微信公众号内置 Python 实现（httpx + BeautifulSoup）、yt-dlp 视频字幕、Twitter Jina+降级、域名路由 + FetchError 统一异常
- [x] 2026-05-03 · **M14** 飞书角色降级为只读镜像：`_mirror_to_feishu` best-effort 写 docx 到「知识库-镜像」目录（`FEISHU_MIRROR_FOLDER_TOKEN`），失败仅告警不阻断；端到端验证 docx 出现在飞书云盘 ✅
- [x] 2026-05-03 · **M15** 索引表下线：`query.py` 改为 ripgrep 本地扫 `Wiki/**/*.md`（`app/vault/search.py`），Python fallback 兜底；删 `client.py` 的 bitable_* 方法；退休 `FEISHU_BITABLE_*` 环境变量；端到端 `/查 知识库架构` 验证 ✅
- [x] 2026-05-03 · **M13** Vault 初始化 + Git 中央仓库：ECS 一键脚本 [`scripts/deploy/ecs_bootstrap_vault.sh`](../scripts/deploy/ecs_bootstrap_vault.sh) 走通 bare 初始化（适配 CentOS 7.6 + git 1.8.3.1 + ripgrep musl 静态包）；SSH 免密 [`scripts/deploy/setup_ssh_keyless.sh`](../scripts/deploy/setup_ssh_keyless.sh) 配好别名 `kb`；新增 `app/vault/{frontmatter,writer,git_sync,search}.py`，ingest.py 流程重写为 vault为主 + 飞书镜像兑底，.env.example 同步更新
- [x] 2026-05-03 · 一期文档分期（README / 技术方案 / feishu-setup 同步到“URL + 文本”口径，markitdown 拆到 `requirements-phase2.txt`）
- [x] 2026-05-03 · 外部参考体系：落地 [01-知识库构建.md](外部参考/01-知识库构建.md) 与 [02-URL读取工具.md](外部参考/02-URL读取工具.md)；技术方案升级为 LLM Wiki 三层架构 + URL 抓取五层策略
- [x] 2026-05-03 · DashScope 接入改走 OpenAI 兼容协议（适配 `sk-sp-` 应用空间 key）
- [x] 2026-05-03 · 存储层架构升级决策：**飞书主存储 → ECS Vault 主存储 + 飞书仅做只读镜像（Wiki 编译产物）**，仓库直接用 ECS 自建 bare，不经 GitHub / Gitee；索引表换为 md frontmatter + ripgrep（展开为 M13/M14/M15/M16 四个里程碑）
