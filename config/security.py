# backend/config/security.py
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from config.database import get_db
import os
from dotenv import load_dotenv
import httpx
from passlib.context import CryptContext
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return pwd_context.hash(password)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    """
    Validate JWT token with Supabase Auth and enrich with database profile
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials
        
        # Call Supabase Auth API to get user (your existing logic)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_KEY
                }
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get basic user data from Supabase
        supabase_user = response.json()
        user_id = supabase_user.get("id")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data from Supabase",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # NEW: Fetch profile data from database
        try:
            from sqlalchemy import text
            query = text("""
                SELECT 
                    id,
                    email,
                    full_name,
                    role,
                    board,
                    class_level,
                    institution_name,
                    is_active,
                    is_verified
                FROM profiles 
                WHERE id = :user_id
            """)
            
            profile_result = db.execute(query, {"user_id": user_id}).fetchone()
            
            if profile_result:
                # Merge Supabase user data with database profile
                enhanced_user = {
                    "id": profile_result.id,
                    "email": profile_result.email or supabase_user.get("email"),
                    "full_name": profile_result.full_name,
                    "role": profile_result.role,  # Use database role, not Supabase role
                    "board": profile_result.board,
                    "class_level": profile_result.class_level,
                    "institution_name": profile_result.institution_name,
                    "is_active": profile_result.is_active,
                    "is_verified": profile_result.is_verified,
                    # Keep Supabase data for reference
                    "supabase_role": supabase_user.get("role"),  # This will be 'authenticated'
                    "supabase_data": supabase_user
                }
                
                logger.info(f"✅ User authenticated: {enhanced_user['email']} with role: {enhanced_user['role']}")
                return enhanced_user
            else:
                # Profile not found in database, create basic user object
                logger.warning(f"⚠️ User {user_id} authenticated but no profile found in database")
                return {
                    "id": user_id,
                    "email": supabase_user.get("email"),
                    "role": None,  # No role since no profile
                    "supabase_role": supabase_user.get("role"),
                    "supabase_data": supabase_user
                }
                
        except Exception as db_error:
            logger.error(f"❌ Database lookup error: {str(db_error)}")
            # Fallback to Supabase data only
            logger.warning(f"⚠️ Falling back to Supabase data only for user {user_id}")
            return supabase_user

    except Exception as e:
        logger.error(f"❌ Auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )