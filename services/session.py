# backend/services/session.py

from redis.asyncio import Redis
from fastapi import HTTPException, status
import json
import os
from datetime import datetime, timedelta
import uuid
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

class SessionService:
    def __init__(self):
        self.redis = Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )
        self.session_expire = int(os.getenv("SESSION_EXPIRE_HOURS", "24"))

    async def create_session(self, user_id: str, user_data: Dict) -> str:
        """Create a new session and return session ID"""
        session_id = str(uuid.uuid4())
        session_data = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            **user_data
        }
        
        await self.redis.setex(
            f"session:{session_id}",
            timedelta(hours=self.session_expire),
            json.dumps(session_data)
        )
        return session_id

    async def get_session(self, session_id: str) -> Dict:
        """Get session data by session ID"""
        session_data = await self.redis.get(f"session:{session_id}")
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid"
            )
        return json.loads(session_data)

    async def update_session(self, session_id: str, update_data: Dict) -> None:
        """Update existing session data"""
        session_data = await self.get_session(session_id)
        session_data.update(update_data)
        
        await self.redis.setex(
            f"session:{session_id}",
            timedelta(hours=self.session_expire),
            json.dumps(session_data)
        )

    async def extend_session(self, session_id: str) -> None:
        """Extend session expiration"""
        session_data = await self.get_session(session_id)
        await self.redis.setex(
            f"session:{session_id}",
            timedelta(hours=self.session_expire),
            json.dumps(session_data)
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session"""
        await self.redis.delete(f"session:{session_id}")

    async def get_user_sessions(self, user_id: str) -> list[str]:
        """Get all active sessions for a user"""
        sessions = []
        async for key in self.redis.scan_iter("session:*"):
            session_data = await self.redis.get(key)
            if session_data:
                data = json.loads(session_data)
                if data.get("user_id") == user_id:
                    sessions.append(key.split(":")[1])
        return sessions

    async def delete_user_sessions(self, user_id: str) -> None:
        """Delete all sessions for a user"""
        sessions = await self.get_user_sessions(user_id)
        for session_id in sessions:
            await self.delete_session(session_id)

session_service = SessionService()