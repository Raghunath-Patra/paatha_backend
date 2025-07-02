# backend/routes/teacher_quizzes.py - FIXED VERSION with consistent datetime handling

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Quiz, QuizQuestion, QuizAttempt, Course, Question, User
from datetime import datetime, timezone, timedelta
import logging

router = APIRouter(prefix="/api/teacher/quizzes", tags=["teacher-quizzes"])

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

# FIXED: Consistent datetime parsing utility
def parse_datetime_string(dt_string: str) -> datetime:
    """
    Parse datetime string consistently across the application.
    Handles multiple formats:
    - "2024-06-21T10:00" (datetime-local format from frontend)
    - "2024-06-21T10:00:00Z" (ISO format with Z)
    - "2024-06-21T10:00:00+00:00" (ISO format with timezone)
    
    All parsed datetimes are treated as India timezone (UTC+5:30)
    """
    if not dt_string:
        return None
    
    try:
        # Handle different formats
        if dt_string.endswith('Z'):
            # ISO format with Z - convert to India time
            utc_dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            offset = timedelta(hours=5, minutes=30)
            return utc_dt.replace(tzinfo=None) + offset
        elif '+' in dt_string or dt_string.count('-') > 2:
            # Already has timezone info - convert to India time
            dt_with_tz = datetime.fromisoformat(dt_string)
            utc_dt = dt_with_tz.astimezone(timezone.utc)
            offset = timedelta(hours=5, minutes=30)
            return utc_dt.replace(tzinfo=None) + offset
        else:
            # datetime-local format (no timezone) - assume India timezone
            dt = datetime.fromisoformat(dt_string)
            return dt  # Already in local timezone (India)
    except ValueError as e:
        logger.error(f"Error parsing datetime string '{dt_string}': {e}")
        return None

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
        offset = timedelta(hours=0, minutes=0)
        return utc_dt.replace(tzinfo=None) + offset

# Pydantic models
class QuizCreate(BaseModel):
    course_id: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    time_limit: Optional[int] = None  # Minutes
    total_marks: int = 100
    passing_marks: int = 50
    attempts_allowed: int = 1
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    auto_grade: bool = True

class QuizUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    time_limit: Optional[int] = None
    total_marks: Optional[int] = None
    passing_marks: Optional[int] = None
    attempts_allowed: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_published: Optional[bool] = None
    auto_grade: Optional[bool] = None

class QuestionAdd(BaseModel):
    question_type: str  # 'ai_generated' or 'custom'
    marks: int = 1
    order_index: int
    
    # For AI-generated questions
    ai_question_id: Optional[str] = None
    
    # For custom questions
    custom_question_text: Optional[str] = None
    custom_question_type: Optional[str] = None  # mcq, short_answer, essay
    custom_options: Optional[List[str]] = None
    custom_correct_answer: Optional[str] = None
    custom_explanation: Optional[str] = None

class QuizResponse(BaseModel):
    id: str
    course_id: str
    course_name: str
    title: str
    description: Optional[str]
    instructions: Optional[str]
    time_limit: Optional[int]
    total_marks: int
    passing_marks: int
    attempts_allowed: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    is_published: bool
    auto_grade: bool
    total_questions: int
    total_attempts: int
    average_score: Optional[float]
    created_at: str
    updated_at: Optional[str]

class QuestionResponse(BaseModel):
    id: str
    question_source: str
    marks: int
    order_index: int
    
    # Question content (from AI or custom)
    question_text: str
    question_type: str
    options: Optional[List[str]]
    correct_answer: str
    explanation: Optional[str]
    
    # AI question metadata (if applicable)
    topic: Optional[str]
    difficulty: Optional[str]
    bloom_level: Optional[str]

class AttemptSummary(BaseModel):
    id: str
    student_id: str
    student_name: Optional[str]
    student_email: str
    attempt_number: int
    obtained_marks: float
    total_marks: float
    percentage: float
    started_at: str
    submitted_at: Optional[str]
    time_taken: Optional[int]
    status: str
    is_auto_graded: bool
    teacher_reviewed: bool

class QuizStats(BaseModel):
    total_attempts: int
    unique_students: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_rate: float
    completion_rate: float

class QuizResultsResponse(BaseModel):
    attempts: List[AttemptSummary]
    stats: Optional[QuizStats]

def check_teacher_permission(user: Dict):
    """Check if user is a teacher"""
    if user.get('role') != 'teacher':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )
    # return True  # For now, assume all users are teachers

