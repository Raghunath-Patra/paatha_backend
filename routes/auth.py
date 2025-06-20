# backend/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user, require_admin
from models import User
from datetime import datetime
import uuid
from typing import Optional, List
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    board: Optional[str] = None
    class_level: Optional[str] = None
    teacher_verified: Optional[bool] = None

class SyncUserRequest(BaseModel):
    email: Optional[str]
    full_name: Optional[str]
    board: Optional[str]
    class_level: Optional[str]
    role: Optional[str] = "student"  # Add role but default to student

class TeacherRegistrationRequest(BaseModel):
    email: str
    full_name: str
    institution_name: str
    phone_number: str
    teaching_experience: int
    qualification: str
    subjects_taught: List[str]
    board: str

class UpdateRoleRequest(BaseModel):
    user_id: str
    new_role: str
    verify_teacher: Optional[bool] = False

# @router.post("/sync-user")
# async def sync_user(
#     user_data: SyncUserRequest,
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Sync Supabase user data with backend database"""
#     try:
#         print(f"Syncing user data for {current_user['id']}")
#         print(f"User data received: {user_data}")
        
#         # Check if user exists
#         user = db.query(User).filter(User.id == current_user['id']).first()

#         if user:
#             print("Updating existing user")
#             # Update existing user with non-None values
#             if user_data.email is not None:
#                 user.email = user_data.email
#             if user_data.full_name is not None:
#                 user.full_name = user_data.full_name
#             if user_data.board is not None:
#                 user.board = user_data.board
#             if user_data.class_level is not None:
#                 user.class_level = user_data.class_level
            
#             # SECURITY: Only allow role change in specific conditions
#             if user_data.role and user_data.role != user.role:
#                 # Students can request to become teachers (but need verification)
#                 if user.role == "student" and user_data.role == "teacher":
#                     user.role = "teacher"
#                     user.teacher_verified = False  # Needs admin verification
#                 # Don't allow other role changes without admin
#                 else:
#                     print(f"Role change denied: {user.role} -> {user_data.role}")
#         else:
#             print("Creating new user")
#             # Create new user - default role is student
#             role = "student"  # Force student role for new users
#             if user_data.role == "teacher":
#                 role = "teacher"
                
#             new_user = User(
#                 id=current_user['id'],
#                 email=user_data.email or current_user['email'],
#                 full_name=user_data.full_name or "",
#                 role=role,
#                 board=user_data.board,
#                 class_level=user_data.class_level,
#                 teacher_verified=False if role == "teacher" else None,
#                 is_verified=True,
#                 created_at=datetime.utcnow()
#             )
#             db.add(new_user)
        
#         db.commit()
#         db.refresh(user if user else new_user)
        
#         final_user = user if user else new_user
        
#         return {
#             "message": "User data synced successfully",
#             "user": {
#                 "id": str(final_user.id),
#                 "email": final_user.email,
#                 "full_name": final_user.full_name,
#                 "role": final_user.role,
#                 "board": final_user.board,
#                 "class_level": final_user.class_level,
#                 "teacher_verified": final_user.teacher_verified
#             }
#         }
#     except Exception as e:
#         print(f"Error syncing user: {str(e)}")
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=str(e)
#         )

@router.post("/request-teacher-role")
async def request_teacher_role(
    teacher_data: TeacherRegistrationRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request teacher role with verification"""
    try:
        user = db.query(User).filter(User.id == current_user['id']).first()
        if not user:
            raise HTTPException(404, "User not found")
        
        # Update user with teacher information
        user.role = "teacher"
        user.full_name = teacher_data.full_name
        user.institution_name = teacher_data.institution_name
        user.phone_number = teacher_data.phone_number
        user.teaching_experience = teacher_data.teaching_experience
        user.qualification = teacher_data.qualification
        user.subjects_taught = teacher_data.subjects_taught
        user.board = teacher_data.board
        user.teacher_verified = False  # Needs admin verification
        
        db.commit()
        
        # TODO: Send notification to admin for verification
        
        return {
            "message": "Teacher role requested successfully. Awaiting admin verification.",
            "status": "pending_verification"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error requesting teacher role: {str(e)}")

@router.post("/admin/update-role")
async def update_user_role(
    request: UpdateRoleRequest,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Update user role and verification status"""
    try:
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        
        old_role = user.role
        user.role = request.new_role
        
        # If making someone a teacher, set verification status
        if request.new_role == "teacher":
            user.teacher_verified = request.verify_teacher or False
        
        db.commit()
        
        return {
            "message": f"User role updated from {old_role} to {request.new_role}",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "teacher_verified": user.teacher_verified
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error updating role: {str(e)}")

@router.get("/admin/pending-teachers")
async def get_pending_teacher_verifications(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Get list of teachers awaiting verification"""
    try:
        pending_teachers = db.query(User).filter(
            User.role == "teacher",
            User.teacher_verified == False
        ).all()
        
        return {
            "pending_teachers": [
                {
                    "id": str(teacher.id),
                    "email": teacher.email,
                    "full_name": teacher.full_name,
                    "institution_name": teacher.institution_name,
                    "teaching_experience": teacher.teaching_experience,
                    "qualification": teacher.qualification,
                    "subjects_taught": teacher.subjects_taught,
                    "created_at": teacher.created_at.isoformat() if teacher.created_at else None
                }
                for teacher in pending_teachers
            ]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching pending teachers: {str(e)}")

@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's complete information"""
    try:
        user = db.query(User).filter(User.id == current_user['id']).first()
        if not user:
            raise HTTPException(404, "User not found")
        
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "board": user.board,
            "class_level": user.class_level,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        
        # Add teacher-specific fields if user is a teacher
        if user.role == "teacher":
            user_data.update({
                "institution_name": user.institution_name,
                "phone_number": user.phone_number,
                "teaching_experience": user.teaching_experience,
                "qualification": user.qualification,
                "subjects_taught": user.subjects_taught,
                "teacher_verified": user.teacher_verified
            })
        
        return {"user": user_data}
    except Exception as e:
        raise HTTPException(500, f"Error fetching user info: {str(e)}")

# # backend/routes/auth.py

# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from config.database import get_db
# from config.security import get_current_user
# from models import User
# from datetime import datetime
# import uuid
# from typing import Optional
# from pydantic import BaseModel, EmailStr

# router = APIRouter(prefix="/auth", tags=["auth"])

# class UserResponse(BaseModel):
#     id: str
#     email: str
#     full_name: Optional[str] = None
#     board: Optional[str] = None
#     class_level: Optional[str] = None

# class SyncUserRequest(BaseModel):
#     email: Optional[str]
#     full_name: Optional[str]
#     board: Optional[str]
#     class_level: Optional[str]

# backend/routes/auth.py - Updated sync_user function

# backend/routes/auth.py
@router.post("/sync-user")
async def sync_user(
    user_data: SyncUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync Supabase user data with backend database"""
    try:
        print(f"Syncing user data for {current_user['id']}")
        print(f"User data received: {user_data}")
        
        # Check if user exists
        try:
            user = db.query(User).filter(User.id == current_user['id']).first()
            print(f"User query result: {user}")
        except Exception as e:
            print(f"Error querying user: {str(e)}")
            raise

        if user:
            print("Updating existing user")
            # Update existing user with non-None values
            if user_data.email is not None:
                user.email = user_data.email
            if user_data.full_name is not None:
                user.full_name = user_data.full_name
            if user_data.board is not None:
                user.board = user_data.board
            if user_data.class_level is not None:
                user.class_level = user_data.class_level
        else:
            print("Creating new user")
            # Create new user
            new_user = User(
                id=current_user['id'],
                email=user_data.email or current_user['email'],
                full_name=user_data.full_name or "",
                board=user_data.board,
                class_level=user_data.class_level,
                is_verified=True,
                created_at=datetime.utcnow()
            )
            db.add(new_user)
        
        try:
            db.commit()
            print("Database commit successful")
        except Exception as e:
            print(f"Error committing to database: {str(e)}")
            db.rollback()
            raise
            
        return {"message": "User data synced successfully"}
    except Exception as e:
        print(f"Error syncing user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )