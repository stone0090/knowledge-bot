# envs/ 环境配置总览

## 加载优先级（后者覆盖前者）

1. `envs/{APP_ENV}.env` —— 环境配置（`local.env` / `ecs.env`，已提交 Git）
2. `envs/.env.secrets` —— 密钥（不提交 Git，见 `.env.secrets.example`）
3. `.env`（项目根目录）—— 可选的本地覆盖，不提交 Git；不需要时不必创建

切换环境：`export APP_ENV=ecs`（默认 `local`）

## 快速开始

```bash
cp envs/.env.secrets.example envs/.env.secrets
# 编辑 envs/.env.secrets 填入真实密钥
```

## 文件清单

| 文件 | 用途 | 提交 Git |
|---|---|---|
| `local.env` | 本地开发环境配置 | ✅ |
| `ecs.env` | ECS 生产环境配置 | ✅ |
| `.env.secrets` | 密钥（飞书、百炼等） | ❌ |
| `.env.secrets.example` | 密钥模板 | ✅ |
| `mihomo.yaml` | ECS 代理真实配置 | ❌ |
| `mihomo.yaml.README` | 代理配置获取方式说明 | ✅ |

## 命名规范

- `.example` 后缀：可直接 `cp` 使用的模板
- `.README` 后缀：仅作说明文档，不可 `cp`（目前只有 `mihomo.yaml.README`，因其获取方式特殊）
- `.` 前缀：敏感文件或遵循 `.env` 生态约定
- 无 `.` 前缀：按场景命名的常规配置
