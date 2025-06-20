# backend/routes/admin.py - Admin routes for teacher management

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from config.database import get_db
from config.security import require_admin, get_current_user
from models import User, Course, Quiz, QuizAttempt, CourseEnrollment, Question, QuizQuestion
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])

# Pydantic models
class TeacherVerificationRequest(BaseModel):
    teacher_id: str
    approve: bool
    notes: Optional[str] = None

class UpdateUserRoleRequest(BaseModel):
    user_id: str
    new_role: str

class SystemStatsResponse(BaseModel):
    total_users: int
    total_teachers: int
    verified_teachers: int
    pending_teacher_verifications: int
    total_courses: int
    total_quizzes: int
    total_questions: int
    recent_signups: int

# Dashboard and Statistics
@router.get("/dashboard", response_model=SystemStatsResponse)
async def get_admin_dashboard(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get admin dashboard with system statistics"""
    try:
        # Get user statistics
        total_users = db.query(User).count()
        total_teachers = db.query(User).filter(User.role == "teacher").count()
        verified_teachers = db.query(User).filter(
            User.role == "teacher",
            User.teacher_verified == True
        ).count()
        pending_teacher_verifications = db.query(User).filter(
            User.role == "teacher",
            User.teacher_verified == False
        ).count()
        
        # Get course and quiz statistics
        total_courses = db.query(Course).count()
        total_quizzes = db.query(Quiz).count()
        total_questions = db.query(Question).count()
        
        # Get recent signups (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_signups = db.query(User).filter(
            User.created_at >= week_ago
        ).count()
        
        return SystemStatsResponse(
            total_users=total_users,
            total_teachers=total_teachers,
            verified_teachers=verified_teachers,
            pending_teacher_verifications=pending_teacher_verifications,
            total_courses=total_courses,
            total_quizzes=total_quizzes,
            total_questions=total_questions,
            recent_signups=recent_signups
        )
    except Exception as e:
        raise HTTPException(500, f"Error fetching admin dashboard: {str(e)}")

# Teacher Management
@router.get("/teachers/pending")
async def get_pending_teacher_verifications(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get list of teachers awaiting verification"""
    try:
        pending_teachers = db.query(User).filter(
            User.role == "teacher",
            User.teacher_verified == False
        ).order_by(User.created_at).all()
        
        teachers_list = []
        for teacher in pending_teachers:
            teachers_list.append({
                "id": str(teacher.id),
                "email": teacher.email,
                "full_name": teacher.full_name,
                "institution_name": teacher.institution_name,
                "phone_number": teacher.phone_number,
                "teaching_experience": teacher.teaching_experience,
                "qualification": teacher.qualification,
                "subjects_taught": teacher.subjects_taught,
                "board": teacher.board,
                "created_at": teacher.created_at.isoformat() if teacher.created_at else None
            })
        
        return {"pending_teachers": teachers_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching pending teachers: {str(e)}")

@router.post("/teachers/verify")
async def verify_teacher(
    verification: TeacherVerificationRequest,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve or reject teacher verification"""
    try:
        teacher = db.query(User).filter(
            User.id == verification.teacher_id,
            User.role == "teacher"
        ).first()
        
        if not teacher:
            raise HTTPException(404, "Teacher not found")
        
        if verification.approve:
            teacher.teacher_verified = True
            message = f"Teacher {teacher.full_name} has been verified and can now create courses"
        else:
            # If rejected, optionally change role back to student
            teacher.role = "student"
            teacher.teacher_verified = False
            message = f"Teacher application for {teacher.full_name} has been rejected"
        
        db.commit()
        
        # TODO: Send notification email to teacher
        
        return {
            "message": message,
            "teacher": {
                "id": str(teacher.id),
                "name": teacher.full_name,
                "email": teacher.email,
                "verified": teacher.teacher_verified,
                "role": teacher.role
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error verifying teacher: {str(e)}")

@router.get("/teachers")
async def get_all_teachers(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    verified_only: bool = Query(False),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """Get list of all teachers with their statistics"""
    try:
        query = db.query(User).filter(User.role == "teacher")
        
        if verified_only:
            query = query.filter(User.teacher_verified == True)
        
        teachers = query.offset(offset).limit(limit).all()
        
        teachers_list = []
        for teacher in teachers:
            # Get teacher statistics
            course_count = db.query(Course).filter(Course.teacher_id == teacher.id).count()
            quiz_count = db.query(Quiz).filter(Quiz.teacher_id == teacher.id).count()
            student_count = db.query(func.count(CourseEnrollment.student_id.distinct())).join(
                Course, CourseEnrollment.course_id == Course.id
            ).filter(Course.teacher_id == teacher.id).scalar()
            
            teachers_list.append({
                "id": str(teacher.id),
                "email": teacher.email,
                "full_name": teacher.full_name,
                "institution_name": teacher.institution_name,
                "teaching_experience": teacher.teaching_experience,
                "qualification": teacher.qualification,
                "subjects_taught": teacher.subjects_taught,
                "teacher_verified": teacher.teacher_verified,
                "created_at": teacher.created_at.isoformat() if teacher.created_at else None,
                "statistics": {
                    "total_courses": course_count,
                    "total_quizzes": quiz_count,
                    "total_students": student_count or 0
                }
            })
        
        return {"teachers": teachers_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching teachers: {str(e)}")

# User Management
@router.post("/users/update-role")
async def update_user_role(
    request: UpdateUserRoleRequest,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update user role (admin only)"""
    try:
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        
        old_role = user.role
        user.role = request.new_role
        
        # If making someone a teacher, they need verification
        if request.new_role == "teacher":
            user.teacher_verified = False
        
        db.commit()
        
        return {
            "message": f"User role updated from {old_role} to {request.new_role}",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "teacher_verified": user.teacher_verified if user.role == "teacher" else None
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error updating user role: {str(e)}")

@router.get("/users")
async def get_all_users(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """Get list of all users with filtering"""
    try:
        query = db.query(User)
        
        if role:
            query = query.filter(User.role == role)
        
        if search:
            query = query.filter(
                User.full_name.ilike(f"%{search}%") |
                User.email.ilike(f"%{search}%")
            )
        
        users = query.order_by(desc(User.created_at)).offset(offset).limit(limit).all()
        
        users_list = []
        for user in users:
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "board": user.board,
                "class_level": user.class_level,
                "is_verified": user.is_verified,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
            
            # Add teacher-specific data if applicable
            if user.role == "teacher":
                user_data.update({
                    "institution_name": user.institution_name,
                    "teacher_verified": user.teacher_verified,
                    "teaching_experience": user.teaching_experience
                })
            
            users_list.append(user_data)
        
        return {"users": users_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching users: {str(e)}")

# Course and Quiz Management
@router.get("/courses")
async def get_all_courses(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    teacher_id: Optional[str] = Query(None),
    board: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    active_only: bool = Query(False),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """Get list of all courses with filtering"""
    try:
        query = db.query(Course)
        
        if teacher_id:
            query = query.filter(Course.teacher_id == teacher_id)
        if board:
            query = query.filter(Course.board == board)
        if subject:
            query = query.filter(Course.subject == subject)
        if active_only:
            query = query.filter(Course.is_active == True)
        
        courses = query.order_by(desc(Course.created_at)).offset(offset).limit(limit).all()
        
        courses_list = []
        for course in courses:
            enrollment_count = db.query(CourseEnrollment).filter(
                CourseEnrollment.course_id == course.id,
                CourseEnrollment.status == 'active'
            ).count()
            
            quiz_count = db.query(Quiz).filter(Quiz.course_id == course.id).count()
            
            courses_list.append({
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "teacher_name": course.teacher.full_name,
                "teacher_email": course.teacher.email,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "is_active": course.is_active,
                "enrolled_students": enrollment_count,
                "total_quizzes": quiz_count,
                "created_at": course.created_at.isoformat()
            })
        
        return {"courses": courses_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching courses: {str(e)}")

@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a course (admin only)"""
    try:
        course = db.query(Course).filter(Course.id == course_id).first()
        if not course:
            raise HTTPException(404, "Course not found")
        
        # Check if course has enrollments or quiz attempts
        enrollment_count = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id
        ).count()
        
        quiz_attempt_count = db.query(QuizAttempt).join(Quiz).filter(
            Quiz.course_id == course_id
        ).count()
        
        if enrollment_count > 0 or quiz_attempt_count > 0:
            raise HTTPException(
                400, 
                "Cannot delete course with enrollments or quiz attempts. "
                "Consider deactivating instead."
            )
        
        course_name = course.course_name
        teacher_name = course.teacher.full_name
        
        db.delete(course)
        db.commit()
        
        return {
            "message": f"Course '{course_name}' by {teacher_name} has been deleted"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error deleting course: {str(e)}")

# System Analytics
@router.get("/analytics/engagement")
async def get_engagement_analytics(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = Query(30, description="Number of days to analyze")
):
    """Get platform engagement analytics"""
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # New user registrations
        new_users = db.query(User).filter(User.created_at >= start_date).count()
        
        # Course enrollments
        new_enrollments = db.query(CourseEnrollment).filter(
            CourseEnrollment.enrolled_at >= start_date
        ).count()
        
        # Quiz attempts
        quiz_attempts = db.query(QuizAttempt).filter(
            QuizAttempt.started_at >= start_date
        ).count()
        
        # Active teachers (created courses/quizzes recently)
        active_teachers = db.query(User.id.distinct()).join(Course).filter(
            User.role == "teacher",
            Course.created_at >= start_date
        ).count()
        
        # Most popular subjects
        popular_subjects = db.query(
            Course.subject,
            func.count(CourseEnrollment.id).label('enrollment_count')
        ).join(CourseEnrollment).filter(
            CourseEnrollment.enrolled_at >= start_date
        ).group_by(Course.subject).order_by(
            desc('enrollment_count')
        ).limit(10).all()
        
        return {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "metrics": {
                "new_users": new_users,
                "new_enrollments": new_enrollments,
                "quiz_attempts": quiz_attempts,
                "active_teachers": active_teachers
            },
            "popular_subjects": [
                {"subject": subject, "enrollments": count}
                for subject, count in popular_subjects
            ]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching engagement analytics: {str(e)}")

@router.get("/analytics/questions")
async def get_question_analytics(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get analytics about AI questions usage in quizzes"""
    try:
        # Total AI questions available
        total_ai_questions = db.query(Question).count()
        
        # AI questions used in quizzes
        used_ai_questions = db.query(func.count(func.distinct(QuizQuestion.ai_question_id))).filter(
            QuizQuestion.ai_question_id.isnot(None)
        ).scalar()
        
        # Custom questions created by teachers
        total_custom_questions = db.query(QuizQuestion).filter(
            QuizQuestion.question_source == 'custom'
        ).count()
        
        # Most used AI questions
        popular_ai_questions = db.query(
            Question.human_readable_id,
            Question.question_text,
            Question.subject,
            Question.difficulty,
            func.count(QuizQuestion.id).label('usage_count')
        ).join(QuizQuestion, Question.id == QuizQuestion.ai_question_id).group_by(
            Question.id
        ).order_by(desc('usage_count')).limit(10).all()
        
        # Subject distribution
        subject_distribution = db.query(
            Question.subject,
            func.count(Question.id).label('question_count')
        ).group_by(Question.subject).order_by(desc('question_count')).all()
        
        return {
            "ai_questions": {
                "total_available": total_ai_questions,
                "used_in_quizzes": used_ai_questions or 0,
                "usage_percentage": (used_ai_questions or 0) / total_ai_questions * 100 if total_ai_questions > 0 else 0
            },
            "custom_questions": {
                "total_created": total_custom_questions
            },
            "popular_ai_questions": [
                {
                    "human_readable_id": q.human_readable_id,
                    "question_text": q.question_text[:100] + "..." if len(q.question_text) > 100 else q.question_text,
                    "subject": q.subject,
                    "difficulty": q.difficulty,
                    "usage_count": q.usage_count
                }
                for q in popular_ai_questions
            ],
            "subject_distribution": [
                {"subject": subject, "question_count": count}
                for subject, count in subject_distribution
            ]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching question analytics: {str(e)}")

# System Health
@router.get("/system/health")
async def check_system_health(
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Check system health and identify potential issues"""
    try:
        issues = []
        
        # Check for teachers without verification
        unverified_teachers = db.query(User).filter(
            User.role == "teacher",
            User.teacher_verified == False
        ).count()
        
        if unverified_teachers > 0:
            issues.append({
                "type": "pending_verifications",
                "message": f"{unverified_teachers} teachers awaiting verification",
                "count": unverified_teachers
            })
        
        # Check for courses without students
        empty_courses = db.query(Course).filter(
            Course.is_active == True,
            ~Course.id.in_(
                db.query(CourseEnrollment.course_id).filter(
                    CourseEnrollment.status == 'active'
                )
            )
        ).count()
        
        if empty_courses > 0:
            issues.append({
                "type": "empty_courses",
                "message": f"{empty_courses} active courses have no enrolled students",
                "count": empty_courses
            })
        
        # Check for quizzes without questions
        empty_quizzes = db.query(Quiz).filter(
            ~Quiz.id.in_(db.query(QuizQuestion.quiz_id))
        ).count()
        
        if empty_quizzes > 0:
            issues.append({
                "type": "empty_quizzes",
                "message": f"{empty_quizzes} quizzes have no questions",
                "count": empty_quizzes
            })
        
        return {
            "status": "healthy" if len(issues) == 0 else "issues_found",
            "issues": issues,
            "checked_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(500, f"Error checking system health: {str(e)}")