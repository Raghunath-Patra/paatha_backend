# backend/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user
from models import User
from datetime import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    board: Optional[str] = None
    class_level: Optional[str] = None

class SyncUserRequest(BaseModel):
    email: Optional[str]
    full_name: Optional[str]
    board: Optional[str]
    class_level: Optional[str]

# backend/routes/auth.py - Updated sync_user function

# backend/routes/auth.py
@router.post("/sync-user")
async def sync_user(
    user_data: SyncUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync Supabase user data with backend database"""
    try:
        print(f"Syncing user data for {current_user['id']}")
        print(f"User data received: {user_data}")
        
        # Check if user exists
        try:
            user = db.query(User).filter(User.id == current_user['id']).first()
            print(f"User query result: {user}")
        except Exception as e:
            print(f"Error querying user: {str(e)}")
            raise

        if user:
            print("Updating existing user")
            # Update existing user with non-None values
            if user_data.email is not None:
                user.email = user_data.email
            if user_data.full_name is not None:
                user.full_name = user_data.full_name
            if user_data.board is not None:
                user.board = user_data.board
            if user_data.class_level is not None:
                user.class_level = user_data.class_level
        else:
            print("Creating new user")
            # Create new user
            new_user = User(
                id=current_user['id'],
                email=user_data.email or current_user['email'],
                full_name=user_data.full_name or "",
                board=user_data.board,
                class_level=user_data.class_level,
                is_verified=True,
                created_at=datetime.utcnow()
            )
            db.add(new_user)
        
        try:
            db.commit()
            print("Database commit successful")
        except Exception as e:
            print(f"Error committing to database: {str(e)}")
            db.rollback()
            raise
            
        return {"message": "User data synced successfully"}
    except Exception as e:
        print(f"Error syncing user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )