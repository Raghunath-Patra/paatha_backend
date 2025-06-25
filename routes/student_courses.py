# backend/routes/student_courses.py - TIMEZONE FIX

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Dict, Optional
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Course, CourseEnrollment, User, Quiz, QuizAttempt
from datetime import datetime, timezone, timedelta
import logging

router = APIRouter(prefix="/api/student/courses", tags=["student-courses"])

logger = logging.getLogger(__name__)

# FIXED: India timezone utilities
def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

def get_india_date():
    """Get current date in India timezone"""
    return get_india_time().date()

def ensure_india_timezone(dt):
    """Ensure datetime is in India timezone"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # If naive, assume it's already in India timezone
        return dt
    else:
        # Convert to India timezone
        utc_dt = dt.astimezone(timezone.utc)
        offset = timedelta(hours=5, minutes=30)  # FIXED: Proper IST offset
        return utc_dt.replace(tzinfo=None) + offset

# FIXED: Function to convert naive datetime to IST ISO string
def to_ist_iso_string(dt):
    """Convert naive datetime (assumed to be in IST) to ISO string with timezone info"""
    if dt is None:
        return None
    
    # If datetime is naive, assume it's in IST
    if dt.tzinfo is None:
        # Create IST timezone (UTC+5:30)
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        # Add timezone info to the datetime
        dt_with_tz = dt.replace(tzinfo=ist_tz)
        return dt_with_tz.isoformat()
    else:
        return dt.isoformat()

# NEW: Subject code decoder
SUBJECT_CODE_TO_NAME = {
    'iesc1dd': 'Science',
    'hesc1dd': 'Science', 
    'jesc1dd': 'Science',
    'iemh1dd': 'Mathematics',
    'jemh1dd': 'Mathematics',
    'kemh1dd': 'Mathematics',
    'lemh1dd': 'Mathematics (Part I)',
    'lemh2dd': 'Mathematics (Part II)',
    'hemh1dd': 'Mathematics',
    'keph1dd': 'Physics (Part I)',
    'keph2dd': 'Physics (Part II)',
    'leph1dd': 'Physics (Part I)',
    'leph2dd': 'Physics (Part II)',
    'kech1dd': 'Chemistry (Part I)',
    'kech2dd': 'Chemistry (Part II)',
    'lech1dd': 'Chemistry (Part I)',
    'lech2dd': 'Chemistry (Part II)',
    'kebo1dd': 'Biology',
    'lebo1dd': 'Biology'
}

def decode_subject_code(subject_code: str) -> str:
    """Convert subject code to human-readable name"""
    if not subject_code:
        return ""
    return SUBJECT_CODE_TO_NAME.get(subject_code.lower(), subject_code)

# Pydantic models
class CourseJoinRequest(BaseModel):
    course_code: str

class StudentCourseResponse(BaseModel):
    id: str
    course_name: str
    course_code: str
    description: Optional[str]
    board: str
    class_level: str
    subject: str
    teacher_name: Optional[str]
    teacher_email: str
    enrollment_status: str
    enrolled_at: str
    total_quizzes: int
    completed_quizzes: int
    average_score: float

class QuizSummary(BaseModel):
    id: str
    title: str
    description: Optional[str]
    total_marks: int
    passing_marks: int
    time_limit: Optional[int]
    is_published: bool
    start_time: Optional[str]
    end_time: Optional[str]
    attempts_allowed: int
    my_attempts: int
    best_score: Optional[float]
    status: str  # 'not_started', 'in_progress', 'completed', 'time_expired'
    quiz_status_value: str  # 'not_started', 'in_progress', 'completed', 'time_expired'

def check_student_permission(user: Dict):
    if user.get('role') != 'student':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this endpoint"
        )

@router.post("/join", response_model=StudentCourseResponse)
async def join_course(
    join_request: CourseJoinRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Join a course using course code"""
    try:
        check_student_permission(current_user)
        
        # Find course by code
        course = db.query(Course).filter(
            Course.course_code == join_request.course_code,
            Course.is_active == True
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or not active"
            )
        
        # Check if already enrolled
        existing_enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if existing_enrollment:
            if existing_enrollment.status == 'active':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already enrolled in this course"
                )
            else:
                # Reactivate enrollment
                existing_enrollment.status = 'active'
                db.commit()
                enrollment = existing_enrollment
        else:
            # Check if course is full
            current_enrollments = db.query(CourseEnrollment).filter(
                CourseEnrollment.course_id == course.id,
                CourseEnrollment.status == 'active'
            ).count()
            
            if current_enrollments >= course.max_students:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Course is full"
                )
            
            # Create new enrollment
            enrollment = CourseEnrollment(
                course_id=course.id,
                student_id=current_user['id'],
                status='active'
            )
            db.add(enrollment)
            db.commit()
            db.refresh(enrollment)
        
        # Get teacher info
        teacher = db.query(User).filter(User.id == course.teacher_id).first()
        
        # Get quiz stats
        total_quizzes = db.query(Quiz).filter(
            Quiz.course_id == course.id,
            Quiz.is_published == True
        ).count()
        
        completed_quizzes = db.query(QuizAttempt).filter(
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.quiz_id.in_(
                db.query(Quiz.id).filter(
                    Quiz.course_id == course.id,
                    Quiz.is_published == True
                )
            ),
            QuizAttempt.status == 'completed'
        ).count()
        
        # Get average score
        avg_score_result = db.query(func.avg(QuizAttempt.percentage)).filter(
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.quiz_id.in_(
                db.query(Quiz.id).filter(Quiz.course_id == course.id)
            ),
            QuizAttempt.status == 'completed'
        ).scalar()
        
        avg_score = float(avg_score_result) if avg_score_result else 0.0
        
        return StudentCourseResponse(
            id=str(course.id),
            course_name=course.course_name,
            course_code=course.course_code,
            description=course.description,
            board=course.board,
            class_level=course.class_level,
            subject=decode_subject_code(course.subject),
            teacher_name=teacher.full_name if teacher else None,
            teacher_email=teacher.email if teacher else "",
            enrollment_status=enrollment.status,
            enrolled_at=enrollment.enrolled_at.isoformat(),
            total_quizzes=total_quizzes,
            completed_quizzes=completed_quizzes,
            average_score=avg_score
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error joining course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error joining course: {str(e)}"
        )

