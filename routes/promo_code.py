# backend/routes/promo_code.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Optional
from config.database import get_db
from config.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/promo-code", tags=["promo-code"])

@router.post("/validate")
async def validate_promo_code(
    promo_data: Dict = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Validate a promo code"""
    try:
        promo_code = promo_data.get("promo_code", "").strip().upper()
        
        if not promo_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Promo code is required"
            )
        
        # Check if this promo code exists and belongs to a marketing partner
        query = text("""
            SELECT id 
            FROM profiles 
            WHERE promo_code = :promo_code 
            AND is_marketing_partner = TRUE
        """)
        
        result = db.execute(query, {"promo_code": promo_code}).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid promo code"
            )
        
        # Check if this user already used this promo code
        already_used_query = text("""
            SELECT id
            FROM promo_code_redemptions
            WHERE marketing_partner_id = :partner_id
            AND subscriber_id = :user_id
        """)
        
        already_used = db.execute(already_used_query, {
            "partner_id": result.id,
            "user_id": current_user["id"]
        }).fetchone()
        
        if already_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already used this promo code"
            )
        
        # Promo code is valid
        return {
            "valid": True,
            "token_bonus": 1000
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error validating promo code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error validating promo code: {str(e)}"
        )

@router.get("/partner/stats")
async def get_partner_stats(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics for a marketing partner"""
    try:
        # Check if the user is a marketing partner
        query = text("""
            SELECT promo_code
            FROM profiles
            WHERE id = :user_id AND is_marketing_partner = TRUE
        """)
        
        partner_result = db.execute(query, {"user_id": current_user["id"]}).fetchone()
        
        if not partner_result:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not registered as a marketing partner."
            )
        
        # Get redemption statistics
        stats_query = text("""
            SELECT
                COUNT(*) as total_redemptions,
                SUM(commission_amount) as total_commission,
                SUM(CASE WHEN is_paid = TRUE THEN commission_amount ELSE 0 END) as paid_commission,
                SUM(CASE WHEN is_paid = FALSE THEN commission_amount ELSE 0 END) as unpaid_commission
            FROM promo_code_redemptions
            WHERE marketing_partner_id = :partner_id
        """)
        
        stats = db.execute(stats_query, {"partner_id": current_user["id"]}).fetchone()
        
        # Get detailed redemption records
        redemptions_query = text("""
            SELECT
                r.id,
                p.email as subscriber_email,
                r.subscription_amount,
                r.subscription_type,
                r.commission_amount,
                r.is_paid,
                r.created_at
            FROM promo_code_redemptions r
            JOIN profiles p ON r.subscriber_id = p.id
            WHERE r.marketing_partner_id = :partner_id
            ORDER BY r.created_at DESC
        """)
        
        redemptions_result = db.execute(redemptions_query, {"partner_id": current_user["id"]}).fetchall()
        
        # Format redemptions for response
        redemptions = []
        for row in redemptions_result:
            redemptions.append({
                "id": str(row.id),
                "subscriber_email": row.subscriber_email,
                "subscription_amount": row.subscription_amount / 100,  # Convert from paise to rupees
                "subscription_type": row.subscription_type,
                "commission_amount": row.commission_amount / 100,  # Convert from paise to rupees
                "is_paid": row.is_paid,
                "created_at": row.created_at.isoformat() if row.created_at else None
            })
        
        return {
            "promo_code": partner_result.promo_code,
            "total_redemptions": stats.total_redemptions or 0,
            "total_commission": (stats.total_commission or 0) / 100,  # Convert from paise to rupees
            "paid_commission": (stats.paid_commission or 0) / 100,  # Convert from paise to rupees
            "unpaid_commission": (stats.unpaid_commission or 0) / 100,  # Convert from paise to rupees
            "redemptions": redemptions
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting partner stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting partner stats: {str(e)}"
        )