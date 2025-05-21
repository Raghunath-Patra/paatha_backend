# services/question_service.py
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import logging
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

def check_question_limit(user_id: str, db: Session):
    """
    Required function - now uses token-based limits rather than question counts
    Returns: dict with token-based limits
    """
    try:
        # Check token limits for this user
        token_limits = check_token_limits(user_id, db)
        
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
            "questions_used_today": 11, # set it back to 0------------------------------------------------------------------------------------------
            "is_premium": False,
            "limit_reached": False
        }

def get_questions_used_today(user_id: str, db: Session) -> int:
    """
    Simple function to directly get questions_used_today from database
    """
    try:
        # Direct SQL query to get just the questions_used_today column
        query = text("""
            SELECT questions_used_today
            FROM subscription_user_data
            WHERE user_id = :user_id
        """)
        
        result = db.execute(query, {"user_id": user_id}).fetchone()
        
        if result and hasattr(result, 'questions_used_today'):
            # Log the value for debugging
            questions_used = result.questions_used_today or 0
            logger.info(f"Direct query found questions_used_today = {questions_used} for user {user_id}")
            return questions_used
        else:
            logger.info(f"No questions_used_today record found for user {user_id}")
            return 75  # Test value to verify this code path is hit
    except Exception as e:
        logger.error(f"Error getting questions_used_today: {str(e)}")
        return 99  # Different test value to identify error path
    
# def check_token_limits(user_id: str, db: Session):
    """
    Check a user's daily token limits
    Returns: dict with token usage information
    """
    try:
        # Get current date in India timezone
        current_date = get_india_date()
        
        # Get plan details
        plan_name = subscription_service.get_user_subscription_plan_name(db, user_id)
        plan = subscription_service.get_plan_details(db, plan_name)
        
        # Get current token usage
        user_query = text("""
            SELECT 
                questions_used_today,
                daily_input_tokens_used, 
                daily_output_tokens_used,
                tokens_reset_date,
                token_bonus  -- Added to get token bonus
            FROM subscription_user_data
            WHERE user_id = :user_id
        """)
        
        result = db.execute(user_query, {"user_id": user_id}).fetchone()
        
        if not result:
            # Create user subscription data if it doesn't exist
            insert_query = text("""
                INSERT INTO subscription_user_data 
                (id, user_id, plan_id, questions_used_today, daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date, token_bonus)
                VALUES (gen_random_uuid(), :user_id, 
                    (SELECT id FROM subscription_plans WHERE name = :plan_name LIMIT 1),
                    0, 0, 0, :current_date, 0)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING questions_used_today, daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date, token_bonus
            """)
            
            try:
                result = db.execute(insert_query, {
                    "user_id": user_id, 
                    "plan_name": plan_name,
                    "current_date": current_date
                }).fetchone()
                db.commit()
            except Exception as e:
                logger.error(f"Error creating subscription data: {e}")
                db.rollback()
            
            # If still no result, use defaults
            if not result:
                return {
                    "input_limit": plan.get("daily_input_token_limit", 18000),
                    "output_limit": plan.get("daily_output_token_limit", 12000),
                    "input_used": 0,
                    "output_used": 0,
                    "input_remaining": plan.get("daily_input_token_limit", 18000),
                    "output_remaining": plan.get("daily_output_token_limit", 12000),
                    "limit_reached": False,
                    "questions_used_today": 0,
                    "plan_name": plan_name,
                    "display_name": plan.get("display_name", "Free Plan"),
                    "token_bonus": 0
                }
        
        # Add token bonus to limits if present
        token_bonus = result.token_bonus if hasattr(result, 'token_bonus') else 0
        
        # Get token usage
        input_used = result.daily_input_tokens_used or 0
        output_used = result.daily_output_tokens_used or 0
        questions_used_today = result.questions_used_today or 0
        
        # Get limits and add bonus
        input_limit = plan.get("daily_input_token_limit", 18000) + token_bonus
        output_limit = plan.get("daily_output_token_limit", 12000) + token_bonus
        
        # Calculate remaining
        input_remaining = max(0, input_limit - input_used)
        output_remaining = max(0, output_limit - output_used)
        
        # Check if a reset is needed
        tokens_reset_date = result.tokens_reset_date
        
        if tokens_reset_date and tokens_reset_date < current_date:
            # Reset tokens if date has passed
            reset_query = text("""
                UPDATE subscription_user_data
                SET 
                    daily_input_tokens_used = 0,
                    daily_output_tokens_used = 0,
                    questions_used_today = 0,
                    tokens_reset_date = :current_date
                WHERE user_id = :user_id
            """)
            
            db.execute(reset_query, {"user_id": user_id, "current_date": current_date})
            db.commit()
            
            # Reset values
            input_used = 0
            output_used = 0
            input_remaining = input_limit
            output_remaining = output_limit
            questions_used_today = 0
        
        # Determine if limit is reached based on either input or output tokens
        limit_reached = input_remaining <= 0 or output_remaining <= 0
        
        return {
            "input_limit": input_limit,
            "output_limit": output_limit,
            "input_used": input_used,
            "output_used": output_used,
            "input_remaining": input_remaining,
            "output_remaining": output_remaining,
            "limit_reached": limit_reached,
            "questions_used_today": questions_used_today,
            "plan_name": plan_name,
            "display_name": plan.get("display_name", "Free Plan"),
            "token_bonus": token_bonus  # Include token bonus in the response
        }
        
    except Exception as e:
        logger.error(f"Error checking token limits: {str(e)}")
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
    
