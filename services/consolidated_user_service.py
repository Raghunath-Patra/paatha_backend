# backend/services/consolidated_user_service.py - CORRECTED VERSION - UPDATE only for existing users

from datetime import datetime, date, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging
import traceback

logger = logging.getLogger(__name__)

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

def get_india_date():
    """Get current date in India timezone"""
    return get_india_time().date()

class ConsolidatedUserService:
    """Single service that handles ALL user status and updates efficiently"""
    
    @staticmethod
    def get_comprehensive_user_status(user_id: str, db: Session) -> Dict[str, Any]:
        """
        SINGLE DATABASE CALL to get ALL user status information
        Creates user records if they don't exist
        Returns everything frontend needs in one go
        """
        try:
            current_date = get_india_date()
            
            # ONE comprehensive query that gets everything we need
            query = text("""
                WITH user_data AS (
                    SELECT 
                        p.id as user_id,
                        p.is_premium,
                        p.subscription_plan_id,
                        COALESCE(sud.questions_used_today, 0) as questions_used_today,
                        COALESCE(sud.questions_used_this_month, 0) as questions_used_this_month,
                        COALESCE(sud.daily_input_tokens_used, 0) as daily_input_tokens_used,
                        COALESCE(sud.daily_output_tokens_used, 0) as daily_output_tokens_used,
                        COALESCE(sud.tokens_reset_date, :current_date) as tokens_reset_date,
                        COALESCE(sud.token_bonus, 0) as token_bonus,
                        COALESCE(sud.is_yearly, false) as is_yearly,
                        COALESCE(sud.subscription_start_date, null) as subscription_start_date,
                        COALESCE(sud.subscription_expires_at, null) as subscription_expires_at,
                        sud.plan_id as subscription_plan_id_from_data,
                        CASE WHEN sud.user_id IS NULL THEN true ELSE false END as needs_subscription_data_creation
                    FROM profiles p
                    LEFT JOIN subscription_user_data sud ON p.id = sud.user_id
                    WHERE p.id = :user_id
                ),
                plan_data AS (
                    SELECT 
                        ud.*,
                        COALESCE(sp.id, free_plan.id) as plan_id,
                        COALESCE(sp.name, free_plan.name) as plan_name,
                        COALESCE(sp.display_name, free_plan.display_name) as display_name,
                        COALESCE(sp.carry_forward, free_plan.carry_forward) as carry_forward,
                        COALESCE(sp.daily_input_token_limit, free_plan.daily_input_token_limit) as daily_input_token_limit,
                        COALESCE(sp.daily_output_token_limit, free_plan.daily_output_token_limit) as daily_output_token_limit,
                        COALESCE(sp.input_tokens_per_question, free_plan.input_tokens_per_question) as input_tokens_per_question,
                        COALESCE(sp.output_tokens_per_question, free_plan.output_tokens_per_question) as output_tokens_per_question,
                        COALESCE(sp.input_token_buffer, free_plan.input_token_buffer, 1000) as input_token_buffer
                    FROM user_data ud
                    LEFT JOIN subscription_plans sp ON (
                        ud.subscription_plan_id_from_data = sp.id OR 
                        ud.subscription_plan_id = sp.id
                    ) AND sp.is_active = true
                    CROSS JOIN (
                        SELECT * FROM subscription_plans 
                        WHERE name = 'free' AND is_active = true 
                        LIMIT 1
                    ) free_plan
                )
                SELECT * FROM plan_data
            """)
            
            result = db.execute(query, {
                "user_id": user_id, 
                "current_date": current_date
            }).fetchone()
            
            if not result:
                # User doesn't exist in profiles table at all
                logger.warning(f"User {user_id} not found in profiles table")
                return ConsolidatedUserService._get_default_status(user_id)
                
            # Check if we need to create subscription_user_data record
            if result.needs_subscription_data_creation:
                logger.info(f"Creating subscription_user_data record for new user {user_id}")
                success = ConsolidatedUserService._create_user_subscription_data(user_id, current_date, db)
                
                if success:
                    # Re-query to get the created data
                    result = db.execute(query, {
                        "user_id": user_id, 
                        "current_date": current_date
                    }).fetchone()
                    
                    if not result:
                        logger.error(f"Failed to retrieve user data after creation for {user_id}")
                        return ConsolidatedUserService._get_default_status(user_id)
                else:
                    logger.error(f"Failed to create user data for {user_id}")
                    return ConsolidatedUserService._get_default_status(user_id)
            
            # Check if daily reset is needed
            needs_reset = result.tokens_reset_date < current_date
            
            # Calculate actual usage (with reset if needed)
            actual_input_used = 0 if needs_reset else result.daily_input_tokens_used
            actual_output_used = 0 if needs_reset else result.daily_output_tokens_used
            actual_questions_used = 0 if needs_reset else result.questions_used_today
            
            # Apply reset if needed (immediate database update)
            if needs_reset:
                ConsolidatedUserService._perform_daily_reset(user_id, current_date, db)
            
            # Calculate limits with bonus
            input_limit = result.daily_input_token_limit + result.token_bonus
            output_limit = result.daily_output_token_limit + result.token_bonus
            
            # Calculate remaining
            input_remaining = max(0, input_limit - actual_input_used)
            output_remaining = max(0, output_limit - actual_output_used)
            
            # Determine if limit is reached
            limit_reached = input_remaining <= 0 or output_remaining <= 0
            
            # Build comprehensive response
            status = {
                # Core identification
                "user_id": user_id,
                "plan_name": result.plan_name,
                "display_name": result.display_name,
                "is_premium": result.is_premium or result.plan_name != "free",
                
                # Token limits and usage
                "input_limit": input_limit,
                "output_limit": output_limit,
                "input_used": actual_input_used,
                "output_used": actual_output_used,
                "input_remaining": input_remaining,
                "output_remaining": output_remaining,
                
                # Question usage
                "questions_used_today": actual_questions_used,
                "questions_used_this_month": result.questions_used_this_month,
                
                # Per-question limits
                "input_tokens_per_question": result.input_tokens_per_question,
                "output_tokens_per_question": result.output_tokens_per_question,
                "input_token_buffer": result.input_token_buffer,
                
                # Status flags
                "limit_reached": limit_reached,
                "carry_forward": result.carry_forward,
                "token_bonus": result.token_bonus,
                
                # Subscription info
                "is_yearly": result.is_yearly,
                "subscription_start_date": result.subscription_start_date.isoformat() if result.subscription_start_date else None,
                "subscription_expires_at": result.subscription_expires_at.isoformat() if result.subscription_expires_at else None,
                
                # Metadata
                "tokens_reset_date": result.tokens_reset_date.isoformat() if result.tokens_reset_date else current_date.isoformat(),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Comprehensive user status retrieved: user={user_id}, "
                       f"plan={status['plan_name']}, questions_used={status['questions_used_today']}, "
                       f"limit_reached={status['limit_reached']}")
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting comprehensive user status: {str(e)}")
            logger.error(traceback.format_exc())
            return ConsolidatedUserService._get_default_status(user_id)
    
    @staticmethod
    def _get_default_status(user_id: str = "") -> Dict[str, Any]:
        """Return safe default status when errors occur"""
        return {
            "user_id": user_id,
            "plan_name": "free",
            "display_name": "Free Plan",
            "is_premium": False,
            "input_limit": 18000,
            "output_limit": 12000,
            "input_used": 0,
            "output_used": 0,
            "input_remaining": 18000,
            "output_remaining": 12000,
            "questions_used_today": 0,
            "questions_used_this_month": 0,
            "input_tokens_per_question": 6000,
            "output_tokens_per_question": 4000,
            "input_token_buffer": 1000,
            "limit_reached": False,
            "carry_forward": False,
            "token_bonus": 0,
            "is_yearly": False,
            "subscription_start_date": None,
            "subscription_expires_at": None,
            "tokens_reset_date": get_india_date().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def _create_user_subscription_data(user_id: str, current_date: date, db: Session) -> bool:
        """Create subscription_user_data record for new user - INSERT ONLY"""
        try:
            # Get free plan ID
            free_plan_query = text("""
                SELECT id FROM subscription_plans 
                WHERE name = 'free' AND is_active = true 
                LIMIT 1
            """)
            
            free_plan_result = db.execute(free_plan_query).fetchone()
            
            if not free_plan_result:
                logger.error("Free plan not found in database")
                return False
                
            free_plan_id = free_plan_result.id
            
            # SIMPLE INSERT - no ON CONFLICT needed since this is only for new users
            create_query = text("""
                INSERT INTO subscription_user_data (
                    id, user_id, plan_id, tokens_reset_date,
                    questions_used_today, questions_used_this_month,
                    daily_input_tokens_used, daily_output_tokens_used,
                    token_bonus, is_yearly
                ) VALUES (
                    gen_random_uuid(), :user_id, :plan_id, :current_date,
                    0, 0, 0, 0, 0, false
                )
            """)
            
            db.execute(create_query, {
                "user_id": user_id,
                "plan_id": free_plan_id,
                "current_date": current_date
            })
            
            db.commit()
            logger.info(f"✅ Created subscription_user_data record for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating subscription_user_data for user {user_id}: {str(e)}")
            logger.error(traceback.format_exc())
            db.rollback()
            return False

    @staticmethod
    def _perform_daily_reset(user_id: str, current_date: date, db: Session):
        """Perform daily reset - SIMPLE UPDATE only"""
        try:
            # SIMPLE UPDATE - user already exists
            reset_query = text("""
                UPDATE subscription_user_data
                SET 
                    questions_used_today = 0,
                    daily_input_tokens_used = 0,
                    daily_output_tokens_used = 0,
                    tokens_reset_date = :current_date
                WHERE user_id = :user_id
            """)
            
            result = db.execute(reset_query, {"user_id": user_id, "current_date": current_date})
            
            if result.rowcount > 0:
                db.commit()
                logger.info(f"✅ Daily reset completed for user {user_id}")
            else:
                logger.warning(f"⚠️ No rows updated during daily reset for user {user_id}")
                
        except Exception as e:
            logger.error(f"❌ Error in daily reset for user {user_id}: {str(e)}")
            logger.error(traceback.format_exc())
            db.rollback()

    @staticmethod
    def update_user_usage_immediate(user_id: str, question_id: str, input_tokens: int, output_tokens: int, question_submitted: bool = False, db: Session = None):
        """
        CORRECTED: Simple UPDATE only - no INSERT attempts
        User must already exist in subscription_user_data table
        """
        try:
            if db is None:
                logger.error("No database session provided to update_user_usage_immediate")
                return False
                
            current_date = get_india_date()
            
            # Check if user exists (should always exist by this point)
            check_query = text("""
                SELECT id, tokens_reset_date FROM subscription_user_data 
                WHERE user_id = :user_id
            """)
            
            user_record = db.execute(check_query, {"user_id": user_id}).fetchone()
            
            if not user_record:
                logger.error(f"❌ User {user_id} not found in subscription_user_data during usage update")
                # This should not happen if get_comprehensive_user_status was called first
                return False
            
            # Check if daily reset is needed
            needs_reset = user_record.tokens_reset_date < current_date
            
            if needs_reset:
                # Reset first, then update
                logger.info(f"🔄 Performing daily reset during usage update for user {user_id}")
                ConsolidatedUserService._perform_daily_reset(user_id, current_date, db)
                
                # After reset, set new usage values (not increment)
                update_query = text("""
                    UPDATE subscription_user_data
                    SET 
                        questions_used_today = CASE WHEN :question_submitted THEN 1 ELSE 0 END,
                        questions_used_this_month = questions_used_this_month + CASE WHEN :question_submitted THEN 1 ELSE 0 END,
                        daily_input_tokens_used = :input_tokens,
                        daily_output_tokens_used = :output_tokens,
                        tokens_reset_date = :current_date
                    WHERE user_id = :user_id
                """)
            else:
                # Normal increment update
                update_query = text("""
                    UPDATE subscription_user_data
                    SET 
                        questions_used_today = questions_used_today + CASE WHEN :question_submitted THEN 1 ELSE 0 END,
                        questions_used_this_month = questions_used_this_month + CASE WHEN :question_submitted THEN 1 ELSE 0 END,
                        daily_input_tokens_used = daily_input_tokens_used + :input_tokens,
                        daily_output_tokens_used = daily_output_tokens_used + :output_tokens
                    WHERE user_id = :user_id
                """)
            
            result = db.execute(update_query, {
                "user_id": user_id,
                "current_date": current_date,
                "question_submitted": question_submitted,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            })
            
            if result.rowcount == 0:
                logger.error(f"❌ No rows updated for user {user_id} usage update")
                return False
            
            # Update user_attempts table if question_id provided
            if question_id:
                attempt_update = text("""
                    UPDATE user_attempts 
                    SET 
                        input_tokens_used = COALESCE(input_tokens_used, 0) + :input_tokens,
                        output_tokens_used = COALESCE(output_tokens_used, 0) + :output_tokens
                    WHERE user_id = :user_id AND question_id = :question_id
                    AND created_at = (
                        SELECT MAX(created_at) FROM user_attempts 
                        WHERE user_id = :user_id AND question_id = :question_id
                    )
                """)
                
                db.execute(attempt_update, {
                    "user_id": user_id,
                    "question_id": question_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                })
            
            db.commit()
            logger.info(f"✅ Usage update completed: user={user_id}, "
                       f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
                       f"question_submitted={question_submitted}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in immediate usage update for user {user_id}: {str(e)}")
            logger.error(traceback.format_exc())
            try:
                db.rollback()
            except:
                pass
            return False
    
    @staticmethod
    def check_can_perform_action(status: Dict[str, Any], action: str) -> Dict[str, Any]:
        """
        Check if user can perform action based on comprehensive status
        No database calls needed - uses already fetched data
        """
        try:
            if status["limit_reached"]:
                return {
                    "allowed": False,
                    "reason": "Daily usage limit reached",
                    "limit_info": {
                        "input_remaining": status["input_remaining"],
                        "output_remaining": status["output_remaining"],
                        "questions_used_today": status["questions_used_today"]
                    }
                }
            
            # Action-specific token requirements
            token_requirements = {
                "fetch_question": {"input": 50, "output": 0},
                "submit_answer": {"input": 200, "output": 150},
                "follow_up_chat": {"input": 100, "output": 100}
            }
            
            required = token_requirements.get(action, {"input": 0, "output": 0})
            
            if (status["input_remaining"] < required["input"] or 
                status["output_remaining"] < required["output"]):
                return {
                    "allowed": False,
                    "reason": f"Insufficient tokens for {action}",
                    "required": required,
                    "available": {
                        "input": status["input_remaining"],
                        "output": status["output_remaining"]
                    }
                }
            
            return {
                "allowed": True,
                "tokens_required": required,
                "tokens_available": {
                    "input": status["input_remaining"],
                    "output": status["output_remaining"]
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking action permission: {str(e)}")
            return {"allowed": True}  # Optimistic fallback

# Singleton instance
consolidated_service = ConsolidatedUserService()