# backend/routes/teacher.py - Updated with AI questions integration

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from config.database import get_db
from config.security import require_teacher, require_verified_teacher, get_current_user, check_teacher_course_access
from models import (User, Course, CourseEnrollment, Quiz, QuizQuestion, QuizAttempt, 
                   Question, QuestionSearchFilter)
from datetime import datetime, timedelta
from typing import Optional, List, Union
from pydantic import BaseModel
import uuid
import random
import string

router = APIRouter(prefix="/teacher", tags=["teacher"])

# Pydantic models
class CourseCreateRequest(BaseModel):
    course_name: str
    description: Optional[str] = None
    board: str
    class_level: str
    subject: str
    max_students: Optional[int] = 100

class CourseUpdateRequest(BaseModel):
    course_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    max_students: Optional[int] = None

class QuizCreateRequest(BaseModel):
    course_id: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    time_limit: Optional[int] = None
    total_marks: Optional[int] = 100
    passing_marks: Optional[int] = 50
    attempts_allowed: Optional[int] = 1
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class QuizQuestionAIRequest(BaseModel):
    """Add AI-generated question to quiz"""
    ai_question_id: str
    marks: Optional[int] = 1
    order_index: int

class QuizQuestionCustomRequest(BaseModel):
    """Add custom question to quiz"""
    question_text: str
    question_type: str  # mcq, short_answer, essay
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: Optional[str] = None
    marks: Optional[int] = 1
    order_index: int

class QuizQuestionMixedRequest(BaseModel):
    """Request for adding questions (either AI or custom)"""
    questions: List[Union[QuizQuestionAIRequest, QuizQuestionCustomRequest]]

class QuestionSearchRequest(BaseModel):
    board: Optional[str] = None
    class_level: Optional[str] = None
    subject: Optional[str] = None
    chapter: Optional[int] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    topic: Optional[str] = None
    bloom_level: Optional[str] = None
    category: Optional[str] = None
    search_text: Optional[str] = None
    limit: Optional[int] = 20
    offset: Optional[int] = 0

class SaveSearchFilterRequest(BaseModel):
    filter_name: str
    board: Optional[str] = None
    class_level: Optional[str] = None
    subject: Optional[str] = None
    chapter: Optional[int] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    topic: Optional[str] = None
    bloom_level: Optional[str] = None
    category: Optional[str] = None
    is_default: Optional[bool] = False

class QuizUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    time_limit: Optional[int] = None
    total_marks: Optional[int] = None
    passing_marks: Optional[int] = None
    attempts_allowed: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_published: Optional[bool] = None