# def check_token_limits(user_id: str, db: Session):
    """
    Check a user's daily token limits
    Returns: dict with token usage information
    """
    try:
        # Get current date in India timezone
        current_date = get_india_date()
        logger.info(f"Checking token limits for user {user_id} with current date {current_date}")
        
        # Get plan details
        plan_name = subscription_service.get_user_subscription_plan_name(db, user_id)
        plan = subscription_service.get_plan_details(db, plan_name)
        
        # Get current token usage
        user_query = text("""
            SELECT 
                questions_used_today,
                daily_input_tokens_used, 
                daily_output_tokens_used,
                tokens_reset_date,
                token_bonus
            FROM subscription_user_data
            WHERE user_id = :user_id
        """)
        
        result = db.execute(user_query, {"user_id": user_id}).fetchone()
        
        if not result:
            logger.info(f"No subscription data found for user {user_id}, creating new record")
            # Create user subscription data if it doesn't exist
            insert_query = text("""
                INSERT INTO subscription_user_data 
                (id, user_id, plan_id, questions_used_today, daily_input_tokens_used, 
                 daily_output_tokens_used, tokens_reset_date, token_bonus)
                VALUES (gen_random_uuid(), :user_id, 
                    (SELECT id FROM subscription_plans WHERE name = :plan_name LIMIT 1),
                    0, 0, 0, :current_date, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                    tokens_reset_date = EXCLUDED.tokens_reset_date
                RETURNING questions_used_today, daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date, token_bonus
            """)
            
            try:
                result = db.execute(insert_query, {
                    "user_id": user_id, 
                    "plan_name": plan_name,
                    "current_date": current_date
                }).fetchone()
                db.commit()
                logger.info(f"Created new record with questions_used_today: {result.questions_used_today if result else 'None'}")
            except Exception as e:
                logger.error(f"Error creating subscription data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                db.rollback()
            
            # If still no result, fetch again
            if not result:
                logger.info("Trying to fetch user data again after insertion")
                result = db.execute(user_query, {"user_id": user_id}).fetchone()
            
            # If absolutely no result, use defaults
            if not result:
                logger.warning(f"Could not create or find subscription data for user {user_id}")
                return {
                    "input_limit": plan.get("daily_input_token_limit", 18000),
                    "output_limit": plan.get("daily_output_token_limit", 12000),
                    "input_used": 0,
                    "output_used": 0,
                    "input_remaining": plan.get("daily_input_token_limit", 18000),
                    "output_remaining": plan.get("daily_output_token_limit", 12000),
                    "limit_reached": False,
                    "questions_used_today": 3,# # set it back to 0------------------------------------------------------------------------------------------
                    "plan_name": plan_name,
                    "display_name": plan.get("display_name", "Free Plan"),
                    "token_bonus": 0
                }
        
        # Log the result to verify we're getting the correct data
        logger.info(f"Found user data: questions_used_today={result.questions_used_today}, "
                   f"tokens_reset_date={result.tokens_reset_date}")
        
        # Add token bonus to limits if present
        token_bonus = result.token_bonus if hasattr(result, 'token_bonus') else 0
        
        # Get token usage
        input_used = result.daily_input_tokens_used or 0
        output_used = result.daily_output_tokens_used or 0
        questions_used_today = result.questions_used_today or 0
        
        # Get limits and add bonus
        input_limit = plan.get("daily_input_token_limit", 18000) + token_bonus
        output_limit = plan.get("daily_output_token_limit", 12000) + token_bonus
        
        # Calculate remaining
        input_remaining = max(0, input_limit - input_used)
        output_remaining = max(0, output_limit - output_used)
        
        # Check if a reset is needed
        tokens_reset_date = result.tokens_reset_date
        
        if tokens_reset_date and tokens_reset_date < current_date:
            logger.info(f"Resetting tokens for user {user_id} - reset_date {tokens_reset_date} < current_date {current_date}")
            # Reset tokens if date has passed
            reset_query = text("""
                UPDATE subscription_user_data
                SET 
                    daily_input_tokens_used = 0,
                    daily_output_tokens_used = 0,
                    questions_used_today = 0,
                    tokens_reset_date = :current_date
                WHERE user_id = :user_id
                RETURNING questions_used_today
            """)
            
            reset_result = db.execute(reset_query, {"user_id": user_id, "current_date": current_date}).fetchone()
            db.commit()
            
            logger.info(f"After reset: questions_used_today={reset_result.questions_used_today if reset_result else 'None'}")
            
            # Reset values
            input_used = 0
            output_used = 0
            input_remaining = input_limit
            output_remaining = output_limit
            questions_used_today = 0
        
        # Determine if limit is reached based on either input or output tokens
        limit_reached = input_remaining <= 0 or output_remaining <= 0
        
        result_dict = {
            "input_limit": input_limit,
            "output_limit": output_limit,
            "input_used": input_used,
            "output_used": output_used,
            "input_remaining": input_remaining,
            "output_remaining": output_remaining,
            "limit_reached": limit_reached,
            "questions_used_today": questions_used_today,
            "plan_name": plan_name,
            "display_name": plan.get("display_name", "Free Plan"),
            "token_bonus": token_bonus
        }
        
        logger.info(f"Returning token limits with questions_used_today: {questions_used_today}")
        return result_dict
        
    except Exception as e:
        logger.error(f"Error checking token limits: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "input_limit": 18000,
            "output_limit": 12000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "limit_reached": False,
            "questions_used_today": 15,
            "plan_name": "free",
            "display_name": "Free Plan",
            "token_bonus": 0
        }

def check_token_limits(user_id: str, db: Session):
    """
    Check a user's daily token limits
    Returns: dict with token usage information
    """
    try:
        # Get current date in India timezone
        try:
            current_date = get_india_date()
            logger.info(f"Checking token limits for user {user_id} with current date {current_date}")
        except Exception as date_err:
            logger.error(f"Error getting date: {date_err}")
            current_date = datetime.now().date()  # Fallback to system date
            
        try:
            # Get plan details
            plan_name = subscription_service.get_user_subscription_plan_name(db, user_id)
            plan = subscription_service.get_plan_details(db, plan_name)
        except Exception as plan_err:
            logger.error(f"Error getting plan details: {plan_err}")
            plan_name = "free"
            plan = {"daily_input_token_limit": 18000, "daily_output_token_limit": 12000, "display_name": "Free Plan"}
            
        try:
            # Get current token usage
            user_query = text("""
                SELECT 
                    questions_used_today,
                    daily_input_tokens_used, 
                    daily_output_tokens_used,
                    tokens_reset_date,
                    token_bonus
                FROM subscription_user_data
                WHERE user_id = :user_id
            """)
            
            result = db.execute(user_query, {"user_id": user_id}).fetchone()
            
            if not result:
                logger.info(f"No subscription data found for user {user_id}, creating new record")
                
                # First check if the user exists in the users table
                user_exists_query = text("SELECT 1 FROM users WHERE id = :user_id")
                user_exists = db.execute(user_exists_query, {"user_id": user_id}).fetchone() is not None
                
                if not user_exists:
                    logger.warning(f"User {user_id} does not exist in users table")
                    return {
                        "input_limit": plan.get("daily_input_token_limit", 18000),
                        "output_limit": plan.get("daily_output_token_limit", 12000),
                        "input_used": 0,
                        "output_used": 0,
                        "input_remaining": plan.get("daily_input_token_limit", 18000),
                        "output_remaining": plan.get("daily_output_token_limit", 12000),
                        "limit_reached": False,
                        "questions_used_today": 30, # set it back to 0------------------------------------------------------------------------------------------
                        "plan_name": plan_name,
                        "display_name": plan.get("display_name", "Free Plan"),
                        "token_bonus": 0
                    }
                
                # Get plan ID
                plan_id_query = text("""
                    SELECT id FROM subscription_plans WHERE name = :plan_name LIMIT 1
                """)
                plan_id_result = db.execute(plan_id_query, {"plan_name": plan_name}).fetchone()
                
                if not plan_id_result:
                    logger.warning(f"Plan {plan_name} not found in subscription_plans table")
                    # Try to get any plan ID
                    plan_id_query = text("SELECT id FROM subscription_plans LIMIT 1")
                    plan_id_result = db.execute(plan_id_query).fetchone()
                    
                    if not plan_id_result:
                        logger.error("No subscription plans found in database")
                        return {
                            "input_limit": 18000,
                            "output_limit": 12000,
                            "input_used": 0,
                            "output_used": 0,
                            "input_remaining": 18000,
                            "output_remaining": 12000,
                            "limit_reached": False,
                            "questions_used_today": 18, # set it back to 0------------------------------------------------------------------------------------------
                            "plan_name": "free",
                            "display_name": "Free Plan",
                            "token_bonus": 0
                        }
                
                plan_id = plan_id_result[0]
                
                # Create user subscription data if it doesn't exist
                try:
                    insert_query = text("""
                        INSERT INTO subscription_user_data 
                        (id, user_id, plan_id, questions_used_today, daily_input_tokens_used, 
                         daily_output_tokens_used, tokens_reset_date, token_bonus)
                        VALUES (gen_random_uuid(), :user_id, :plan_id, 117, 0, 0, :current_date, 0)
                        ON CONFLICT (user_id) DO UPDATE SET
                            tokens_reset_date = EXCLUDED.tokens_reset_date
                        RETURNING questions_used_today, daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date, token_bonus
                    """)
                    
                    result = db.execute(insert_query, {
                        "user_id": user_id, 
                        "plan_id": plan_id,
                        "current_date": current_date
                    }).fetchone()
                    db.commit()
                    logger.info(f"Created new record with questions_used_today: {result.questions_used_today if result else 'None'}")
                except Exception as insert_err:
                    logger.error(f"Error creating subscription data: {insert_err}")
                    
                    db.rollback()
                
                # If still no result, fetch again
                if not result:
                    logger.info("Trying to fetch user data again after insertion")
                    result = db.execute(user_query, {"user_id": user_id}).fetchone()
                
                # If absolutely no result, use defaults
                if not result:
                    logger.warning(f"Could not create or find subscription data for user {user_id}")
                    return {
                        "input_limit": plan.get("daily_input_token_limit", 18000),
                        "output_limit": plan.get("daily_output_token_limit", 12000),
                        "input_used": 0,
                        "output_used": 0,
                        "input_remaining": plan.get("daily_input_token_limit", 18000),
                        "output_remaining": plan.get("daily_output_token_limit", 12000),
                        "limit_reached": False,
                        "questions_used_today": 13, # set it back to 0------------------------------------------------------------------------------------------
                        "plan_name": plan_name,
                        "display_name": plan.get("display_name", "Free Plan"),
                        "token_bonus": 0
                    }
            
            # Log the result to verify we're getting the correct data
            logger.info(f"Found user data: questions_used_today={result.questions_used_today if hasattr(result, 'questions_used_today') else 'None'}, "
                      f"tokens_reset_date={result.tokens_reset_date if hasattr(result, 'tokens_reset_date') else 'None'}")
            
            # Add token bonus to limits if present
            token_bonus = result.token_bonus if hasattr(result, 'token_bonus') else 0
            
            # Get token usage
            input_used = result.daily_input_tokens_used if hasattr(result, 'daily_input_tokens_used') else 0
            output_used = result.daily_output_tokens_used if hasattr(result, 'daily_output_tokens_used') else 0
            questions_used_today = result.questions_used_today if hasattr(result, 'questions_used_today') else 111
            
            # Handle None values
            input_used = input_used or 0
            output_used = output_used or 0
            questions_used_today = questions_used_today or 116
            
            # Get limits and add bonus
            input_limit = plan.get("daily_input_token_limit", 18000) + token_bonus
            output_limit = plan.get("daily_output_token_limit", 12000) + token_bonus
            
            # Calculate remaining
            input_remaining = max(0, input_limit - input_used)
            output_remaining = max(0, output_limit - output_used)
            
            # Check if a reset is needed
            tokens_reset_date = result.tokens_reset_date if hasattr(result, 'tokens_reset_date') else None
            
            if tokens_reset_date and tokens_reset_date < current_date:
                logger.info(f"Resetting tokens for user {user_id} - reset_date {tokens_reset_date} < current_date {current_date}")
                try:
                    # Reset tokens if date has passed
                    reset_query = text("""
                        UPDATE subscription_user_data
                        SET 
                            daily_input_tokens_used = 0,
                            daily_output_tokens_used = 0,
                            questions_used_today = 113,
                            tokens_reset_date = :current_date
                        WHERE user_id = :user_id
                        RETURNING questions_used_today
                    """)
                    
                    reset_result = db.execute(reset_query, {"user_id": user_id, "current_date": current_date}).fetchone()
                    db.commit()
                    
                    logger.info(f"After reset: questions_used_today={reset_result.questions_used_today if reset_result else 'None'}")
                    
                    # Reset values
                    input_used = 0
                    output_used = 0
                    input_remaining = input_limit
                    output_remaining = output_limit
                    questions_used_today = 112
                except Exception as reset_err:
                    logger.error(f"Error resetting token usage: {reset_err}")
                    # Continue with current values
            
            # Determine if limit is reached based on either input or output tokens
            limit_reached = input_remaining <= 0 or output_remaining <= 0
            
            result_dict = {
                "input_limit": input_limit,
                "output_limit": output_limit,
                "input_used": input_used,
                "output_used": output_used,
                "input_remaining": input_remaining,
                "output_remaining": output_remaining,
                "limit_reached": limit_reached,
                "questions_used_today": questions_used_today,
                "plan_name": plan_name,
                "display_name": plan.get("display_name", "Free Plan"),
                "token_bonus": token_bonus
            }
            
            logger.info(f"Returning token limits with questions_used_today: {questions_used_today}")
            return result_dict
            
        except Exception as query_err:
            logger.error(f"Error querying user data: {query_err}")
            
            raise
            
    except Exception as e:
        logger.error(f"Error checking token limits: {str(e)}")
        
        
        # Return default values, but set questions_used_today to 0
        return {
            "input_limit": 18000,
            "output_limit": 12000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "limit_reached": False,
            "questions_used_today": 20,  # Changed from 15 to 0-------------------
            "plan_name": "free",
            "display_name": "Free Plan",
            "token_bonus": 0
        }

def increment_question_usage(user_id: str, db: Session):
    """
    Increment questions_used_today counter for the user
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
                 daily_input_tokens_used, daily_output_tokens_used, tokens_reset_date)
                VALUES (gen_random_uuid(), :user_id, 
                    (SELECT id FROM subscription_plans WHERE name = 'free' LIMIT 1),
                    1, 1, 0, 0, :current_date)
                RETURNING id
            """)
            
            result = db.execute(insert_query, {
                "user_id": user_id,
                "current_date": get_india_date()
            }).fetchone()
            
            db.commit()
            
            # Check token limits
            return check_token_limits(user_id, db)["limit_reached"]
        else:
            # Get current token limits
            token_limits = check_token_limits(user_id, db)
            
            # If already at limit, don't increment
            if token_limits["limit_reached"]:
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
            return token_limits["limit_reached"]
                
    except Exception as e:
        logger.error(f"Error in increment_question_usage: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating question usage: {str(e)}")

