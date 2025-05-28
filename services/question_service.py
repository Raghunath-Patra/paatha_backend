# backend/services/question_service.py - Lightweight wrapper around consolidated service

from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import logging
from typing import Dict, Optional
from .token_service import token_service
from .consolidated_user_service import consolidated_service

logger = logging.getLogger(__name__)

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)  # IST offset from UTC
    return utc_now + offset

def get_india_date():
    """Get current date in India timezone"""
    india_time = get_india_time()
    return india_time.date()

def get_user_token_status(user_id: str, db: Session) -> Dict:
    """
    OPTIMIZED: Get comprehensive token status using consolidated service
    Single database call for everything
    """
    try:
        logger.info(f"Getting comprehensive token status for user {user_id}")
        
        # Use consolidated service - single database call
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        
        logger.info(f"Token status retrieved: plan={status['plan_name']}, "
                   f"questions_used={status['questions_used_today']}, "
                   f"limit_reached={status['limit_reached']}")
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting user token status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return safe defaults on error
        return consolidated_service._get_default_status(user_id)

def check_token_limits(user_id: str, db: Session) -> Dict:
    """
    LEGACY WRAPPER: Maintains backward compatibility with main.py
    Uses consolidated service internally
    """
    try:
        # Get comprehensive status from consolidated service
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        
        # Return in exact format expected by existing main.py code
        return {
            "input_limit": status["input_limit"],
            "output_limit": status["output_limit"],
            "input_used": status["input_used"],
            "output_used": status["output_used"],
            "input_remaining": status["input_remaining"],
            "output_remaining": status["output_remaining"],
            "limit_reached": status["limit_reached"],
            "questions_used_today": status["questions_used_today"],
            "plan_name": status["plan_name"],
            "display_name": status["display_name"],
        }
        
    except Exception as e:
        logger.error(f"Error in check_token_limits: {str(e)}")
        defaults = consolidated_service._get_default_status(user_id)
        return {
            "input_limit": defaults["input_limit"],
            "output_limit": defaults["output_limit"],
            "input_used": defaults["input_used"],
            "output_used": defaults["output_used"],
            "input_remaining": defaults["input_remaining"],
            "output_remaining": defaults["output_remaining"],
            "limit_reached": defaults["limit_reached"],
            "questions_used_today": defaults["questions_used_today"],
            "plan_name": defaults["plan_name"],
            "display_name": defaults["display_name"],
        }

def check_question_limit(user_id: str, db: Session) -> Dict:
    """
    LEGACY WRAPPER: Uses consolidated service
    """
    try:
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        
        return {
            "plan_name": status["plan_name"],
            "display_name": status["display_name"],
            "input_limit": status["input_limit"],
            "output_limit": status["output_limit"],
            "input_used": status["input_used"],
            "output_used": status["output_used"],
            "input_remaining": status["input_remaining"],
            "output_remaining": status["output_remaining"],
            "questions_used_today": status["questions_used_today"],
            "is_premium": status["is_premium"],
            "limit_reached": status["limit_reached"]
        }
    except Exception as e:
        logger.error(f"Error in check_question_limit: {e}")
        defaults = consolidated_service._get_default_status(user_id)
        return {
            "plan_name": defaults["plan_name"],
            "display_name": defaults["display_name"],
            "input_limit": defaults["input_limit"],
            "output_limit": defaults["output_limit"],
            "input_used": defaults["input_used"],
            "output_used": defaults["output_used"],
            "input_remaining": defaults["input_remaining"],
            "output_remaining": defaults["output_remaining"],
            "questions_used_today": defaults["questions_used_today"],
            "is_premium": defaults["is_premium"],
            "limit_reached": defaults["limit_reached"]
        }

def increment_question_usage(user_id: str, db: Session):
    """
    DEPRECATED: This is now handled by consolidated background updates
    Kept for backward compatibility but does nothing
    """
    logger.info(f"increment_question_usage called for user {user_id} - now handled by background updates")
    return False  # Don't block on this legacy function

def update_token_usage(user_id: str, question_id: str, input_tokens: int, output_tokens: int, db: Session):
    """
    OPTIMIZED: Schedule background update instead of blocking operation
    This allows immediate response to user while updating database in background
    """
    try:
        # Schedule background update (non-blocking)
        future = consolidated_service.update_user_usage(
            user_id=user_id,
            question_id=question_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            question_submitted=True  # Indicates this is from answer submission
        )
        
        logger.info(f"Scheduled background usage update for user {user_id}: "
                   f"input={input_tokens}, output={output_tokens}")
        return True
        
    except Exception as e:
        logger.error(f"Error scheduling token usage update: {str(e)}")
        return False

