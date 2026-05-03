"""FastAPI 入口。

暴露两个端点：
- GET /healthz       健康检查
- POST /feishu/event 飞书事件回调（消息、URL 验证）
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.handlers.dispatcher import dispatch_event

app = FastAPI(title="Knowledge Bot", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/feishu/event")
async def feishu_event(request: Request) -> JSONResponse:
    """飞书事件订阅回调。

    - 首次配置时飞书会发 `url_verification` 请求，需原样返回 challenge。
    - 消息等业务事件走 dispatch_event。
    """
    payload = await request.json()
    logger.debug("feishu event: {}", payload)

    # URL 校验
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload.get("challenge", "")})

    # v2 事件统一走 header+event 结构
    try:
        await dispatch_event(payload)
    except Exception as exc:  # pragma: no cover
        logger.exception("dispatch_event failed: {}", exc)

    # 飞书要求快速返回 2xx，业务异步处理
    return JSONResponse({"code": 0, "msg": "ok"})


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
