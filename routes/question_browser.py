# backend/routes/question_browser.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_, and_
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Question, QuestionSearchFilter
import logging

router = APIRouter(prefix="/api/teacher/questions", tags=["question-browser"])

logger = logging.getLogger(__name__)

# Pydantic models
class QuestionBrowseResponse(BaseModel):
    id: str
    question_text: str
    type: str
    difficulty: str
    options: Optional[List[str]]
    correct_answer: str
    explanation: Optional[str]
    topic: Optional[str]
    bloom_level: Optional[str]
    board: str
    class_level: str
    subject: str
    chapter: int
    category: str
    human_readable_id: Optional[str]

class QuestionFilters(BaseModel):
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

class SearchFilterCreate(BaseModel):
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
    is_default: bool = False

class SearchFilterResponse(BaseModel):
    id: str
    filter_name: str
    board: Optional[str]
    class_level: Optional[str]
    subject: Optional[str]
    chapter: Optional[int]
    difficulty: Optional[str]
    question_type: Optional[str]
    topic: Optional[str]
    bloom_level: Optional[str]
    category: Optional[str]
    is_default: bool
    created_at: str

class QuestionStats(BaseModel):
    total_questions: int
    by_difficulty: Dict[str, int]
    by_type: Dict[str, int]
    by_category: Dict[str, int]
    by_bloom_level: Dict[str, int]

def check_teacher_permission(user: Dict):
    """Check if user is a teacher"""
    if user.get('role') != 'teacher':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )

