# backend/services/video_credit_service.py

from sqlalchemy.orm import Session
from sqlalchemy import text, func
from models import UserCredits, CreditPackage, CreditUsage, Project
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class VideoCreditService:
    
    @staticmethod
    def get_user_balance(user_id: str, db: Session) -> Dict[str, Any]:
        """Get user's current credit balance and package info"""
        try:
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            if not user_credits:
                return {
                    "available_credits": 0,
                    "current_package": None,
                    "purchased_at": None
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
                "purchased_at": user_credits.purchased_at.isoformat() if user_credits.purchased_at else None
            }
        except Exception as e:
            logger.error(f"Error getting user balance: {str(e)}")
            return {"available_credits": 0, "current_package": None, "purchased_at": None}
    
    @staticmethod
    def check_sufficient_credits(user_id: str, required_credits: int, db: Session) -> bool:
        """Check if user has sufficient credits"""
        try:
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            return user_credits and user_credits.available_credits >= required_credits
        except Exception as e:
            logger.error(f"Error checking credits: {str(e)}")
            return False
    
    @staticmethod
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
            
            logger.info(f"Deducted {credits_amount} credits from user {user_id} for project {project_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error deducting credits: {str(e)}")
            return False
    
    @staticmethod
    def add_credits(user_id: str, package_id: str, db: Session) -> bool:
        """Add credits to user account from package"""
        try:
            # Get package details
            package = db.query(CreditPackage).filter(
                CreditPackage.id == package_id
            ).first()
            
            if not package:
                logger.error(f"Package {package_id} not found")
                return False
            
            # Update or create user credits
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            if user_credits:
                # Add credits to existing balance
                user_credits.available_credits += package.credits_amount
                user_credits.pack_id = package.id
                user_credits.purchased_at = func.now()
            else:
                # Create new credit record
                user_credits = UserCredits(
                    user_id=user_id,
                    available_credits=package.credits_amount,
                    pack_id=package.id
                )
                db.add(user_credits)
            
            db.commit()
            logger.info(f"Added {package.credits_amount} credits to user {user_id} from package {package.package_name}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding credits: {str(e)}")
            return False
    
    @staticmethod
    def initialize_free_credits(user_id: str, db: Session) -> bool:
        """Give free credits to new user (call during registration)"""
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
            
            if not free_package:
                logger.warning("No free credit package found")
                return False
            
            user_credits = UserCredits(
                user_id=user_id,
                available_credits=free_package.credits_amount,
                pack_id=free_package.id
            )
            db.add(user_credits)
            db.commit()
            
            logger.info(f"Initialized {free_package.credits_amount} free credits for user {user_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error initializing free credits: {str(e)}")
            return False
    
    @staticmethod
    def get_usage_history(user_id: str, limit: int = 20, offset: int = 0, db: Session = None) -> Dict[str, Any]:
        """Get user's credit usage history with project details"""
        try:
            # Get usage with project details
            usage_query = db.query(CreditUsage, Project).join(
                Project, CreditUsage.project_id == Project.id
            ).filter(
                CreditUsage.user_id == user_id
            ).order_by(CreditUsage.used_at.desc())
            
            total_count = usage_query.count()
            usage_records = usage_query.offset(offset).limit(limit).all()
            
            return {
                "usage_history": [
                    {
                        "project_id": str(usage.project_id),
                        "project_title": project.title,
                        "project_status": project.status,
                        "credits_used": usage.credits_used,
                        "used_at": usage.used_at.isoformat(),
                        "description": f"Project: {project.title} - {usage.credits_used} credits"
                    }
                    for usage, project in usage_records
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
            return {"usage_history": [], "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False}}
    
    @staticmethod
    def get_project_usage(project_id: str, db: Session) -> Optional[CreditUsage]:
        """Get credit usage for a specific project"""
        try:
            return db.query(CreditUsage).filter(
                CreditUsage.project_id == project_id
            ).first()
        except Exception as e:
            logger.error(f"Error getting project usage: {str(e)}")
            return None
    
    @staticmethod
    def calculate_script_generation_cost(input_content: str) -> int:
        """Calculate credit cost for script generation based on input content"""
        if not input_content:
            return 50  # Minimum cost for empty input
        
        # Base cost
        base_cost = 100
        
        # Cost based on content length
        word_count = len(input_content.split())
        char_count = len(input_content)
        
        # Progressive pricing - more expensive for longer content
        if word_count <= 50:
            word_cost = word_count * 2
        elif word_count <= 200:
            word_cost = 100 + (word_count - 50) * 3
        else:
            word_cost = 550 + (word_count - 200) * 4
        
        # Additional cost for complex content (heuristic)
        complexity_score = 0
        if '?' in input_content:
            complexity_score += 10  # Questions add complexity
        if any(word in input_content.lower() for word in ['technical', 'detailed', 'comprehensive', 'analysis']):
            complexity_score += 20  # Technical terms
        if char_count > 1000:
            complexity_score += 30  # Long content
        
        total_cost = base_cost + word_cost + complexity_score
        
        # Ensure minimum and maximum bounds
        return max(min(total_cost, 2000), 50)  # Between 50 and 2000 credits
    
    @staticmethod
    def calculate_video_generation_cost(
        script_length: int = 0,
        quality: str = "HD", 
        duration_estimate: int = 30,
        video_type: str = "STANDARD"
    ) -> int:
        """Calculate credit cost for video generation (when you add video features)"""
        # Base cost for video generation
        base_cost = 200
        
        # Cost based on estimated video duration
        duration_cost = duration_estimate * 10  # 10 credits per second
        
        # Quality multipliers
        quality_multipliers = {
            "SD": 1.0,
            "HD": 1.5,
            "4K": 2.5
        }
        
        # Video type multipliers
        type_multipliers = {
            "STANDARD": 1.0,
            "PREMIUM": 1.5,
            "CUSTOM": 2.0
        }
        
        # Script complexity factor
        script_factor = min(script_length / 1000, 2.0)  # Max 2x multiplier for very long scripts
        
        # Calculate total cost
        quality_multiplier = quality_multipliers.get(quality, 1.0)
        type_multiplier = type_multipliers.get(video_type, 1.0)
        
        total_cost = int(
            (base_cost + duration_cost) * 
            quality_multiplier * 
            type_multiplier * 
            (1 + script_factor)
        )
        
        return max(total_cost, 100)  # Minimum 100 credits for video generation

# Create service instance
video_credit_service = VideoCreditService()
        # backend/services/video_credit_service.py

from sqlalchemy.orm import Session
from sqlalchemy import text
from models import UserCredits, CreditPackage, CreditUsage
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class VideoCreditService:
    
    @staticmethod
    def get_user_balance(user_id: str, db: Session) -> Dict[str, Any]:
        """Get user's current credit balance and package info"""
        try:
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            if not user_credits:
                return {
                    "available_credits": 0,
                    "current_package": None,
                    "purchased_at": None
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
                "purchased_at": user_credits.purchased_at.isoformat() if user_credits.purchased_at else None
            }
        except Exception as e:
            logger.error(f"Error getting user balance: {str(e)}")
            return {"available_credits": 0, "current_package": None, "purchased_at": None}
    
    @staticmethod
    def check_sufficient_credits(user_id: str, required_credits: int, db: Session) -> bool:
        """Check if user has sufficient credits"""
        try:
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            return user_credits and user_credits.available_credits >= required_credits
        except Exception as e:
            logger.error(f"Error checking credits: {str(e)}")
            return False
    
    @staticmethod
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
            
            logger.info(f"Deducted {credits_amount} credits from user {user_id} for project {project_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error deducting credits: {str(e)}")
            return False
    
    @staticmethod
    def add_credits(user_id: str, package_id: str, db: Session) -> bool:
        """Add credits to user account from package"""
        try:
            # Get package details
            package = db.query(CreditPackage).filter(
                CreditPackage.id == package_id
            ).first()
            
            if not package:
                logger.error(f"Package {package_id} not found")
                return False
            
            # Update or create user credits
            user_credits = db.query(UserCredits).filter(
                UserCredits.user_id == user_id
            ).first()
            
            if user_credits:
                # Add credits to existing balance
                user_credits.available_credits += package.credits_amount
                user_credits.pack_id = package.id
                user_credits.purchased_at = func.now()
            else:
                # Create new credit record
                user_credits = UserCredits(
                    user_id=user_id,
                    available_credits=package.credits_amount,
                    pack_id=package.id
                )
                db.add(user_credits)
            
            db.commit()
            logger.info(f"Added {package.credits_amount} credits to user {user_id} from package {package.package_name}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding credits: {str(e)}")
            return False
    
    @staticmethod
    def initialize_free_credits(user_id: str, db: Session) -> bool:
        """Give free credits to new user (call during registration)"""
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
            
            if not free_package:
                logger.warning("No free credit package found")
                return False
            
            user_credits = UserCredits(
                user_id=user_id,
                available_credits=free_package.credits_amount,
                pack_id=free_package.id
            )
            db.add(user_credits)
            db.commit()
            
            logger.info(f"Initialized {free_package.credits_amount} free credits for user {user_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error initializing free credits: {str(e)}")
            return False
    
    @staticmethod
    def get_usage_history(user_id: str, limit: int = 20, offset: int = 0, db: Session = None) -> Dict[str, Any]:
        """Get user's credit usage history with pagination"""
        try:
            usage_query = db.query(CreditUsage).filter(
                CreditUsage.user_id == user_id
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
            return {"usage_history": [], "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False}}
    
    @staticmethod
    def calculate_video_cost(duration_seconds: int, quality: str = "HD", video_type: str = "STANDARD") -> int:
        """Calculate credit cost for video generation (customize based on your pricing)"""
        # Base cost calculation - customize this based on your requirements
        base_cost = 50  # Base cost per video
        
        # Cost per second (adjust based on your pricing model)
        cost_per_second = 2
        
        # Quality multipliers
        quality_multipliers = {
            "SD": 1.0,
            "HD": 1.5,
            "4K": 2.5
        }
        
        # Video type multipliers
        type_multipliers = {
            "STANDARD": 1.0,
            "PREMIUM": 1.5,
            "CUSTOM": 2.0
        }
        
        # Calculate total cost
        duration_cost = duration_seconds * cost_per_second
        quality_multiplier = quality_multipliers.get(quality, 1.0)
        type_multiplier = type_multipliers.get(video_type, 1.0)
        
        total_cost = int((base_cost + duration_cost) * quality_multiplier * type_multiplier)
        
        return max(total_cost, 10)  # Minimum 10 credits

# Create service instance
video_credit_service = VideoCreditService()