# backend/middleware/security.py

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os
from dotenv import load_dotenv

load_dotenv()

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: FastAPI,
        frontend_url: str = os.getenv("FRONTEND_URL", "https://www.paatha.ai")  # Update this
    ):
        super().__init__(app)
        self.frontend_url = frontend_url.rstrip('/')  # Remove trailing slash

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response