@router.get("/browse", response_model=List[QuestionBrowseResponse])
async def browse_questions(
    board: Optional[str] = Query(None),
    class_level: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    chapter: Optional[int] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    bloom_level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search_text: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Browse AI-generated questions with filters and pagination"""
    try:
        check_teacher_permission(current_user)
        
        # Start with base query
        query = db.query(Question)
        
        # Apply filters
        if board:
            query = query.filter(Question.board == board)
        if class_level:
            query = query.filter(Question.class_level == class_level)
        if subject:
            query = query.filter(Question.subject == subject)
        if chapter is not None:
            query = query.filter(Question.chapter == chapter)
        if difficulty:
            query = query.filter(Question.difficulty == difficulty)
        if question_type:
            query = query.filter(Question.type == question_type)
        if topic:
            query = query.filter(Question.topic.ilike(f"%{topic}%"))
        if bloom_level:
            query = query.filter(Question.bloom_level == bloom_level)
        if category:
            query = query.filter(Question.category == category)
        if search_text:
            query = query.filter(
                or_(
                    Question.question_text.ilike(f"%{search_text}%"),
                    Question.topic.ilike(f"%{search_text}%"),
                    Question.explanation.ilike(f"%{search_text}%")
                )
            )
        
        # Get total count for pagination
        total_count = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        questions = query.offset(offset).limit(per_page).all()
        
        # Convert to response format
        results = []
        for q in questions:
            results.append(QuestionBrowseResponse(
                id=str(q.id),
                question_text=q.question_text,
                type=q.type,
                difficulty=q.difficulty,
                options=q.options if q.options else None,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                topic=q.topic,
                bloom_level=q.bloom_level,
                board=q.board,
                class_level=q.class_level,
                subject=q.subject,
                chapter=q.chapter,
                category=q.category,
                human_readable_id=q.human_readable_id
            ))
        
        return results
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error browsing questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error browsing questions: {str(e)}"
        )

@router.get("/stats", response_model=QuestionStats)
async def get_question_stats(
    board: Optional[str] = Query(None),
    class_level: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics about available questions"""
    try:
        check_teacher_permission(current_user)
        
        # Build base query
        base_query = db.query(Question)
        
        # Apply basic filters
        if board:
            base_query = base_query.filter(Question.board == board)
        if class_level:
            base_query = base_query.filter(Question.class_level == class_level)
        if subject:
            base_query = base_query.filter(Question.subject == subject)
        
        # Get total count
        total_questions = base_query.count()
        
        # Get counts by difficulty
        difficulty_stats = db.query(
            Question.difficulty,
            func.count(Question.id)
        ).filter(
            Question.id.in_(base_query.with_entities(Question.id))
        ).group_by(Question.difficulty).all()
        
        by_difficulty = {item[0]: item[1] for item in difficulty_stats}
        
        # Get counts by type
        type_stats = db.query(
            Question.type,
            func.count(Question.id)
        ).filter(
            Question.id.in_(base_query.with_entities(Question.id))
        ).group_by(Question.type).all()
        
        by_type = {item[0]: item[1] for item in type_stats}
        
        # Get counts by category
        category_stats = db.query(
            Question.category,
            func.count(Question.id)
        ).filter(
            Question.id.in_(base_query.with_entities(Question.id))
        ).group_by(Question.category).all()
        
        by_category = {item[0]: item[1] for item in category_stats}
        
        # Get counts by bloom level
        bloom_stats = db.query(
            Question.bloom_level,
            func.count(Question.id)
        ).filter(
            Question.id.in_(base_query.with_entities(Question.id)),
            Question.bloom_level.isnot(None)
        ).group_by(Question.bloom_level).all()
        
        by_bloom_level = {item[0]: item[1] for item in bloom_stats}
        
        return QuestionStats(
            total_questions=total_questions,
            by_difficulty=by_difficulty,
            by_type=by_type,
            by_category=by_category,
            by_bloom_level=by_bloom_level
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting question stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting question stats: {str(e)}"
        )

@router.get("/filters", response_model=List[Dict[str, Any]])
async def get_available_filters(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available filter options for question browsing"""
    try:
        check_teacher_permission(current_user)
        
        # Get distinct values for each filter field
        boards = db.query(Question.board).distinct().all()
        class_levels = db.query(Question.class_level).distinct().all()
        subjects = db.query(Question.subject).distinct().all()
        difficulties = db.query(Question.difficulty).distinct().all()
        types = db.query(Question.type).distinct().all()
        categories = db.query(Question.category).distinct().all()
        bloom_levels = db.query(Question.bloom_level).filter(
            Question.bloom_level.isnot(None)
        ).distinct().all()
        
        return [
            {
                "field": "board",
                "label": "Board",
                "options": [{"value": item[0], "label": item[0].upper()} for item in boards]
            },
            {
                "field": "class_level", 
                "label": "Class Level",
                "options": [{"value": item[0], "label": item[0].upper()} for item in class_levels]
            },
            {
                "field": "subject",
                "label": "Subject", 
                "options": [{"value": item[0], "label": item[0].replace('_', ' ').title()} for item in subjects]
            },
            {
                "field": "difficulty",
                "label": "Difficulty",
                "options": [{"value": item[0], "label": item[0].title()} for item in difficulties]
            },
            {
                "field": "question_type",
                "label": "Question Type",
                "options": [{"value": item[0], "label": item[0]} for item in types]
            },
            {
                "field": "category", 
                "label": "Category",
                "options": [{"value": item[0], "label": item[0].replace('_', ' ').title()} for item in categories]
            },
            {
                "field": "bloom_level",
                "label": "Bloom Level", 
                "options": [{"value": item[0], "label": item[0].title()} for item in bloom_levels]
            }
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting filter options: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting filter options: {str(e)}"
        )

@router.get("/{question_id}", response_model=QuestionBrowseResponse)
async def get_question_details(
    question_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific question"""
    try:
        check_teacher_permission(current_user)
        
        question = db.query(Question).filter(Question.id == question_id).first()
        
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        return QuestionBrowseResponse(
            id=str(question.id),
            question_text=question.question_text,
            type=question.type,
            difficulty=question.difficulty,
            options=question.options if question.options else None,
            correct_answer=question.correct_answer,
            explanation=question.explanation,
            topic=question.topic,
            bloom_level=question.bloom_level,
            board=question.board,
            class_level=question.class_level,
            subject=question.subject,
            chapter=question.chapter,
            category=question.category,
            human_readable_id=question.human_readable_id
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting question details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting question details: {str(e)}"
        )

# Search filter management endpoints
@router.post("/search-filters", response_model=SearchFilterResponse)
async def create_search_filter(
    filter_data: SearchFilterCreate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a saved search filter"""
    try:
        check_teacher_permission(current_user)
        
        new_filter = QuestionSearchFilter(
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
        
        db.add(new_filter)
        db.commit()
        db.refresh(new_filter)
        
        return SearchFilterResponse(
            id=str(new_filter.id),
            filter_name=new_filter.filter_name,
            board=new_filter.board,
            class_level=new_filter.class_level,
            subject=new_filter.subject,
            chapter=new_filter.chapter,
            difficulty=new_filter.difficulty,
            question_type=new_filter.question_type,
            topic=new_filter.topic,
            bloom_level=new_filter.bloom_level,
            category=new_filter.category,
            is_default=new_filter.is_default,
            created_at=new_filter.created_at.isoformat()
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating search filter: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating search filter: {str(e)}"
        )

@router.get("/search-filters/", response_model=List[SearchFilterResponse])
async def get_search_filters(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all saved search filters for the teacher"""
    try:
        check_teacher_permission(current_user)
        
        filters = db.query(QuestionSearchFilter).filter(
            QuestionSearchFilter.teacher_id == current_user['id']
        ).order_by(QuestionSearchFilter.is_default.desc(), QuestionSearchFilter.created_at.desc()).all()
        
        return [
            SearchFilterResponse(
                id=str(filter_obj.id),
                filter_name=filter_obj.filter_name,
                board=filter_obj.board,
                class_level=filter_obj.class_level,
                subject=filter_obj.subject,
                chapter=filter_obj.chapter,
                difficulty=filter_obj.difficulty,
                question_type=filter_obj.question_type,
                topic=filter_obj.topic,
                bloom_level=filter_obj.bloom_level,
                category=filter_obj.category,
                is_default=filter_obj.is_default,
                created_at=filter_obj.created_at.isoformat()
            )
            for filter_obj in filters
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting search filters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting search filters: {str(e)}"
        )

@router.delete("/search-filters/{filter_id}")
async def delete_search_filter(
    filter_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a saved search filter"""
    try:
        check_teacher_permission(current_user)
        
        filter_obj = db.query(QuestionSearchFilter).filter(
            QuestionSearchFilter.id == filter_id,
            QuestionSearchFilter.teacher_id == current_user['id']
        ).first()
        
        if not filter_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Search filter not found"
            )
        
        db.delete(filter_obj)
        db.commit()
        
        return {"message": "Search filter deleted successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting search filter: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting search filter: {str(e)}"
        )