# File: backend/routes/limits.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import get_db
from config.security import get_current_user
import logging
from services.question_service import check_token_limits, check_question_token_limit

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/user/question-status")
async def get_question_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's current token usage status"""
    try:
        # Use the token-based approach
        token_limits = check_token_limits(current_user['id'], db)
        
        # Return token-based information
        return {
            "plan_name": token_limits["plan_name"],
            "display_name": token_limits["display_name"],
            "input_limit": token_limits["input_limit"],
            "output_limit": token_limits["output_limit"],
            "input_used": token_limits["input_used"],
            "output_used": token_limits["output_used"],
            "input_remaining": token_limits["input_remaining"],
            "output_remaining": token_limits["output_remaining"],
            "questions_used_today": token_limits["questions_used_today"],
            "is_premium": token_limits["plan_name"] == "premium",
            "limit_reached": token_limits["limit_reached"]
        }
        
    except Exception as e:
        logger.error(f"Error getting token status: {str(e)}")
        # For API stability, return sensible defaults rather than an error
        return {
            "plan_name": "free",
            "display_name": "Free Plan",
            "input_limit": 18000,
            "output_limit": 12000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "questions_used_today": 0,
            "is_premium": False,
            "limit_reached": False
        }


@router.get("/user/token-status")
async def get_token_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's detailed token usage status"""
    try:
        # Get token limit information
        limits = check_token_limits(current_user['id'], db)
        
        return {
            "input_limit": limits["input_limit"],
            "output_limit": limits["output_limit"],
            "input_used": limits["input_used"],
            "output_used": limits["output_used"],
            "input_remaining": limits["input_remaining"],
            "output_remaining": limits["output_remaining"],
            "limit_reached": limits["limit_reached"],
            "questions_used_today": limits["questions_used_today"],
            "plan_name": limits["plan_name"],
            "display_name": limits["display_name"]
        }
        
    except Exception as e:
        logger.error(f"Error getting detailed token status: {str(e)}")
        # For API stability, return sensible defaults rather than an error
        return {
            "input_limit": 18000,
            "output_limit": 12000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "limit_reached": False,
            "questions_used_today": 0,
            "plan_name": "free",
            "display_name": "Free Plan"
        }