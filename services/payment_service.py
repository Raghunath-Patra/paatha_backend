# backend/services/payment_service.py - Modified for video credits

import razorpay
import os
from sqlalchemy.orm import Session
from models import Payment
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Razorpay client
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

def create_payment_order(
    user_id: str, 
    db: Session, 
    plan_duration: str = None,  # For subscription payments
    amount: int = None,         # For custom amounts (video credits)
    description: str = None,    # Custom description
    metadata: Dict = None       # Additional metadata
) -> Dict[str, Any]:
    """
    Create Razorpay payment order
    - For subscriptions: use plan_duration
    - For video credits: use amount, description, metadata
    """
    try:
        # Determine payment type and amount
        if amount is not None:
            # Custom payment (video credits)
            payment_amount = amount
            payment_description = description or "Video Credits Purchase"
            payment_metadata = metadata or {}
        else:
            # Subscription payment (existing logic)
            if plan_duration not in ["monthly", "six_month", "yearly"]:
                raise ValueError("Invalid plan duration")
            
            # Your existing subscription pricing logic
            pricing = {
                "monthly": 29900,     # ₹299
                "six_month": 159900,  # ₹1599  
                "yearly": 299900      # ₹2999
            }
            
            payment_amount = pricing[plan_duration]
            payment_description = f"Premium {plan_duration} subscription"
            payment_metadata = {"plan_duration": plan_duration, "service_type": "subscription"}

        # Create Razorpay order
        razorpay_order = razorpay_client.order.create({
            "amount": payment_amount,
            "currency": "INR",
            "notes": payment_metadata
        })

        # Save payment record
        payment = Payment(
            user_id=user_id,
            amount=payment_amount,
            currency="INR",
            razorpay_order_id=razorpay_order["id"],
            status="created"
        )
        db.add(payment)
        db.commit()

        return {
            "order_id": razorpay_order["id"],
            "amount": payment_amount,
            "currency": "INR",
            "key_id": os.getenv("RAZORPAY_KEY_ID"),
            "description": payment_description
        }

    except Exception as e:
        logger.error(f"Error creating payment order: {str(e)}")
        raise Exception(f"Failed to create payment order: {str(e)}")

def verify_payment(
    user_id: str, 
    payment_data: Dict[str, Any], 
    db: Session
) -> Dict[str, Any]:
    """
    Verify Razorpay payment
    Returns success status and payment details
    """
    try:
        # Verify payment signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': payment_data['razorpay_order_id'],
            'razorpay_payment_id': payment_data['razorpay_payment_id'],
            'razorpay_signature': payment_data['razorpay_signature']
        })

        # Update payment record
        payment = db.query(Payment).filter(
            Payment.razorpay_order_id == payment_data['razorpay_order_id'],
            Payment.user_id == user_id
        ).first()

        if not payment:
            raise Exception("Payment record not found")

        payment.razorpay_payment_id = payment_data['razorpay_payment_id']
        payment.razorpay_signature = payment_data['razorpay_signature']
        payment.status = "completed"

        db.commit()

        logger.info(f"Payment verified successfully for user {user_id}")
        
        return {
            "success": True,
            "payment_id": payment.id,
            "razorpay_payment_id": payment_data['razorpay_payment_id'],
            "amount": payment.amount
        }

    except Exception as e:
        # Update payment status to failed
        if 'payment' in locals():
            payment.status = "failed"
            db.commit()
        
        logger.error(f"Payment verification failed: {str(e)}")
        raise Exception(f"Payment verification failed: {str(e)}")

# Helper function to get payment details
def get_payment_by_order_id(order_id: str, db: Session) -> Optional[Payment]:
    """Get payment record by Razorpay order ID"""
    return db.query(Payment).filter(
        Payment.razorpay_order_id == order_id
    ).first()