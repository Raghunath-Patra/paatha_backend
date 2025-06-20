# backend/routes/teacher_courses.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Dict, Optional
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Course, CourseEnrollment, User, Quiz
import logging
import string
import random

router = APIRouter(prefix="/api/teacher/courses", tags=["teacher-courses"])

logger = logging.getLogger(__name__)

# Pydantic models
class CourseCreate(BaseModel):
    course_name: str
    description: Optional[str] = None
    board: str
    class_level: str
    subject: str
    max_students: Optional[int] = 100

class CourseUpdate(BaseModel):
    course_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    max_students: Optional[int] = None

class CourseResponse(BaseModel):
    id: str
    course_name: str
    course_code: str
    description: Optional[str]
    board: str
    class_level: str
    subject: str
    is_active: bool
    max_students: int
    current_students: int
    total_quizzes: int
    created_at: str
    updated_at: Optional[str]

class StudentResponse(BaseModel):
    id: str
    full_name: Optional[str]
    email: str
    status: str
    enrolled_at: str
    total_quizzes_taken: int
    average_score: float

def generate_course_code() -> str:
    """Generate a unique 8-character course code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=8))

def check_teacher_permission(user: Dict):
    """Check if user is a teacher"""
    if user.get('role') != 'teacher':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )

@router.post("/", response_model=CourseResponse)
async def create_course(
    course_data: CourseCreate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new course"""
    try:
        check_teacher_permission(current_user)
        
        # Generate unique course code
        course_code = generate_course_code()
        while db.query(Course).filter(Course.course_code == course_code).first():
            course_code = generate_course_code()
        
        # Create course
        new_course = Course(
            teacher_id=current_user['id'],
            course_name=course_data.course_name,
            course_code=course_code,
            description=course_data.description,
            board=course_data.board,
            class_level=course_data.class_level,
            subject=course_data.subject,
            max_students=course_data.max_students
        )
        
        db.add(new_course)
        db.commit()
        db.refresh(new_course)
        
        # Get student count
        student_count = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == new_course.id
        ).count()
        
        # Get quiz count
        quiz_count = db.query(Quiz).filter(
            Quiz.course_id == new_course.id
        ).count()
        
        return CourseResponse(
            id=str(new_course.id),
            course_name=new_course.course_name,
            course_code=new_course.course_code,
            description=new_course.description,
            board=new_course.board,
            class_level=new_course.class_level,
            subject=new_course.subject,
            is_active=new_course.is_active,
            max_students=new_course.max_students,
            current_students=student_count,
            total_quizzes=quiz_count,
            created_at=new_course.created_at.isoformat(),
            updated_at=new_course.updated_at.isoformat() if new_course.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating course: {str(e)}"
        )

