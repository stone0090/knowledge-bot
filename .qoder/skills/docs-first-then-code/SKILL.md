---
name: docs-first-then-code
description: Before touching any code that affects architecture, interfaces, dependencies, configuration, milestones, or cross-module contracts, the agent must first align the project documentation (README / docs/技术方案.md / docs/feishu-setup.md / docs/todo.md / docs/外部参考/*) — audit, list concrete issues, edit to consistency — and only then proceed to code changes. Use when the user asks for a feature, refactor, dependency change, phase/milestone adjustment, naming migration, or any task described in vague "also update the design" terms.
---

# 先改文档，再写代码（docs-first-then-code）

## 何时触发

**必须触发**：

- 新增/拆分/下线**功能特性**、调整**分期（一期/二期/三期）**、挪动**里程碑编号**
- 改**依赖配置**（`requirements*.txt`、`package.json`）、**环境变量名**、**目录结构**
- 改**对外契约**：飞书权限、字段名、路由、卡片格式、SCHEMA、prompt 结构
- 引入**外部参考/新方法论**（如集成一篇文章的思想到架构）
- 用户说"顺便把文档也改一下" / "先更新方案，再改代码" / "把 X 放到二期"这类句式

**可以跳过**：

- 纯 bug 修复，不改任何对外行为
- 局部重命名/格式化，**且**没有文档提及该符号
- 用户明确说"只改代码，别动文档"

## 工作流（五步）

### 1. 影响面识别

读一下用户的话，回答三个问题再动手：

- 这次改动会让**哪些文档**过时？（README 功能段？分期表？里程碑？架构图？环境变量表？）
- 是否触达**外部参考**（`docs/外部参考/`）的引用关系？
- 是否新增了"已规划但还没写进代码"的事？→ 需要登记到 `docs/todo.md`

### 2. 登记 TODO

用 `todo_write` 工具开一张任务表，至少两类条目：

- **文档类**（本轮要完成的）：逐份文档一项
- **代码类**（本轮**不做**但要留痕的）：写进 `docs/todo.md`，保持"未做事项单一来源"

### 3. 文档体检（必须完整读）

**并行**读完所有受影响文档（`read_file` 不限行范围，整份读）。读完后为每份列一张**问题清单**，每条带出：

- 位置（章节或行号）
- 问题类型：陈旧 / 自相矛盾 / 重复 / 错字 / 标题与正文不符 / 断链
- 修复方向（一句话）

不允许不读就改、不允许基于记忆改。

### 4. 交叉一致性检查（四个维度对齐）

本项目必须同时满足（迁到别的项目时改这个清单）：

| 维度 | 必须一致的位置 |
|------|------------|
| 分期（一期/二期/三期） | README §功能 / `技术方案.md §零` / `feishu-setup.md §2` / `todo.md §一` |
| 里程碑编号（M1–M12） | README §里程碑 / `todo.md §一` |
| 目录结构（Raw/Wiki/SCHEMA） | `技术方案.md §三` / `feishu-setup.md §2` / `todo.md` |
| 环境变量名 | `.env.example` / `feishu-setup.md` / `app/config.py` / `todo.md`（如有改名计划） |

任一处修改后，**立即扫另外三处**同步。

### 5. 编辑 → 自检 → 交付

用 `search_replace` 按组修改。每份文档改完一轮再切下一份，避免并行编辑同一份。改完后：

- `read_file` 回看修改段落，检查代码块围栏、链接语法、错字
- 给用户**摘要清单**：每份文档改了什么、哪些"该做的事"已登记到 todo

**只有文档段落全部交付给用户，用户确认后，才进入代码编辑阶段。**

## 反模式

- ❌ **边写代码边改文档**：最后文档永远落后
- ❌ **文档里描述未实现的接口**，不标"待实现 / 见 todo.md"
- ❌ **散落的 🚧 / TODO 标记**：必须回收到 `docs/todo.md` 单一来源
- ❌ **标题与内容不符**：例如标题写"M1 环境准备"但正文含 ECS 部署
- ❌ **只看一处改一处**：改了分期表不同步里程碑、改了目录结构不同步 env var

## 本项目文档映射（改哪里 → 要同步哪里）

| 改动类型 | 至少要改的文档 |
|---------|--------------|
| 新增/下线一个里程碑 | `README.md` §里程碑 + `docs/todo.md` §一 |
| 调整分期范围 | `README.md` §功能 + `docs/技术方案.md §零` + `docs/feishu-setup.md §2`（如涉目录）+ `docs/todo.md` |
| 新增/改动环境变量 | `.env.example` + `docs/feishu-setup.md` + `app/config.py` + `docs/todo.md`（如计划改名） |
| 改 Wiki 目录结构 | `docs/技术方案.md §三` + `docs/feishu-setup.md §2` + 代码里 `handlers/ingest.py::_write_wiki` |
| 引入新的外部参考 | 本地归档 `docs/外部参考/NN-xxx.md` + `docs/外部参考/外部参考目录.md` + 被引用处 |
| 新增"规划了但没写代码"的事 | **只**改 `docs/todo.md`（不要散落到其它文档） |

## 交付模板

改完文档后，给用户的总结消息按这个结构组织：

```
## 一、新增
- 列出新增文件及作用

## 二、精修
- 每份文档一个子项，每项列 3–6 条具体改动（不要笼统说"更新了 XX"）

## 三、交叉一致性自检
- 分期口径 ✅
- 里程碑编号 ✅
- 目录结构 ✅
- 环境变量名 ✅

下一步代码改动候选：
- 选项 A …
- 选项 B …
```

## 快速示例（摘自本项目实战）

**场景**：用户要把 PDF/PPT/Excel 从一期移到二期

- ❌ 错误做法：直接改 `requirements.txt` 删 `markitdown` → 跑测试 → 写完
- ✅ 正确做法：
  1. 识别影响面：README（功能段/里程碑/技术栈表）、`技术方案.md §零分期表`、`feishu-setup.md §1 im:resource 权限 + §6 冒烟测试`、新建 `requirements-phase2.txt`
  2. 登记 TODO：5 项文档类 + 2 项代码类（代码其实零改动，因为 markitdown 是惰性 import）
  3. 读完 4 份文档列问题清单
  4. 按四维度交叉对齐（分期表 vs 里程碑 vs 功能段 vs 权限表）
  5. 改完给用户看摘要 → 确认 → 再跑 `curl /healthz` 验证代码零回归

文档先行会把架构问题**提前暴露在文字层**，避免代码改两遍。
