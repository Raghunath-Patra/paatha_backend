# backend/routes/teacher_courses.py - ENHANCED VERSION with Practice Performance and Subject Decoder

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, or_
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Course, CourseEnrollment, User, Quiz, UserAttempt
import logging
import json

router = APIRouter(prefix="/api/teacher/courses", tags=["teacher-courses"])

logger = logging.getLogger(__name__)

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

# Existing models...
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

# NEW: Practice Performance Models
class StudentPracticePerformance(BaseModel):
    student_id: str
    student_name: Optional[str]
    student_email: str
    total_practice_attempts: int
    average_practice_score: float  # Out of 10
    total_practice_time: int  # In seconds
    unique_questions_attempted: int
    chapters_covered: List[int]
    best_score: float
    latest_attempt_date: Optional[str]
    performance_trend: str  # "improving", "declining", "stable"

class ChapterPerformance(BaseModel):
    chapter: int
    chapter_name: Optional[str] = None
    total_attempts: int
    average_score: float
    student_count: int
    best_score: float
    worst_score: float

class PracticePerformanceStats(BaseModel):
    total_students_practiced: int
    total_practice_attempts: int
    overall_average_score: float
    most_attempted_chapter: Optional[int]
    best_performing_chapter: Optional[int]
    chapters_covered: List[int]

class CoursePracticePerformanceResponse(BaseModel):
    students: List[StudentPracticePerformance]
    chapters: List[ChapterPerformance]
    stats: PracticePerformanceStats

# Add after the existing CoursePracticePerformanceResponse model
class StudentPracticeDetail(BaseModel):
    student_id: str
    student_name: Optional[str]
    student_email: str
    total_practice_attempts: int
    average_practice_score: float
    total_practice_time: int
    unique_questions_attempted: int
    chapters_covered: List[int]
    best_score: float
    worst_score: float
    latest_attempt_date: Optional[str]
    performance_trend: str
    streak_days: int
    last_practice_date: Optional[str]
    weekly_attempts: int
    improvement_rate: float

class ChapterDetail(BaseModel):
    chapter: int
    chapter_name: Optional[str] = None
    attempts: int
    average_score: float
    best_score: float
    worst_score: float
    time_spent: int
    questions_attempted: int
    accuracy_rate: float
    last_attempted: str
    difficulty_distribution: Dict[str, int]

class PracticeSession(BaseModel):
    id: str
    date: str
    chapter: int
    questions_attempted: int
    score: float
    time_spent: int
    accuracy: float
    topics_covered: List[str]

class PerformanceAnalytics(BaseModel):
    weekly_trend: List[Dict[str, Any]]
    accuracy_by_topic: List[Dict[str, Any]]
    time_distribution: List[Dict[str, int]]
    streak_info: Dict[str, Any]

class StudentPracticeDetailsResponse(BaseModel):
    student: StudentPracticeDetail
    chapters: List[ChapterDetail]
    recent_sessions: List[PracticeSession]
    performance_analytics: PerformanceAnalytics
    recommendations: List[str]

def check_teacher_permission(user: Dict):
    """Check if user is a teacher"""
    if user.get('role') != 'teacher':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )

# Existing endpoints... (keeping all the original ones)

