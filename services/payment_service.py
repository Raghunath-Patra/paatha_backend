# File: backend/services/payment_service.py

import os
import uuid
import random
import string
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import razorpay
from models import User
from dotenv import load_dotenv

load_dotenv()

# Get Razorpay credentials from environment variables
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

# Initialize Razorpay client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)  # IST offset from UTC
    return utc_now + offset

def generate_short_receipt_id():
    """Generate a short receipt ID under 40 characters"""
    timestamp = int(time.time())
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"r{timestamp}{random_str}"

# Update these functions in your existing payment_service.py file

def create_payment_order(user_id: str, db: Session, plan_duration: str = "monthly"):
    """
    Create a Razorpay order for premium subscription
    plan_duration can be 'monthly', 'six_month', or 'yearly'
    """
    try:
        # Get user profile
        # Modified to only select columns that exist in the profiles table
        user_query = text("""
            SELECT id 
            FROM profiles 
            WHERE id = :user_id
        """)
        
        user_result = db.execute(user_query, {"user_id": user_id}).fetchone()
        
        if not user_result:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get premium plan details from database
        plan_query = text("""
            SELECT id, monthly_price, six_month_price, yearly_price
            FROM subscription_plans
            WHERE name = 'premium' AND is_active = TRUE
            LIMIT 1
        """)
        
        plan_result = db.execute(plan_query).fetchone()
        
        if plan_result:
            # Use the appropriate price based on plan_duration
            if plan_duration == "six_month" and plan_result.six_month_price:
                amount = plan_result.six_month_price
            elif plan_duration == "yearly" and plan_result.yearly_price:
                amount = plan_result.yearly_price
            else:  # Default to monthly
                amount = plan_result.monthly_price
        else:
            # Fallback to default prices
            if plan_duration == "six_month":
                amount = 159900  # ₹1599 in paise
            elif plan_duration == "yearly":
                amount = 299900  # ₹2999 in paise
            else:
                amount = 29900   # ₹299 in paise
        
        # Create Razorpay order with shorter receipt and include plan_duration
        payment_data = {
            'amount': amount,
            'currency': 'INR',
            'receipt': generate_short_receipt_id(),
            'notes': {
                'user_id': str(user_id),
                'plan_duration': plan_duration
            }
        }
        
        order = client.order.create(data=payment_data)
        
        # Store order in database using proper SQLAlchemy text() function
        sql = text("""
            INSERT INTO payments (user_id, amount, currency, razorpay_order_id, status)
            VALUES (:user_id, :amount, :currency, :order_id, :status)
            RETURNING id
        """)
        
        result = db.execute(
            sql,
            {
                'user_id': user_id,
                'amount': amount,
                'currency': 'INR',
                'order_id': order['id'],
                'status': 'created'
            }
        ).fetchone()
        
        db.commit()
        
        return {
            "order_id": order['id'],
            "amount": amount,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID
        }
    except Exception as e:
        db.rollback()
        print(f"Error in create_payment_order: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating payment order: {str(e)}")

