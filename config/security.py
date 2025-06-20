# backend/config/security.py
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from config.database import get_db
from models import User
import os
from dotenv import load_dotenv
import httpx
from passlib.context import CryptContext

load_dotenv()

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

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security), 
    db: Session = Depends(get_db)
):
    """
    Validate JWT token with Supabase Auth and fetch user role from database
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials
        
        # Call Supabase Auth API to get user
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

        supabase_user = response.json()
        
        # Get user role from database
        user = db.query(User).filter(User.id == supabase_user['id']).first()
        
        # Return user data with role from database
        return {
            "id": supabase_user['id'],
            "email": supabase_user['email'],
            "role": user.role if user else "student",  # Default to student
            "email_verified": supabase_user.get('email_confirmed_at') is not None,
            "supabase_data": supabase_user  # Keep original data if needed
        }

    except Exception as e:
        print(f"Auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Authorization dependencies
def require_role(required_role: str):
    """Create a dependency that requires a specific role"""
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. {required_role.title()} role required."
            )
        return current_user
    return role_checker

def require_any_role(*roles: str):
    """Create a dependency that requires any of the specified roles"""
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. One of these roles required: {', '.join(roles)}"
            )
        return current_user
    return role_checker

def require_teacher_or_admin():
    """Require teacher or admin role"""
    return require_any_role("teacher", "admin")

def require_verified_teacher():
    """Require verified teacher"""
    def teacher_checker(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        if current_user.get("role") != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Teacher role required"
            )
        
        # Check if teacher is verified
        user = db.query(User).filter(User.id == current_user['id']).first()
        if not user or not user.teacher_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Teacher account not verified. Contact admin."
            )
        
        return current_user
    return teacher_checker

# Convenience dependencies
require_student = require_role("student")
require_teacher = require_role("teacher") 
require_admin = require_role("admin")

# Check if user owns a resource
def check_resource_ownership(user_id: str, resource_owner_id: str):
    """Check if user owns a resource"""
    if user_id != str(resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own resources."
        )

def check_teacher_course_access(current_user: dict, course_teacher_id: str):
    """Check if teacher can access a specific course"""
    if current_user.get("role") == "admin":
        return  # Admins can access any course
    
    if current_user.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher role required"
        )
    
    if current_user.get("id") != str(course_teacher_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own courses."
        )