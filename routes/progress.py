# backend/routes/progress.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user
from config.subjects import SUBJECT_CONFIG, SubjectType
from models import User, UserAttempt, Question, ChapterDefinition
from typing import Dict
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["progress"])
def get_mapped_subject_info(board: str, class_level: str, subject: str) -> tuple[str, str, str]:
    """Get actual board/class/subject to use for shared subjects"""
    try:
        print(f"Original subject mapping request: {board}/{class_level}/{subject}")
        
        board_config = SUBJECT_CONFIG.get(board)
        if not board_config:
            print(f"No mapping found, using original: {board}/{class_level}/{subject}")
            return board, class_level, subject
            
        class_config = board_config.classes.get(class_level)
        if not class_config:
            print(f"No mapping found, using original: {board}/{class_level}/{subject}")
            return board, class_level, subject
        
        # First check if the subject is a direct code match (most efficient path)
        subject_obj = next(
            (s for s in class_config.subjects if s.code.lower() == subject.lower()),
            None
        )
        
        # If not found by code, try to match by display name with various transformations
        if not subject_obj:
            # Try different normalizations of the subject name
            normalized_subject = subject.lower().replace('-', ' ').replace('_', ' ')
            subject_obj = next(
                (s for s in class_config.subjects if 
                 s.name.lower() == normalized_subject or
                 s.name.lower().replace(' ', '-') == subject.lower() or 
                 s.name.lower().replace(' ', '_') == subject.lower()),
                None
            )
        
        if subject_obj:
            print(f"Found subject: {subject} mapped to {subject_obj.code}")
            
            # If this is a shared subject, use its mapping
            if subject_obj.type == SubjectType.SHARED and subject_obj.shared_mapping:
                mapping = subject_obj.shared_mapping
                print(f"Using shared mapping: {mapping.source_board}/{mapping.source_class}/{mapping.source_subject}")
                # Return source mapping, but ALSO include the original subject code as a 4th return value
                # This helps the caller know both the source mapping AND the original code
                return mapping.source_board, mapping.source_class, mapping.source_subject
            
            # Otherwise return the original board/class with the correct subject code
            print(f"No mapping found, using original: {board}/{class_level}/{subject_obj.code}")
            return board, class_level, subject_obj.code
        
        print(f"No mapping found, using original: {board}/{class_level}/{subject}")
        return board, class_level, subject
    except Exception as e:
        logger.error(f"Error in get_mapped_subject_info: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"No mapping found, using original: {board}/{class_level}/{subject}")
        return board, class_level, subject
    

def normalize_chapter_number(chapter: int) -> int:
    """Convert chapter numbers like 101 to 1"""
    if chapter >= 100:
        return chapter % 100
    return chapter
@router.get("/user/{board}/{class_level}")
async def get_user_progress(
    board: str,
    class_level: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        print(f"\n=== Progress Report for {current_user['id']} ===")
        print(f"Board: {board}, Class: {class_level}")

        # First, get all attempts for this user
        attempt_records = db.query(
            UserAttempt.subject,
            UserAttempt.chapter,
            func.count(UserAttempt.id)
        ).filter(
            UserAttempt.user_id == current_user['id']
        ).group_by(
            UserAttempt.subject,
            UserAttempt.chapter
        ).all()
        
        print("\n=== Checking UserAttempt Records ===")
        for record in attempt_records:
            print(f"Found {record[2]} attempts for {record[0]} chapter {record[1]}")

        # Track subjects and their mappings
        subject_mappings = {}
        original_to_source = {}  # Map from original subject code to source subject code
        source_to_original = {}  # Map from source subject code to original subject code
        
        if board in SUBJECT_CONFIG:
            board_config = SUBJECT_CONFIG[board]
            if class_level in board_config.classes:
                for subject in board_config.classes[class_level].subjects:
                    if subject.type == SubjectType.SHARED and subject.shared_mapping:
                        subject_mappings[subject.code] = {
                            'board': subject.shared_mapping.source_board,
                            'class': subject.shared_mapping.source_class,
                            'subject': subject.shared_mapping.source_subject
                        }
                        # Create bidirectional mappings between codes
                        original_to_source[subject.code.lower()] = subject.shared_mapping.source_subject.lower()
                        source_to_original[subject.shared_mapping.source_subject.lower()] = subject.code.lower()

        # Get all subject codes we might need to process
        subject_codes_from_attempts = [record[0] for record in attempt_records]
        subject_codes_from_mappings = list(subject_mappings.keys())
        
        # Get all chapter definitions for this board/class
        chapter_defs = db.query(
            ChapterDefinition.subject_code
        ).filter(
            ChapterDefinition.board == board,
            ChapterDefinition.class_level == class_level
        ).distinct().all()
        
        subject_codes_from_chapters = [row[0] for row in chapter_defs]
        
        # Combine all possible subject codes
        all_subject_codes = set(subject_codes_from_attempts + 
                               subject_codes_from_mappings + 
                               subject_codes_from_chapters)
        
        print(f"All subject codes to process: {all_subject_codes}")

        # Get total questions count for each subject/chapter
        total_questions = []
        processed_subjects = set()
        original_to_mapped = {}  # Track original subject to mapped subject
        
        # Process each subject code to get question counts
        for subject_code in all_subject_codes:
            if subject_code in processed_subjects:
                continue
                
            mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
                board, class_level, subject_code
            )
            
            # Track the mapping for later use
            original_to_mapped[subject_code] = (mapped_board, mapped_class, mapped_subject)
            
            # Get question counts for this subject
            questions = db.query(
                Question.subject,
                Question.chapter,
                func.count(Question.id).label('total_questions')
            ).filter(
                func.lower(Question.board) == mapped_board.lower(),
                func.lower(Question.class_level) == mapped_class.lower(),
                func.lower(Question.subject) == mapped_subject.lower()
            ).group_by(
                Question.subject,
                Question.chapter
            ).all()
            
            # Store results with ORIGINAL subject code for consistent lookup
            modified_questions = []
            for q in questions:
                # Important: when storing questions data, use the ORIGINAL subject code
                # This ensures frontend can look up progress with the same code used in URLs
                modified_questions.append((subject_code, q.chapter, q.total_questions))
            
            total_questions.extend(modified_questions)
            processed_subjects.add(subject_code)
            
        print("\n=== Available Questions Per Chapter ===")
        questions_per_chapter = {}
        for q in total_questions:
            subject_code, chapter, count = q
            normalized_chapter = normalize_chapter_number(chapter) if isinstance(chapter, int) else int(chapter)
            
            # Use original subject code as key
            subject_key = subject_code.lower()
            
            print(f"Subject: {subject_key}, Chapter: {normalized_chapter}, Questions: {count}")
            questions_per_chapter[f"{subject_key}_{normalized_chapter}"] = count

        # Get user attempts and scores
        attempts = db.query(
            UserAttempt.subject,
            UserAttempt.chapter,
            func.count(UserAttempt.id).label('attempted'),
            func.avg(UserAttempt.score).label('average_score')
        ).filter(
            UserAttempt.user_id == current_user['id']
        ).group_by(
            UserAttempt.subject,
            UserAttempt.chapter
        ).all()

        print("\n=== Processing Progress Data ===")
        progress = {}
        
        # Process attempt data - IMPORTANT: Don't skip entries with total=0
        for attempt in attempts:
            # The subject in the attempt could be either original or source code
            attempt_subject_key = attempt.subject.lower()
            normalized_chapter = normalize_chapter_number(attempt.chapter)
            
            # If the subject in the attempt is a source subject (like hemh1dd), 
            # map it back to the original subject code for this board (like mathematics)
            subject_key = source_to_original.get(attempt_subject_key, attempt_subject_key)
            
            # Now also check if it's an original subject that maps to a source
            mapped_subject_key = original_to_source.get(subject_key, subject_key)
            
            # Ensure we have an entry for both the original subject key and source subject key
            for key in [subject_key, mapped_subject_key]:
                if key not in progress:
                    progress[key] = {}
            
            # Try both lookup keys to find total questions
            total = 0
            for lookup_key in [f"{subject_key}_{normalized_chapter}", f"{mapped_subject_key}_{normalized_chapter}"]:
                if lookup_key in questions_per_chapter:
                    total = questions_per_chapter[lookup_key]
                    break
            
            print(f"\nProcessing {subject_key} chapter {normalized_chapter}:")
            print(f"  Total questions in database: {total}")
            print(f"  User attempts in database: {attempt.attempted}")
            
            # Store progress for both original and mapped subjects
            for key in [subject_key, mapped_subject_key]:
                if key == subject_key or key != mapped_subject_key:  # Skip if both are the same
                    progress[key][str(normalized_chapter)] = {
                        "attempted": attempt.attempted,
                        "total": max(total, attempt.attempted),  # If we have attempts but no questions found, show at least the attempts
                        "averageScore": float(attempt.average_score or 0)
                    }

        # Add chapters with no attempts but have questions
        for key, total in questions_per_chapter.items():
            subject, chapter_str = key.split('_')
            
            # Check if we need to map source to original
            subject_to_use = source_to_original.get(subject, subject)
            
            if subject_to_use not in progress:
                progress[subject_to_use] = {}
            if chapter_str not in progress[subject_to_use]:
                progress[subject_to_use][chapter_str] = {
                    "attempted": 0,
                    "total": total,
                    "averageScore": 0
                }
                
            # Also add to source subject if needed
            mapped_subject = original_to_source.get(subject, None)
            if mapped_subject and mapped_subject not in progress:
                progress[mapped_subject] = {}
            if mapped_subject and chapter_str not in progress[mapped_subject]:
                progress[mapped_subject][chapter_str] = {
                    "attempted": 0,
                    "total": total,
                    "averageScore": 0
                }

        return {"progress": progress}
        
    except Exception as e:
        print(f"Error fetching progress: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching progress data: {str(e)}"
        )

@router.get("/user/detailed-report/{board}/{class_level}/{subject}/{chapter}")
async def get_detailed_chapter_report(
    board: str,
    class_level: str,
    subject: str,
    chapter: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed performance report for a specific chapter"""
    try:
        logger.info(f"Generating report for {board}/{class_level}/{subject}/chapter-{chapter}")
        
        # Map to source board/class/subject for shared subjects
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        logger.info(f"Mapped to {mapped_board}/{mapped_class}/{mapped_subject}")
        
        # Clean and normalize input
        try:
            base_chapter = int(chapter)
        except ValueError:
            base_chapter = int(chapter.replace('chapter-', ''))

        # Query attempts with question data
        attempts_query = (
            db.query(UserAttempt)
            .join(Question, UserAttempt.question_id == Question.id)
            .filter(
                UserAttempt.user_id == current_user['id'],
                Question.board == mapped_board,
                Question.class_level == mapped_class,
                Question.subject == mapped_subject,
                UserAttempt.chapter == base_chapter
            )
            .order_by(desc(UserAttempt.created_at))
            .all()
        )

        logger.info(f"Found {len(attempts_query)} attempts")

        if not attempts_query:
            return {
                "total_attempts": 0,
                "average_score": 0.0,
                "total_time": 0,
                "attempts": []
            }

        # Calculate overall statistics
        total_attempts = len(attempts_query)
        average_score = sum(attempt.score for attempt in attempts_query if attempt.score is not None) / total_attempts
        total_time = sum(attempt.time_taken or 0 for attempt in attempts_query)

        # Format attempts
        formatted_attempts = []
        for attempt in attempts_query:
            try:
                # Get the question
                question = db.query(Question).get(attempt.question_id)
                if not question:
                    logger.warning(f"Question {attempt.question_id} not found")
                    continue

                # Get question statistics
                stats = db.query(
                    func.count(UserAttempt.id).label('total_attempts'),
                    func.avg(UserAttempt.score).label('average_score')
                ).filter(
                    UserAttempt.question_id == question.id
                ).first()

                # Parse question metadata
                question_number = "N/A"
                source = "Unknown"
                
                if question.human_readable_id:
                    match = re.search(r'_(g|ic|ec)(\d+)$', question.human_readable_id)
                    if match:
                        category_code = match.group(1)
                        number = match.group(2)
                        category_mapping = {
                            'g': 'Generated',
                            'ic': 'In-Chapter',
                            'ec': 'Exercise'
                        }
                        source = category_mapping.get(category_code, 'Unknown')
                        question_number = f"Q #{number.zfill(3)}"

                formatted_attempt = {
                    "question_id": str(question.id),
                    "question_text": question.question_text,
                    "user_answer": attempt.answer,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation or "",
                    "score": attempt.score,
                    "time_taken": attempt.time_taken or 0,
                    "timestamp": attempt.created_at.isoformat(),
                    "feedback": attempt.feedback or "",
                    "transcribed_text": attempt.transcribed_text or "",
                    "metadata": {
                        "questionNumber": question_number,
                        "source": source,
                        "level": question.difficulty,
                        "type": question.type,
                        "bloomLevel": question.bloom_level or "Not Specified",
                        "statistics": {
                            "totalAttempts": stats.total_attempts,
                            "averageScore": round(float(stats.average_score or 0), 1)
                        }
                    }
                }
                formatted_attempts.append(formatted_attempt)
                
            except Exception as e:
                logger.error(f"Error formatting attempt {attempt.id}: {str(e)}")
                continue

        return {
            "total_attempts": total_attempts,
            "average_score": round(average_score, 1),
            "total_time": total_time,
            "attempts": formatted_attempts
        }

    except ValueError as ve:
        logger.error(f"Invalid input parameters: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input parameters: {str(ve)}"
        )
    except Exception as e:
        logger.error(f"Error generating detailed report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating detailed report: {str(e)}"
        )