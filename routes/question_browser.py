# backend/routes/question_browser.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Question
import logging

router = APIRouter(prefix="/api/teacher/question-browser", tags=["question-browser"])

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
    category: Optional[str]
    board: str
    class_level: str
    subject: str
    chapter: Optional[int]
    human_readable_id: Optional[str]
    metadata: Optional[Dict]

class QuestionBrowseResult(BaseModel):
    questions: List[QuestionBrowseResponse]
    total_count: int
    filters_applied: Dict[str, str]
    pagination: Dict[str, int]

def check_teacher_permission(user: Dict):
    """Check if user is a teacher"""
    if user.get('role') != 'teacher':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )

def get_subject_mapping(board: str, class_: str, subject: str) -> Tuple[str, str, str]:
    """Get actual board/class/subject to use, considering shared subjects and handling code/display name variations"""
    try:
        from config.subjects import SUBJECT_CONFIG, SubjectType
        
        print(f"Original subject mapping request: {board}/{class_}/{subject}")
        
        # Try exact lookup from SUBJECT_CONFIG first
        if board in SUBJECT_CONFIG:
            board_config = SUBJECT_CONFIG[board]
            if class_ in board_config.classes:
                class_config = board_config.classes[class_]
                
                # First try code match
                subject_obj = next(
                    (s for s in class_config.subjects if s.code.lower() == subject.lower()),
                    None
                )
                
                # Then try name match with different formats
                if not subject_obj:
                    normalized_subject = subject.lower().replace('-', ' ').replace('_', ' ')
                    subject_obj = next(
                        (s for s in class_config.subjects if 
                         s.name.lower() == normalized_subject or
                         s.name.lower().replace(' ', '-') == subject.lower() or 
                         s.name.lower().replace(' ', '_') == subject.lower()),
                        None
                    )
                
                if subject_obj and subject_obj.type == SubjectType.SHARED and subject_obj.shared_mapping:
                    mapping = subject_obj.shared_mapping
                    print(f"Found SHARED mapping in config: {mapping.source_board}/{mapping.source_class}/{mapping.source_subject}")
                    return mapping.source_board, mapping.source_class, mapping.source_subject
        
        # If not found in config, check database
        try:
            from sqlalchemy import text
            from config.database import SessionLocal
            
            db = SessionLocal()
            try:
                query = text("""
                    SELECT s.source_board, s.source_class, s.source_subject 
                    FROM subjects s
                    JOIN class_levels cl ON s.class_level_id = cl.id
                    JOIN boards b ON cl.board_id = b.id
                    WHERE b.code = :board 
                      AND cl.code = :class
                      AND (s.code = :subject OR s.display_name = :subject_name)
                      AND s.type = 'SHARED'
                      AND s.source_board IS NOT NULL
                """)
                
                normalized_subject_name = subject.replace('-', ' ').replace('_', ' ')
                result = db.execute(query, {
                    "board": board,
                    "class": class_,
                    "subject": subject,
                    "subject_name": normalized_subject_name
                }).fetchone()
                
                if result:
                    print(f"Found SHARED mapping in database: {result.source_board}/{result.source_class}/{result.source_subject}")
                    return result.source_board, result.source_class, result.source_subject
            finally:
                db.close()
        except Exception as db_err:
            print(f"Database lookup error: {str(db_err)}")
        
        # If no mapping found, return the original values
        print(f"No mapping found, using original: {board}/{class_}/{subject}")
        return board, class_, subject
            
    except Exception as e:
        print(f"Error in get_subject_mapping: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return board, class_, subject

# def get_subject_mapping(board: str, class_: str, subject: str):
#     """Get actual board/class/subject to use, considering shared subjects"""
#     # This function should match the one in main.py
#     # For now, return the original values - you can enhance this later
#     return board.lower(), class_.lower(), subject.lower()

@router.get("/{board}/{class_level}/{subject}", response_model=QuestionBrowseResult)
async def browse_questions(
    board: str,
    class_level: str,
    subject: str,
    # Query parameters for filtering
    difficulty: Optional[str] = Query(None, description="Filter by difficulty: Easy, Medium, Hard"),
    type: Optional[str] = Query(None, description="Filter by question type: MCQ, Short Answer, Long Answer"),
    category: Optional[str] = Query(None, description="Filter by category: generated, in_chapter, exercise"),
    chapter: Optional[int] = Query(None, description="Filter by chapter number"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    bloom_level: Optional[str] = Query(None, description="Filter by Bloom's taxonomy level"),
    search: Optional[str] = Query(None, description="Search in question text"),
    limit: Optional[int] = Query(50, ge=1, le=200, description="Number of questions to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of questions to skip"),
    # Authentication
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Browse questions available for adding to quizzes.
    Supports filtering by difficulty, type, category, chapter, topic, etc.
    """
    try:
        check_teacher_permission(current_user)
        
        # Map to actual board/class/subject (handle shared subjects)
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board, class_level, subject
        )
        
        logger.info(f"Browsing questions for {actual_board}/{actual_class}/{actual_subject}")
        
        # Build base query
        query = db.query(Question).filter(
            Question.board == actual_board,
            Question.class_level == actual_class,
            Question.subject == actual_subject
        )
        
        # Apply filters
        filters_applied = {
            "board": actual_board,
            "class_level": actual_class,
            "subject": actual_subject
        }
        
        if difficulty:
            query = query.filter(Question.difficulty == difficulty)
            filters_applied["difficulty"] = difficulty
        
        if type:
            query = query.filter(Question.type == type)
            filters_applied["type"] = type
        
        if category:
            query = query.filter(Question.category == category)
            filters_applied["category"] = category
        
        if chapter:
            # Handle both base chapter and extended chapter formats
            base_chapter = chapter
            extended_chapter = 100 + chapter
            query = query.filter(
                or_(
                    Question.chapter == base_chapter,
                    Question.chapter == extended_chapter
                )
            )
            filters_applied["chapter"] = str(chapter)
        
        if topic:
            query = query.filter(Question.topic.ilike(f"%{topic}%"))
            filters_applied["topic"] = topic
        
        if bloom_level:
            query = query.filter(Question.bloom_level == bloom_level)
            filters_applied["bloom_level"] = bloom_level
        
        if search:
            query = query.filter(Question.question_text.ilike(f"%{search}%"))
            filters_applied["search"] = search
        
        # Get total count before pagination
        total_count = query.count()
        
        # Apply pagination and ordering
        questions = query.order_by(
            Question.difficulty,
            Question.chapter,
            Question.human_readable_id
        ).offset(offset).limit(limit).all()
        
        # Format response
        question_responses = []
        for q in questions:
            # Parse category from human_readable_id if available
            category_display = "Unknown"
            if q.human_readable_id:
                if "_g" in q.human_readable_id:
                    category_display = "Generated"
                elif "_ic" in q.human_readable_id:
                    category_display = "In-Chapter"
                elif "_ec" in q.human_readable_id:
                    category_display = "Exercise"
            
            question_responses.append(QuestionBrowseResponse(
                id=str(q.id),
                question_text=q.question_text,
                type=q.type,
                difficulty=q.difficulty,
                options=q.options if q.options else None,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                topic=q.topic,
                bloom_level=q.bloom_level,
                category=category_display,
                board=q.board,
                class_level=q.class_level,
                subject=q.subject,
                chapter=q.chapter,
                human_readable_id=q.human_readable_id,
                metadata={
                    "file_source": q.file_source,
                    "section_id": q.section_id
                }
            ))
        
        pagination_info = {
            "limit": limit,
            "offset": offset,
            "total": total_count,
            "returned": len(question_responses),
            "has_more": (offset + limit) < total_count
        }
        
        logger.info(f"Found {total_count} questions, returning {len(question_responses)}")
        
        return QuestionBrowseResult(
            questions=question_responses,
            total_count=total_count,
            filters_applied=filters_applied,
            pagination=pagination_info
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error browsing questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error browsing questions: {str(e)}"
        )

@router.get("/{board}/{class_level}/{subject}/stats")
async def get_question_stats(
    board: str,
    class_level: str,
    subject: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics about available questions for the given board/class/subject"""
    try:
        check_teacher_permission(current_user)
        
        # Map to actual board/class/subject
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board, class_level, subject
        )
        
        # Get question statistics
        stats_query = text("""
            SELECT 
                COUNT(*) as total_questions,
                COUNT(DISTINCT chapter) as total_chapters,
                COUNT(CASE WHEN difficulty = 'Easy' THEN 1 END) as easy_questions,
                COUNT(CASE WHEN difficulty = 'Medium' THEN 1 END) as medium_questions,
                COUNT(CASE WHEN difficulty = 'Hard' THEN 1 END) as hard_questions,
                COUNT(CASE WHEN type = 'MCQ' THEN 1 END) as mcq_questions,
                COUNT(CASE WHEN type = 'Short Answer' THEN 1 END) as short_answer_questions,
                COUNT(CASE WHEN type = 'Long Answer' THEN 1 END) as long_answer_questions,
                COUNT(CASE WHEN category = 'generated' THEN 1 END) as generated_questions,
                COUNT(CASE WHEN category = 'in_chapter' THEN 1 END) as in_chapter_questions,
                COUNT(CASE WHEN category = 'exercise' THEN 1 END) as exercise_questions
            FROM questions 
            WHERE board = :board AND class_level = :class_level AND subject = :subject
        """)
        
        stats = db.execute(stats_query, {
            "board": actual_board,
            "class_level": actual_class,
            "subject": actual_subject
        }).fetchone()
        
        # Get available chapters
        chapters_query = text("""
            SELECT DISTINCT chapter 
            FROM questions 
            WHERE board = :board AND class_level = :class_level AND subject = :subject
            ORDER BY chapter
        """)
        
        chapters = db.execute(chapters_query, {
            "board": actual_board,
            "class_level": actual_class,
            "subject": actual_subject
        }).fetchall()
        
        # Get available topics
        topics_query = text("""
            SELECT DISTINCT topic 
            FROM questions 
            WHERE board = :board AND class_level = :class_level AND subject = :subject
            AND topic IS NOT NULL
            ORDER BY topic
        """)
        
        topics = db.execute(topics_query, {
            "board": actual_board,
            "class_level": actual_class,
            "subject": actual_subject
        }).fetchall()
        
        return {
            "subject_info": {
                "board": actual_board,
                "class_level": actual_class,
                "subject": actual_subject
            },
            "total_questions": stats.total_questions if stats else 0,
            "total_chapters": stats.total_chapters if stats else 0,
            "difficulty_breakdown": {
                "easy": stats.easy_questions if stats else 0,
                "medium": stats.medium_questions if stats else 0,
                "hard": stats.hard_questions if stats else 0
            },
            "type_breakdown": {
                "mcq": stats.mcq_questions if stats else 0,
                "short_answer": stats.short_answer_questions if stats else 0,
                "long_answer": stats.long_answer_questions if stats else 0
            },
            "category_breakdown": {
                "generated": stats.generated_questions if stats else 0,
                "in_chapter": stats.in_chapter_questions if stats else 0,
                "exercise": stats.exercise_questions if stats else 0
            },
            "available_chapters": [ch.chapter for ch in chapters] if chapters else [],
            "available_topics": [t.topic for t in topics] if topics else []
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting question stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting question stats: {str(e)}"
        )

@router.get("/{board}/{class_level}/{subject}/chapters")
async def get_available_chapters(
    board: str,
    class_level: str,
    subject: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of chapters that have questions available"""
    try:
        check_teacher_permission(current_user)
        
        # Map to actual board/class/subject
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board, class_level, subject
        )
        
        # Get chapters with question counts
        chapters_query = text("""
            SELECT 
                chapter,
                COUNT(*) as question_count,
                COUNT(CASE WHEN difficulty = 'Easy' THEN 1 END) as easy_count,
                COUNT(CASE WHEN difficulty = 'Medium' THEN 1 END) as medium_count,
                COUNT(CASE WHEN difficulty = 'Hard' THEN 1 END) as hard_count
            FROM questions 
            WHERE board = :board AND class_level = :class_level AND subject = :subject
            GROUP BY chapter
            ORDER BY chapter
        """)
        
        chapters = db.execute(chapters_query, {
            "board": actual_board,
            "class_level": actual_class,
            "subject": actual_subject
        }).fetchall()
        
        return {
            "chapters": [
                {
                    "chapter_number": ch.chapter,
                    "total_questions": ch.question_count,
                    "difficulty_breakdown": {
                        "easy": ch.easy_count,
                        "medium": ch.medium_count,
                        "hard": ch.hard_count
                    }
                }
                for ch in chapters
            ]
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting available chapters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting available chapters: {str(e)}"
        )