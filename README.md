# Knowledge Bot

飞书收集和查询，Obsidian 阅读编辑，Markdown + Git 保存同步。

## 默认流程

消息先持久化到服务器收集队列，再保存原始记录、抓取正文、生成 Wiki，最后提交并推送 Git。飞书直接回复预览及真实同步状态，不再创建云盘文档。

- `Raw/`：原始消息及抓取正文，模型失败时也保留。
- `Wiki/`：普通知识笔记，不再强制拆分 entity/concept；既有人工修改不被生成流程覆盖。
- `_archive/`：历史问答、旧导航。保留文件与历史，不参与默认查询。
- `STATE_PATH`：SQLite 队列、解析缓存和原始上传文件，位于知识库之外，不同步到手机。

## 命令

直接发送链接、文字或附件即可收藏；链接可附备注。

| 命令 | 行为 |
|---|---|
| `/查 问题` | 搜索 Raw 和 Wiki 的相关片段并回答，不生成新文件 |
| `/保存` | 将本会话最近一次有来源的回答保存为 Wiki |
| `/保存 任务编号` | 保存本会话指定查询回答 |
| `/重试 [任务编号]` | 重试本会话失败任务，默认最近一条 |
| `/状态 [任务编号]` | 查看任务状态，默认最近一条 |

删除与归档在 Obsidian 中完成。旧 `/del`、`/archive`、`/skill`、`/lint` 不再作为机器人入口；历史笔记不会因此被删除。

## 配置与运行

Python 3.10+；`pip install -r requirements.txt`。

配置优先级：进程环境变量 > `.env` > `envs/.env.secrets` > `envs/{APP_ENV}.env`。

- `VAULT_PATH`：Git 工作副本。
- `STATE_PATH`：队列目录，默认 `/opt/knowledge-bot-state`，必须位于 Vault 之外。
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：应用认证。
- `FEISHU_VERIFICATION_TOKEN`：配置后校验回调 token；未配置时会在启动日志警告。不要把回调入口视为已验证来源。
- `FEISHU_ALLOWED_OPEN_IDS`：可选，允许的发送者 open_id，用逗号分隔。
- `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `DASHSCOPE_MODEL_COMPILE` / `DASHSCOPE_MODEL_QUERY`：模型配置。
- `MAX_JOB_ATTEMPTS`：处理失败最大自动尝试次数，默认 3；之后可手动重试。

运行：`APP_ENV=ecs uvicorn app.main:app --host 127.0.0.1 --port 8000`。当前设计为单进程单 worker，锁文件阻止多个进程同时消费同一队列。后台任务恢复依赖持久化 STATE_PATH，不能放在临时目录。

## 验证与迁移

离线测试：`python -m unittest scripts.tests.test_simplified -v`。测试使用临时 Vault、临时 SQLite 和本机 bare Git，不调用模型、网页或飞书。

迁移旧笔记：先停止机器人，确认 Git 已同步且无未提交修改，再运行：

```bash
python scripts/migrate_collection.py --vault /opt/vault --backup /opt/knowledge-bot-migration-backup
# 核对统计后加 --apply。备份目录必须在库外且尚不存在。
```

迁移保留正文，扁平化旧 Wiki 分类，修复相对链接，归档旧问答与 index/log/SCHEMA。不会重新调用模型，不会删除原始来源。恢复时先停服务，用备份恢复对应版本的工作副本及程序；若已有新提交，需先保全新数据，禁止盲目强推。

分类由库根目录 `分类规则.md` 管理，新内容自动归类；规则修改经 Git 同步后生效。新 Wiki 文件名为可读标题，Raw 按收藏年月存放。历史目录不随规则变更自动移动。
