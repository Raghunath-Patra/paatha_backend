# File: backend/services/subscription_service.py - FIXED for actual table schema

from datetime import datetime, date, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Dict, Any
import logging
import traceback

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

class SubscriptionService:
    """Service for managing user subscriptions and token usage limits"""
    
    @staticmethod
    def get_plan_details(db: Session, plan_name: str = "free") -> Dict[str, Any]:
        """Get details for a specific subscription plan"""
        try:
            # Check if plan_name is either "free" or "premium"
            if plan_name not in ["free", "premium"]:
                logger.warning(f"Plan {plan_name} not supported, falling back to free plan")
                plan_name = "free"
                
            # Try to get plan from database first
            query = text("""
                SELECT * FROM subscription_plans 
                WHERE name = :plan_name AND is_active = TRUE
                LIMIT 1
            """)
            
            result = db.execute(query, {"plan_name": plan_name}).fetchone()
            
            if result:
                # Convert DB row to dictionary
                plan = {col: getattr(result, col) for col in result._mapping.keys()}
                return plan
            
            # If not found in database, return hardcoded defaults
            logger.warning(f"Plan {plan_name} not found in database, using defaults")
            
            if plan_name == "free":
                return {
                    "id": None,
                    "name": "free",
                    "display_name": "Free Plan",
                    "daily_input_token_limit": 18000,
                    "daily_output_token_limit": 12000,
                    "input_tokens_per_question": 6000,
                    "output_tokens_per_question": 4000,
                    "input_token_buffer": 1000
                }
            else:  # premium plan
                return {
                    "id": None,
                    "name": "premium",
                    "display_name": "Premium Plan",
                    "daily_input_token_limit": 36000,  # Increased for premium
                    "daily_output_token_limit": 24000,
                    "input_tokens_per_question": 12000,
                    "output_tokens_per_question": 8000,
                    "monthly_price": 29900,
                    "yearly_price": 299900,
                    "six_month_price": 159900,
                    "input_token_buffer": 1000
                }
        except Exception as e:
            logger.error(f"Error fetching plan details: {str(e)}")
            logger.error(traceback.format_exc())
            # Return a minimal default plan as fallback
            return {
                "id": None,
                "name": "free",
                "display_name": "Free Plan",
                "daily_input_token_limit": 18000,
                "daily_output_token_limit": 12000,
                "input_tokens_per_question": 6000,
                "output_tokens_per_question": 4000,
                "input_token_buffer": 1000
            }

    @staticmethod
    def get_user_subscription_data(db: Session, user_id: str) -> Dict[str, Any]:
        """Get subscription data for a user - FIXED for actual schema"""
        try:
            # Get the user profile
            profile_query = text("""
                SELECT 
                    id, 
                    is_premium, 
                    subscription_plan_id
                FROM profiles
                WHERE id = :user_id
            """)
            
            profile_result = db.execute(profile_query, {"user_id": user_id}).fetchone()
            
            if not profile_result:
                # If no user found, return default minimal data
                return {
                    "user_id": user_id,
                    "plan_id": None,
                    "questions_used_today": 0,
                    "daily_input_tokens_used": 0,
                    "daily_output_tokens_used": 0,
                    "tokens_reset_date": get_india_date(),
                    "is_yearly": False
                }
            
            # Try to get subscription data - FIXED: removed questions_used_this_month
            subscription_query = text("""
                SELECT 
                    plan_id,
                    questions_used_today,
                    daily_input_tokens_used,
                    daily_output_tokens_used,
                    tokens_reset_date,
                    is_yearly,
                    subscription_start_date,
                    subscription_expires_at
                FROM subscription_user_data
                WHERE user_id = :user_id
            """)
            
            subscription_result = db.execute(subscription_query, {"user_id": user_id}).fetchone()
            
            # Initialize data with defaults
            subscription = {
                "user_id": user_id,
                "is_premium": profile_result.is_premium,
                "subscription_plan_id": profile_result.subscription_plan_id,
                "questions_used_today": 0,
                "daily_input_tokens_used": 0,
                "daily_output_tokens_used": 0,
                "tokens_reset_date": get_india_date(),
                "is_yearly": False,
                "plan_id": profile_result.subscription_plan_id
            }
            
            # If subscription data exists, update values
            if subscription_result:
                subscription.update({
                    "questions_used_today": subscription_result.questions_used_today or 0,
                    "daily_input_tokens_used": subscription_result.daily_input_tokens_used or 0,
                    "daily_output_tokens_used": subscription_result.daily_output_tokens_used or 0,
                    "tokens_reset_date": subscription_result.tokens_reset_date or get_india_date(),
                    "is_yearly": subscription_result.is_yearly or False,
                    "plan_id": subscription_result.plan_id or profile_result.subscription_plan_id,
                    "subscription_start_date": subscription_result.subscription_start_date,
                    "subscription_expires_at": subscription_result.subscription_expires_at
                })
            
            # Get current date in India timezone
            current_india_date = get_india_date()
            
            # Check if daily reset is needed
            if subscription["tokens_reset_date"] < current_india_date:
                # Reset daily counters
                reset_query = text("""
                    UPDATE subscription_user_data
                    SET 
                        questions_used_today = 0,
                        daily_input_tokens_used = 0,
                        daily_output_tokens_used = 0,
                        tokens_reset_date = :current_date
                    WHERE user_id = :user_id
                """)
                
                db.execute(reset_query, {
                    "user_id": user_id,
                    "current_date": current_india_date
                })
                
                # Reset these values in the returned dictionary
                subscription["questions_used_today"] = 0
                subscription["daily_input_tokens_used"] = 0
                subscription["daily_output_tokens_used"] = 0
                subscription["tokens_reset_date"] = current_india_date
            
            # Commit changes
            db.commit()
            
            return subscription
            
        except Exception as e:
            logger.error(f"Error getting user subscription data: {str(e)}")
            logger.error(traceback.format_exc())
            db.rollback()
            
            # Return minimal default data
            return {
                "user_id": user_id,
                "plan_id": None,
                "questions_used_today": 0,
                "daily_input_tokens_used": 0,
                "daily_output_tokens_used": 0,
                "tokens_reset_date": get_india_date(),
                "is_yearly": False
            }
            

    @staticmethod
    def check_daily_token_limits(db: Session, user_id: str) -> Dict[str, Any]:
        """
        Check a user's daily token limits
        Returns information about token usage and limits
        """
        try:
            # Get user's subscription data
            subscription = SubscriptionService.get_user_subscription_data(db, user_id)
            
            # Get plan details
            plan = SubscriptionService.get_plan_details(db, SubscriptionService.get_user_subscription_plan_name(db, user_id))
            
            # Get the total token limits from the plan (not from profiles)
            daily_input_limit = plan.get("daily_input_token_limit", 18000)
            daily_output_limit = plan.get("daily_output_token_limit", 12000)
            
            # Get current token usage from subscription_user_data
            daily_input_used = subscription.get("daily_input_tokens_used", 0)
            daily_output_used = subscription.get("daily_output_tokens_used", 0)
            questions_used_today = subscription.get("questions_used_today", 0)
            
            # Calculate remaining tokens
            input_remaining = max(0, daily_input_limit - daily_input_used)
            output_remaining = max(0, daily_output_limit - daily_output_used)
            
            # Determine if limit is reached
            limit_reached = input_remaining <= 0 or output_remaining <= 0
            
            return {
                "plan_name": plan.get("name", "free"),
                "display_name": plan.get("display_name", "Free Plan"),
                "input_limit": daily_input_limit,
                "output_limit": daily_output_limit,
                "input_used": daily_input_used,
                "output_used": daily_output_used,
                "input_remaining": input_remaining,
                "output_remaining": output_remaining,
                "questions_used_today": questions_used_today,
                "limit_reached": limit_reached,
                "is_premium": plan.get("name") == "premium"
            }
                
        except Exception as e:
            logger.error(f"Error checking daily token limits: {str(e)}")
            logger.error(traceback.format_exc())
                
            # Return default values
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
    
    @staticmethod
    def change_user_plan(db: Session, user_id: str, plan_name: str) -> Dict[str, Any]:
        """Change a user's subscription plan"""
        try:
            # Get the target plan
            plan = SubscriptionService.get_plan_details(db, plan_name)
            
            if not plan["id"]:
                # Get the plan ID from the database
                plan_query = text("""
                    SELECT id FROM subscription_plans
                    WHERE name = :plan_name AND is_active = TRUE
                    LIMIT 1
                """)
                
                plan_result = db.execute(plan_query, {"plan_name": plan_name}).fetchone()
                
                if not plan_result:
                    raise HTTPException(status_code=404, detail=f"Plan {plan_name} not found")
                
                plan_id = plan_result.id
            else:
                plan_id = plan["id"]
            
            # Update subscription data
            update_subscription = text("""
                UPDATE subscription_user_data
                SET 
                    plan_id = :plan_id,
                    updated_at = NOW()
                WHERE user_id = :user_id
                RETURNING *
            """)
            
            result = db.execute(
                update_subscription, 
                {"user_id": user_id, "plan_id": plan_id}
            ).fetchone()
            
            if not result:
                # Create new subscription record
                # Get current date in India timezone
                india_date = get_india_date()
                
                insert_query = text("""
                    INSERT INTO subscription_user_data 
                    (id, user_id, plan_id, tokens_reset_date)
                    VALUES (gen_random_uuid(), :user_id, :plan_id, :india_date)
                    RETURNING *
                """)
                
                result = db.execute(
                    insert_query, 
                    {"user_id": user_id, "plan_id": plan_id, "india_date": india_date}
                ).fetchone()
            
            # Also update the profile
            update_profile = text("""
                UPDATE profiles
                SET subscription_plan_id = :plan_id
                WHERE id = :user_id
            """)
            
            db.execute(update_profile, {"user_id": user_id, "plan_id": plan_id})
            db.commit()
            
            # Convert DB row to dictionary
            updated_subscription = {col: getattr(result, col) for col in result._mapping.keys()}
            return {**updated_subscription, "plan": plan}
            
        except HTTPException as he:
            raise he
        except Exception as e:
            db.rollback()
            logger.error(f"Error changing user plan: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error updating subscription plan: {str(e)}"
            )
    
    @staticmethod
    def get_user_subscription_plan_name(db: Session, user_id: str) -> str:
        """Get the current subscription plan name for a user"""
        try:
            # First try to get plan from subscription_user_data
            subscription_query = text("""
                SELECT sp.name 
                FROM subscription_user_data sud
                JOIN subscription_plans sp ON sud.plan_id = sp.id
                WHERE sud.user_id = :user_id
            """)
            
            result = db.execute(subscription_query, {"user_id": user_id}).fetchone()
            
            if result and result.name:
                return result.name
                
            # If not found in subscription_user_data, check if user is premium
            user_query = text("""
                SELECT is_premium
                FROM profiles
                WHERE id = :user_id
            """)
            
            user_result = db.execute(user_query, {"user_id": user_id}).fetchone()
            
            if user_result and user_result.is_premium:
                return "premium"
                
            # Default to free plan
            return "free"
            
        except Exception as e:
            logger.error(f"Error getting user subscription plan name: {str(e)}")
            return "free"  # Default to free plan on error


# Singleton instance
subscription_service = SubscriptionService()