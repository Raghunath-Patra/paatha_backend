# services/question_service.py - PROPER FIX that works with existing subscription_service

from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import logging
from typing import Dict, Optional
from .token_service import token_service
from .subscription_service import subscription_service

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
    OPTIMIZED: Main function that gets comprehensive token status
    Uses existing subscription_service.check_daily_token_limits()
    """
    try:
        logger.info(f"Getting token status for user {user_id}")
        
        # Use the existing subscription service method - this already does all the work!
        token_status = subscription_service.check_daily_token_limits(db, user_id)
        
        logger.info(f"Token status retrieved: plan={token_status['plan_name']}, "
                   f"questions_used={token_status['questions_used_today']}, "
                   f"limit_reached={token_status['limit_reached']}")
        
        return token_status
        
    except Exception as e:
        logger.error(f"Error getting user token status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return safe defaults on error
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
            "limit_reached": False,
            "is_premium": False
        }

def check_token_limits(user_id: str, db: Session) -> Dict:
    """
    LEGACY WRAPPER: Uses the optimized get_user_token_status internally
    Maintains backward compatibility with existing main.py code
    """
    try:
        # Use the optimized function that calls subscription_service
        status = get_user_token_status(user_id, db)
        
        # Return in exact format expected by existing callers in main.py
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
            "display_name": "Free Plan",
        }

def check_question_limit(user_id: str, db: Session) -> Dict:
    """
    LEGACY FUNCTION: Uses optimized token status
    """
    try:
        status = get_user_token_status(user_id, db)
        
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
            "is_premium": status.get("is_premium", False),
            "limit_reached": status["limit_reached"]
        }
    except Exception as e:
        logger.error(f"Error in check_question_limit: {e}")
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

def increment_question_usage(user_id: str, db: Session):
    """
    Increment questions_used_today counter for the user
    Uses existing database structure
    """
    try:
        # Check if user record exists first
        check_query = text("""
            SELECT id FROM subscription_user_data
            WHERE user_id = :user_id
        """)
        
        exists = db.execute(check_query, {"user_id": user_id}).fetchone()
        
        if not exists:
            # Create new record if it doesn't exist
            insert_query = text("""
                INSERT INTO subscription_user_data 
                (id, user_id, plan_id, questions_used_today, questions_used_this_month, 
                 daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date, token_bonus)
                VALUES (gen_random_uuid(), :user_id, 
                    (SELECT id FROM subscription_plans WHERE name = 'free' LIMIT 1),
                    1, 1, 0, 0, :current_date, 0)
                ON CONFLICT (user_id) DO NOTHING
            """)
            
            db.execute(insert_query, {
                "user_id": user_id,
                "current_date": get_india_date()
            })
            db.commit()
            
            # Check token limits
            status = get_user_token_status(user_id, db)
            return status["limit_reached"]
        else:
            # Get current limits
            status = get_user_token_status(user_id, db)
            
            # If already at limit, don't increment
            if status["limit_reached"]:
                return True
                
            # Increment counters
            update_query = text("""
                UPDATE subscription_user_data
                SET 
                    questions_used_today = COALESCE(questions_used_today, 0) + 1,
                    questions_used_this_month = COALESCE(questions_used_this_month, 0) + 1
                WHERE user_id = :user_id
            """)
            
            db.execute(update_query, {"user_id": user_id})
            db.commit()
            
            logger.info(f"Incremented question usage for user {user_id}")
            return status["limit_reached"]
                
    except Exception as e:
        logger.error(f"Error in increment_question_usage: {e}")
        db.rollback()
        return False  # Don't block on error

def update_token_usage(user_id: str, question_id: str, input_tokens: int, output_tokens: int, db: Session):
    """Update token usage for both user data and question attempt"""
    try:
        # Update user's daily token usage
        user_update = text("""
            UPDATE subscription_user_data
            SET 
                daily_input_tokens_used = COALESCE(daily_input_tokens_used, 0) + :input_tokens,
                daily_output_tokens_used = COALESCE(daily_output_tokens_used, 0) + :output_tokens,
                tokens_reset_date = COALESCE(tokens_reset_date, CURRENT_DATE)
            WHERE user_id = :user_id
        """)
        
        db.execute(user_update, {
            "user_id": user_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        })
        
        # Update question attempt if question_id provided
        if question_id:
            find_attempt_query = text("""
                SELECT id FROM user_attempts
                WHERE user_id = :user_id AND question_id = :question_id
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            attempt_result = db.execute(find_attempt_query, {
                "user_id": user_id,
                "question_id": question_id
            }).fetchone()
            
            if attempt_result:
                attempt_update = text("""
                    UPDATE user_attempts
                    SET 
                        input_tokens_used = COALESCE(input_tokens_used, 0) + :input_tokens,
                        output_tokens_used = COALESCE(output_tokens_used, 0) + :output_tokens
                    WHERE id = :attempt_id
                """)
                
                db.execute(attempt_update, {
                    "attempt_id": attempt_result[0],
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                })
        
        db.commit()
        logger.info(f"Updated token usage for user {user_id}: input={input_tokens}, output={output_tokens}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating token usage: {str(e)}")
        db.rollback()
        return False

def check_question_token_limit(user_id: str, question_id: str, db: Session, reset_tokens: bool = False):
    """Check token limit for specific question"""
    try:
        # Get plan details using subscription service
        status = get_user_token_status(user_id, db)
        plan = subscription_service.get_plan_details(db, status["plan_name"])
        
        # Get per-question token limits
        input_limit = plan.get("input_tokens_per_question", 6000)
        output_limit = plan.get("output_tokens_per_question", 4000)
        
        if reset_tokens:
            # Reset token usage for this question
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
        
        # Check current usage for this question
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
    Track follow-up question usage based on token limits
    """
    try:
        # Get token limits using optimized function
        status = get_user_token_status(user_id, db)
        
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