@router.get("/", response_model=List[CourseResponse])
async def get_teacher_courses(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all courses for the current teacher"""
    try:
        check_teacher_permission(current_user)
        
        # Query courses with student and quiz counts
        query = text("""
            SELECT 
                c.*,
                COALESCE(student_counts.student_count, 0) as current_students,
                COALESCE(quiz_counts.quiz_count, 0) as total_quizzes
            FROM courses c
            LEFT JOIN (
                SELECT course_id, COUNT(*) as student_count
                FROM course_enrollments
                WHERE status = 'active'
                GROUP BY course_id
            ) student_counts ON c.id = student_counts.course_id
            LEFT JOIN (
                SELECT course_id, COUNT(*) as quiz_count
                FROM quizzes
                GROUP BY course_id
            ) quiz_counts ON c.id = quiz_counts.course_id
            WHERE c.teacher_id = :teacher_id
            ORDER BY c.created_at DESC
        """)
        
        courses = db.execute(query, {"teacher_id": current_user['id']}).fetchall()
        
        return [
            CourseResponse(
                id=str(course.id),
                course_name=course.course_name,
                course_code=course.course_code,
                description=course.description,
                board=course.board,
                class_level=course.class_level,
                subject=course.subject,
                is_active=course.is_active,
                max_students=course.max_students,
                current_students=course.current_students,
                total_quizzes=course.total_quizzes,
                created_at=course.created_at.isoformat(),
                updated_at=course.updated_at.isoformat() if course.updated_at else None
            )
            for course in courses
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching courses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching courses: {str(e)}"
        )

@router.get("/{course_id}", response_model=CourseResponse)
async def get_course_details(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific course"""
    try:
        check_teacher_permission(current_user)
        
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        # Get student count
        student_count = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.status == 'active'
        ).count()
        
        # Get quiz count
        quiz_count = db.query(Quiz).filter(
            Quiz.course_id == course.id
        ).count()
        
        return CourseResponse(
            id=str(course.id),
            course_name=course.course_name,
            course_code=course.course_code,
            description=course.description,
            board=course.board,
            class_level=course.class_level,
            subject=course.subject,
            is_active=course.is_active,
            max_students=course.max_students,
            current_students=student_count,
            total_quizzes=quiz_count,
            created_at=course.created_at.isoformat(),
            updated_at=course.updated_at.isoformat() if course.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching course details: {str(e)}"
        )

@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: str,
    course_data: CourseUpdate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a course"""
    try:
        check_teacher_permission(current_user)
        
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        # Update fields
        update_data = course_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(course, field, value)
        
        db.commit()
        db.refresh(course)
        
        # Get student count
        student_count = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.status == 'active'
        ).count()
        
        # Get quiz count
        quiz_count = db.query(Quiz).filter(
            Quiz.course_id == course.id
        ).count()
        
        return CourseResponse(
            id=str(course.id),
            course_name=course.course_name,
            course_code=course.course_code,
            description=course.description,
            board=course.board,
            class_level=course.class_level,
            subject=course.subject,
            is_active=course.is_active,
            max_students=course.max_students,
            current_students=student_count,
            total_quizzes=quiz_count,
            created_at=course.created_at.isoformat(),
            updated_at=course.updated_at.isoformat() if course.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating course: {str(e)}"
        )

@router.delete("/{course_id}")
async def delete_course(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a course"""
    try:
        check_teacher_permission(current_user)
        
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        db.delete(course)
        db.commit()
        
        return {"message": "Course deleted successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting course: {str(e)}"
        )

@router.get("/{course_id}/students", response_model=List[StudentResponse])
async def get_course_students(
    course_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all students enrolled in a course"""
    try:
        check_teacher_permission(current_user)
        
        # Verify course ownership
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        # Query students with enrollment details
        query = text("""
            SELECT 
                u.id,
                u.full_name,
                u.email,
                ce.status,
                ce.enrolled_at,
                ce.total_quizzes_taken,
                ce.average_score
            FROM course_enrollments ce
            JOIN profiles u ON ce.student_id = u.id
            WHERE ce.course_id = :course_id
            ORDER BY ce.enrolled_at DESC
        """)
        
        students = db.execute(query, {"course_id": course_id}).fetchall()
        
        return [
            StudentResponse(
                id=str(student.id),
                full_name=student.full_name,
                email=student.email,
                status=student.status,
                enrolled_at=student.enrolled_at.isoformat(),
                total_quizzes_taken=student.total_quizzes_taken,
                average_score=student.average_score
            )
            for student in students
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course students: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching course students: {str(e)}"
        )

@router.post("/{course_id}/remove-student/{student_id}")
async def remove_student(
    course_id: str,
    student_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a student from a course"""
    try:
        check_teacher_permission(current_user)
        
        # Verify course ownership
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        # Find enrollment
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == student_id
        ).first()
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found in this course"
            )
        
        # Remove enrollment
        db.delete(enrollment)
        db.commit()
        
        return {"message": "Student removed from course successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error removing student: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing student: {str(e)}"
        )