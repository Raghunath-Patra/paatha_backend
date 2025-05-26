# File: backend/routes/limits.py - Final Version with subscription_service

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import get_db
from config.security import get_current_user
import logging
from services.question_service import get_user_token_status

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/user/question-status")
async def get_question_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the user's current token usage status and question information.
    This is the MAIN endpoint used by frontend for all token-related data.
    Uses optimized get_user_token_status() which calls subscription_service internally.
    """
    try:
        # Use the optimized function that calls subscription_service.check_daily_token_limits()
        status = get_user_token_status(current_user['id'], db)
        
        # Log what we're returning for debugging
        logger.info(f"Returning comprehensive token status: plan={status['plan_name']}, "
                   f"questions_used={status['questions_used_today']}, "
                   f"limit_reached={status['limit_reached']}")
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting question status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
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
            "limit_reached": False,
            "token_bonus": 0
        }

# REMOVED: /user/token-status endpoint (was unused by frontend)
# The /user/question-status endpoint now provides all needed token information

@router.get("/debug/question-usage")
async def debug_question_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debug endpoint to check question usage directly from DB"""
    try:
        query = text("""
            SELECT 
                questions_used_today,
                questions_used_this_month,
                daily_input_tokens_used,
                daily_output_tokens_used,
                tokens_reset_date,
                token_bonus,
                su.plan_id,
                sp.name as plan_name,
                sp.display_name
            FROM subscription_user_data su
            LEFT JOIN subscription_plans sp ON su.plan_id = sp.id
            WHERE su.user_id = :user_id
        """)
        
        result = db.execute(query, {"user_id": current_user['id']}).fetchone()
        
        if not result:
            return {
                "error": "No subscription data found for user",
                "user_id": current_user['id']
            }
            
        return {
            "user_id": current_user['id'],
            "questions_used_today": result.questions_used_today,
            "questions_used_this_month": result.questions_used_this_month,
            "daily_input_tokens_used": result.daily_input_tokens_used,
            "daily_output_tokens_used": result.daily_output_tokens_used,
            "tokens_reset_date": result.tokens_reset_date.isoformat() if result.tokens_reset_date else None,
            "token_bonus": result.token_bonus,
            "plan_id": result.plan_id,
            "plan_name": result.plan_name,
            "display_name": result.display_name
        }
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        return {
            "error": str(e),
            "user_id": current_user['id']
        }