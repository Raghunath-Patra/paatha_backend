# backend/routes/user.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user
from models import User, UserAttempt  # Removed VerificationToken, RefreshToken
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/user", tags=["user"])

class UserUpdateSchema(BaseModel):
    full_name: str
    board: Optional[str] = None
    class_level: Optional[str] = None

@router.put("/profile")
async def update_profile(
    user_data: UserUpdateSchema,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get user from database
        user = db.query(User).filter(User.id == current_user['id']).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Update user info
        user.full_name = user_data.full_name
        if user_data.board:
            user.board = user_data.board
        if user_data.class_level:
            user.class_level = user_data.class_level
        
        db.commit()
        db.refresh(user)
        
        return {
            "message": "Profile updated successfully",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "board": user.board,
                "class_level": user.class_level
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )