# backend/middleware/rate_limit.py

from fastapi import FastAPI, Request, HTTPException
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
import os
from dotenv import load_dotenv
from starlette.types import ASGIApp, Receive, Scope, Send

load_dotenv()

async def setup_rate_limiter(app: FastAPI):
    redis_instance = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    await FastAPILimiter.init(redis_instance)

# Rate limit decorators
login_limiter = RateLimiter(times=5, seconds=60)  # 5 attempts per minute
register_limiter = RateLimiter(times=3, seconds=60)  # 3 attempts per minute
general_limiter = RateLimiter(times=30, seconds=60)  # 30 requests per minute

class RateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive)

        # Skip rate limiting for static files
        if request.url.path.startswith("/static"):
            return await self.app(scope, receive, send)

        # Get client IP
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0] if forwarded else request.client.host

        try:
            return await self.app(scope, receive, send)
        except Exception as e:
            if "Rate limit exceeded" in str(e):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later."
                )
            raise e