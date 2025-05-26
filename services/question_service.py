# services/question_service.py - Optimized Version
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

def get_user_token_status(user_id: str, db: Session, force_refresh: bool = False) -> Dict:
    """
    OPTIMIZED: Get comprehensive token usage information directly from the database
    This is now the main function used by all token-related operations
    """
    try:
        current_date = get_india_date()
        logger.debug(f"Getting token status for user {user_id} with current date {current_date}")
        
        # Single optimized query to get all needed data
        query = text("""
            SELECT 
                su.questions_used_today,
                su.daily_input_tokens_used,
                su.daily_output_tokens_used,
                su.token_bonus,
                su.tokens_reset_date,
                su.plan_id,
                sp.name as plan_name,
                sp.display_name,
                sp.daily_input_token_limit,
                sp.daily_output_token_limit
            FROM subscription_user_data su
            LEFT JOIN subscription_plans sp ON su.plan_id = sp.id
            WHERE su.user_id = :user_id
        """)
        
        result = db.execute(query, {"user_id": user_id}).fetchone()
        
        if result:
            # Check if reset is needed
            tokens_reset_date = result.tokens_reset_date
            reset_needed = tokens_reset_date and tokens_reset_date < current_date
            
            if reset_needed:
                logger.info(f"Resetting tokens for user {user_id} - reset_date {tokens_reset_date} < current_date {current_date}")
                reset_query = text("""
                    UPDATE subscription_user_data
                    SET 
                        daily_input_tokens_used = 0,
                        daily_output_tokens_used = 0,
                        questions_used_today = 0,
                        tokens_reset_date = :current_date
                    WHERE user_id = :user_id
                    RETURNING questions_used_today, daily_input_tokens_used, daily_output_tokens_used
                """)
                
                reset_result = db.execute(reset_query, {"user_id": user_id, "current_date": current_date}).fetchone()
                db.commit()
                
                # Update values after reset
                questions_used_today = 0
                input_used = 0
                output_used = 0
            else:
                # Use current values
                questions_used_today = result.questions_used_today or 0
                input_used = result.daily_input_tokens_used or 0
                output_used = result.daily_output_tokens_used or 0
            
            # Get plan details
            token_bonus = result.token_bonus or 0
            plan_name = result.plan_name or "free"
            display_name = result.display_name or "Free Plan"
            input_limit = (result.daily_input_token_limit or 18000) + token_bonus
            output_limit = (result.daily_output_token_limit or 12000) + token_bonus
            
        else:
            # No record found, create one with defaults
            logger.info(f"No subscription data found for user {user_id}, creating with defaults")
            
            # Get default plan details
            plan_query = text("""
                SELECT id, name, display_name, daily_input_token_limit, daily_output_token_limit
                FROM subscription_plans
                WHERE name = 'free'
                LIMIT 1
            """)
            
            plan_result = db.execute(plan_query).fetchone()
            
            if plan_result:
                plan_id = plan_result.id
                plan_name = plan_result.name
                display_name = plan_result.display_name
                input_limit = plan_result.daily_input_token_limit
                output_limit = plan_result.daily_output_token_limit
            else:
                # Fallback to hardcoded defaults
                plan_id = None
                plan_name = "free"
                display_name = "Free Plan"
                input_limit = 18000
                output_limit = 12000
            
            # Try to create new record
            if plan_id:
                try:
                    insert_query = text("""
                        INSERT INTO subscription_user_data 
                        (id, user_id, plan_id, questions_used_today, daily_input_tokens_used, 
                         daily_output_tokens_used, tokens_reset_date, token_bonus)
                        VALUES (gen_random_uuid(), :user_id, :plan_id, 0, 0, 0, :current_date, 0)
                        ON CONFLICT (user_id) DO NOTHING
                    """)
                    
                    db.execute(insert_query, {
                        "user_id": user_id,
                        "plan_id": plan_id,
                        "current_date": current_date
                    })
                    db.commit()
                except Exception as insert_err:
                    logger.error(f"Error creating subscription data: {insert_err}")
                    db.rollback()
            
            # Set default values
            questions_used_today = 0
            input_used = 0
            output_used = 0
            token_bonus = 0
        
        # Calculate remaining tokens
        input_remaining = max(0, input_limit - input_used)
        output_remaining = max(0, output_limit - output_used)
        
        # Determine if limit is reached
        limit_reached = input_remaining <= 0 or output_remaining <= 0
        
        # Comprehensive response
        status = {
            "questions_used_today": questions_used_today,
            "input_used": input_used,
            "output_used": output_used,
            "input_limit": input_limit,
            "output_limit": output_limit,
            "input_remaining": input_remaining,
            "output_remaining": output_remaining,
            "plan_name": plan_name,
            "display_name": display_name,
            "limit_reached": limit_reached,
            "token_bonus": token_bonus,
            "is_premium": plan_name == "premium"
        }
        
        logger.debug(f"Token status for user {user_id}: questions_used={questions_used_today}, limit_reached={limit_reached}")
        return status
        
    except Exception as e:
        logger.error(f"Error getting user token status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return safe defaults
        return {
            "questions_used_today": 0,
            "input_used": 0,
            "output_used": 0,
            "input_limit": 18000,
            "output_limit": 12000,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "plan_name": "free",
            "display_name": "Free Plan",
            "limit_reached": False,
            "token_bonus": 0,
            "is_premium": False
        }

def check_token_limits(user_id: str, db: Session) -> Dict:
    """
    OPTIMIZED: Legacy function that now uses get_user_token_status internally
    Maintained for backward compatibility with existing code in main.py
    """
    try:
        # Use the optimized function
        status = get_user_token_status(user_id, db)
        
        # Return in the format expected by existing callers
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
            "token_bonus": status["token_bonus"]
        }
        
    except Exception as e:
        logger.error(f"Error in check_token_limits: {str(e)}")
        # Return safe defaults
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
            "token_bonus": 0
        }

