# Create this new file: app/utils/questions.py

from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import Question
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

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


def get_section_questions_count_helper(
    db: Session,
    board: str, 
    class_level: str, 
    subject: str, 
    chapter: str, 
    section: str
) -> int:
    """
    Helper function to get total number of questions available in a specific section
    This function is designed to be called from other Python modules
    
    Args:
        db: Database session (passed directly, not via FastAPI Depends)
        board: Board code (e.g., 'cbse')
        class_level: Class level (e.g., 'xi')
        subject: Subject code (e.g., 'kebo1dd')
        chapter: Chapter number as string (e.g., 'chapter-1', '1')
        section: Section number as string (e.g., '1', '2', '3')
    
    Returns:
        int: Total number of questions in the section
    """
    try:
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        clean_board = actual_board
        clean_class = actual_class
        clean_subject = actual_subject.replace('-', '_')
        clean_chapter = chapter.replace('chapter-', '')
        clean_section = section
        
        # Create section pattern (same logic as main.py section endpoints)
        try:
            chapter_int = int(clean_chapter)
            section_int = int(clean_section)
            
            # Use chapter % 100 for section pattern as in main.py
            chapter_for_section = chapter_int % 100
            
            # Filter by chapter number (like existing chapter endpoints)
            chapter_conditions = [
                Question.chapter == chapter_int,
                Question.chapter == (100 + chapter_int)  # Handle both formats
            ]
            
            # Create section pattern for section_id column filtering
            section_pattern = f"%section_{chapter_for_section}_{section_int}%"
        except ValueError:
            chapter_conditions = [
                Question.chapter == clean_chapter
            ]
            section_pattern = f"%section_{clean_chapter}_{clean_section}%"
        
        logger.info(f"Counting section questions with pattern: {section_pattern}")
        
        # Query for section questions using both chapter and section_id filters
        # (Same query logic as main.py get_random_section_question)
        query = db.query(Question).filter(
            Question.board == clean_board,
            Question.class_level == clean_class,
            Question.subject == clean_subject,
            or_(*chapter_conditions),
            Question.section_id.like(section_pattern)
        )
        
        count = query.count()
        logger.info(f"Found {count} questions for section {section} in chapter {chapter}")
        
        # If no questions found, try fallback searches
        if count == 0:
            # Fallback: try without board/class restrictions
            fallback_query = db.query(Question).filter(
                Question.subject == clean_subject,
                or_(*chapter_conditions),
                Question.section_id.like(section_pattern)
            )
            
            fallback_count = fallback_query.count()
            logger.info(f"Fallback query found {fallback_count} questions")
            
            if fallback_count > 0:
                return fallback_count
            
            # Final fallback - return reasonable default
            logger.info("No questions found, using default count of 10")
            return 10
        
        return count
        
    except Exception as e:
        logger.error(f"Error getting section questions count: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        # Return reasonable default on error
        return 10