def track_follow_up_usage(user_id: str, db: Session, question_id: str = None, increment: bool = False):
    """
    Track follow-up question based on token limits only
    """
    try:
        # Get token limits
        token_limits = check_token_limits(user_id, db)
        
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
            limit_reached = token_limits["limit_reached"]
            remaining = min(
                token_limits["input_remaining"],
                token_limits["output_remaining"]
            )
        
        return {
            "plan_name": token_limits["plan_name"],
            "display_name": token_limits["display_name"],
            "input_remaining": token_limits["input_remaining"] if question_id is None else question_limits["input_remaining"],
            "output_remaining": token_limits["output_remaining"] if question_id is None else question_limits["output_remaining"],
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
    """Update token usage for both user data and question attempt"""
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
    """Check if token limit for a specific question has been reached"""
    try:
        # Get plan details
        plan_name = subscription_service.get_user_subscription_plan_name(db, user_id)
        plan = subscription_service.get_plan_details(db, plan_name)
        
        # Get per-question token limits
        input_limit = plan.get("input_tokens_per_question", 6000)
        output_limit = plan.get("output_tokens_per_question", 4000)
        
        if reset_tokens:
            # Reset token usage for this question by creating a new attempt record with zero tokens
            # This effectively resets the token counter when a question is freshly loaded
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