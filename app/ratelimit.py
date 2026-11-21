"""Simple per-user hourly limit in Redis."""

from __future__ import annotations


async def allow(redis, user_id: int, limit: int) -> bool:
    if limit <= 0:
        return True
    key = f"rl:checks:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)
    return count <= limit
