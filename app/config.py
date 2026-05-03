"""全局配置：多文件加载，通过 `settings` 单例访问。

加载优先级（后者覆盖前者）：
  1. envs/local.env 或 envs/ecs.env  —— 环境相关配置（可提交 Git）
  2. envs/.env.secrets              —— 密钥（不提交 Git）
  3. .env                             —— 本地覆盖 / 兜底（不提交 Git）

切换环境：设置环境变量 APP_ENV=ecs 即可切换到 ECS 配置。
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 通过 APP_ENV 环境变量切换：local（默认） / ecs
_APP_ENV = os.getenv("APP_ENV", "local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            f"envs/{_APP_ENV}.env",  # 1. 环境配置
            "envs/.env.secrets",         # 2. 密钥
            ".env",                  # 3. 本地覆盖 / 兜底
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 飞书
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""

    # 飞书云盘「知识库-镜像」目录 token（只读镜像，best-effort，失败仅告警）
    feishu_mirror_folder_token: str = ""

    # Vault（真相源：ECS 本地 md + git）
    vault_path: str = "/opt/vault"
    vault_git_remote: str = "/opt/vault-bare.git"
    vault_git_author_name: str = "Knowledge Bot"
    vault_git_author_email: str = "bot@knowledge-bot.local"

    # 百炼
    dashscope_api_key: str = ""
    # —— OpenAI 兼容协议端点（适配 sk-sp- 类型的 key）
    dashscope_base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    # ——兜底（当前生效）
    dashscope_model_compile: str = "qwen3.5-plus"
    dashscope_model_query: str = "qwen3.5-plus"
    # ——预留：投喂侧场景路由（待 ingest 路由函数接入后生效）
    dashscope_model_compile_text: str = "qwen3.5-plus"
    dashscope_model_compile_long: str = "kimi-k2.5"
    dashscope_model_compile_vision: str = "qwen3.6-plus"
    dashscope_model_compile_code: str = "qwen3-coder-plus"
    dashscope_model_compile_deep: str = "qwen3-max-2026-01-23"
    # ——预留：检索侧场景路由（待 query 路由函数接入后生效）
    dashscope_model_query_fast: str = "qwen3.5-plus"
    dashscope_model_query_deep: str = "qwen3-max-2026-01-23"
    dashscope_model_query_long: str = "kimi-k2.5"
    dashscope_model_query_vision: str = "qwen3.6-plus"

    # 代理（用于访问 Jina Reader / YouTube 等海外服务）
    http_proxy: str = ""

    # 服务
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
