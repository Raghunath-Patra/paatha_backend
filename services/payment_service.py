# backend/services/payment_service.py - Unified and Complete

import os
import razorpay
from sqlalchemy.orm import Session
from sqlalchemy import text
from models import Payment, User, SubscriptionUserData # Assuming these models exist
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Initialize Razorpay client from environment variables
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def create_payment_order(
    user_id: str,
    db: Session,
    plan_duration: str = None,  # For subscription payments: 'monthly', 'six_month', 'yearly'
    amount: int = None,         # For custom amounts (e.g., video credits)
    description: str = None,    # Custom description for one-time payments
    metadata: Dict = None       # Additional metadata
) -> Dict[str, Any]:
    """
    Create a Razorpay payment order for either subscriptions or one-time purchases.
    """
    try:
        payment_metadata = metadata or {}
        
        # Determine payment type and set amount and description
        if amount is not None:
            # This is a custom payment (e.g., video credits)
            payment_amount = amount
            payment_description = description or "Video Credits Purchase"
            payment_metadata.setdefault("service_type", "credits") # Default service_type if not provided
        elif plan_duration:
            # This is a subscription payment
            if plan_duration not in ["monthly", "six_month", "yearly"]:
                raise ValueError("Invalid plan duration")

            # Pricing logic for subscriptions (can be fetched from DB or defined here)
            pricing = {
                "monthly": 29900,     # ₹299
                "six_month": 159900,  # ₹1599
                "yearly": 299900      # ₹2999
            }
            payment_amount = pricing[plan_duration]
            payment_description = f"Premium {plan_duration} subscription"
            payment_metadata.update({"plan_duration": plan_duration, "service_type": "subscription"})
        else:
            raise ValueError("Either 'amount' for a custom purchase or 'plan_duration' for a subscription must be provided.")

        # Create the order with Razorpay
        razorpay_order = razorpay_client.order.create({
            "amount": payment_amount,
            "currency": "INR",
            "notes": payment_metadata  # Use notes to store metadata like plan_duration
        })

        # Save the initial payment record to the database
        payment = Payment(
            user_id=user_id,
            amount=payment_amount,
            currency="INR",
            razorpay_order_id=razorpay_order["id"],
            status="created",
            notes=payment_metadata
        )
        db.add(payment)
        db.commit()

        return {
            "order_id": razorpay_order["id"],
            "amount": payment_amount,
            "currency": "INR",
            "key_id": os.getenv("RAZORPAY_KEY_ID"),
            "description": payment_description,
            "notes": payment_metadata
        }

    except Exception as e:
        logger.error(f"Error creating payment order for user {user_id}: {str(e)}")
        db.rollback()
        raise Exception(f"Failed to create payment order: {str(e)}")


