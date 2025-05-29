# File: backend/routes/subscriptions.py - FIXED for actual table schema

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from services.subscription_service import subscription_service
from sqlalchemy import text
from datetime import datetime

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

class PlanResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    monthly_price: int
    yearly_price: int
    monthly_question_limit: int
    monthly_chat_limit: int
    requests_per_question: int
    follow_up_questions_per_day: int
    features: Dict[str, Any]

class UserSubscriptionResponse(BaseModel):
    plan_name: str
    display_name: str
    is_active: bool
    is_yearly: bool
    monthly_question_limit: int
    monthly_chat_limit: int
    questions_used: int
    questions_remaining: int
    chat_requests_used: int
    chat_requests_remaining: int
    follow_up_questions_per_day: int
    follow_up_questions_used_today: int
    follow_up_questions_remaining: int
    subscription_expires_at: Optional[str] = None

class ChangePlanRequest(BaseModel):
    plan_name: str

@router.get("/plans", response_model=List[PlanResponse])
async def get_subscription_plans(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available subscription plans"""
    try:
        # Query all active plans
        query = text("""
            SELECT * FROM subscription_plans
            WHERE is_active = TRUE
            ORDER BY monthly_price ASC
        """)
        
        plans = db.execute(query).fetchall()
        
        # Convert to dictionary list
        return [
            {
                "id": str(plan.id),
                "name": plan.name,
                "display_name": plan.display_name,
                "description": plan.description,
                "monthly_price": plan.monthly_price,
                "yearly_price": plan.yearly_price,
                "monthly_question_limit": plan.monthly_question_limit,
                "monthly_chat_limit": plan.monthly_chat_limit,
                "requests_per_question": plan.requests_per_question,
                "follow_up_questions_per_day": plan.follow_up_questions_per_day,
                "features": plan.features or {}
            }
            for plan in plans
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching subscription plans: {str(e)}"
        )

@router.get("/status", response_model=UserSubscriptionResponse)
async def get_user_subscription_status(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's subscription status - FIXED for actual schema"""
    try:
        # Get user's subscription data
        user_id = current_user["id"]
        subscription = subscription_service.get_user_subscription_data(db, user_id)
        
        # Get plan details
        plan_query = text("""
            SELECT * FROM subscription_plans 
            WHERE id = :plan_id AND is_active = TRUE
        """)
        
        plan_result = db.execute(plan_query, {"plan_id": subscription["plan_id"]}).fetchone()
        
        if not plan_result:
            # Fallback to free plan
            plan = subscription_service.get_plan_details(db, "free")
        else:
            # Convert DB row to dictionary
            plan = {col: getattr(plan_result, col) for col in plan_result._mapping.keys()}
        
        # Check if subscription is active
        is_active = True
        subscription_expires_at = None
        if subscription.get("subscription_expires_at"):
            subscription_expires_at = subscription["subscription_expires_at"].isoformat()
            is_active = subscription["subscription_expires_at"] > datetime.now()
        
        # Calculate remaining questions - FIXED: use only questions_used_today
        questions_used = subscription["questions_used_today"]
        questions_limit = plan.get("monthly_question_limit", 100)  # Default fallback
        questions_remaining = max(0, questions_limit - questions_used)
        
        # Calculate remaining chat requests (using same as questions for simplicity)
        chat_used = subscription["questions_used_today"]  # Use same counter
        chat_limit = plan.get("monthly_chat_limit", 100)  # Default fallback
        chat_remaining = max(0, chat_limit - chat_used)
        
        # Calculate remaining follow-up questions (using same as questions for simplicity)
        follow_up_used = subscription["questions_used_today"]  # Use same counter
        follow_up_limit = plan.get("follow_up_questions_per_day", 20)  # Default fallback
        follow_up_remaining = max(0, follow_up_limit - follow_up_used)
        
        return {
            "plan_name": plan["name"],
            "display_name": plan["display_name"],
            "is_active": is_active,
            "is_yearly": subscription.get("is_yearly", False),
            "monthly_question_limit": questions_limit,
            "monthly_chat_limit": chat_limit,
            "questions_used": questions_used,
            "questions_remaining": questions_remaining,
            "chat_requests_used": chat_used,
            "chat_requests_remaining": chat_remaining,
            "follow_up_questions_per_day": follow_up_limit,
            "follow_up_questions_used_today": follow_up_used,
            "follow_up_questions_remaining": follow_up_remaining,
            "subscription_expires_at": subscription_expires_at
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching subscription status: {str(e)}"
        )

@router.post("/change-plan")
async def change_subscription_plan(
    request: ChangePlanRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user's subscription plan (admin only)"""
    try:
        # Check if user is an admin (You'll need to implement this based on your auth system)
        if not current_user.get("is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can change plans directly"
            )
        
        # Change the user's plan
        user_id = current_user["id"]
        updated = subscription_service.change_user_plan(db, user_id, request.plan_name)
        
        return {
            "success": True,
            "message": f"Successfully changed plan to {request.plan_name}",
            "plan": updated["plan"]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error changing subscription plan: {str(e)}"
        )

@router.get("/chat-usage")
async def check_chat_usage(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    increment: bool = False
):
    """Check or increment chat usage limits"""
    from services.question_service import track_chat_usage
    
    try:
        # Use the question service function
        usage = track_chat_usage(current_user["id"], db, increment)
        
        return {
            "plan_name": usage["plan_name"],
            "display_name": usage["display_name"],
            "chat_limit": usage["chat_limit"],
            "used": usage["used"],
            "remaining": usage["remaining"],
            "limit_reached": usage["limit_reached"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking chat usage: {str(e)}"
        )

@router.get("/follow-up-usage")
async def check_follow_up_usage(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    increment: bool = False
):
    """Check or increment follow-up question usage limits"""
    from services.question_service import track_follow_up_usage
    
    try:
        # Use the question service function
        usage = track_follow_up_usage(current_user["id"], db, increment)
        
        return {
            "plan_name": usage["plan_name"],
            "display_name": usage["display_name"],
            "daily_limit": usage["daily_limit"],
            "used": usage["used"],
            "remaining": usage["remaining"],
            "limit_reached": usage["limit_reached"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking follow-up usage: {str(e)}"
        )