@router.post("/", response_model=CourseResponse)
async def create_course(
    course_data: CourseCreate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new course"""
    try:
        check_teacher_permission(current_user)
        
        new_course = Course(
            teacher_id=current_user['id'],
            course_name=course_data.course_name,
            description=course_data.description,
            board=course_data.board,
            class_level=course_data.class_level,
            subject=course_data.subject,
            max_students=course_data.max_students
        )
        
        db.add(new_course)
        db.commit()
        db.refresh(new_course)
        
        stats_query = text("""
            SELECT 
                COALESCE(student_count, 0) as current_students,
                COALESCE(quiz_count, 0) as total_quizzes
            FROM (
                SELECT 
                    (SELECT COUNT(*) FROM course_enrollments WHERE course_id = :course_id AND status = 'active') as student_count,
                    (SELECT COUNT(*) FROM quizzes WHERE course_id = :course_id) as quiz_count
            ) stats
        """)
        
        stats = db.execute(stats_query, {"course_id": str(new_course.id)}).fetchone()
        
        return CourseResponse(
            id=str(new_course.id),
            course_name=new_course.course_name,
            course_code=new_course.course_code,
            description=new_course.description,
            board=new_course.board,
            class_level=new_course.class_level,
            subject=decode_subject_code(new_course.subject),  # FIXED: Decode subject
            is_active=new_course.is_active,
            max_students=new_course.max_students,
            current_students=stats.current_students if stats else 0,
            total_quizzes=stats.total_quizzes if stats else 0,
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
        
        query = text("""
            SELECT 
                c.id,
                c.course_name,
                c.course_code,
                c.description,
                c.board,
                c.class_level,
                c.subject,
                c.is_active,
                c.max_students,
                c.created_at,
                c.updated_at,
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
                subject=decode_subject_code(course.subject),  # FIXED: Decode subject
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
        
        query = text("""
            SELECT 
                c.id,
                c.course_name,
                c.course_code,
                c.description,
                c.board,
                c.class_level,
                c.subject,
                c.is_active,
                c.max_students,
                c.created_at,
                c.updated_at,
                (SELECT COUNT(*) FROM course_enrollments WHERE course_id = c.id AND status = 'active') as current_students,
                (SELECT COUNT(*) FROM quizzes WHERE course_id = c.id) as total_quizzes
            FROM courses c
            WHERE c.id = :course_id AND c.teacher_id = :teacher_id
        """)
        
        course = db.execute(query, {
            "course_id": course_id, 
            "teacher_id": current_user['id']
        }).fetchone()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        return CourseResponse(
            id=str(course.id),
            course_name=course.course_name,
            course_code=course.course_code,
            description=course.description,
            board=course.board,
            class_level=course.class_level,
            subject=decode_subject_code(course.subject),  # FIXED: Decode subject
            is_active=course.is_active,
            max_students=course.max_students,
            current_students=course.current_students,
            total_quizzes=course.total_quizzes,
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
        
        update_data = course_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(course, field, value)
        
        db.commit()
        db.refresh(course)
        
        stats_query = text("""
            SELECT 
                (SELECT COUNT(*) FROM course_enrollments WHERE course_id = :course_id AND status = 'active') as current_students,
                (SELECT COUNT(*) FROM quizzes WHERE course_id = :course_id) as total_quizzes
        """)
        
        stats = db.execute(stats_query, {"course_id": course_id}).fetchone()
        
        return CourseResponse(
            id=str(course.id),
            course_name=course.course_name,
            course_code=course.course_code,
            description=course.description,
            board=course.board,
            class_level=course.class_level,
            subject=decode_subject_code(course.subject),  # FIXED: Decode subject
            is_active=course.is_active,
            max_students=course.max_students,
            current_students=stats.current_students if stats else 0,
            total_quizzes=stats.total_quizzes if stats else 0,
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
    """Delete a course and all related data"""
    try:
        check_teacher_permission(current_user)
        
        # Find the course and verify ownership
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or you don't have permission to delete it"
            )
        
        # Delete the course - cascade will handle all related data
        db.delete(course)
        db.commit()
        
        return {"message": "Course and all related data deleted successfully"}
        
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
        
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
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
        
        verify_query = text("""
            SELECT ce.id
            FROM course_enrollments ce
            JOIN courses c ON ce.course_id = c.id
            WHERE c.id = :course_id 
              AND c.teacher_id = :teacher_id
              AND ce.student_id = :student_id
        """)
        
        enrollment = db.execute(verify_query, {
            "course_id": course_id,
            "teacher_id": current_user['id'],
            "student_id": student_id
        }).fetchone()
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found in your course"
            )
        
        delete_query = text("""
            DELETE FROM course_enrollments 
            WHERE course_id = :course_id AND student_id = :student_id
        """)
        
        db.execute(delete_query, {
            "course_id": course_id,
            "student_id": student_id
        })
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

# NEW: Practice Performance Endpoints

@router.get("/{course_id}/practice-performance", response_model=CoursePracticePerformanceResponse)
async def get_course_practice_performance(
    course_id: str,
    student_id: Optional[str] = None,
    chapter: Optional[int] = None,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get practice performance for all students in a course - SIMPLIFIED VERSION"""
    try:
        logger.info(f"Starting get_course_practice_performance for course_id: {course_id}, teacher_id: {current_user['id']}")
        logger.info(f"Filters - student_id: {student_id}, chapter: {chapter}")
        
        check_teacher_permission(current_user)
        logger.debug("Teacher permission check passed")
        
        # Verify course ownership and get course details
        course_query = text("""
            SELECT id, board, class_level, subject
            FROM courses 
            WHERE id = :course_id AND teacher_id = :teacher_id
        """)
        
        logger.debug(f"Executing course query for course_id: {course_id}, teacher_id: {current_user['id']}")
        course = db.execute(course_query, {
            "course_id": course_id,
            "teacher_id": current_user['id']
        }).fetchone()
        
        if not course:
            logger.warning(f"Course not found - course_id: {course_id}, teacher_id: {current_user['id']}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        logger.info(f"Course found - ID: {course.id}, Board: {course.board}, Class: {course.class_level}, Subject: {course.subject}")
        
        # Get enrolled students for this course
        enrolled_students_query = text("""
            SELECT ce.student_id, u.full_name, u.email 
            FROM course_enrollments ce
            JOIN profiles u ON ce.student_id = u.id
            WHERE ce.course_id = :course_id AND ce.status = 'active'
        """)
        
        logger.debug(f"Fetching enrolled students for course_id: {course_id}")
        enrolled_students = db.execute(enrolled_students_query, {"course_id": course_id}).fetchall()
        
        logger.info(f"Found {len(enrolled_students)} enrolled students")
        if len(enrolled_students) > 0:
            logger.debug(f"Sample enrolled student: {enrolled_students[0].full_name} ({enrolled_students[0].student_id})")
        
        if not enrolled_students:
            logger.warning("No enrolled students found, returning empty response")
            return CoursePracticePerformanceResponse(
                students=[],
                chapters=[],
                stats=PracticePerformanceStats(
                    total_students_practiced=0,
                    total_practice_attempts=0,
                    overall_average_score=0.0,
                    most_attempted_chapter=None,
                    best_performing_chapter=None,
                    chapters_covered=[]
                )
            )
        
        # Get student UUIDs for the query
        student_uuids = [str(student.student_id) for student in enrolled_students]
        student_uuid_placeholders = "'" + "','".join(student_uuids) + "'"
        
        logger.debug(f"Student UUIDs for query: {student_uuids[:3]}{'...' if len(student_uuids) > 3 else ''}")
        
        # Build the main query to fetch practice attempts
        base_query = f"""
            SELECT 
                ua.user_id,
                u.full_name,
                u.email,
                ua.chapter,
                COUNT(*) as attempt_count,
                AVG(ua.score) as avg_score,
                MAX(ua.score) as max_score,
                MIN(ua.score) as min_score,
                SUM(COALESCE(ua.time_taken, 0)) as total_time,
                COUNT(DISTINCT ua.question_id) as unique_questions,
                MAX(ua.created_at) as latest_attempt
            FROM user_attempts ua
            JOIN profiles u ON ua.user_id = u.id
            WHERE ua.user_id::text IN ({student_uuid_placeholders})
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
        """
        
        # Add filters if specified
        if student_id:
            base_query += f" AND ua.user_id::text = '{student_id}'"
            logger.info(f"Added student_id filter: {student_id}")
        if chapter:
            base_query += " AND ua.chapter = :chapter"
            logger.info(f"Added chapter filter: {chapter}")
            
        base_query += " GROUP BY ua.user_id, u.full_name, u.email, ua.chapter"
        base_query += " ORDER BY u.full_name, ua.chapter"
        
        # Set parameters
        params = {
            "course_board": course.board,
            "course_class": course.class_level,
            "course_subject": course.subject
        }
        
        if chapter:
            params["chapter"] = chapter
            
        logger.info(f"Query parameters: {params}")
        logger.debug(f"Executing performance query...")
        
        performance_data = db.execute(text(base_query), params).fetchall()
        
        logger.info(f"Performance query returned {len(performance_data)} rows")
        if len(performance_data) > 0:
            logger.debug(f"Sample performance row: User: {performance_data[0].full_name}, Chapter: {performance_data[0].chapter}, Attempts: {performance_data[0].attempt_count}, Avg Score: {performance_data[0].avg_score}")
        else:
            logger.warning("No performance data found - checking if this is expected")
            logger.debug(f"Query was looking for board: {course.board}, class: {course.class_level}, subject: {course.subject}")
        
        # Process student performance
        student_performance_map = {}
        chapter_performance_map = {}
        all_chapters = set()
        
        logger.debug("Starting data processing...")
        
        for i, row in enumerate(performance_data):
            if i == 0:
                logger.debug(f"Processing first row: {row.full_name}, Chapter {row.chapter}")
            
            student_id_key = str(row.user_id)
            chapter_key = row.chapter
            
            # Track chapters
            all_chapters.add(chapter_key)
            
            # Aggregate student data
            if student_id_key not in student_performance_map:
                student_performance_map[student_id_key] = {
                    'student_id': student_id_key,
                    'student_name': row.full_name,
                    'student_email': row.email,
                    'total_attempts': 0,
                    'total_score': 0,
                    'total_time': 0,
                    'unique_questions': 0,
                    'chapters': [],
                    'best_score': 0,
                    'latest_attempt': None
                }
                logger.debug(f"Created new student entry for: {row.full_name}")
            
            student_data = student_performance_map[student_id_key]
            student_data['total_attempts'] += row.attempt_count
            student_data['total_score'] += row.avg_score * row.attempt_count
            student_data['total_time'] += row.total_time
            student_data['unique_questions'] += row.unique_questions
            student_data['chapters'].append(chapter_key)
            student_data['best_score'] = max(student_data['best_score'], row.max_score)
            
            if not student_data['latest_attempt'] or row.latest_attempt > student_data['latest_attempt']:
                student_data['latest_attempt'] = row.latest_attempt
            
            # Aggregate chapter data
            if chapter_key not in chapter_performance_map:
                chapter_performance_map[chapter_key] = {
                    'chapter': chapter_key,
                    'total_attempts': 0,
                    'total_score': 0,
                    'student_count': 0,
                    'best_score': 0,
                    'worst_score': 10
                }
                logger.debug(f"Created new chapter entry for: Chapter {chapter_key}")
            
            chapter_data = chapter_performance_map[chapter_key]
            chapter_data['total_attempts'] += row.attempt_count
            chapter_data['total_score'] += row.avg_score * row.attempt_count
            chapter_data['student_count'] += 1
            chapter_data['best_score'] = max(chapter_data['best_score'], row.max_score)
            chapter_data['worst_score'] = min(chapter_data['worst_score'], row.min_score)
        
        logger.info(f"Data processing complete. Students processed: {len(student_performance_map)}, Chapters found: {len(chapter_performance_map)}")
        logger.info(f"All chapters discovered: {sorted(list(all_chapters))}")
        
        # Build student responses
        students = []
        logger.debug("Building student responses...")
        
        for student_data in student_performance_map.values():
            avg_score = student_data['total_score'] / student_data['total_attempts'] if student_data['total_attempts'] > 0 else 0
            
            # Simple trend calculation
            performance_trend = "stable"
            if avg_score >= 8:
                performance_trend = "improving"
            elif avg_score < 5:
                performance_trend = "declining"
            
            student_performance = StudentPracticePerformance(
                student_id=student_data['student_id'],
                student_name=student_data['student_name'],
                student_email=student_data['student_email'],
                total_practice_attempts=student_data['total_attempts'],
                average_practice_score=round(avg_score, 2),
                total_practice_time=student_data['total_time'],
                unique_questions_attempted=student_data['unique_questions'],
                chapters_covered=list(set(student_data['chapters'])),  # Remove duplicates
                best_score=student_data['best_score'],
                latest_attempt_date=student_data['latest_attempt'].isoformat() if student_data['latest_attempt'] else None,
                performance_trend=performance_trend
            )
            
            students.append(student_performance)
            logger.debug(f"Added student: {student_data['student_name']} - {student_data['total_attempts']} attempts, avg: {avg_score:.2f}")
        
        # Build chapter responses
        chapters = []
        logger.debug("Building chapter responses...")
        
        for chapter_data in chapter_performance_map.values():
            avg_score = chapter_data['total_score'] / chapter_data['total_attempts'] if chapter_data['total_attempts'] > 0 else 0
            
            chapter_performance = ChapterPerformance(
                chapter=chapter_data['chapter'],
                total_attempts=chapter_data['total_attempts'],
                average_score=round(avg_score, 2),
                student_count=chapter_data['student_count'],
                best_score=chapter_data['best_score'],
                worst_score=chapter_data['worst_score'] if chapter_data['worst_score'] < 10 else 0
            )
            
            chapters.append(chapter_performance)
            logger.debug(f"Added chapter: {chapter_data['chapter']} - {chapter_data['total_attempts']} attempts, {chapter_data['student_count']} students, avg: {avg_score:.2f}")
        
        # Sort chapters by chapter number
        chapters.sort(key=lambda x: x.chapter)
        
        # Calculate overall stats
        total_attempts = sum(s.total_practice_attempts for s in students)
        overall_avg = sum(s.average_practice_score * s.total_practice_attempts for s in students) / total_attempts if total_attempts > 0 else 0
        
        most_attempted_chapter = max(chapters, key=lambda x: x.total_attempts).chapter if chapters else None
        best_performing_chapter = max(chapters, key=lambda x: x.average_score).chapter if chapters else None
        
        logger.info(f"Final stats calculated:")
        logger.info(f"  - Total students with practice data: {len(students)}")
        logger.info(f"  - Total practice attempts: {total_attempts}")
        logger.info(f"  - Overall average score: {overall_avg:.2f}")
        logger.info(f"  - Most attempted chapter: {most_attempted_chapter}")
        logger.info(f"  - Best performing chapter: {best_performing_chapter}")
        
        stats = PracticePerformanceStats(
            total_students_practiced=len(students),
            total_practice_attempts=total_attempts,
            overall_average_score=round(overall_avg, 2),
            most_attempted_chapter=most_attempted_chapter,
            best_performing_chapter=best_performing_chapter,
            chapters_covered=sorted(list(all_chapters))
        )
        
        response = CoursePracticePerformanceResponse(
            students=students,
            chapters=chapters,
            stats=stats
        )
        
        logger.info(f"Successfully returning response with {len(students)} students and {len(chapters)} chapters")
        return response
        
    except HTTPException as he:
        logger.error(f"HTTP Exception in get_course_practice_performance: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in get_course_practice_performance: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching practice performance: {str(e)}"
        )

@router.get("/{course_id}/practice-performance/student/{student_id}")
async def get_student_detailed_practice_performance(
    course_id: str,
    student_id: str,
    chapter: Optional[int] = None,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed practice performance for a specific student - SIMPLIFIED VERSION"""
    try:
        check_teacher_permission(current_user)
        
        # Verify course ownership, student enrollment, and get course details
        verify_query = text("""
            SELECT c.id, c.board, c.class_level, c.subject
            FROM courses c
            JOIN course_enrollments ce ON c.id = ce.course_id
            WHERE c.id = :course_id 
              AND c.teacher_id = :teacher_id
              AND ce.student_id::text = :student_id
              AND ce.status = 'active'
        """)
        
        course_info = db.execute(verify_query, {
            "course_id": course_id,
            "teacher_id": current_user['id'],
            "student_id": student_id
        }).fetchone()
        
        if not course_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or student not enrolled"
            )
        
        # Get detailed attempt data with exact matching
        detail_query = f"""
            SELECT 
                ua.*,
                q.question_text,
                q.correct_answer,
                q.difficulty,
                q.type as question_type
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id::text = '{student_id}'
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
        """
        
        if chapter:
            detail_query += " AND ua.chapter = :chapter"
            
        detail_query += " ORDER BY ua.created_at DESC LIMIT 100"
        
        params = {
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }
        
        if chapter:
            params["chapter"] = chapter
            
        attempts = db.execute(text(detail_query), params).fetchall()
        
        # Format detailed response
        detailed_attempts = []
        for attempt in attempts:
            detailed_attempts.append({
                "id": str(attempt.id),
                "question_id": str(attempt.question_id),
                "question_text": attempt.question_text if hasattr(attempt, 'question_text') else None,
                "user_answer": attempt.answer,
                "correct_answer": attempt.correct_answer if hasattr(attempt, 'correct_answer') else None,
                "score": attempt.score,
                "max_score": 10,
                "feedback": attempt.feedback,
                "time_taken": attempt.time_taken,
                "chapter": attempt.chapter,
                "difficulty": attempt.difficulty if hasattr(attempt, 'difficulty') else None,
                "question_type": attempt.question_type if hasattr(attempt, 'question_type') else None,
                "attempted_at": attempt.created_at.isoformat()
            })
        
        return {
            "student_id": student_id,
            "course_id": course_id,
            "chapter_filter": chapter,
            "total_attempts": len(detailed_attempts),
            "attempts": detailed_attempts
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching student detailed practice performance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching detailed practice performance: {str(e)}"
        )
    
# Add these imports to the top of teacher_courses.py (if not already present)
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, or_, exists
from models import User, Course, CourseEnrollment, Quiz, UserAttempt
import uuid

# Add these Pydantic models after the existing ones in teacher_courses.py

class CourseInvitationRequest(BaseModel):
    student_email: str
    course_name: str
    teacher_name: str

class PublicNoticeRequest(BaseModel):
    title: str
    message: str
    priority: str = 'medium'

class NotificationResponse(BaseModel):
    success: bool
    message: str
    notification_id: Optional[str] = None
    student_id: Optional[str] = None
    error: Optional[str] = None

# Add these endpoints at the end of teacher_courses.py

@router.post("/{course_id}/invite-student", response_model=NotificationResponse)
async def invite_student_to_course(
    course_id: str,
    invitation_data: CourseInvitationRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Invite a student to join the course by email"""
    try:
        check_teacher_permission(current_user)
        
        # Verify teacher owns this course
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or you don't have permission to access it"
            )
        
        # Check if student exists and is actually a student
        student = db.query(User).filter(
            User.email == invitation_data.student_email,
            User.role == 'student'
        ).first()
        logger.info(f"Inviting student: {invitation_data.student_email} to course: {course_id} by teacher: {current_user['id']}")
        logger.debug(f"Found student: {student.full_name if student else 'None'}")
        logger.debug(f"Student ID: {student.id if student else 'None'}")
        if not student:
            return NotificationResponse(
                success=False,
                error="Student not found",
                message="No student account found with this email address"
            )
        
        # Check if student is already enrolled
        existing_enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == student.id,
            CourseEnrollment.status == 'active'
        ).first()
        
        if existing_enrollment:
            return NotificationResponse(
                success=False,
                error="Already enrolled",
                message="Student is already enrolled in this course"
            )
        
        # Check for existing pending invitation
        from models import Base
        
        # Define notification model inline if not in models.py yet
        if not hasattr(Base.metadata.tables, 'notifications'):
            # Create a simple query using raw SQL for now
            existing_invitation_query = text("""
                SELECT id FROM notifications 
                WHERE student_id = :student_id 
                AND course_id = :course_id 
                AND type = 'course_invitation'
                AND status = 'pending'
                AND expires_at > NOW()
            """)
            
            existing_invitation = db.execute(existing_invitation_query, {
                "student_id": str(student.id),
                "course_id": course_id
            }).fetchone()
        else:
            # Use ORM if notification model is available
            from models import Notification
            existing_invitation = db.query(Notification).filter(
                Notification.student_id == student.id,
                Notification.course_id == course_id,
                Notification.type == 'course_invitation',
                Notification.status == 'pending',
                Notification.expires_at > datetime.utcnow()
            ).first()
        
        if existing_invitation:
            return NotificationResponse(
                success=False,
                error="Invitation pending",
                message="A course invitation is already pending for this student"
            )
        
        # Create the invitation notification
        notification_id = str(uuid.uuid4())
        
        create_notification_query = text("""
            INSERT INTO notifications (
                id, teacher_id, student_id, course_id, type, scope,
                title, message, metadata, created_at, expires_at
            ) VALUES (
                :notification_id, :teacher_id, :student_id, :course_id, 
                'course_invitation', 'private', :title, :message, 
                :metadata, NOW(), NOW() + INTERVAL '3 months'
            )
        """)
        
        title = f"Course Invitation: {invitation_data.course_name}"
        message = f"{invitation_data.teacher_name} has invited you to join the course \"{invitation_data.course_name}\". Click to accept or decline this invitation."
        
        metadata = {
            "course_name": invitation_data.course_name,
            "teacher_name": invitation_data.teacher_name,
            "invitation_type": "course_enrollment"
        }
        
        db.execute(create_notification_query, {
            "notification_id": notification_id,
            "teacher_id": current_user['id'],
            "student_id": str(student.id),
            "course_id": course_id,
            "title": title,
            "message": message,
            "metadata": json.dumps(metadata)
        })
        
        db.commit()
        
        logger.info(f"Course invitation sent: teacher_id={current_user['id']}, student_id={student.id}, course_id={course_id}")
        
        return NotificationResponse(
            success=True,
            message="Invitation sent successfully",
            notification_id=notification_id,
            student_id=str(student.id)
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error inviting student to course: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending invitation: {str(e)}"
        )

@router.post("/{course_id}/public-notice", response_model=NotificationResponse)
async def send_public_notice(
    course_id: str,
    notice_data: PublicNoticeRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a public notice to all students enrolled in the course"""
    try:
        check_teacher_permission(current_user)
        
        # Verify teacher owns this course
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or you don't have permission to access it"
            )
        
        # Validate input
        if not notice_data.title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notice title is required"
            )
        
        if not notice_data.message.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notice message is required"
            )
        
        if notice_data.priority not in ['low', 'medium', 'high']:
            notice_data.priority = 'medium'
        
        # Get count of enrolled students for response
        enrolled_count_query = text("""
            SELECT COUNT(*) as student_count
            FROM course_enrollments
            WHERE course_id = :course_id AND status = 'active'
        """)
        
        enrolled_count = db.execute(enrolled_count_query, {
            "course_id": course_id
        }).scalar()
        
        # Create the public notice notification
        notification_id = str(uuid.uuid4())
        
        create_notice_query = text("""
            INSERT INTO notifications (
                id, teacher_id, student_id, course_id, type, scope,
                title, message, priority, metadata, created_at, expires_at
            ) VALUES (
                :notification_id, :teacher_id, NULL, :course_id, 
                'public_notice', 'public', :title, :message, :priority,
                :metadata, NOW(), NOW() + INTERVAL '3 months'
            )
        """)
        
        metadata = {
            "notice_type": "class_announcement",
            "recipients_count": enrolled_count,
            "course_name": course.course_name
        }
        
        db.execute(create_notice_query, {
            "notification_id": notification_id,
            "teacher_id": current_user['id'],
            "course_id": course_id,
            "title": notice_data.title.strip(),
            "message": notice_data.message.strip(),
            "priority": notice_data.priority,
            "metadata": json.dumps(metadata)
        })
        
        db.commit()
        
        logger.info(f"Public notice sent: teacher_id={current_user['id']}, course_id={course_id}, recipients={enrolled_count}")
        
        return NotificationResponse(
            success=True,
            message=f"Notice sent to all {enrolled_count} students",
            notification_id=notification_id
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error sending public notice: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending notice: {str(e)}"
        )