def check_question_limit(user_id: str, db: Session):
    """
    OPTIMIZED: Uses the main token status function
    Required function - now uses token-based limits rather than question counts
    """
    try:
        # Use the optimized function
        status = get_user_token_status(user_id, db)
        
        # Return in expected format
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
        # Return default response
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
    OPTIMIZED: Increment questions_used_today counter for the user
    Returns: bool indicating if limit is reached
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
                RETURNING id
            """)
            
            result = db.execute(insert_query, {
                "user_id": user_id,
                "current_date": get_india_date()
            }).fetchone()
            
            db.commit()
            
            # Check token limits using optimized function
            status = get_user_token_status(user_id, db)
            return status["limit_reached"]
        else:
            # Get current token limits before incrementing
            status = get_user_token_status(user_id, db)
            
            # If already at limit, don't increment
            if status["limit_reached"]:
                return True  # Limit reached
                
            # Increment both daily and monthly counters
            update_query = text("""
                UPDATE subscription_user_data
                SET 
                    questions_used_today = COALESCE(questions_used_today, 0) + 1,
                    questions_used_this_month = COALESCE(questions_used_this_month, 0) + 1
                WHERE user_id = :user_id
                RETURNING questions_used_today
            """)
            
            result = db.execute(update_query, {"user_id": user_id}).fetchone()
            db.commit()
            
            if result:
                logger.info(f"Updated questions_used_today to {result.questions_used_today} for user {user_id}")
            else:
                logger.error(f"Failed to update question usage for user {user_id}")
            
            # Return whether token limit is reached
            return status["limit_reached"]
                
    except Exception as e:
        logger.error(f"Error in increment_question_usage: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating question usage: {str(e)}")

def track_follow_up_usage(user_id: str, db: Session, question_id: str = None, increment: bool = False):
    """
    OPTIMIZED: Track follow-up question based on token limits only
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
        # Return sensible defaults
        return {
            "plan_name": "free",
            "display_name": "Free Plan",
            "input_remaining": 6000,
            "output_remaining": 4000,
            "remaining": 4000,
            "limit_reached": False
        }

def update_token_usage(
    user_id: str, 
    question_id: str,
    input_tokens: int, 
    output_tokens: int, 
    db: Session
):
    """OPTIMIZED: Update token usage for both user data and question attempt"""
    try:
        # Start transaction
        transaction = db.begin_nested()
        
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
            
            # Update the question attempt if a question ID is provided
            if question_id:
                # Find the latest attempt for this question
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
                    # Update the attempt with token usage
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
            
            # Commit the transaction
            transaction.commit()
            
        except Exception as inner_error:
            transaction.rollback()
            raise inner_error
        
        # Commit the outer transaction
        db.commit()
        return True
        
    except Exception as e:
        logger.error(f"Error updating token usage: {str(e)}")
        db.rollback()
        return False

def check_question_token_limit(user_id: str, question_id: str, db: Session, reset_tokens: bool = False):
    """OPTIMIZED: Check if token limit for a specific question has been reached"""
    try:
        # Get plan details using optimized function
        status = get_user_token_status(user_id, db)
        plan_name = status["plan_name"]
        plan = subscription_service.get_plan_details(db, plan_name)
        
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
                db.execute(reset_query, {
                    "user_id": user_id, 
                    "question_id": question_id
                })
                db.commit()
                
                # Return fresh token limits
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
                logger.error(f"Error resetting question token usage: {str(e)}")
                db.rollback()
        
        # Check current usage for this question
        query = text("""
            SELECT 
                COALESCE(SUM(input_tokens_used), 0) as total_input,
                COALESCE(SUM(output_tokens_used), 0) as total_output
            FROM user_attempts
            WHERE user_id = :user_id AND question_id = :question_id
        """)
        
        result = db.execute(query, {
            "user_id": user_id, 
            "question_id": question_id
        }).fetchone()
        
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