@router.get("/", response_model=List[StudentCourseResponse])
async def get_enrolled_courses(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all courses the student is enrolled in"""
    try:
        check_student_permission(current_user)
        
        # Query enrolled courses with stats
        query = text("""
            SELECT 
                c.id,
                c.course_name,
                c.course_code,
                c.description,
                c.board,
                c.class_level,
                c.subject,
                ce.status as enrollment_status,
                ce.enrolled_at,
                u.full_name as teacher_name,
                u.email as teacher_email,
                COALESCE(quiz_stats.total_quizzes, 0) as total_quizzes,
                COALESCE(attempt_stats.completed_quizzes, 0) as completed_quizzes,
                COALESCE(attempt_stats.average_score, 0) as average_score
            FROM course_enrollments ce
            JOIN courses c ON ce.course_id = c.id
            JOIN profiles u ON c.teacher_id = u.id
            LEFT JOIN (
                SELECT course_id, COUNT(*) as total_quizzes
                FROM quizzes
                WHERE is_published = true
                GROUP BY course_id
            ) quiz_stats ON c.id = quiz_stats.course_id
            LEFT JOIN (
                SELECT 
                    q.course_id,
                    COUNT(DISTINCT qa.quiz_id) as completed_quizzes,
                    AVG(qa.percentage) as average_score
                FROM quiz_attempts qa
                JOIN quizzes q ON qa.quiz_id = q.id
                WHERE qa.student_id = :student_id AND qa.status = 'completed'
                GROUP BY q.course_id
            ) attempt_stats ON c.id = attempt_stats.course_id
            WHERE ce.student_id = :student_id AND ce.status = 'active'
            ORDER BY ce.enrolled_at DESC
        """)
        
        courses = db.execute(query, {"student_id": current_user['id']}).fetchall()
        
        return [
            StudentCourseResponse(
                id=str(course.id),
                course_name=course.course_name,
                course_code=course.course_code,
                description=course.description,
                board=course.board,
                class_level=course.class_level,
                subject=decode_subject_code(course.subject),
                teacher_name=course.teacher_name,
                teacher_email=course.teacher_email,
                enrollment_status=course.enrollment_status,
                enrolled_at=course.enrolled_at.isoformat(),
                total_quizzes=course.total_quizzes,
                completed_quizzes=course.completed_quizzes,
                average_score=float(course.average_score)
            )
            for course in courses
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching enrolled courses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching enrolled courses: {str(e)}"
        )

@router.get("/{course_id}/quizzes", response_model=List[QuizSummary])
async def get_course_quizzes(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quizzes for a course the student is enrolled in"""
    try:
        check_student_permission(current_user)
        
        # Verify enrollment
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == current_user['id'],
            CourseEnrollment.status == 'active'
        ).first()
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course"
            )
        
        # Query quizzes with attempt statistics
        query = text("""
            SELECT 
                q.id,
                q.title,
                q.description,
                q.total_marks,
                q.passing_marks,
                q.time_limit,
                q.is_published,
                q.start_time,
                q.end_time,
                q.attempts_allowed,
                COALESCE(attempt_stats.attempt_count, 0) as my_attempts,
                attempt_stats.best_score
            FROM quizzes q
            LEFT JOIN (
                SELECT 
                    quiz_id,
                    COUNT(*) as attempt_count,
                    MAX(percentage) as best_score
                FROM quiz_attempts
                WHERE student_id = :student_id
                GROUP BY quiz_id
            ) attempt_stats ON q.id = attempt_stats.quiz_id
            WHERE q.course_id = :course_id AND q.is_published = true
            ORDER BY q.created_at DESC
        """)
        
        quizzes = db.execute(query, {
            "course_id": course_id,
            "student_id": current_user['id']
        }).fetchall()
        
        results = []
        for quiz in quizzes:
            # Determine quiz status
            status_value = "not_started"
            if quiz.my_attempts > 0:
                if quiz.my_attempts >= quiz.attempts_allowed:
                    status_value = "completed"
                else:
                    status_value = "in_progress"
            
            # Handle datetime comparison safely with India timezone
            now = get_india_time()
            start_time = quiz.start_time
            end_time = quiz.end_time
            
            quiz_status_value = "in_progress"  # Default to in_progress
            if start_time and start_time > now:
                quiz_status_value = "not_started"
            elif end_time and end_time < now:
                quiz_status_value = "time_expired"
            
            results.append(QuizSummary(
                id=str(quiz.id),
                title=quiz.title,
                description=quiz.description,
                total_marks=quiz.total_marks,
                passing_marks=quiz.passing_marks,
                time_limit=quiz.time_limit,
                is_published=quiz.is_published,
                # FIXED: Use the new function to properly format datetime with timezone
                start_time=to_ist_iso_string(quiz.start_time),
                end_time=to_ist_iso_string(quiz.end_time),
                attempts_allowed=quiz.attempts_allowed,
                my_attempts=quiz.my_attempts,
                best_score=float(quiz.best_score) if quiz.best_score else None,
                status=status_value,
                quiz_status_value=quiz_status_value
            ))
        
        return results
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course quizzes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching course quizzes: {str(e)}"
        )

@router.post("/{course_id}/leave")
async def leave_course(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Leave a course"""
    try:
        check_student_permission(current_user)
        
        # Find enrollment
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not enrolled in this course"
            )
        
        # Update status to inactive instead of deleting
        enrollment.status = 'inactive'
        db.commit()
        
        return {"message": "Successfully left the course"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error leaving course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error leaving course: {str(e)}"
        )