@router.get("/{course_id}/notifications")
async def get_course_notifications(
    course_id: str,
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notifications for a course (for teacher management)"""
    try:
        check_teacher_permission(current_user)
        
        # Verify teacher owns this course
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or you don't have permission to access it"
            )
        
        # Build query with filters
        where_conditions = ["teacher_id = :teacher_id", "course_id = :course_id"]
        params = {
            "teacher_id": current_user['id'],
            "course_id": course_id,
            "limit": limit,
            "offset": offset
        }
        
        if status:
            where_conditions.append("status = :status")
            params["status"] = status
        
        if type:
            where_conditions.append("type = :type")
            params["type"] = type
        
        where_clause = " AND ".join(where_conditions)
        
        # Get notifications with student details for private notifications
        notifications_query = text(f"""
            SELECT 
                n.id,
                n.type,
                n.scope,
                n.title,
                n.message,
                n.status,
                n.priority,
                n.metadata,
                n.created_at,
                n.expires_at,
                n.responded_at,
                u.id as student_id,
                u.full_name as student_name,
                u.email as student_email
            FROM notifications n
            LEFT JOIN profiles u ON n.student_id = u.id
            WHERE {where_clause}
            ORDER BY n.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        notifications = db.execute(notifications_query, params).fetchall()
        
        # Get total count
        count_query = text(f"""
            SELECT COUNT(*) 
            FROM notifications 
            WHERE {where_clause}
        """)
        
        # Remove limit and offset from params for count query
        count_params = {k: v for k, v in params.items() if k not in ['limit', 'offset']}
        total_count = db.execute(count_query, count_params).scalar()
        
        # Format response
        formatted_notifications = []
        for notification in notifications:
            # Handle metadata properly - it might be a dict, string, or None
            metadata = {}
            if notification.metadata:
                if isinstance(notification.metadata, dict):
                    # Already a dict (PostgreSQL JSON column)
                    metadata = notification.metadata
                elif isinstance(notification.metadata, str):
                    # String that needs parsing
                    try:
                        metadata = json.loads(notification.metadata)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Failed to parse metadata for notification {notification.id}: {notification.metadata}")
                        metadata = {}
                else:
                    # Some other type, log and use empty dict
                    logger.warning(f"Unexpected metadata type for notification {notification.id}: {type(notification.metadata)}")
                    metadata = {}
            
            formatted_notification = {
                "id": str(notification.id),
                "type": notification.type,
                "scope": notification.scope,
                "title": notification.title,
                "message": notification.message,
                "status": notification.status,
                "priority": notification.priority,
                "metadata": metadata,
                "created_at": notification.created_at.isoformat(),
                "expires_at": notification.expires_at.isoformat() if notification.expires_at else None,
                "responded_at": notification.responded_at.isoformat() if notification.responded_at else None
            }
            
            # Add student info for private notifications
            if notification.student_id:
                formatted_notification["student"] = {
                    "id": str(notification.student_id),
                    "full_name": notification.student_name,
                    "email": notification.student_email
                }
            
            formatted_notifications.append(formatted_notification)
        
        # Get stats
        stats_query = text("""
            SELECT 
                COUNT(*) as total_sent,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'accepted' THEN 1 END) as accepted,
                COUNT(CASE WHEN status = 'declined' THEN 1 END) as declined,
                COUNT(CASE WHEN status = 'read' THEN 1 END) as read
            FROM notifications
            WHERE teacher_id = :teacher_id AND course_id = :course_id
        """)
        
        stats = db.execute(stats_query, {
            "teacher_id": current_user['id'],
            "course_id": course_id
        }).fetchone()
        
        return {
            "notifications": formatted_notifications,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            },
            "stats": {
                "total_sent": stats.total_sent,
                "pending": stats.pending,
                "accepted": stats.accepted,
                "declined": stats.declined,
                "read": stats.read
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching notifications: {str(e)}"
        )
    
@router.get("/{course_id}/students/{student_id}/practice-details", response_model=StudentPracticeDetailsResponse)
async def get_student_practice_details(
    course_id: str,
    student_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive practice performance details for a specific student"""
    try:
        logger.info(f"Getting detailed practice performance for student {student_id} in course {course_id}")
        
        check_teacher_permission(current_user)
        
        # Verify course ownership and student enrollment
        verify_query = text("""
            SELECT c.id, c.board, c.class_level, c.subject, c.course_name,
                   u.full_name, u.email
            FROM courses c
            JOIN course_enrollments ce ON c.id = ce.course_id
            JOIN profiles u ON ce.student_id = u.id
            WHERE c.id = :course_id 
              AND c.teacher_id = :teacher_id
              AND ce.student_id::text = :student_id
              AND ce.status = 'active'
        """)
        
        course_info = db.execute(verify_query, {
            "course_id": course_id,
            "teacher_id": current_user['id'],
            "student_id": student_id
        }).fetchone()
        
        if not course_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or student not enrolled"
            )
        
        logger.info(f"Found student: {course_info.full_name} in course: {course_info.course_name}")
        
        # Get comprehensive student practice data
        student_detail_query = text("""
            WITH student_attempts AS (
                SELECT 
                    ua.user_id,
                    ua.chapter,
                    ua.score,
                    ua.time_taken,
                    ua.question_id,
                    ua.created_at,
                    q.difficulty,
                    q.type as question_type,
                    EXTRACT(WEEK FROM ua.created_at) as week_number,
                    EXTRACT(YEAR FROM ua.created_at) as year_number,
                    DATE(ua.created_at) as attempt_date
                FROM user_attempts ua
                LEFT JOIN questions q ON ua.question_id = q.id
                WHERE ua.user_id::text = :student_id
                AND ua.board = :course_board
                AND ua.class_level = :course_class
                AND ua.subject = :course_subject
                ORDER BY ua.created_at DESC
            ),
            daily_stats AS (
                SELECT 
                    attempt_date,
                    COUNT(*) as daily_attempts,
                    AVG(score) as daily_avg_score
                FROM student_attempts
                GROUP BY attempt_date
                ORDER BY attempt_date DESC
            ),
            weekly_stats AS (
                SELECT 
                    year_number,
                    week_number,
                    COUNT(*) as weekly_attempts,
                    AVG(score) as weekly_avg_score,
                    MIN(attempt_date) as week_start
                FROM student_attempts
                GROUP BY year_number, week_number
                ORDER BY year_number DESC, week_number DESC
                LIMIT 8
            )
            SELECT 
                -- Basic student stats
                (SELECT COUNT(*) FROM student_attempts) as total_attempts,
                (SELECT AVG(score) FROM student_attempts) as avg_score,
                (SELECT SUM(COALESCE(time_taken, 0)) FROM student_attempts) as total_time,
                (SELECT COUNT(DISTINCT question_id) FROM student_attempts) as unique_questions,
                (SELECT MAX(score) FROM student_attempts) as best_score,
                (SELECT MIN(score) FROM student_attempts) as worst_score,
                (SELECT MAX(created_at) FROM student_attempts) as latest_attempt,
                (SELECT COUNT(DISTINCT chapter) FROM student_attempts) as chapters_count,
                
                -- Recent performance (last 10 attempts vs previous 10)
                (SELECT AVG(score) FROM (
                    SELECT score FROM student_attempts ORDER BY created_at DESC LIMIT 10
                ) recent) as recent_avg,
                (SELECT AVG(score) FROM (
                    SELECT score FROM student_attempts ORDER BY created_at DESC LIMIT 20 OFFSET 10
                ) previous) as previous_avg,
                
                -- Streak calculation
                (SELECT COUNT(*) FROM daily_stats WHERE daily_attempts > 0) as practice_days,
                
                -- Weekly attempts
                (SELECT AVG(weekly_attempts) FROM weekly_stats) as avg_weekly_attempts
        """)
        
        student_stats = db.execute(student_detail_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchone()
        
        if not student_stats or student_stats.total_attempts == 0:
            # Return empty response for students with no practice data
            return StudentPracticeDetailsResponse(
                student=StudentPracticeDetail(
                    student_id=student_id,
                    student_name=course_info.full_name,
                    student_email=course_info.email,
                    total_practice_attempts=0,
                    average_practice_score=0.0,
                    total_practice_time=0,
                    unique_questions_attempted=0,
                    chapters_covered=[],
                    best_score=0.0,
                    worst_score=0.0,
                    latest_attempt_date=None,
                    performance_trend="stable",
                    streak_days=0,
                    last_practice_date=None,
                    weekly_attempts=0,
                    improvement_rate=0.0
                ),
                chapters=[],
                recent_sessions=[],
                performance_analytics=PerformanceAnalytics(
                    weekly_trend=[],
                    accuracy_by_topic=[],
                    time_distribution=[],
                    streak_info={"current_streak": 0, "longest_streak": 0, "streak_start": ""}
                ),
                recommendations=["Start practicing to see detailed analytics here!"]
            )
        
        logger.info(f"Student has {student_stats.total_attempts} practice attempts")
        
        # Calculate performance trend
        performance_trend = "stable"
        if student_stats.recent_avg and student_stats.previous_avg:
            if student_stats.recent_avg > student_stats.previous_avg + 0.5:
                performance_trend = "improving"
            elif student_stats.recent_avg < student_stats.previous_avg - 0.5:
                performance_trend = "declining"
        
        # Calculate improvement rate
        improvement_rate = 0.0
        if student_stats.recent_avg and student_stats.previous_avg and student_stats.previous_avg > 0:
            improvement_rate = ((student_stats.recent_avg - student_stats.previous_avg) / student_stats.previous_avg) * 100
        
        # Get chapters covered
        chapters_query = text("""
            SELECT DISTINCT ua.chapter
            FROM user_attempts ua
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            ORDER BY ua.chapter
        """)
        
        chapters_covered = [row.chapter for row in db.execute(chapters_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()]
        
        # Build student detail object
        student_detail = StudentPracticeDetail(
            student_id=student_id,
            student_name=course_info.full_name,
            student_email=course_info.email,
            total_practice_attempts=student_stats.total_attempts,
            average_practice_score=round(student_stats.avg_score, 2) if student_stats.avg_score else 0,
            total_practice_time=student_stats.total_time or 0,
            unique_questions_attempted=student_stats.unique_questions or 0,
            chapters_covered=chapters_covered,
            best_score=student_stats.best_score or 0,
            worst_score=student_stats.worst_score or 0,
            latest_attempt_date=student_stats.latest_attempt.isoformat() if student_stats.latest_attempt else None,
            performance_trend=performance_trend,
            streak_days=student_stats.practice_days or 0,
            last_practice_date=student_stats.latest_attempt.isoformat() if student_stats.latest_attempt else None,
            weekly_attempts=round(student_stats.avg_weekly_attempts, 1) if student_stats.avg_weekly_attempts else 0,
            improvement_rate=round(improvement_rate, 1)
        )
        
        # Get detailed chapter performance - FIXED: Use table prefixes
        chapter_details_query = text("""
            SELECT 
                ua.chapter,
                COUNT(*) as attempts,
                AVG(ua.score) as avg_score,
                MAX(ua.score) as best_score,
                MIN(ua.score) as worst_score,
                SUM(COALESCE(ua.time_taken, 0)) as total_time,
                COUNT(DISTINCT ua.question_id) as questions_attempted,
                MAX(ua.created_at) as last_attempted,
                COUNT(CASE WHEN q.difficulty = 'Easy' THEN 1 END) as easy_count,
                COUNT(CASE WHEN q.difficulty = 'Medium' THEN 1 END) as medium_count,
                COUNT(CASE WHEN q.difficulty = 'Hard' THEN 1 END) as hard_count,
                COUNT(CASE WHEN ua.score >= 5 THEN 1 END) as correct_count
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            GROUP BY ua.chapter
            ORDER BY ua.chapter
        """)
        
        chapter_results = db.execute(chapter_details_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()
        
        chapters = []
        for chapter in chapter_results:
            accuracy_rate = (chapter.correct_count / chapter.attempts * 100) if chapter.attempts > 0 else 0
            
            chapter_detail = ChapterDetail(
                chapter=chapter.chapter,
                attempts=chapter.attempts,
                average_score=round(chapter.avg_score, 2),
                best_score=chapter.best_score,
                worst_score=chapter.worst_score,
                time_spent=chapter.total_time or 0,
                questions_attempted=chapter.questions_attempted,
                accuracy_rate=round(accuracy_rate, 1),
                last_attempted=chapter.last_attempted.isoformat(),
                difficulty_distribution={
                    "easy": chapter.easy_count or 0,
                    "medium": chapter.medium_count or 0,
                    "hard": chapter.hard_count or 0
                }
            )
            chapters.append(chapter_detail)
        
        # Get recent practice sessions (group by date and chapter) - FIXED: Use table prefixes
        recent_sessions_query = text("""
            SELECT 
                DATE(ua.created_at) as session_date,
                ua.chapter,
                COUNT(*) as questions_attempted,
                AVG(ua.score) as avg_score,
                SUM(COALESCE(ua.time_taken, 0)) as total_time,
                COUNT(CASE WHEN ua.score >= 5 THEN 1 END) as correct_answers,
                string_agg(DISTINCT q.type, ', ') as topics_covered
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            GROUP BY DATE(ua.created_at), ua.chapter
            ORDER BY session_date DESC, ua.chapter
            LIMIT 20
        """)
        
        session_results = db.execute(recent_sessions_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()
        
        recent_sessions = []
        for i, session in enumerate(session_results):
            accuracy = (session.correct_answers / session.questions_attempted * 100) if session.questions_attempted > 0 else 0
            topics = session.topics_covered.split(', ') if session.topics_covered else []
            
            practice_session = PracticeSession(
                id=f"session_{i}_{session.session_date}_{session.chapter}",
                date=session.session_date.isoformat(),
                chapter=session.chapter,
                questions_attempted=session.questions_attempted,
                score=round(session.avg_score, 2),
                time_spent=session.total_time or 0,
                accuracy=round(accuracy, 1),
                topics_covered=topics
            )
            recent_sessions.append(practice_session)
        
        # Get weekly performance trend - FIXED: Use table prefixes
        weekly_trend_query = text("""
            SELECT 
                TO_CHAR(DATE_TRUNC('week', ua.created_at), 'Mon DD') as week_label,
                COUNT(*) as attempts,
                AVG(ua.score) as avg_score
            FROM user_attempts ua
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            AND ua.created_at >= NOW() - INTERVAL '8 weeks'
            GROUP BY DATE_TRUNC('week', ua.created_at)
            ORDER BY DATE_TRUNC('week', ua.created_at) DESC
            LIMIT 8
        """)
        
        weekly_results = db.execute(weekly_trend_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()
        
        weekly_trend = [
            {
                "week": week.week_label,
                "score": round(week.avg_score, 2),
                "attempts": week.attempts
            }
            for week in weekly_results
        ]
        
        # Get accuracy by topic (question type) - FIXED: Use table prefixes
        topic_accuracy_query = text("""
            SELECT 
                COALESCE(q.type, 'Unknown') as topic,
                COUNT(*) as total_attempts,
                COUNT(CASE WHEN ua.score >= 5 THEN 1 END) as correct_attempts
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            GROUP BY q.type
            HAVING COUNT(*) >= 3
            ORDER BY COUNT(*) DESC
        """)
        
        topic_results = db.execute(topic_accuracy_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()
        
        accuracy_by_topic = [
            {
                "topic": topic.topic,
                "accuracy": round((topic.correct_attempts / topic.total_attempts * 100), 1) if topic.total_attempts > 0 else 0
            }
            for topic in topic_results
        ]
        
        # Calculate streak info - FIXED: Use table prefixes
        streak_query = text("""
            WITH daily_practice AS (
                SELECT DISTINCT DATE(ua.created_at) as practice_date
                FROM user_attempts ua
                WHERE ua.user_id::text = :student_id
                AND ua.board = :course_board
                AND ua.class_level = :course_class
                AND ua.subject = :course_subject
                ORDER BY practice_date DESC
            ),
            streak_calc AS (
                SELECT 
                    practice_date,
                    practice_date - ROW_NUMBER() OVER (ORDER BY practice_date DESC)::int as streak_group
                FROM daily_practice
            )
            SELECT 
                COUNT(*) as streak_length,
                MIN(practice_date) as streak_start,
                MAX(practice_date) as streak_end
            FROM streak_calc
            WHERE streak_group = (
                SELECT streak_group 
                FROM streak_calc 
                ORDER BY practice_date DESC 
                LIMIT 1
            )
        """)
        
        streak_result = db.execute(streak_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchone()
        
        # Get time distribution (practice hours) - FIXED: Use table prefixes
        time_distribution_query = text("""
            SELECT 
                EXTRACT(HOUR FROM ua.created_at) as hour,
                COUNT(*) as attempts
            FROM user_attempts ua
            WHERE ua.user_id::text = :student_id
            AND ua.board = :course_board
            AND ua.class_level = :course_class
            AND ua.subject = :course_subject
            GROUP BY EXTRACT(HOUR FROM ua.created_at)
            ORDER BY attempts DESC
            LIMIT 10
        """)
        
        time_results = db.execute(time_distribution_query, {
            "student_id": student_id,
            "course_board": course_info.board,
            "course_class": course_info.class_level,
            "course_subject": course_info.subject
        }).fetchall()
        
        time_distribution = [
            {"hour": int(time.hour), "attempts": time.attempts}
            for time in time_results
        ]
        
        # Build performance analytics
        performance_analytics = PerformanceAnalytics(
            weekly_trend=weekly_trend,
            accuracy_by_topic=accuracy_by_topic,
            time_distribution=time_distribution,
            streak_info={
                "current_streak": streak_result.streak_length if streak_result else 0,
                "longest_streak": streak_result.streak_length if streak_result else 0,  # Could calculate this separately
                "streak_start": streak_result.streak_start.isoformat() if streak_result and streak_result.streak_start else ""
            }
        )
        
        # Generate recommendations
        recommendations = []
        
        if student_stats.avg_score < 5:
            recommendations.append("Focus on fundamental concepts - current average is below passing threshold")
        
        if student_stats.practice_days < 5:
            recommendations.append("Encourage more consistent daily practice for better retention")
        
        if len(chapters_covered) < 3:
            recommendations.append("Explore more chapters to broaden knowledge base")
        
        if performance_trend == "declining":
            recommendations.append("Recent performance shows decline - consider reviewing difficult topics")
        
        if student_stats.avg_weekly_attempts < 10:
            recommendations.append("Increase practice frequency - aim for at least 2-3 sessions per week")
        
        # Check for chapters with low performance
        weak_chapters = [ch for ch in chapters if ch.average_score < 5]
        if weak_chapters:
            chapter_list = ", ".join([f"Chapter {ch.chapter}" for ch in weak_chapters[:3]])
            recommendations.append(f"Focus on improving performance in: {chapter_list}")
        
        if not recommendations:
            recommendations.append("Great work! Keep maintaining this consistent practice pattern")
        
        logger.info(f"Successfully compiled detailed practice data for student {student_id}")
        
        return StudentPracticeDetailsResponse(
            student=student_detail,
            chapters=chapters,
            recent_sessions=recent_sessions,
            performance_analytics=performance_analytics,
            recommendations=recommendations
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching student practice details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching student practice details: {str(e)}"
        )