def verify_course_ownership(course_id: str, teacher_id: str, db: Session):
    """Verify that the teacher owns the course"""
    course = db.query(Course).filter(
        Course.id == course_id,
        Course.teacher_id == teacher_id
    ).first()
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found or you don't have permission"
        )
    
    return course

@router.post("/", response_model=QuizResponse)
async def create_quiz(
    quiz_data: QuizCreate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify course ownership
        course = verify_course_ownership(quiz_data.course_id, current_user['id'], db)
        
        # FIXED: Parse datetime strings consistently
        start_time = parse_datetime_string(quiz_data.start_time)
        end_time = parse_datetime_string(quiz_data.end_time)
        
        # Create quiz
        new_quiz = Quiz(
            teacher_id=current_user['id'],
            course_id=quiz_data.course_id,
            title=quiz_data.title,
            description=quiz_data.description,
            instructions=quiz_data.instructions,
            time_limit=quiz_data.time_limit,
            total_marks=quiz_data.total_marks,
            passing_marks=quiz_data.passing_marks,
            attempts_allowed=quiz_data.attempts_allowed,
            start_time=start_time,
            end_time=end_time,
            auto_grade=quiz_data.auto_grade
        )
        
        db.add(new_quiz)
        db.commit()
        db.refresh(new_quiz)
        
        return QuizResponse(
            id=str(new_quiz.id),
            course_id=str(new_quiz.course_id),
            course_name=course.course_name,
            title=new_quiz.title,
            description=new_quiz.description,
            instructions=new_quiz.instructions,
            time_limit=new_quiz.time_limit,
            total_marks=new_quiz.total_marks,
            passing_marks=new_quiz.passing_marks,
            attempts_allowed=new_quiz.attempts_allowed,
            start_time=new_quiz.start_time.isoformat() if new_quiz.start_time else None,
            end_time=new_quiz.end_time.isoformat() if new_quiz.end_time else None,
            is_published=new_quiz.is_published,
            auto_grade=new_quiz.auto_grade,
            total_questions=0,
            total_attempts=0,
            average_score=None,
            created_at=new_quiz.created_at.isoformat(),
            updated_at=new_quiz.updated_at.isoformat() if new_quiz.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating quiz: {str(e)}"
        )

@router.get("/", response_model=List[QuizResponse])
async def get_teacher_quizzes(
    course_id: Optional[str] = None,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quizzes for the teacher (optionally filtered by course)"""
    try:
        check_teacher_permission(current_user)
        
        # Build query
        query = text("""
            SELECT 
                q.*,
                c.course_name,
                COALESCE(question_stats.question_count, 0) as total_questions,
                COALESCE(attempt_stats.attempt_count, 0) as total_attempts,
                attempt_stats.average_score
            FROM quizzes q
            JOIN courses c ON q.course_id = c.id
            LEFT JOIN (
                SELECT quiz_id, COUNT(*) as question_count
                FROM quiz_questions
                GROUP BY quiz_id
            ) question_stats ON q.id = question_stats.quiz_id
            LEFT JOIN (
                SELECT 
                    quiz_id,
                    COUNT(*) as attempt_count,
                    AVG(percentage) as average_score
                FROM quiz_attempts
                WHERE status = 'completed'
                GROUP BY quiz_id
            ) attempt_stats ON q.id = attempt_stats.quiz_id
            WHERE q.teacher_id = :teacher_id
            {} 
            ORDER BY q.created_at DESC
        """.format("AND q.course_id = :course_id" if course_id else ""))
        
        params = {"teacher_id": current_user['id']}
        if course_id:
            params["course_id"] = course_id
        
        quizzes = db.execute(query, params).fetchall()
        
        return [
            QuizResponse(
                id=str(quiz.id),
                course_id=str(quiz.course_id),
                course_name=quiz.course_name,
                title=quiz.title,
                description=quiz.description,
                instructions=quiz.instructions,
                time_limit=quiz.time_limit,
                total_marks=quiz.total_marks,
                passing_marks=quiz.passing_marks,
                attempts_allowed=quiz.attempts_allowed,
                start_time= quiz.start_time if quiz.start_time else None,
                end_time=quiz.end_time if quiz.end_time else None,
                is_published=quiz.is_published,
                auto_grade=quiz.auto_grade,
                total_questions=quiz.total_questions,
                total_attempts=quiz.total_attempts,
                average_score=float(quiz.average_score) if quiz.average_score else None,
                created_at=quiz.created_at.isoformat(),
                updated_at=quiz.updated_at.isoformat() if quiz.updated_at else None
            )
            for quiz in quizzes
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching quizzes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching quizzes: {str(e)}"
        )

@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz_details(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Get course info
        course = db.query(Course).filter(Course.id == quiz.course_id).first()
        
        # Get statistics
        total_questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz.id
        ).count()
        
        total_attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.status == 'completed'
        ).count()
        
        avg_score = db.query(func.avg(QuizAttempt.percentage)).filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.status == 'completed'
        ).scalar()
        
        return QuizResponse(
            id=str(quiz.id),
            course_id=str(quiz.course_id),
            course_name=course.course_name if course else "",
            title=quiz.title,
            description=quiz.description,
            instructions=quiz.instructions,
            time_limit=quiz.time_limit,
            total_marks=quiz.total_marks,
            passing_marks=quiz.passing_marks,
            attempts_allowed=quiz.attempts_allowed,
            start_time=quiz.start_time.isoformat() if quiz.start_time else None,
            end_time=quiz.end_time.isoformat() if quiz.end_time else None,
            is_published=quiz.is_published,
            auto_grade=quiz.auto_grade,
            total_questions=total_questions,
            total_attempts=total_attempts,
            average_score=float(avg_score) if avg_score else None,
            created_at=quiz.created_at.isoformat(),
            updated_at=quiz.updated_at.isoformat() if quiz.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching quiz details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching quiz details: {str(e)}"
        )

@router.put("/{quiz_id}", response_model=QuizResponse)
async def update_quiz(
    quiz_id: str,
    quiz_data: QuizUpdate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Update fields
        update_data = quiz_data.dict(exclude_unset=True)
        
        # FIXED: Handle datetime fields consistently
        if 'start_time' in update_data:
            update_data['start_time'] = parse_datetime_string(update_data['start_time'])
        if 'end_time' in update_data:
            update_data['end_time'] = parse_datetime_string(update_data['end_time'])
        
        for field, value in update_data.items():
            setattr(quiz, field, value)
        
        db.commit()
        db.refresh(quiz)
        
        # Get course info and stats for response
        course = db.query(Course).filter(Course.id == quiz.course_id).first()
        total_questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
        total_attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.status == 'completed'
        ).count()
        avg_score = db.query(func.avg(QuizAttempt.percentage)).filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.status == 'completed'
        ).scalar()
        
        return QuizResponse(
            id=str(quiz.id),
            course_id=str(quiz.course_id),
            course_name=course.course_name if course else "",
            title=quiz.title,
            description=quiz.description,
            instructions=quiz.instructions,
            time_limit=quiz.time_limit,
            total_marks=quiz.total_marks,
            passing_marks=quiz.passing_marks,
            attempts_allowed=quiz.attempts_allowed,
            start_time=quiz.start_time.isoformat() if quiz.start_time else None,
            end_time=quiz.end_time.isoformat() if quiz.end_time else None,
            is_published=quiz.is_published,
            auto_grade=quiz.auto_grade,
            total_questions=total_questions,
            total_attempts=total_attempts,
            average_score=float(avg_score) if avg_score else None,
            created_at=quiz.created_at.isoformat(),
            updated_at=quiz.updated_at.isoformat() if quiz.updated_at else None
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating quiz: {str(e)}"
        )

@router.delete("/{quiz_id}")
async def delete_quiz(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Check if quiz has attempts
        attempt_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count()
        if attempt_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete quiz with existing attempts"
            )
        
        db.delete(quiz)
        db.commit()
        
        return {"message": "Quiz deleted successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting quiz: {str(e)}"
        )


@router.get("/{quiz_id}/questions", response_model=List[QuestionResponse])
async def get_quiz_questions(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all questions in a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Get questions with AI question details
        query = text("""
            SELECT 
                qq.*,
                q.question_text as ai_question_text,
                q.type as ai_question_type,
                q.options as ai_options,
                q.correct_answer as ai_correct_answer,
                q.explanation as ai_explanation,
                q.topic,
                q.difficulty,
                q.bloom_level
            FROM quiz_questions qq
            LEFT JOIN questions q ON qq.ai_question_id = q.id
            WHERE qq.quiz_id = :quiz_id
            ORDER BY qq.order_index
        """)
        
        questions = db.execute(query, {"quiz_id": quiz_id}).fetchall()
        
        results = []
        for q in questions:
            # Use AI question data if available, otherwise use custom data
            question_text = q.ai_question_text if q.ai_question_text else q.custom_question_text
            question_type = q.ai_question_type if q.ai_question_type else q.custom_question_type
            correct_answer = q.ai_correct_answer if q.ai_correct_answer else q.custom_correct_answer
            explanation = q.ai_explanation if q.ai_explanation else q.custom_explanation
            
            # Handle options (convert JSON to list if needed)
            options = None
            if q.ai_options:
                options = q.ai_options if isinstance(q.ai_options, list) else []
            elif q.custom_options:
                options = q.custom_options if isinstance(q.custom_options, list) else []
            
            results.append(QuestionResponse(
                id=str(q.id),
                question_source=q.question_source,
                marks=q.marks,
                order_index=q.order_index,
                question_text=question_text,
                question_type=question_type,
                options=options,
                correct_answer=correct_answer,
                explanation=explanation,
                topic=q.topic,
                difficulty=q.difficulty,
                bloom_level=q.bloom_level
            ))
        
        return results
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching quiz questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching quiz questions: {str(e)}"
        )

@router.post("/{quiz_id}/questions", response_model=QuestionResponse)
async def add_question_to_quiz(
    quiz_id: str,
    question_data: QuestionAdd,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a question to a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Create quiz question
        quiz_question_data = {
            "quiz_id": quiz_id,
            "marks": question_data.marks,
            "order_index": question_data.order_index,
            "question_source": question_data.question_type
        }
        
        if question_data.question_type == 'ai_generated':
            if not question_data.ai_question_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="AI question ID is required for AI-generated questions"
                )
            quiz_question_data["ai_question_id"] = question_data.ai_question_id
        else:
            # Custom question
            if not all([
                question_data.custom_question_text,
                question_data.custom_question_type,
                question_data.custom_correct_answer
            ]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom question text, type, and correct answer are required"
                )
            
            quiz_question_data.update({
                "custom_question_text": question_data.custom_question_text,
                "custom_question_type": question_data.custom_question_type,
                "custom_options": question_data.custom_options,
                "custom_correct_answer": question_data.custom_correct_answer,
                "custom_explanation": question_data.custom_explanation
            })
        
        new_question = QuizQuestion(**quiz_question_data)
        db.add(new_question)
        db.commit()
        db.refresh(new_question)
        
        # Get question details for response
        if question_data.question_type == 'ai_generated':
            ai_question = db.query(Question).filter(
                Question.id == question_data.ai_question_id
            ).first()
            
            return QuestionResponse(
                id=str(new_question.id),
                question_source=new_question.question_source,
                marks=new_question.marks,
                order_index=new_question.order_index,
                question_text=ai_question.question_text,
                question_type=ai_question.type,
                options=ai_question.options,
                correct_answer=ai_question.correct_answer,
                explanation=ai_question.explanation,
                topic=ai_question.topic,
                difficulty=ai_question.difficulty,
                bloom_level=ai_question.bloom_level
            )
        else:
            return QuestionResponse(
                id=str(new_question.id),
                question_source=new_question.question_source,
                marks=new_question.marks,
                order_index=new_question.order_index,
                question_text=new_question.custom_question_text,
                question_type=new_question.custom_question_type,
                options=new_question.custom_options,
                correct_answer=new_question.custom_correct_answer,
                explanation=new_question.custom_explanation,
                topic=None,
                difficulty=None,
                bloom_level=None
            )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error adding question to quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding question to quiz: {str(e)}"
        )

@router.delete("/{quiz_id}/questions/{question_id}")
async def remove_question_from_quiz(
    quiz_id: str,
    question_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a question from a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Find and delete question
        question = db.query(QuizQuestion).filter(
            QuizQuestion.id == question_id,
            QuizQuestion.quiz_id == quiz_id
        ).first()
        
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this quiz"
            )
        
        db.delete(question)
        db.commit()
        
        return {"message": "Question removed from quiz successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error removing question from quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing question from quiz: {str(e)}"
        )

# FIXED: Optimized quiz results endpoint in teacher_quizzes.py

@router.get("/{quiz_id}/results")
async def get_quiz_attempts(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all attempts for a quiz with statistics - OPTIMIZED VERSION"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # OPTIMIZED: Single query to get attempts with student info and compute stats
        query = text("""
            WITH attempt_data AS (
                SELECT 
                    qa.id,
                    qa.student_id,
                    COALESCE(u.full_name, 'Unknown Student') as student_name,
                    u.email as student_email,
                    qa.attempt_number,
                    qa.obtained_marks,
                    qa.total_marks,
                    qa.percentage,
                    qa.started_at,
                    qa.submitted_at,
                    qa.time_taken,
                    qa.status,
                    qa.is_auto_graded,
                    qa.teacher_reviewed,
                    CASE WHEN qa.status = 'completed' THEN 1 ELSE 0 END as is_completed,
                    CASE WHEN qa.status = 'completed' AND qa.percentage >= :passing_percentage THEN 1 ELSE 0 END as is_passed
                FROM quiz_attempts qa
                LEFT JOIN profiles u ON qa.student_id = u.id
                WHERE qa.quiz_id = :quiz_id
            ),
            stats_data AS (
                SELECT 
                    COUNT(*) as total_attempts,
                    COUNT(DISTINCT student_id) as unique_students,
                    COUNT(*) FILTER (WHERE is_completed = 1) as completed_attempts,
                    COUNT(*) FILTER (WHERE is_passed = 1) as passed_attempts,
                    COALESCE(AVG(percentage) FILTER (WHERE is_completed = 1), 0) as avg_score,
                    COALESCE(MAX(percentage) FILTER (WHERE is_completed = 1), 0) as max_score,
                    COALESCE(MIN(percentage) FILTER (WHERE is_completed = 1), 0) as min_score
                FROM attempt_data
            )
            SELECT 
                ad.*,
                sd.total_attempts,
                sd.unique_students,
                sd.completed_attempts,
                sd.passed_attempts,
                sd.avg_score,
                sd.max_score,
                sd.min_score
            FROM attempt_data ad
            CROSS JOIN stats_data sd
            ORDER BY ad.started_at DESC
        """)
        
        # Calculate passing percentage
        passing_percentage = (quiz.passing_marks / quiz.total_marks) * 100
        
        results = db.execute(query, {
            "quiz_id": quiz_id,
            "passing_percentage": passing_percentage
        }).fetchall()
        
        if not results:
            # No attempts found
            return []
        
        # Extract stats from first row (same for all rows due to CROSS JOIN)
        first_row = results[0]
        
        # Format response as direct array for frontend compatibility
        attempts = []
        for row in results:
            attempts.append({
                "id": str(row.id),
                "student_id": str(row.student_id),
                "student_name": row.student_name,
                "student_email": row.student_email,
                "attempt_number": row.attempt_number,
                "obtained_marks": float(row.obtained_marks),
                "total_marks": float(row.total_marks),
                "percentage": float(row.percentage),
                "started_at": row.started_at.isoformat(),
                "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                "time_taken": row.time_taken,
                "status": row.status,
                "is_auto_graded": row.is_auto_graded,
                "teacher_reviewed": row.teacher_reviewed,
                # Include computed stats for frontend use
                "_stats": {
                    "total_attempts": first_row.total_attempts,
                    "unique_students": first_row.unique_students,
                    "average_score": float(first_row.avg_score),
                    "highest_score": float(first_row.max_score),
                    "lowest_score": float(first_row.min_score),
                    "pass_rate": (first_row.passed_attempts / first_row.completed_attempts * 100) if first_row.completed_attempts > 0 else 0,
                    "completion_rate": (first_row.completed_attempts / first_row.total_attempts * 100) if first_row.total_attempts > 0 else 0
                } if row == first_row else None
            })
        
        return attempts
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching quiz attempts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching quiz attempts: {str(e)}"
        )
    
# Add this endpoint to your teacher_quizzes.py file

class QuestionMarksUpdate(BaseModel):
    marks: int

@router.put("/{quiz_id}/questions/{question_id}/marks", response_model=QuestionResponse)
async def update_question_marks(
    quiz_id: str,
    question_id: str,
    marks_data: QuestionMarksUpdate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update marks for a specific question in a quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Find and update question marks
        question = db.query(QuizQuestion).filter(
            QuizQuestion.id == question_id,
            QuizQuestion.quiz_id == quiz_id
        ).first()
        
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this quiz"
            )
        
        # Validate marks
        if marks_data.marks < 1 or marks_data.marks > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Marks must be between 1 and 100"
            )
        
        # Update marks
        question.marks = marks_data.marks
        db.commit()
        db.refresh(question)
        
        # Get question details for response
        if question.question_source == 'ai_generated' and question.ai_question_id:
            ai_question = db.query(Question).filter(
                Question.id == question.ai_question_id
            ).first()
            
            return QuestionResponse(
                id=str(question.id),
                question_source=question.question_source,
                marks=question.marks,
                order_index=question.order_index,
                question_text=ai_question.question_text if ai_question else "",
                question_type=ai_question.type if ai_question else "",
                options=ai_question.options if ai_question else None,
                correct_answer=ai_question.correct_answer if ai_question else "",
                explanation=ai_question.explanation if ai_question else None,
                topic=ai_question.topic if ai_question else None,
                difficulty=ai_question.difficulty if ai_question else None,
                bloom_level=ai_question.bloom_level if ai_question else None
            )
        else:
            return QuestionResponse(
                id=str(question.id),
                question_source=question.question_source,
                marks=question.marks,
                order_index=question.order_index,
                question_text=question.custom_question_text or "",
                question_type=question.custom_question_type or "",
                options=question.custom_options,
                correct_answer=question.custom_correct_answer or "",
                explanation=question.custom_explanation,
                topic=None,
                difficulty=None,
                bloom_level=None
            )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating question marks: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating question marks: {str(e)}"
        )
    
class TeacherAttemptResultResponse(BaseModel):
    attempt: AttemptSummary
    questions_with_answers: List[Dict[str, Any]]
    summary: Dict[str, Any]
    student_info: Dict[str, Any]

@router.get("/{quiz_id}/students/{student_id}/attempts/{attempt_id}/results", response_model=TeacherAttemptResultResponse)
async def get_teacher_attempt_results(
    quiz_id: str,
    student_id: str,  # NOW USING STUDENT ID
    attempt_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed results for a specific student attempt (teacher view) - FIXED VERSION"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership first
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found or you don't have permission"
            )
        
        # FIXED: Get attempt and verify it belongs to BOTH the quiz AND the student
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.id == attempt_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == student_id  # ADDED: Validate student_id
        ).first()
        
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attempt not found for this student and quiz combination"
            )
        
        # FIXED: Get student info and verify the student exists
        student = db.query(User).filter(
            User.id == student_id,
            User.role == 'student'  # Additional validation
        ).first()
        
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found"
            )
        
        # Get responses with question details using the same query as student endpoint
        query = text("""
            SELECT 
                qr.*,
                qq.marks,
                COALESCE(q.correct_answer, qq.custom_correct_answer) as correct_answer,
                COALESCE(q.question_text, qq.custom_question_text) as question_text,
                COALESCE(q.type, qq.custom_question_type) as question_type,
                CASE 
                    WHEN q.options IS NOT NULL THEN q.options::json
                    WHEN qq.custom_options IS NOT NULL THEN qq.custom_options::json
                    ELSE NULL
                END as options,
                COALESCE(q.explanation, qq.custom_explanation) as explanation,
                qq.order_index
            FROM quiz_responses qr
            JOIN quiz_questions qq ON qr.question_id = qq.id
            LEFT JOIN questions q ON qq.ai_question_id = q.id
            WHERE qr.attempt_id = :attempt_id
              AND qr.student_id = :student_id  -- ADDED: Additional validation
              AND qr.quiz_id = :quiz_id        -- ADDED: Additional validation
            ORDER BY qq.order_index
        """)
        
        responses_with_questions = db.execute(query, {
            "attempt_id": attempt_id,
            "student_id": student_id,
            "quiz_id": quiz_id
        }).fetchall()
        
        questions_with_answers = []
        correct_count = 0
        
        for resp in responses_with_questions:
            if resp.is_correct:
                correct_count += 1
            
            questions_with_answers.append({
                "question_id": str(resp.question_id),
                "question_text": resp.question_text,
                "question_type": resp.question_type,
                "options": resp.options,
                "student_answer": resp.response,
                "correct_answer": resp.correct_answer,
                "explanation": resp.explanation,
                "marks": resp.marks,
                "score": resp.score,
                "is_correct": resp.is_correct,
                "feedback": resp.feedback,
                "time_spent": resp.time_spent,
                "confidence_level": resp.confidence_level,
                "flagged_for_review": resp.flagged_for_review
            })
        
        # Create attempt summary
        attempt_summary = AttemptSummary(
            id=str(attempt.id),
            student_id=str(attempt.student_id),
            student_name=student.full_name,
            student_email=student.email,
            attempt_number=attempt.attempt_number,
            obtained_marks=attempt.obtained_marks,
            total_marks=attempt.total_marks,
            percentage=attempt.percentage,
            started_at=attempt.started_at.isoformat(),
            submitted_at=attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            time_taken=attempt.time_taken,
            status=attempt.status,
            is_auto_graded=attempt.is_auto_graded,
            teacher_reviewed=attempt.teacher_reviewed
        )
        
        # Create summary
        summary = {
            "total_questions": len(responses_with_questions),
            "correct_answers": correct_count,
            "total_marks": attempt.total_marks,
            "obtained_marks": attempt.obtained_marks,
            "percentage": attempt.percentage,
            "passed": attempt.obtained_marks >= quiz.passing_marks,
            "time_taken": attempt.time_taken,
            "ai_grading_used": attempt.is_auto_graded,
            "quiz_title": quiz.title,
            "quiz_passing_marks": quiz.passing_marks
        }
        
        # Student info
        student_info = {
            "id": str(student.id),
            "name": student.full_name,
            "email": student.email,
            "board": student.board or "",
            "class_level": student.class_level or "",
            "institution_name": student.institution_name or ""
        }
        
        logger.info(f"Teacher {current_user['id']} accessed attempt {attempt_id} for student {student_id} in quiz {quiz_id}")
        
        return TeacherAttemptResultResponse(
            attempt=attempt_summary,
            questions_with_answers=questions_with_answers,
            summary=summary,
            student_info=student_info
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting teacher attempt results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting attempt results: {str(e)}"
        )

@router.post("/{quiz_id}/trigger-grading")
async def trigger_quiz_grading(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger auto-grading for a specific quiz"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Check if quiz has auto-grading enabled
        if not quiz.auto_grade:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This quiz does not have auto-grading enabled"
            )
        
        # Import auto-grading service
        from services.auto_grading_service import auto_grading_service
        
        # Get course info for the quiz
        course = db.query(Course).filter(Course.id == quiz.course_id).first()
        
        # Prepare quiz info for auto-grading
        quiz_info = {
            "quiz_id": str(quiz.id),
            "title": quiz.title,
            "course_id": str(quiz.course_id),
            "teacher_id": str(quiz.teacher_id),
            "teacher_name": current_user.get('full_name', 'Unknown'),
            "teacher_email": current_user.get('email', ''),
            "course_name": course.course_name if course else '',
            "end_time": quiz.end_time,
            "total_marks": quiz.total_marks
        }
        
        # Check if there are ungraded submissions
        ungraded_submissions = auto_grading_service.find_ungraded_submissions(quiz_id, db)
        
        if not ungraded_submissions:
            auto_grading_service.mark_quiz_as_graded(quiz_id, db)
            logger.info(f"No ungraded submissions found for quiz {quiz_id}. Marking as graded.")
            return {
                "success": True,
                "message": "No ungraded submissions found for this quiz",
                "graded_submissions": 0,
                "total_tokens": 0
            }
        
        logger.info(f"Manual grading triggered for quiz {quiz_id} by teacher {current_user['id']}")
        
        # Process auto-grading for this quiz
        result = auto_grading_service.process_quiz_auto_grading(quiz_info, db)
        
        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Auto-grading failed: {result['error']}"
            )
        
        # Prepare success response
        response = {
            "success": True,
            "message": f"Auto-grading completed successfully",
            "quiz_title": quiz.title,
            "graded_submissions": result.get("graded_submissions", 0),
            "total_tokens": result.get("total_tokens", 0),
            "processing_time": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Manual grading completed for quiz {quiz_id}: {result.get('graded_submissions', 0)} submissions graded")
        
        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error triggering manual grading for quiz {quiz_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error triggering auto-grading: {str(e)}"
        )
    
@router.put("/{quiz_id}/end")
async def end_quiz(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """End a quiz and mark it as completed"""
    try:
        check_teacher_permission(current_user)
        
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Check if quiz is already ended
        if quiz.end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quiz is already ended"
            )
        
        # Set end time to now
        quiz.end_time = get_india_time()
        db.commit()
        
        logger.info(f"Quiz {quiz_id} ended by teacher {current_user['id']}")
        
        return {"message": "Quiz ended successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error ending quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ending quiz: {str(e)}"
        )