# Updated verify_payment function in payment_service.py
def verify_payment(user_id: str, payment_data: dict, db: Session):
    """
    Verify Razorpay payment and update user to premium
    """
    try:
        # Start a transaction to ensure all updates are atomic
        transaction = db.begin_nested()
        
        try:
            # Verify signature
            params_dict = {
                'razorpay_order_id': payment_data['razorpay_order_id'],
                'razorpay_payment_id': payment_data['razorpay_payment_id'],
                'razorpay_signature': payment_data['razorpay_signature']
            }
            
            client.utility.verify_payment_signature(params_dict)
            
            # Retrieve order details to get plan_duration from notes
            # First try to get from the payment_data
            plan_duration = payment_data.get('plan_duration', 'monthly')
            
            # If not in payment_data, try to get from order notes in Razorpay
            if not plan_duration or plan_duration not in ['monthly', 'six_month', 'yearly']:
                try:
                    order = client.order.fetch(payment_data['razorpay_order_id'])
                    plan_duration = order.get('notes', {}).get('plan_duration', 'monthly')
                except Exception as order_err:
                    print(f"Error fetching order details: {order_err}")
                    plan_duration = 'monthly'  # Default to monthly if we can't get it
            
            # Calculate dates for premium period based on plan_duration
            now = get_india_time()
            premium_start_date = now
            
            if plan_duration == 'six_month':
                premium_expires_at = now + timedelta(days=182)  # ~6 months
            elif plan_duration == 'yearly':
                premium_expires_at = now + timedelta(days=365)  # 1 year
            else:  # monthly
                premium_expires_at = now + timedelta(days=30)  # 1 month
            
            # 1. Update payment record with plan_duration and premium period
            update_payment_sql = text("""
                UPDATE payments
                SET razorpay_payment_id = :payment_id,
                    razorpay_signature = :signature,
                    status = 'completed',
                    premium_start_date = :start_date,
                    premium_end_date = :end_date,
                    updated_at = NOW()
                WHERE razorpay_order_id = :order_id AND user_id = :user_id
            """)

            db.execute(
                update_payment_sql,
                {
                    'payment_id': payment_data['razorpay_payment_id'],
                    'signature': payment_data['razorpay_signature'],
                    'order_id': payment_data['razorpay_order_id'],
                    'user_id': user_id,
                    'start_date': premium_start_date,
                    'end_date': premium_expires_at
                }
            )
            
            # 2. Get the premium plan ID
            premium_plan_query = text("""
                SELECT id FROM subscription_plans WHERE name = 'premium' LIMIT 1
            """)
            
            premium_plan = db.execute(premium_plan_query).fetchone()
            if not premium_plan:
                raise Exception("Premium plan not found in database")
            
            premium_plan_id = premium_plan.id
            
            # 3. Update subscription_user_data record with plan_duration
            # First check if a record exists
            subscription_query = text("""
                SELECT id FROM subscription_user_data WHERE user_id = :user_id
            """)
            
            subscription = db.execute(subscription_query, {'user_id': user_id}).fetchone()
            
            if subscription:
                # Update existing subscription
                update_subscription_sql = text("""
                    UPDATE subscription_user_data
                    SET plan_id = :plan_id,
                        subscription_start_date = :start_date,
                        subscription_expires_at = :expires_at,
                        updated_at = NOW(),
                        is_yearly = :is_yearly
                    WHERE user_id = :user_id
                """)
                
                db.execute(
                    update_subscription_sql,
                    {
                        'user_id': user_id,
                        'plan_id': premium_plan_id,
                        'start_date': premium_start_date,
                        'expires_at': premium_expires_at,
                        'is_yearly': plan_duration == 'yearly'
                    }
                )
            else:
                # Create new subscription record
                insert_subscription_sql = text("""
                    INSERT INTO subscription_user_data
                    (user_id, plan_id, subscription_start_date, subscription_expires_at,
                    is_yearly, questions_used_today, daily_input_tokens_used, 
                    daily_output_tokens_used, tokens_reset_date, token_bonus)
                    VALUES
                    (:user_id, :plan_id, :start_date, :expires_at,
                    :is_yearly, 0, 0, 0, CURRENT_DATE, 0)
                """)
                                
                db.execute(
                    insert_subscription_sql,
                    {
                        'user_id': user_id,
                        'plan_id': premium_plan_id,
                        'start_date': premium_start_date,
                        'expires_at': premium_expires_at,
                        'is_yearly': plan_duration == 'yearly'
                    }
                )
                            
            # 4. Update user profile with premium status and subscription duration info
            # Modified to remove daily_question_limit
            update_user_sql = text("""
                UPDATE profiles
                SET is_premium = TRUE,
                    premium_start_date = :start_date,
                    premium_expires_at = :expires_at,
                    subscription_plan_id = :plan_id,
                    updated_at = NOW()
                WHERE id = :user_id
            """)
            
            db.execute(
                update_user_sql,
                {
                    'user_id': user_id,
                    'start_date': premium_start_date,
                    'expires_at': premium_expires_at,
                    'plan_id': premium_plan_id
                }
            )
            
            # Process promo code if provided
            promo_code = payment_data.get('promo_code')
            if promo_code:
                try:
                    # Assuming the order data is already fetched above, or fetch it here if needed
                    subscription_amount = payment_data.get('amount')
                    if subscription_amount is None and 'razorpay_order_id' in payment_data:
                        try:
                            # If we don't have the amount, try to get it from the order
                            if 'order' not in locals():
                                order = client.order.fetch(payment_data['razorpay_order_id'])
                            subscription_amount = order.get('amount')
                        except Exception as order_err:
                            print(f"Error fetching order amount: {order_err}")
                            subscription_amount = None

                    process_result = process_promo_code_redemption(
                        user_id=user_id,
                        promo_code=promo_code,
                        subscription_amount=subscription_amount,  # From order data
                        subscription_type=plan_duration,  # From earlier in the function
                        db=db
                    )
                    if not process_result:
                        print(f"Warning: Failed to process promo code: {promo_code}")
                        # Continue with the payment process even if promo code processing fails
                except Exception as promo_err:
                    # Log the error but don't fail the transaction
                    print(f"Error processing promo code: {promo_err}")
                    # Continue with the payment process even if promo code processing fails
            
            # All operations completed successfully, commit the transaction
            transaction.commit()
            
        except Exception as tx_error:
            # Rollback the transaction if any step fails
            transaction.rollback()
            raise tx_error
            
        # Commit the main transaction
        db.commit()
        
        return {
            "success": True, 
            "message": "Payment successful!",
            "plan_duration": plan_duration,
            "expiry_date": premium_expires_at.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        print(f"Error in verify_payment: {e}")
        raise HTTPException(status_code=400, detail=f"Payment verification failed: {str(e)}")
    

# Add this to services/payment_service.py
def cancel_subscription(user_id: str, db: Session):
    """
    Cancel a user's subscription when they delete their account
    """
    try:
        # Get user profile to check if premium
        profile = db.query(User).filter(User.id == user_id).first()
        if not profile or not profile.is_premium:
            return {"success": True, "message": "No active subscription to cancel"}
        
        # Find the payment records for the user to get subscription ID
        # This assumes you store the subscription ID somewhere
        payment_sql = text("""
            SELECT razorpay_subscription_id 
            FROM payments
            WHERE user_id = :user_id AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        payment_result = db.execute(payment_sql, {'user_id': user_id}).fetchone()
        
        if payment_result and payment_result.razorpay_subscription_id:
            # Cancel the subscription with Razorpay
            try:
                subscription_id = payment_result.razorpay_subscription_id
                client.subscription.cancel(subscription_id)
            except Exception as razorpay_err:
                # Log error but continue - we still want to clean up our database
                print(f"Error canceling Razorpay subscription: {razorpay_err}")
        
        # Update user record to remove premium status
        update_sql = text("""
            UPDATE profiles
            SET is_premium = FALSE,
                updated_at = NOW()
            WHERE id = :user_id
        """)
        
        db.execute(update_sql, {'user_id': user_id})
        
        # Mark subscription as canceled in payments table
        cancel_sql = text("""
            UPDATE payments
            SET status = 'canceled',
                canceled_at = NOW(),
                canceled_reason = 'account_deletion'
            WHERE user_id = :user_id AND status = 'completed'
        """)
        
        db.execute(cancel_sql, {'user_id': user_id})
        db.commit()
        
        return {"success": True, "message": "Subscription canceled successfully"}
    except Exception as e:
        db.rollback()
        print(f"Error in cancel_subscription: {e}")
        raise




def process_promo_code_redemption(user_id: str, promo_code: str, 
                                  subscription_amount: int, subscription_type: str, 
                                  db: Session) -> bool:
    """
    Process a promo code redemption when payment is verified
    
    Args:
        user_id: The user who made the purchase
        promo_code: The promo code used
        subscription_amount: The subscription amount in paise
        subscription_type: monthly, six_month, or yearly
        db: Database session
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not promo_code:
            return True  # No promo code to process
        
        # Find the marketing partner associated with this promo code
        partner_query = text("""
            SELECT id
            FROM profiles 
            WHERE promo_code = :promo_code 
            AND is_marketing_partner = TRUE
        """)
        
        partner = db.execute(partner_query, {"promo_code": promo_code}).fetchone()
        
        if not partner:
            # No valid marketing partner found
            return False
        
        # Calculate commission (5% of subscription amount)
        commission_amount = int(subscription_amount * 0.05)
        
        # Add redemption record
        insert_query = text("""
            INSERT INTO promo_code_redemptions
            (marketing_partner_id, subscriber_id, subscription_amount, 
             subscription_type, commission_amount)
            VALUES (:partner_id, :user_id, :amount, :type, :commission)
        """)
        
        db.execute(insert_query, {
            "partner_id": partner.id,
            "user_id": user_id,
            "amount": subscription_amount,
            "type": subscription_type,
            "commission": commission_amount
        })
        
        # Add token bonus to the user's subscription
        update_token_bonus = text("""
            UPDATE subscription_user_data
            SET token_bonus = 1000
            WHERE user_id = :user_id
        """)
        
        db.execute(update_token_bonus, {"user_id": user_id})
        
        # Also update the user's profile
        update_profile = text("""
            UPDATE profiles
            SET token_bonus = 1000
            WHERE id = :user_id
        """)
        
        db.execute(update_profile, {"user_id": user_id})
        
        # Commit is handled by the calling function
        return True
        
    except Exception as e:
        print(f"Error processing promo code redemption: {str(e)}")
        return False