def generate_course_code(length: int = 8) -> str:
    """Generate a random course code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

# Dashboard and Course Management (same as before)
@router.get("/dashboard")
async def get_teacher_dashboard(
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get teacher dashboard statistics"""
    try:
        teacher_id = current_user['id']
        
        # Get course statistics
        total_courses = db.query(Course).filter(Course.teacher_id == teacher_id).count()
        active_courses = db.query(Course).filter(
            Course.teacher_id == teacher_id,
            Course.is_active == True
        ).count()
        
        # Get student statistics
        total_students = db.query(func.count(CourseEnrollment.student_id.distinct())).join(
            Course, CourseEnrollment.course_id == Course.id
        ).filter(Course.teacher_id == teacher_id).scalar()
        
        # Get quiz statistics
        total_quizzes = db.query(Quiz).filter(Quiz.teacher_id == teacher_id).count()
        published_quizzes = db.query(Quiz).filter(
            Quiz.teacher_id == teacher_id,
            Quiz.is_published == True
        ).count()
        
        # Recent activity
        recent_enrollments = db.query(CourseEnrollment).join(
            Course, CourseEnrollment.course_id == Course.id
        ).filter(Course.teacher_id == teacher_id).order_by(
            desc(CourseEnrollment.enrolled_at)
        ).limit(5).all()
        
        return {
            "statistics": {
                "total_courses": total_courses,
                "active_courses": active_courses,
                "total_students": total_students or 0,
                "total_quizzes": total_quizzes,
                "published_quizzes": published_quizzes
            },
            "recent_enrollments": [
                {
                    "student_name": enrollment.student.full_name,
                    "course_name": enrollment.course.course_name,
                    "enrolled_at": enrollment.enrolled_at.isoformat()
                }
                for enrollment in recent_enrollments if enrollment.student
            ]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching dashboard: {str(e)}")

@router.post("/courses")
async def create_course(
    course_data: CourseCreateRequest,
    current_user: dict = Depends(require_verified_teacher),
    db: Session = Depends(get_db)
):
    """Create a new course"""
    try:
        # Generate unique course code
        course_code = generate_course_code()
        while db.query(Course).filter(Course.course_code == course_code).first():
            course_code = generate_course_code()
        
        course = Course(
            teacher_id=current_user['id'],
            course_name=course_data.course_name,
            course_code=course_code,
            description=course_data.description,
            board=course_data.board,
            class_level=course_data.class_level,
            subject=course_data.subject,
            max_students=course_data.max_students
        )
        
        db.add(course)
        db.commit()
        db.refresh(course)
        
        return {
            "message": "Course created successfully",
            "course": {
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "description": course.description,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "is_active": course.is_active,
                "max_students": course.max_students,
                "created_at": course.created_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error creating course: {str(e)}")

@router.get("/courses")
async def get_teacher_courses(
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db),
    active_only: bool = Query(False)
):
    """Get all courses for the teacher"""
    try:
        query = db.query(Course).filter(Course.teacher_id == current_user['id'])
        
        if active_only:
            query = query.filter(Course.is_active == True)
        
        courses = query.order_by(desc(Course.created_at)).all()
        
        course_list = []
        for course in courses:
            # Get enrollment count
            enrollment_count = db.query(CourseEnrollment).filter(
                CourseEnrollment.course_id == course.id,
                CourseEnrollment.status == 'active'
            ).count()
            
            # Get quiz count
            quiz_count = db.query(Quiz).filter(Quiz.course_id == course.id).count()
            
            course_list.append({
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "description": course.description,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "is_active": course.is_active,
                "max_students": course.max_students,
                "enrolled_students": enrollment_count,
                "total_quizzes": quiz_count,
                "created_at": course.created_at.isoformat()
            })
        
        return {"courses": course_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching courses: {str(e)}")

# AI Question Search and Management
@router.post("/questions/search")
async def search_ai_questions(
    search_params: QuestionSearchRequest,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Search AI-generated questions for quiz creation"""
    try:
        query = db.query(Question)
        
        # Apply filters
        if search_params.board:
            query = query.filter(Question.board == search_params.board)
        if search_params.class_level:
            query = query.filter(Question.class_level == search_params.class_level)
        if search_params.subject:
            query = query.filter(Question.subject == search_params.subject)
        if search_params.chapter:
            query = query.filter(Question.chapter == search_params.chapter)
        if search_params.difficulty:
            query = query.filter(Question.difficulty == search_params.difficulty)
        if search_params.question_type:
            query = query.filter(Question.type == search_params.question_type)
        if search_params.topic:
            query = query.filter(Question.topic.ilike(f"%{search_params.topic}%"))
        if search_params.bloom_level:
            query = query.filter(Question.bloom_level == search_params.bloom_level)
        if search_params.category:
            query = query.filter(Question.category == search_params.category)
        if search_params.search_text:
            query = query.filter(
                Question.question_text.ilike(f"%{search_params.search_text}%")
            )
        
        # Get total count for pagination
        total_count = query.count()
        
        # Apply pagination
        questions = query.offset(search_params.offset).limit(search_params.limit).all()
        
        question_list = []
        for question in questions:
            question_list.append({
                "id": str(question.id),
                "human_readable_id": question.human_readable_id,
                "question_text": question.question_text,
                "type": question.type,
                "difficulty": question.difficulty,
                "options": question.options,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "topic": question.topic,
                "bloom_level": question.bloom_level,
                "board": question.board,
                "class_level": question.class_level,
                "subject": question.subject,
                "chapter": question.chapter,
                "category": question.category
            })
        
        return {
            "questions": question_list,
            "total_count": total_count,
            "offset": search_params.offset,
            "limit": search_params.limit
        }
    except Exception as e:
        raise HTTPException(500, f"Error searching questions: {str(e)}")

@router.get("/questions/filters")
async def get_question_filter_options(
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get available filter options for question search"""
    try:
        # Get unique values for each filter field
        boards = db.query(Question.board.distinct()).all()
        class_levels = db.query(Question.class_level.distinct()).all()
        subjects = db.query(Question.subject.distinct()).all()
        difficulties = db.query(Question.difficulty.distinct()).all()
        question_types = db.query(Question.type.distinct()).all()
        categories = db.query(Question.category.distinct()).all()
        bloom_levels = db.query(Question.bloom_level.distinct()).filter(
            Question.bloom_level.isnot(None)
        ).all()
        
        return {
            "boards": [item[0] for item in boards],
            "class_levels": [item[0] for item in class_levels],
            "subjects": [item[0] for item in subjects],
            "difficulties": [item[0] for item in difficulties],
            "question_types": [item[0] for item in question_types],
            "categories": [item[0] for item in categories],
            "bloom_levels": [item[0] for item in bloom_levels if item[0]]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching filter options: {str(e)}")

@router.post("/questions/filters/save")
async def save_search_filter(
    filter_data: SaveSearchFilterRequest,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Save a search filter for future use"""
    try:
        # If setting as default, remove default flag from other filters
        if filter_data.is_default:
            db.query(QuestionSearchFilter).filter(
                QuestionSearchFilter.teacher_id == current_user['id'],
                QuestionSearchFilter.is_default == True
            ).update({"is_default": False})
        
        search_filter = QuestionSearchFilter(
            teacher_id=current_user['id'],
            filter_name=filter_data.filter_name,
            board=filter_data.board,
            class_level=filter_data.class_level,
            subject=filter_data.subject,
            chapter=filter_data.chapter,
            difficulty=filter_data.difficulty,
            question_type=filter_data.question_type,
            topic=filter_data.topic,
            bloom_level=filter_data.bloom_level,
            category=filter_data.category,
            is_default=filter_data.is_default
        )
        
        db.add(search_filter)
        db.commit()
        db.refresh(search_filter)
        
        return {
            "message": "Search filter saved successfully",
            "filter": {
                "id": str(search_filter.id),
                "filter_name": search_filter.filter_name,
                "is_default": search_filter.is_default
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error saving search filter: {str(e)}")

@router.get("/questions/filters/saved")
async def get_saved_search_filters(
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get teacher's saved search filters"""
    try:
        filters = db.query(QuestionSearchFilter).filter(
            QuestionSearchFilter.teacher_id == current_user['id']
        ).order_by(desc(QuestionSearchFilter.is_default), QuestionSearchFilter.filter_name).all()
        
        filter_list = []
        for filter_obj in filters:
            filter_list.append({
                "id": str(filter_obj.id),
                "filter_name": filter_obj.filter_name,
                "board": filter_obj.board,
                "class_level": filter_obj.class_level,
                "subject": filter_obj.subject,
                "chapter": filter_obj.chapter,
                "difficulty": filter_obj.difficulty,
                "question_type": filter_obj.question_type,
                "topic": filter_obj.topic,
                "bloom_level": filter_obj.bloom_level,
                "category": filter_obj.category,
                "is_default": filter_obj.is_default,
                "created_at": filter_obj.created_at.isoformat()
            })
        
        return {"filters": filter_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching saved filters: {str(e)}")

# Quiz Management with Mixed Questions
@router.post("/quizzes")
async def create_quiz(
    quiz_data: QuizCreateRequest,
    current_user: dict = Depends(require_verified_teacher),
    db: Session = Depends(get_db)
):
    """Create a new quiz"""
    try:
        # Verify teacher owns the course
        course = db.query(Course).filter(
            Course.id == quiz_data.course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(404, "Course not found or access denied")
        
        quiz = Quiz(
            teacher_id=current_user['id'],
            course_id=quiz_data.course_id,
            title=quiz_data.title,
            description=quiz_data.description,
            instructions=quiz_data.instructions,
            time_limit=quiz_data.time_limit,
            total_marks=quiz_data.total_marks,
            passing_marks=quiz_data.passing_marks,
            attempts_allowed=quiz_data.attempts_allowed,
            start_time=quiz_data.start_time,
            end_time=quiz_data.end_time
        )
        
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        
        return {
            "message": "Quiz created successfully",
            "quiz": {
                "id": str(quiz.id),
                "title": quiz.title,
                "description": quiz.description,
                "course_id": str(quiz.course_id),
                "course_name": course.course_name,
                "is_published": quiz.is_published,
                "created_at": quiz.created_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error creating quiz: {str(e)}")

@router.post("/quizzes/{quiz_id}/questions/ai")
async def add_ai_question_to_quiz(
    quiz_id: str,
    question_data: QuizQuestionAIRequest,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Add an AI-generated question to a quiz"""
    try:
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or access denied")
        
        # Verify AI question exists
        ai_question = db.query(Question).filter(Question.id == question_data.ai_question_id).first()
        if not ai_question:
            raise HTTPException(404, "AI question not found")
        
        # Check if question already added to this quiz
        existing = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz_id,
            QuizQuestion.ai_question_id == question_data.ai_question_id
        ).first()
        
        if existing:
            raise HTTPException(400, "This question is already added to the quiz")
        
        quiz_question = QuizQuestion(
            quiz_id=quiz_id,
            ai_question_id=question_data.ai_question_id,
            marks=question_data.marks,
            order_index=question_data.order_index,
            question_source='ai_generated'
        )
        
        db.add(quiz_question)
        db.commit()
        db.refresh(quiz_question)
        
        return {
            "message": "AI question added to quiz successfully",
            "quiz_question": {
                "id": str(quiz_question.id),
                "question_text": ai_question.question_text,
                "question_type": ai_question.type,
                "marks": quiz_question.marks,
                "order_index": quiz_question.order_index,
                "source": "ai_generated"
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error adding AI question to quiz: {str(e)}")

@router.post("/quizzes/{quiz_id}/questions/custom")
async def add_custom_question_to_quiz(
    quiz_id: str,
    question_data: QuizQuestionCustomRequest,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Add a custom question to a quiz"""
    try:
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or access denied")
        
        quiz_question = QuizQuestion(
            quiz_id=quiz_id,
            custom_question_text=question_data.question_text,
            custom_question_type=question_data.question_type,
            custom_options=question_data.options,
            custom_correct_answer=question_data.correct_answer,
            custom_explanation=question_data.explanation,
            marks=question_data.marks,
            order_index=question_data.order_index,
            question_source='custom'
        )
        
        db.add(quiz_question)
        db.commit()
        db.refresh(quiz_question)
        
        return {
            "message": "Custom question added to quiz successfully",
            "quiz_question": {
                "id": str(quiz_question.id),
                "question_text": quiz_question.custom_question_text,
                "question_type": quiz_question.custom_question_type,
                "marks": quiz_question.marks,
                "order_index": quiz_question.order_index,
                "source": "custom"
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error adding custom question to quiz: {str(e)}")

@router.get("/quizzes/{quiz_id}/questions")
async def get_quiz_questions(
    quiz_id: str,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get all questions in a quiz with full details"""
    try:
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or access denied")
        
        quiz_questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz_id
        ).order_by(QuizQuestion.order_index).all()
        
        questions_list = []
        for qq in quiz_questions:
            if qq.question_source == 'ai_generated' and qq.ai_question:
                # AI-generated question
                questions_list.append({
                    "id": str(qq.id),
                    "question_text": qq.ai_question.question_text,
                    "question_type": qq.ai_question.type,
                    "options": qq.ai_question.options,
                    "correct_answer": qq.ai_question.correct_answer,
                    "explanation": qq.ai_question.explanation,
                    "marks": qq.marks,
                    "order_index": qq.order_index,
                    "source": "ai_generated",
                    "ai_question_id": str(qq.ai_question_id),
                    "difficulty": qq.ai_question.difficulty,
                    "topic": qq.ai_question.topic,
                    "bloom_level": qq.ai_question.bloom_level
                })
            else:
                # Custom question
                questions_list.append({
                    "id": str(qq.id),
                    "question_text": qq.custom_question_text,
                    "question_type": qq.custom_question_type,
                    "options": qq.custom_options,
                    "correct_answer": qq.custom_correct_answer,
                    "explanation": qq.custom_explanation,
                    "marks": qq.marks,
                    "order_index": qq.order_index,
                    "source": "custom"
                })
        
        return {
            "quiz": {
                "id": str(quiz.id),
                "title": quiz.title,
                "total_marks": quiz.total_marks,
                "is_published": quiz.is_published
            },
            "questions": questions_list
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching quiz questions: {str(e)}")

@router.delete("/quizzes/{quiz_id}/questions/{question_id}")
async def remove_question_from_quiz(
    quiz_id: str,
    question_id: str,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Remove a question from a quiz"""
    try:
        # Verify quiz ownership
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or access denied")
        
        # Don't allow editing published quizzes that have attempts
        if quiz.is_published:
            attempt_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz_id).count()
            if attempt_count > 0:
                raise HTTPException(400, "Cannot modify quiz that has student attempts")
        
        quiz_question = db.query(QuizQuestion).filter(
            QuizQuestion.id == question_id,
            QuizQuestion.quiz_id == quiz_id
        ).first()
        
        if not quiz_question:
            raise HTTPException(404, "Question not found in this quiz")
        
        db.delete(quiz_question)
        db.commit()
        
        return {"message": "Question removed from quiz successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error removing question from quiz: {str(e)}")

@router.get("/quizzes")
async def get_teacher_quizzes(
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db),
    course_id: Optional[str] = Query(None)
):
    """Get all quizzes for the teacher with question counts"""
    try:
        query = db.query(Quiz).filter(Quiz.teacher_id == current_user['id'])
        
        if course_id:
            query = query.filter(Quiz.course_id == course_id)
        
        quizzes = query.order_by(desc(Quiz.created_at)).all()
        
        quiz_list = []
        for quiz in quizzes:
            attempt_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count()
            question_count = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
            
            # Count AI vs custom questions
            ai_questions = db.query(QuizQuestion).filter(
                QuizQuestion.quiz_id == quiz.id,
                QuizQuestion.question_source == 'ai_generated'
            ).count()
            custom_questions = question_count - ai_questions
            
            quiz_list.append({
                "id": str(quiz.id),
                "title": quiz.title,
                "description": quiz.description,
                "course_name": quiz.course.course_name,
                "course_id": str(quiz.course_id),
                "is_published": quiz.is_published,
                "total_marks": quiz.total_marks,
                "question_count": question_count,
                "ai_questions": ai_questions,
                "custom_questions": custom_questions,
                "attempt_count": attempt_count,
                "start_time": quiz.start_time.isoformat() if quiz.start_time else None,
                "end_time": quiz.end_time.isoformat() if quiz.end_time else None,
                "created_at": quiz.created_at.isoformat()
            })
        
        return {"quizzes": quiz_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching quizzes: {str(e)}")

# Rest of the existing endpoints remain the same...
@router.get("/courses/{course_id}")
async def get_course_details(
    course_id: str,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific course"""
    try:
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.teacher_id == current_user['id']
        ).first()
        
        if not course:
            raise HTTPException(404, "Course not found")
        
        # Get enrolled students
        enrollments = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == 'active'
        ).all()
        
        students = []
        for enrollment in enrollments:
            if enrollment.student:
                students.append({
                    "id": str(enrollment.student.id),
                    "name": enrollment.student.full_name,
                    "email": enrollment.student.email,
                    "enrolled_at": enrollment.enrolled_at.isoformat(),
                    "total_quizzes_taken": enrollment.total_quizzes_taken,
                    "average_score": enrollment.average_score
                })
        
        # Get quizzes
        quizzes = db.query(Quiz).filter(Quiz.course_id == course_id).all()
        quiz_list = []
        for quiz in quizzes:
            attempt_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count()
            question_count = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
            
            quiz_list.append({
                "id": str(quiz.id),
                "title": quiz.title,
                "description": quiz.description,
                "is_published": quiz.is_published,
                "total_marks": quiz.total_marks,
                "question_count": question_count,
                "attempt_count": attempt_count,
                "created_at": quiz.created_at.isoformat()
            })
        
        return {
            "course": {
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "description": course.description,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "is_active": course.is_active,
                "max_students": course.max_students,
                "created_at": course.created_at.isoformat()
            },
            "students": students,
            "quizzes": quiz_list
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching course details: {str(e)}")

@router.get("/quizzes/{quiz_id}/results")
async def get_quiz_results(
    quiz_id: str,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Get quiz results and analytics"""
    try:
        # Verify teacher owns the quiz
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.teacher_id == current_user['id']
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or access denied")
        
        # Get all attempts
        attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.status == "submitted"
        ).all()
        
        results = []
        total_scores = []
        
        for attempt in attempts:
            if attempt.student:
                results.append({
                    "student_name": attempt.student.full_name,
                    "student_email": attempt.student.email,
                    "attempt_number": attempt.attempt_number,
                    "obtained_marks": attempt.obtained_marks,
                    "total_marks": attempt.total_marks,
                    "percentage": attempt.percentage,
                    "time_taken": attempt.time_taken,
                    "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None
                })
                total_scores.append(attempt.percentage)
        
        # Calculate statistics
        analytics = {
            "total_attempts": len(attempts),
            "average_score": sum(total_scores) / len(total_scores) if total_scores else 0,
            "highest_score": max(total_scores) if total_scores else 0,
            "lowest_score": min(total_scores) if total_scores else 0,
            "pass_rate": len([s for s in total_scores if s >= (quiz.passing_marks / quiz.total_marks * 100)]) / len(total_scores) * 100 if total_scores else 0
        }
        
        return {
            "quiz": {
                "id": str(quiz.id),
                "title": quiz.title,
                "total_marks": quiz.total_marks,
                "passing_marks": quiz.passing_marks
            },
            "analytics": analytics,
            "results": results
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching quiz results: {str(e)}")