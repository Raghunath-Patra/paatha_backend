# backend/routes/student_courses.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Dict, Optional
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Course, CourseEnrollment, User, Quiz, QuizAttempt
import logging

router = APIRouter(prefix="/api/student/courses", tags=["student-courses"])

logger = logging.getLogger(__name__)

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

def check_student_permission(user: Dict):
    """Check if user is a student"""
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
            subject=course.subject,
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
                subject=course.subject,
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
            status = "not_started"
            if quiz.my_attempts > 0:
                if quiz.my_attempts >= quiz.attempts_allowed:
                    status = "completed"
                else:
                    status = "in_progress"
            
            # Check time constraints
            from datetime import datetime
            now = datetime.utcnow()
            if quiz.start_time and now < quiz.start_time:
                status = "not_started"
            elif quiz.end_time and now > quiz.end_time:
                status = "time_expired"
            
            results.append(QuizSummary(
                id=str(quiz.id),
                title=quiz.title,
                description=quiz.description,
                total_marks=quiz.total_marks,
                passing_marks=quiz.passing_marks,
                time_limit=quiz.time_limit,
                is_published=quiz.is_published,
                start_time=quiz.start_time.isoformat() if quiz.start_time else None,
                end_time=quiz.end_time.isoformat() if quiz.end_time else None,
                attempts_allowed=quiz.attempts_allowed,
                my_attempts=quiz.my_attempts,
                best_score=float(quiz.best_score) if quiz.best_score else None,
                status=status
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

# Add this endpoint to routes/student_courses.py

@router.get("/{course_id}/quizzes", response_model=List[QuizSummary])
async def get_course_quizzes(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quizzes for a specific course that the student is enrolled in"""
    try:
        check_student_permission(current_user)
        
        # Verify student is enrolled in the course
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
        
        # Query quizzes with student's attempt information
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
                COALESCE(attempt_count.attempts, 0) as my_attempts,
                best_attempt.best_score,
                CASE 
                    WHEN q.is_published = false THEN 'not_published'
                    WHEN COALESCE(attempt_count.attempts, 0) = 0 THEN 'not_started'
                    WHEN COALESCE(attempt_count.attempts, 0) >= q.attempts_allowed THEN 'completed'
                    WHEN q.end_time IS NOT NULL AND NOW() > q.end_time THEN 'time_expired'
                    ELSE 'in_progress'
                END as status
            FROM quizzes q
            LEFT JOIN (
                SELECT 
                    quiz_id,
                    COUNT(*) as attempts
                FROM quiz_attempts
                WHERE student_id = :student_id
                GROUP BY quiz_id
            ) attempt_count ON q.id = attempt_count.quiz_id
            LEFT JOIN (
                SELECT 
                    quiz_id,
                    MAX(score) as best_score
                FROM quiz_attempts
                WHERE student_id = :student_id AND status = 'completed'
                GROUP BY quiz_id
            ) best_attempt ON q.id = best_attempt.quiz_id
            WHERE q.course_id = :course_id
            ORDER BY q.created_at DESC
        """)
        
        quizzes = db.execute(query, {
            "course_id": course_id,
            "student_id": current_user['id']
        }).fetchall()
        
        return [
            QuizSummary(
                id=str(quiz.id),
                title=quiz.title,
                description=quiz.description,
                total_marks=quiz.total_marks,
                passing_marks=quiz.passing_marks,
                time_limit=quiz.time_limit,
                is_published=quiz.is_published,
                start_time=quiz.start_time.isoformat() if quiz.start_time else None,
                end_time=quiz.end_time.isoformat() if quiz.end_time else None,
                attempts_allowed=quiz.attempts_allowed,
                my_attempts=quiz.my_attempts,
                best_score=float(quiz.best_score) if quiz.best_score else None,
                status=quiz.status
            )
            for quiz in quizzes
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course quizzes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching course quizzes: {str(e)}"
        )