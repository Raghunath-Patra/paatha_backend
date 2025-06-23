# backend/routes/teacher_courses.py - ENHANCED VERSION with Practice Performance

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, or_
from typing import List, Dict, Optional
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Course, CourseEnrollment, User, Quiz, UserAttempt
import logging

router = APIRouter(prefix="/api/teacher/courses", tags=["teacher-courses"])

logger = logging.getLogger(__name__)

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

class StudentPracticeFilter(BaseModel):
    student_id: Optional[str] = None
    chapter: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None

class CoursePracticePerformanceResponse(BaseModel):
    students: List[StudentPracticePerformance]
    chapters: List[ChapterPerformance]
    stats: PracticePerformanceStats

# Utility functions for normalization
def normalize_class_level(class_level: str) -> str:
    """Normalize class level to standard format"""
    if not class_level:
        return class_level
    
    class_mapping = {
        # Class 10 variations
        'x': 'x', '10': 'x', '10th': 'x', 'tenth': 'x',
        # Class 11 variations  
        'xi': 'xi', '11': 'xi', '11th': 'xi', 'eleventh': 'xi',
        # Class 12 variations
        'xii': 'xii', '12': 'xii', '12th': 'xii', 'twelfth': 'xii',
        # Class 9 variations
        'ix': 'ix', '9': 'ix', '9th': 'ix', 'ninth': 'ix',
        # Class 8 variations
        'viii': 'viii', '8': 'viii', '8th': 'viii', 'eighth': 'viii'
    }
    
    normalized = class_level.lower().strip()
    return class_mapping.get(normalized, class_level.lower())

def normalize_subject(subject: str) -> str:
    """Normalize subject name to standard format"""
    if not subject:
        return subject
    
    subject_mapping = {
        # Physics variations
        'physics': 'physics', 'phy': 'physics',
        # Chemistry variations  
        'chemistry': 'chemistry', 'chem': 'chemistry', 'che': 'chemistry',
        # Mathematics variations
        'mathematics': 'mathematics', 'maths': 'mathematics', 'math': 'mathematics',
        # Science variations
        'science': 'science', 'sci': 'science',
        # Biology variations
        'biology': 'biology', 'bio': 'biology'
    }
    
    normalized = subject.lower().strip().replace('-', ' ').replace('_', ' ')
    return subject_mapping.get(normalized, subject.lower())

