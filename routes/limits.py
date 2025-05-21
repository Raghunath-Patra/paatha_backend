# File: backend/routes/limits.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import get_db
from config.security import get_current_user
import logging
from services.question_service import check_token_limits, check_question_token_limit, get_user_token_status

logger = logging.getLogger(__name__)

router = APIRouter()

# @router.get("/user/question-status")
# async def get_question_status(
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get the user's current token usage status"""
#     try:
#         # Use the direct approach instead of check_token_limits
#         questions_used_today = get_questions_used_today(current_user['id'], db)
        
#         # Log what we're returning
#         logger.info(f"Returning questions_used_today = {questions_used_today} to frontend")
        
#         # Return token-based information with defaults for everything except questions_used_today
#         return {
#             "plan_name": "free",
#             "display_name": "Free Plan",
#             "input_limit": 18000,
#             "output_limit": 12000,
#             "input_used": 0,
#             "output_used": 0,
#             "input_remaining": 18000,
#             "output_remaining": 12000,
#             "questions_used_today": questions_used_today,  # Use the value from our simple function
#             "is_premium": False,
#             "limit_reached": False
#         }
        
#     except Exception as e:
#         logger.error(f"Error getting question status: {str(e)}")
#         import traceback
#         logger.error(traceback.format_exc())
        
#         # For API stability, return sensible defaults rather than an error
#         return {
#             "plan_name": "free",
#             "display_name": "Free Plan",
#             "input_limit": 18000,
#             "output_limit": 12000,
#             "input_used": 0,
#             "output_used": 0,
#             "input_remaining": 18000,
#             "output_remaining": 12000,
#             "questions_used_today": 42,  # Different test value to identify this error path
#             "is_premium": False,
#             "limit_reached": False
#         }

@router.get("/user/question-status")
async def get_question_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's current token usage status"""
    try:
        # Use the direct approach to get all token status info
        status = get_user_token_status(current_user['id'], db)
        
        # Log what we're returning
        logger.info(f"Returning question status to frontend: questions_used_today={status['questions_used_today']}")
        
        # Return the complete status
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
            "questions_used_today": 222,
            "is_premium": False,
            "limit_reached": False,
            "token_bonus": 0
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
        
        # Log the value we're returning
        logger.info(f"Token status endpoint returning questions_used_today: {limits['questions_used_today']}")
        
        # If for some reason questions_used_today is None, set to 0
        if limits["questions_used_today"] is None:
            limits["questions_used_today"] = 1 # set it back to
        
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
        import traceback
        logger.error(traceback.format_exc())
        
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
                token_bonus
            FROM subscription_user_data
            WHERE user_id = :user_id
        """)
        
        result = db.execute(query, {"user_id": current_user['id']}).fetchone()
        
        if not result:
            return {
                "error": "No subscription data found for user",
                "user_id": current_user['id']
            }
            
        return {
            "questions_used_today": result.questions_used_today,
            "questions_used_this_month": result.questions_used_this_month,
            "daily_input_tokens_used": result.daily_input_tokens_used,
            "daily_output_tokens_used": result.daily_output_tokens_used,
            "tokens_reset_date": result.tokens_reset_date.isoformat() if result.tokens_reset_date else None,
            "token_bonus": result.token_bonus
        }
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        return {
            "error": str(e)
        }