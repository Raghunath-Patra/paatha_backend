# backend/routes/payments.py

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Dict
from config.database import get_db
from config.security import get_current_user
from services.payment_service import create_payment_order, verify_payment
import logging

router = APIRouter(prefix="/api/payments", tags=["payments"])

logger = logging.getLogger(__name__)

@router.post("/create-order")
async def create_order_endpoint(
    request_data: Dict = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a Razorpay order for subscription"""
    try:
        plan_duration = request_data.get("plan_duration", "monthly")
        
        # Validate plan_duration
        if plan_duration not in ["monthly", "six_month", "yearly"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid plan duration. Must be 'monthly', 'six_month', or 'yearly'"
            )
        
        # Create the payment order with the specified duration
        order_data = create_payment_order(
            user_id=current_user['id'],
            db=db,
            plan_duration=plan_duration
        )
        
        return order_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating payment order: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment order: {str(e)}"
        )

@router.post("/verify")
async def verify_payment_endpoint(
    payment_data: Dict = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify Razorpay payment and activate premium subscription"""
    try:
        # Get plan duration from payment data
        plan_duration = payment_data.get("plan_duration", "monthly")
        
        # Validate plan_duration
        if plan_duration not in ["monthly", "six_month", "yearly"]:
            logger.warning(f"Invalid plan duration in verify_payment: {plan_duration}, defaulting to monthly")
            plan_duration = "monthly"
        
        # Include plan_duration in payment_data
        payment_data_with_duration = {
            **payment_data,
            "plan_duration": plan_duration
        }
        
        # Verify the payment
        result = verify_payment(
            user_id=current_user['id'],
            payment_data=payment_data_with_duration,
            db=db
        )
        
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error verifying payment: {str(e)}"
        )