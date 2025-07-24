# backend/routes/video_credits.py

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, List
from config.database import get_db
from config.security import get_current_user
from models import CreditPackage, UserCredits, CreditUsage
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-credits", tags=["video-credits"])

@router.get("/packages")
async def get_credit_packages(db: Session = Depends(get_db)):
    """Get all active credit packages"""
    try:
        packages = db.query(CreditPackage).filter(
            CreditPackage.is_active == True
        ).order_by(CreditPackage.credits_amount).all()
        
        return {
            "packages": [
                {
                    "id": str(package.id),
                    "name": package.package_name,
                    "credits": package.credits_amount,
                    "price": package.price_inr / 100,  # Convert to rupees
                    "price_per_credit": round((package.price_inr / 100) / package.credits_amount, 4) if package.price_inr > 0 else 0
                }
                for package in packages
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching credit packages: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching packages")

@router.get("/balance")
async def get_user_balance(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's current credit balance with new user detection"""
    try:
        user_credits = db.query(UserCredits).filter(
            UserCredits.user_id == current_user['id']
        ).first()
        
        # Check if user is new (no credit record exists)
        is_new_user = user_credits is None
        
        if not user_credits:
            return {
                "available_credits": 0,
                "current_package": None,
                "purchased_at": None,
                "is_new_user": True,
                "eligible_for_bonus": True
            }
        
        # Get package details
        package = db.query(CreditPackage).filter(
            CreditPackage.id == user_credits.pack_id
        ).first()
        
        return {
            "available_credits": user_credits.available_credits,
            "current_package": {
                "name": package.package_name if package else "Unknown",
                "total_credits": package.credits_amount if package else 0
            } if package else None,
            "purchased_at": user_credits.purchased_at.isoformat() if user_credits.purchased_at else None,
            "is_new_user": False,
            "eligible_for_bonus": False
        }
    except Exception as e:
        logger.error(f"Error fetching user balance: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching balance")

@router.post("/claim-bonus")
async def claim_free_bonus(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Claim free bonus credits for new users"""
    try:
        # Verify user is truly new (double-check)
        existing_credits = db.query(UserCredits).filter(
            UserCredits.user_id == current_user['id']
        ).first()
        
        if existing_credits:
            raise HTTPException(status_code=400, detail="User already has credits, not eligible for bonus")
        
        # Get free bonus package
        free_package = db.query(CreditPackage).filter(
            CreditPackage.price_inr == 0,
            CreditPackage.is_active == True
        ).first()
        
        if not free_package:
            raise HTTPException(status_code=404, detail="Free bonus package not found")
        
        # Create credit record with bonus
        user_credits = UserCredits(
            user_id=current_user['id'],
            available_credits=free_package.credits_amount,
            pack_id=free_package.id
        )
        db.add(user_credits)
        db.commit()
        
        logger.info(f"Granted {free_package.credits_amount} bonus credits to new user {current_user['id']}")
        
        return {
            "success": True,
            "message": f"Congratulations! You've received {free_package.credits_amount} free credits!",
            "credits_granted": free_package.credits_amount,
            "package_name": free_package.package_name,
            "new_balance": free_package.credits_amount
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error claiming bonus credits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error claiming bonus: {str(e)}")

@router.post("/create-order")
async def create_credit_order(
    request_data: Dict = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create payment order for credit package"""
    try:
        package_id = request_data.get("package_id")
        
        if not package_id:
            raise HTTPException(status_code=400, detail="Package ID is required")
        
        # Get package details
        package = db.query(CreditPackage).filter(
            CreditPackage.id == package_id,
            CreditPackage.is_active == True
        ).first()
        
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        
        if package.price_inr == 0:
            raise HTTPException(status_code=400, detail="Cannot purchase free package")
        
        # Use existing payment service
        from services.payment_service import create_payment_order
        
        # Create payment order with package details
        order_data = create_payment_order(
            user_id=current_user['id'],
            db=db,
            amount=package.price_inr,  # Pass custom amount
            description=f"{package.package_name} - {package.credits_amount} credits",
            metadata={"package_id": str(package.id), "service_type": "video_credits"}
        )
        
        return order_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating credit order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")

@router.post("/verify")
async def verify_credit_payment(
    payment_data: Dict = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify payment and add credits to user account"""
    try:
        package_id = payment_data.get("package_id")
        
        if not package_id:
            raise HTTPException(status_code=400, detail="Package ID is required")
        
        # Verify payment using existing service
        from services.payment_service import verify_payment
        
        payment_result = verify_payment(
            user_id=current_user['id'],
            payment_data=payment_data,
            db=db
        )
        
        if not payment_result.get("success"):
            raise HTTPException(status_code=400, detail="Payment verification failed")
        
        # Get package details
        package = db.query(CreditPackage).filter(
            CreditPackage.id == package_id
        ).first()
        
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        
        # Update or create user credits
        user_credits = db.query(UserCredits).filter(
            UserCredits.user_id == current_user['id']
        ).first()
        
        if user_credits:
            # Add credits to existing balance
            user_credits.available_credits += package.credits_amount
            user_credits.pack_id = package.id
            user_credits.purchased_at = func.now()
        else:
            # Create new credit record
            user_credits = UserCredits(
                user_id=current_user['id'],
                available_credits=package.credits_amount,
                pack_id=package.id
            )
            db.add(user_credits)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Successfully added {package.credits_amount} credits",
            "new_balance": user_credits.available_credits,
            "package_name": package.package_name
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying credit payment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing payment: {str(e)}")

@router.get("/usage-history")
async def get_usage_history(
    limit: int = 20,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's credit usage history"""
    try:
        usage_query = db.query(CreditUsage).filter(
            CreditUsage.user_id == current_user['id']
        ).order_by(CreditUsage.used_at.desc())
        
        total_count = usage_query.count()
        usage_records = usage_query.offset(offset).limit(limit).all()
        
        return {
            "usage_history": [
                {
                    "project_id": str(record.project_id),
                    "credits_used": record.credits_used,
                    "used_at": record.used_at.isoformat(),
                    "description": f"Video generation - {record.credits_used} credits"
                }
                for record in usage_records
            ],
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            }
        }
    except Exception as e:
        logger.error(f"Error fetching usage history: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching usage history")

# Helper function to deduct credits (use in video generation)
def deduct_credits(user_id: str, project_id: str, credits_amount: int, db: Session) -> bool:
    """Deduct credits from user account and record usage"""
    try:
        user_credits = db.query(UserCredits).filter(
            UserCredits.user_id == user_id
        ).first()
        
        if not user_credits or user_credits.available_credits < credits_amount:
            return False
        
        # Deduct credits
        user_credits.available_credits -= credits_amount
        
        # Record usage
        usage = CreditUsage(
            user_id=user_id,
            project_id=project_id,
            credits_used=credits_amount
        )
        db.add(usage)
        db.commit()
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deducting credits: {str(e)}")
        return False

# Helper function to initialize free credits for new users
def initialize_free_credits(user_id: str, db: Session) -> bool:
    """Give free credits to new user"""
    try:
        # Check if user already has credits
        existing = db.query(UserCredits).filter(
            UserCredits.user_id == user_id
        ).first()
        
        if existing:
            return True
        
        # Get free package
        free_package = db.query(CreditPackage).filter(
            CreditPackage.price_inr == 0,
            CreditPackage.is_active == True
        ).first()
        
        if free_package:
            user_credits = UserCredits(
                user_id=user_id,
                available_credits=free_package.credits_amount,
                pack_id=free_package.id
            )
            db.add(user_credits)
            db.commit()
            return True
        
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Error initializing free credits: {str(e)}")
        return False