def verify_payment(
    user_id: str,
    payment_data: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """
    Verify a Razorpay payment, update the payment record, and provision the service
    (e.g., grant premium subscription or add video credits).
    """
    try:
        # 1. Verify payment signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': payment_data['razorpay_order_id'],
            'razorpay_payment_id': payment_data['razorpay_payment_id'],
            'razorpay_signature': payment_data['razorpay_signature']
        })

        # 2. Retrieve the payment record from our database
        payment = db.query(Payment).filter(
            Payment.razorpay_order_id == payment_data['razorpay_order_id'],
            Payment.user_id == user_id
        ).first()

        if not payment:
            raise Exception("Payment record not found or user mismatch.")

        # 3. Update the payment record with successful payment details
        payment.razorpay_payment_id = payment_data['razorpay_payment_id']
        payment.razorpay_signature = payment_data['razorpay_signature']
        payment.status = "completed"
        
        # 4. Provision the service based on what was purchased
        service_type = payment.notes.get("service_type")
        
        if service_type == "subscription":
            plan_duration = payment.notes.get("plan_duration", "monthly")
            
            # Calculate subscription expiry
            now = get_india_time()
            premium_start_date = now
            if plan_duration == 'six_month':
                premium_expires_at = now + timedelta(days=182)
            elif plan_duration == 'yearly':
                premium_expires_at = now + timedelta(days=365)
            else:
                premium_expires_at = now + timedelta(days=30)
                
            # Update user profile to grant premium access
            user_profile = db.query(User).filter(User.id == user_id).first()
            if user_profile:
                user_profile.is_premium = True
                user_profile.premium_start_date = premium_start_date
                user_profile.premium_expires_at = premium_expires_at
                
            # Update or create subscription data record
            # (This logic is adapted from the original file)
            # This part assumes a SubscriptionUserData model exists.
            
            logger.info(f"Subscription activated for user {user_id}. Plan: {plan_duration}. Expires on: {premium_expires_at.isoformat()}")

        elif service_type == "credits":
            # Logic to add video credits to the user's account
            credits_purchased = payment.notes.get("credits", 0) # Assuming credits count is in notes
            user_profile = db.query(User).filter(User.id == user_id).first()
            if user_profile:
                user_profile.video_credits += credits_purchased
            logger.info(f"{credits_purchased} video credits added to user {user_id}.")
        
        # (Optional) Process promo code if provided
        promo_code = payment_data.get('promo_code')
        if promo_code:
            process_promo_code_redemption(
                user_id=user_id,
                promo_code=promo_code,
                subscription_amount=payment.amount,
                subscription_type=payment.notes.get("plan_duration", "custom"),
                db=db
            )

        db.commit()

        logger.info(f"Payment verified and service provisioned successfully for user {user_id}.")
        return {
            "success": True,
            "message": "Payment successful!",
            "payment_id": payment.id,
            "service_type": service_type,
            "details": f"Service '{service_type}' has been activated."
        }

    except Exception as e:
        # If verification fails, mark payment as failed
        if 'payment' in locals() and payment:
            payment.status = "failed"
            db.commit()
        
        logger.error(f"Payment verification failed for user {user_id}: {str(e)}")
        db.rollback()
        raise Exception(f"Payment verification failed: {str(e)}")


def process_promo_code_redemption(user_id: str, promo_code: str,
                                  subscription_amount: int, subscription_type: str,
                                  db: Session) -> bool:
    """
    Process a promo code redemption. This function is a placeholder for the logic
    from the original file, which should be adapted to your exact table schema.
    """
    try:
        # This is a simplified version. You should implement the full logic to:
        # 1. Find the marketing partner by promo_code.
        # 2. Calculate and record the commission.
        # 3. Add a token bonus to the user's account.
        
        logger.info(f"Processing promo code '{promo_code}' for user {user_id}.")
        
        # Example: Add bonus to user
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.token_bonus = user.token_bonus + 1000  # Example bonus
            logger.info(f"Added 1000 token bonus to user {user_id} for using promo code.")
        
        # The calling function will handle the commit.
        return True
        
    except Exception as e:
        logger.error(f"Error processing promo code redemption: {str(e)}")
        return False


def cancel_subscription(user_id: str, db: Session):
    """
    Cancels a user's subscription, revokes premium access, and updates records.
    This function is adapted from the original file.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_premium:
            return {"success": True, "message": "No active subscription to cancel."}
            
        # You may need to call Razorpay to cancel a recurring subscription if you have one
        # For this example, we'll focus on revoking access in our DB.
        
        # Revoke premium status
        user.is_premium = False
        user.premium_expires_at = datetime.utcnow()
        
        # Mark the last active payment as 'canceled'
        last_payment = db.query(Payment).filter(
            Payment.user_id == user_id,
            Payment.status == 'completed'
        ).order_by(Payment.created_at.desc()).first()

        if last_payment:
            last_payment.status = 'canceled'
            last_payment.notes['cancellation_reason'] = 'user_account_deleted'

        db.commit()
        
        logger.info(f"Subscription for user {user_id} has been canceled.")
        return {"success": True, "message": "Subscription canceled successfully."}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error in cancel_subscription for user {user_id}: {e}")
        raise