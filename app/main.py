"""Authenticated callback when a verification token is configured; durable inbox."""
from __future__ import annotations
import asyncio
import hmac
from contextlib import asynccontextmanager,suppress
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from app.config import settings
from app.handlers.dispatcher import dispatch_event
from app.worker import run_worker

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(run_worker())
    app.state.worker=task
    await asyncio.sleep(0)
    if task.done():task.result()
    if not settings.feishu_verification_token:
        logger.warning('FEISHU_VERIFICATION_TOKEN is not configured; callback token validation disabled')
    try:yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):await task

app=FastAPI(title='Knowledge Bot',version='0.2.0',lifespan=lifespan)

@app.get('/healthz')
async def healthz():
    task=getattr(app.state,'worker',None)
    if task is None or task.done():return JSONResponse({'status':'worker_unavailable'},status_code=503)
    return {'status':'ok','worker':'running'}

@app.post('/feishu/event')
async def feishu_event(request:Request):
    payload=await request.json()
    if not isinstance(payload,dict):raise HTTPException(400,'Invalid event')
    if 'encrypt' in payload:raise HTTPException(400,'Encrypted events are not configured for this deployment')
    expected=settings.feishu_verification_token
    token=(payload.get('header') or {}).get('token') or payload.get('token') or ''
    if expected and not hmac.compare_digest(str(token),expected):raise HTTPException(403,'Invalid verification token')
    if payload.get('type')=='url_verification':return {'challenge':payload.get('challenge','')}
    # Do not acknowledge before persistence succeeds: Feishu may retry on non-2xx.
    await dispatch_event(payload)
    return {'code':0,'msg':'ok'}