def check_question_token_limit(user_id: str, question_id: str, db: Session, reset_tokens: bool = False):
    """
    OPTIMIZED: Check per-question limits using comprehensive status
    """
    try:
        # Get comprehensive status (single database call)
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        
        # Get per-question limits from status
        input_limit = status["input_tokens_per_question"]
        output_limit = status["output_tokens_per_question"]
        
        if reset_tokens:
            # Schedule background reset
            reset_query = text("""
                UPDATE user_attempts
                SET input_tokens_used = 0, output_tokens_used = 0
                WHERE user_id = :user_id AND question_id = :question_id
            """)
            
            try:
                db.execute(reset_query, {"user_id": user_id, "question_id": question_id})
                db.commit()
                logger.info(f"Reset question tokens for user {user_id}, question {question_id}")
                
                return {
                    "input_limit": input_limit,
                    "output_limit": output_limit,
                    "input_used": 0,
                    "output_used": 0,
                    "input_remaining": input_limit,
                    "output_remaining": output_limit,
                    "limit_reached": False
                }
            except Exception as e:
                logger.error(f"Error resetting question tokens: {str(e)}")
                db.rollback()
        
        # Check current usage for this specific question
        query = text("""
            SELECT 
                COALESCE(SUM(input_tokens_used), 0) as total_input,
                COALESCE(SUM(output_tokens_used), 0) as total_output
            FROM user_attempts
            WHERE user_id = :user_id AND question_id = :question_id
        """)
        
        result = db.execute(query, {"user_id": user_id, "question_id": question_id}).fetchone()
        
        if not result:
            return {
                "input_limit": input_limit,
                "output_limit": output_limit,
                "input_used": 0,
                "output_used": 0,
                "input_remaining": input_limit,
                "output_remaining": output_limit,
                "limit_reached": False
            }
            
        input_used = result.total_input
        output_used = result.total_output
        input_remaining = max(0, input_limit - input_used)
        output_remaining = max(0, output_limit - output_used)
        limit_reached = input_remaining <= 0 or output_remaining <= 0
        
        return {
            "input_limit": input_limit,
            "output_limit": output_limit,
            "input_used": input_used,
            "output_used": output_used,
            "input_remaining": input_remaining,
            "output_remaining": output_remaining,
            "limit_reached": limit_reached
        }
        
    except Exception as e:
        logger.error(f"Error checking question token limit: {str(e)}")
        return {
            "input_limit": 6000,
            "output_limit": 4000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 6000,
            "output_remaining": 4000,
            "limit_reached": False
        }

def track_follow_up_usage(user_id: str, db: Session, question_id: str = None, increment: bool = False):
    """
    OPTIMIZED: Track follow-up usage using comprehensive status
    """
    try:
        # Get comprehensive status (single database call)
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        
        # Get the per-question token limits if question_id is provided
        if question_id:
            question_limits = check_question_token_limit(user_id, question_id, db)
            limit_reached = question_limits["limit_reached"]
            remaining = min(
                question_limits["input_remaining"],
                question_limits["output_remaining"]
            )
        else:
            # If no question_id, use overall token limits
            limit_reached = status["limit_reached"]
            remaining = min(
                status["input_remaining"],
                status["output_remaining"]
            )
        
        return {
            "plan_name": status["plan_name"],
            "display_name": status["display_name"],
            "input_remaining": status["input_remaining"] if question_id is None else question_limits["input_remaining"],
            "output_remaining": status["output_remaining"] if question_id is None else question_limits["output_remaining"],
            "remaining": remaining,
            "limit_reached": limit_reached
        }
    except Exception as e:
        logger.error(f"Error tracking follow-up usage: {str(e)}")
        return {
            "plan_name": "free",
            "display_name": "Free Plan",
            "input_remaining": 6000,
            "output_remaining": 4000,
            "remaining": 4000,
            "limit_reached": False
        }

# New optimized functions using consolidated service

def check_user_can_fetch_question(user_id: str, db: Session) -> Dict:
    """
    OPTIMIZED: Check if user can fetch a question using consolidated service
    """
    try:
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        return consolidated_service.check_can_perform_action(status, "fetch_question")
    except Exception as e:
        logger.error(f"Error checking fetch question permission: {str(e)}")
        return {"allowed": True}  # Optimistic fallback

def check_user_can_submit_answer(user_id: str, db: Session) -> Dict:
    """
    OPTIMIZED: Check if user can submit an answer using consolidated service
    """
    try:
        status = consolidated_service.get_comprehensive_user_status(user_id, db)
        return consolidated_service.check_can_perform_action(status, "submit_answer")
    except Exception as e:
        logger.error(f"Error checking submit answer permission: {str(e)}")
        return {"allowed": True}  # Optimistic fallback

def schedule_background_update(user_id: str, question_id: str, input_tokens: int, output_tokens: int, question_submitted: bool = False):
    """
    OPTIMIZED: Schedule background database update
    Returns immediately, allowing fast API response
    """
    try:
        future = consolidated_service.update_user_usage(
            user_id=user_id,
            question_id=question_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            question_submitted=question_submitted
        )
        
        logger.info(f"Background update scheduled for user {user_id}")
        return future
        
    except Exception as e:
        logger.error(f"Error scheduling background update: {str(e)}")
        return None