def normalize_board(board: str) -> str:
    """Normalize board name to standard format"""
    if not board:
        return board
    
    board_mapping = {
        'cbse': 'cbse',
        'icse': 'icse', 
        'isc': 'isc',
        'state': 'state',
        'ncert': 'cbse'  # NCERT usually maps to CBSE
    }
    
    normalized = board.lower().strip()
    return board_mapping.get(normalized, board.lower())

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
            subject=new_course.subject,
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
            subject=course.subject,
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
            subject=course.subject,
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
    """Delete a course"""
    try:
        check_teacher_permission(current_user)
        
        check_query = text("""
            SELECT 
                c.id,
                (SELECT COUNT(*) FROM course_enrollments WHERE course_id = c.id) as enrollment_count,
                (SELECT COUNT(*) FROM quizzes WHERE course_id = c.id) as quiz_count
            FROM courses c
            WHERE c.id = :course_id AND c.teacher_id = :teacher_id
        """)
        
        result = db.execute(check_query, {
            "course_id": course_id,
            "teacher_id": current_user['id']
        }).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )
        
        if result.enrollment_count > 0 or result.quiz_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete course with existing enrollments or quizzes"
            )
        
        course = db.query(Course).filter(Course.id == course_id).first()
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
    """Get practice performance for all students in a course"""
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
        
        # Get enrolled students
        enrolled_students_query = text("""
            SELECT u.id, u.full_name, u.email 
            FROM course_enrollments ce
            JOIN profiles u ON ce.student_id = u.id
            WHERE ce.course_id = :course_id AND ce.status = 'active'
        """)
        
        enrolled_students = db.execute(enrolled_students_query, {"course_id": course_id}).fetchall()
        
        if not enrolled_students:
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
        
        student_ids = [str(student.id) for student in enrolled_students]
        
        # Normalize course details for matching
        course_board = normalize_board(course.board)
        course_class = normalize_class_level(course.class_level)
        course_subject = normalize_subject(course.subject)
        
        # Build dynamic query for practice performance
        base_query = """
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
            WHERE ua.user_id = ANY(:student_ids)
            AND (
                (LOWER(ua.board) = :course_board OR :course_board = '' OR ua.board IS NULL)
                AND (
                    LOWER(ua.class_level) = :course_class 
                    OR LOWER(ua.class_level) = :course_class_alt1
                    OR LOWER(ua.class_level) = :course_class_alt2
                    OR :course_class = '' 
                    OR ua.class_level IS NULL
                )
                AND (
                    LOWER(ua.subject) = :course_subject
                    OR LOWER(REPLACE(REPLACE(ua.subject, '-', ' '), '_', ' ')) = :course_subject
                    OR :course_subject = ''
                    OR ua.subject IS NULL
                )
            )
        """
        
        # Add filters if specified
        if student_id:
            base_query += " AND ua.user_id = :student_id"
        if chapter:
            base_query += " AND ua.chapter = :chapter"
            
        base_query += " GROUP BY ua.user_id, u.full_name, u.email, ua.chapter"
        
        # Generate class level alternatives
        class_alternatives = {
            'x': ['10', '10th'],
            'xi': ['11', '11th'], 
            'xii': ['12', '12th'],
            'ix': ['9', '9th'],
            'viii': ['8', '8th']
        }
        
        alt1, alt2 = class_alternatives.get(course_class, ['', ''])[:2] if course_class in class_alternatives else ['', '']
        
        params = {
            "student_ids": student_ids,
            "course_board": course_board,
            "course_class": course_class,
            "course_class_alt1": alt1,
            "course_class_alt2": alt2,
            "course_subject": course_subject
        }
        
        if student_id:
            params["student_id"] = student_id
        if chapter:
            params["chapter"] = chapter
            
        performance_data = db.execute(text(base_query), params).fetchall()
        
        # Process student performance
        student_performance_map = {}
        chapter_performance_map = {}
        all_chapters = set()
        
        for row in performance_data:
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
                    'worst_score': 10,
                    'attempt_counts': []
                }
            
            chapter_data = chapter_performance_map[chapter_key]
            chapter_data['total_attempts'] += row.attempt_count
            chapter_data['total_score'] += row.avg_score * row.attempt_count
            chapter_data['student_count'] += 1
            chapter_data['best_score'] = max(chapter_data['best_score'], row.max_score)
            chapter_data['worst_score'] = min(chapter_data['worst_score'], row.min_score)
            chapter_data['attempt_counts'].append(row.attempt_count)
        
        # Build student responses
        students = []
        for student_data in student_performance_map.values():
            avg_score = student_data['total_score'] / student_data['total_attempts'] if student_data['total_attempts'] > 0 else 0
            
            # Simple trend calculation (could be enhanced)
            performance_trend = "stable"
            if avg_score >= 8:
                performance_trend = "improving"
            elif avg_score < 5:
                performance_trend = "declining"
            
            students.append(StudentPracticePerformance(
                student_id=student_data['student_id'],
                student_name=student_data['student_name'],
                student_email=student_data['student_email'],
                total_practice_attempts=student_data['total_attempts'],
                average_practice_score=round(avg_score, 2),
                total_practice_time=student_data['total_time'],
                unique_questions_attempted=student_data['unique_questions'],
                chapters_covered=student_data['chapters'],
                best_score=student_data['best_score'],
                latest_attempt_date=student_data['latest_attempt'].isoformat() if student_data['latest_attempt'] else None,
                performance_trend=performance_trend
            ))
        
        # Build chapter responses
        chapters = []
        for chapter_data in chapter_performance_map.values():
            avg_score = chapter_data['total_score'] / chapter_data['total_attempts'] if chapter_data['total_attempts'] > 0 else 0
            
            chapters.append(ChapterPerformance(
                chapter=chapter_data['chapter'],
                total_attempts=chapter_data['total_attempts'],
                average_score=round(avg_score, 2),
                student_count=chapter_data['student_count'],
                best_score=chapter_data['best_score'],
                worst_score=chapter_data['worst_score'] if chapter_data['worst_score'] < 10 else 0
            ))
        
        # Calculate overall stats
        total_attempts = sum(s.total_practice_attempts for s in students)
        overall_avg = sum(s.average_practice_score * s.total_practice_attempts for s in students) / total_attempts if total_attempts > 0 else 0
        
        most_attempted_chapter = max(chapters, key=lambda x: x.total_attempts).chapter if chapters else None
        best_performing_chapter = max(chapters, key=lambda x: x.average_score).chapter if chapters else None
        
        stats = PracticePerformanceStats(
            total_students_practiced=len(students),
            total_practice_attempts=total_attempts,
            overall_average_score=round(overall_avg, 2),
            most_attempted_chapter=most_attempted_chapter,
            best_performing_chapter=best_performing_chapter,
            chapters_covered=sorted(list(all_chapters))
        )
        
        return CoursePracticePerformanceResponse(
            students=students,
            chapters=chapters,
            stats=stats
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching course practice performance: {str(e)}")
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
    """Get detailed practice performance for a specific student"""
    try:
        check_teacher_permission(current_user)
        
        # Verify course ownership and student enrollment
        verify_query = text("""
            SELECT c.id, c.board, c.class_level, c.subject
            FROM courses c
            JOIN course_enrollments ce ON c.id = ce.course_id
            WHERE c.id = :course_id 
              AND c.teacher_id = :teacher_id
              AND ce.student_id = :student_id
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
        
        # Normalize course details
        course_board = normalize_board(course_info.board)
        course_class = normalize_class_level(course_info.class_level)
        course_subject = normalize_subject(course_info.subject)
        
        # Get detailed attempt data
        detail_query = """
            SELECT 
                ua.*,
                q.question_text,
                q.correct_answer,
                q.difficulty,
                q.type as question_type
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = :student_id
            AND (
                (LOWER(ua.board) = :course_board OR :course_board = '' OR ua.board IS NULL)
                AND (
                    LOWER(ua.class_level) = :course_class 
                    OR LOWER(ua.class_level) = :course_class_alt1
                    OR LOWER(ua.class_level) = :course_class_alt2
                    OR :course_class = '' 
                    OR ua.class_level IS NULL
                )
                AND (
                    LOWER(ua.subject) = :course_subject
                    OR LOWER(REPLACE(REPLACE(ua.subject, '-', ' '), '_', ' ')) = :course_subject
                    OR :course_subject = ''
                    OR ua.subject IS NULL
                )
            )
        """
        
        if chapter:
            detail_query += " AND ua.chapter = :chapter"
            
        detail_query += " ORDER BY ua.created_at DESC LIMIT 100"
        
        # Generate class level alternatives
        class_alternatives = {
            'x': ['10', '10th'],
            'xi': ['11', '11th'], 
            'xii': ['12', '12th'],
            'ix': ['9', '9th'],
            'viii': ['8', '8th']
        }
        
        alt1, alt2 = class_alternatives.get(course_class, ['', ''])[:2] if course_class in class_alternatives else ['', '']
        
        params = {
            "student_id": student_id,
            "course_board": course_board,
            "course_class": course_class,
            "course_class_alt1": alt1,
            "course_class_alt2": alt2,
            "course_subject": course_subject
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