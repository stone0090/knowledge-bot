"""Vault 写闸锁：所有对 /opt/vault 的写入共享同一把全局 asyncio 锁。

避免并发任务碰撞：
- .git/index.lock 冲突
- index.md / log.md 的 append 竞争（后写覆盖先写）
- 秒级时间戳文件名撞名

用法：
    async with vault_write_gate.acquire(on_queued=notifier):
        # 读 / 写 md + commit_and_push 放这里
        ...

`on_queued` 是可选的 async 回调，签名 `async def f(ahead: int) -> None`。
当前面已有任务正在持锁时触发（`ahead` 不含自己），调用方可用于给用户发
「⏳ 前方 N 个任务处理中」的提示。自己是第一个则不触发。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Optional


OnQueued = Optional[Callable[[int], Awaitable[None]]]


class VaultWriteGate:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending = 0  # 已入队（含正在执行 + 等待拿锁）的任务数

    @property
    def pending(self) -> int:
        """当前队列中（含正在执行）的任务总数。"""
        return self._pending

    @asynccontextmanager
    async def acquire(self, on_queued: OnQueued = None) -> AsyncIterator[int]:
        """进入 vault 写临界区。

        yield 出 `ahead`：自己入队前前面的任务数（0 = 直接执行，无需等待）。
        """
        ahead = self._pending  # 不含自己
        self._pending += 1
        try:
            if ahead > 0 and on_queued is not None:
                try:
                    await on_queued(ahead)
                except Exception:  # noqa: BLE001 - 提示失败不影响主流程
                    pass
            async with self._lock:
                yield ahead
        finally:
            self._pending -= 1


# 全局单例：整个进程共用这一把锁
vault_write_gate = VaultWriteGate()
