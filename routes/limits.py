# backend/routes/limits.py - FIXED for actual table schema

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import get_db
from config.security import get_current_user
import logging
import time
from services.consolidated_user_service import consolidated_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/user/question-status")
async def get_question_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    OPTIMIZED: Get comprehensive user status in single database call
    Returns ALL data frontend needs for token management
    """
    try:
        # Single call to get everything - no multiple database queries
        status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Log for debugging
        logger.info(f"Comprehensive user status returned: plan={status['plan_name']}, "
                   f"questions_used={status['questions_used_today']}, "
                   f"limit_reached={status['limit_reached']}, "
                   f"input_remaining={status['input_remaining']}, "
                   f"output_remaining={status['output_remaining']}")
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting comprehensive question status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return safe defaults for API stability
        return {
            "user_id": current_user['id'],
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
            "input_tokens_per_question": 6000,
            "output_tokens_per_question": 4000,
            "input_token_buffer": 1000,
            "limit_reached": False,
            "carry_forward": False,
            "token_bonus": 0,
            "is_yearly": False,
            "subscription_start_date": None,
            "subscription_expires_at": None,
            "tokens_reset_date": None,
            "last_updated": None
        }

@router.get("/debug/comprehensive-status")
async def debug_comprehensive_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debug endpoint to see full comprehensive status with performance metrics"""
    start_time = time.time()
    
    try:
        # Get comprehensive status
        status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        query_time = time.time() - start_time
        
        return {
            "user_id": current_user['id'],
            "query_time_ms": round(query_time * 1000, 2),
            "status": status,
            "performance": {
                "single_query": True,
                "background_updates": True,
                "database_calls": 1
            }
        }
        
    except Exception as e:
        logger.error(f"Error in debug comprehensive status: {str(e)}")
        return {
            "error": str(e),
            "user_id": current_user['id'],
            "query_time_ms": round((time.time() - start_time) * 1000, 2)
        }

@router.get("/debug/question-usage")
async def debug_question_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debug endpoint to check question usage directly from DB - FIXED for actual schema"""
    try:
        query = text("""
            SELECT 
                sud.questions_used_today,
                sud.daily_input_tokens_used,
                sud.daily_output_tokens_used,
                sud.tokens_reset_date,
                sud.token_bonus,
                sud.plan_id,
                sp.name as plan_name,
                sp.display_name,
                sp.daily_input_token_limit,
                sp.daily_output_token_limit
            FROM subscription_user_data sud
            LEFT JOIN subscription_plans sp ON sud.plan_id = sp.id
            WHERE sud.user_id = :user_id
        """)
        
        result = db.execute(query, {"user_id": current_user['id']}).fetchone()
        
        if not result:
            return {
                "error": "No subscription data found for user",
                "user_id": current_user['id']
            }
            
        return {
            "user_id": current_user['id'],
            "raw_database_data": {
                "questions_used_today": result.questions_used_today,
                "daily_input_tokens_used": result.daily_input_tokens_used,
                "daily_output_tokens_used": result.daily_output_tokens_used,
                "tokens_reset_date": result.tokens_reset_date.isoformat() if result.tokens_reset_date else None,
                "token_bonus": result.token_bonus,
                "plan_id": result.plan_id,
                "plan_name": result.plan_name,
                "display_name": result.display_name,
                "daily_input_token_limit": result.daily_input_token_limit,
                "daily_output_token_limit": result.daily_output_token_limit
            },
            "consolidated_service_data": consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        }
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        return {
            "error": str(e),
            "user_id": current_user['id']
        }

@router.get("/debug/test-new-user")
async def test_new_user_creation(
    test_user_id: str = "test-user-123",
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to demonstrate new user creation flow
    This shows how the system handles users who don't have subscription_user_data records
    """
    try:
        start_time = time.time()
        
        # First, check if user exists in subscription_user_data
        check_query = text("""
            SELECT user_id FROM subscription_user_data WHERE user_id = :user_id
        """)
        
        existing_user = db.execute(check_query, {"user_id": test_user_id}).fetchone()
        
        # Get comprehensive status (this will create the user if they don't exist)
        status = consolidated_service.get_comprehensive_user_status(test_user_id, db)
        
        # Check if user was created
        user_after = db.execute(check_query, {"user_id": test_user_id}).fetchone()
        
        query_time = time.time() - start_time
        
        return {
            "test_user_id": test_user_id,
            "user_existed_before": existing_user is not None,
            "user_exists_after": user_after is not None,
            "user_was_created": existing_user is None and user_after is not None,
            "comprehensive_status": status,
            "query_time_ms": round(query_time * 1000, 2),
            "flow_explanation": {
                "step_1": "Check if user has subscription_user_data record",
                "step_2": "Call get_comprehensive_user_status()",
                "step_3": "If user doesn't exist, create subscription_user_data record automatically",
                "step_4": "Return comprehensive status with default free plan values",
                "step_5": "Background tasks can now update this user's usage without errors"
            }
        }
        
    except Exception as e:
        logger.error(f"Error in test new user creation: {str(e)}")
        return {
            "error": str(e),
            "test_user_id": test_user_id
        }

@router.post("/debug/simulate-new-user-flow")
async def simulate_new_user_flow(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Simulate the complete flow for a new user:
    1. Get status (creates user if needed)
    2. Perform some actions (question fetch, answer submission)
    3. Show background updates
    """
    try:
        import uuid
        test_user_id = f"new-user-{str(uuid.uuid4())[:8]}"
        
        # Step 1: Get initial status (creates user)
        print(f"Step 1: Getting status for new user {test_user_id}")
        initial_status = consolidated_service.get_comprehensive_user_status(test_user_id, db)
        
        # Step 2: Simulate question fetch
        print(f"Step 2: Simulating question fetch")
        consolidated_service.update_user_usage(
            user_id=test_user_id,
            question_id="test-question-123",
            input_tokens=50,
            output_tokens=0,
            question_submitted=False
        )
        
        # Step 3: Simulate answer submission
        print(f"Step 3: Simulating answer submission")
        consolidated_service.update_user_usage(
            user_id=test_user_id,
            question_id="test-question-123",
            input_tokens=200,
            output_tokens=150,
            question_submitted=True  # This increments questions_used_today
        )
        
        # Step 4: Get updated status (after background tasks complete)
        # Note: In real scenario, you'd wait a moment for background tasks
        import time
        time.sleep(1)  # Brief wait for background tasks
        
        updated_status = consolidated_service.get_comprehensive_user_status(test_user_id, db)
        
        return {
            "test_user_id": test_user_id,
            "simulation_steps": [
                "Created new user with default values",
                "Simulated question fetch (50 input tokens)",
                "Simulated answer submission (200 input + 150 output tokens, 1 question)",
                "Retrieved updated status"
            ],
            "initial_status": {
                "questions_used_today": initial_status["questions_used_today"],
                "input_used": initial_status["input_used"],
                "output_used": initial_status["output_used"],
                "plan_name": initial_status["plan_name"]
            },
            "final_status": {
                "questions_used_today": updated_status["questions_used_today"],
                "input_used": updated_status["input_used"],
                "output_used": updated_status["output_used"],
                "input_remaining": updated_status["input_remaining"],
                "output_remaining": updated_status["output_remaining"],
                "plan_name": updated_status["plan_name"]
            },
            "expected_changes": {
                "questions_used_today": "0 → 1",
                "input_used": "0 → 250",
                "output_used": "0 → 150"
            }
        }
        
    except Exception as e:
        logger.error(f"Error in simulate new user flow: {str(e)}")
        return {
            "error": str(e)
        }