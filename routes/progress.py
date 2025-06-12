# backend/routes/progress.py - COMPLETE FILE with new analytics endpoints
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, desc, text, or_
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user
from config.subjects import SUBJECT_CONFIG, SubjectType
from models import User, UserAttempt, Question, ChapterDefinition
from typing import Dict, List, Any
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

# ✅ NEW ENDPOINT: Fast performance summary
@router.get("/user/performance-summary/{board}/{class_level}/{subject}/{chapter}")
async def get_performance_summary(
    board: str,
    class_level: str, 
    subject: str,
    chapter: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    OPTIMIZED: Get performance summary only (fast call)
    Returns aggregate statistics without detailed question data
    """
    try:
        logger.info(f"Fetching performance summary for {board}/{class_level}/{subject}/chapter-{chapter}")
        
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

        # Single optimized query for performance metrics only
        summary_query = text("""
            SELECT 
                COUNT(ua.id) as total_attempts,
                COALESCE(AVG(ua.score), 0) as average_score,
                COALESCE(SUM(ua.time_taken), 0) as total_time,
                COUNT(DISTINCT ua.question_id) as unique_questions,
                COUNT(CASE WHEN ua.score >= 8 THEN 1 END) as excellent_attempts,
                COUNT(CASE WHEN ua.score >= 6 AND ua.score < 8 THEN 1 END) as good_attempts,
                COUNT(CASE WHEN ua.score < 6 THEN 1 END) as needs_improvement_attempts,
                MAX(ua.created_at) as last_attempt_date,
                MIN(ua.created_at) as first_attempt_date
            FROM user_attempts ua
            WHERE ua.user_id = :user_id 
            AND ua.board = :board 
            AND ua.class_level = :class_level 
            AND ua.subject = :subject 
            AND ua.chapter = :chapter
        """)
        
        result = db.execute(summary_query, {
            "user_id": current_user['id'],
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": base_chapter
        }).fetchone()
        
        if not result or result.total_attempts == 0:
            return {
                "total_attempts": 0,
                "average_score": 0.0,
                "total_time": 0,
                "unique_questions": 0,
                "performance_breakdown": {
                    "excellent": 0,  # 8-10
                    "good": 0,       # 6-7.9
                    "needs_improvement": 0  # 0-5.9
                },
                "date_range": {
                    "first_attempt": None,
                    "last_attempt": None
                },
                "chapter_info": {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject,
                    "chapter": chapter
                }
            }
        
        # Return optimized summary response
        return {
            "total_attempts": result.total_attempts,
            "average_score": round(float(result.average_score), 2),
            "total_time": result.total_time or 0,
            "unique_questions": result.unique_questions,
            "performance_breakdown": {
                "excellent": result.excellent_attempts or 0,
                "good": result.good_attempts or 0,
                "needs_improvement": result.needs_improvement_attempts or 0
            },
            "date_range": {
                "first_attempt": result.first_attempt_date.isoformat() if result.first_attempt_date else None,
                "last_attempt": result.last_attempt_date.isoformat() if result.last_attempt_date else None
            },
            "chapter_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching performance summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching performance summary: {str(e)}")

# ✅ NEW ENDPOINT: Lightweight analytics data
@router.get("/user/performance-analytics/{board}/{class_level}/{subject}/{chapter}")
async def get_performance_analytics(
    board: str,
    class_level: str,
    subject: str,
    chapter: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    OPTIMIZED: Get lightweight analytics data for charts
    Returns only essential data needed for performance visualizations
    """
    try:
        logger.info(f"Fetching performance analytics for {board}/{class_level}/{subject}/chapter-{chapter}")
        
        # Map to source board/class/subject for shared subjects
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        # Clean and normalize input
        try:
            base_chapter = int(chapter)
        except ValueError:
            base_chapter = int(chapter.replace('chapter-', ''))

        # Lightweight query for analytics data only
        analytics_query = text("""
            SELECT 
                ua.score,
                ua.time_taken,
                ua.created_at,
                q.difficulty,
                q.type,
                q.bloom_level,
                q.human_readable_id,
                -- Extract category from human_readable_id
                CASE 
                    WHEN q.human_readable_id ~ '_g\d+$' THEN 'Generated'
                    WHEN q.human_readable_id ~ '_ic\d+$' THEN 'In-Chapter' 
                    WHEN q.human_readable_id ~ '_ec\d+$' THEN 'Exercise'
                    ELSE 'Unknown'
                END as question_category
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = :user_id 
            AND ua.board = :board 
            AND ua.class_level = :class_level 
            AND ua.subject = :subject 
            AND ua.chapter = :chapter
            ORDER BY ua.created_at ASC
        """)
        
        results = db.execute(analytics_query, {
            "user_id": current_user['id'],
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": base_chapter
        }).fetchall()
        
        if not results:
            return {
                "analytics_data": [],
                "score_trends": [],
                "category_performance": {},
                "difficulty_breakdown": {},
                "time_performance": [],
                "chapter_info": {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject,
                    "chapter": chapter
                }
            }
        
        # Process results for different chart types
        analytics_data = []
        score_trends = []
        category_performance = {}
        difficulty_breakdown = {}
        time_performance = []
        
        for i, row in enumerate(results):
            # Basic analytics data point
            data_point = {
                "attempt_number": i + 1,
                "score": row.score,
                "time_taken": row.time_taken or 0,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "difficulty": row.difficulty or "Unknown",
                "type": row.type or "Unknown",
                "bloom_level": row.bloom_level or "Unknown",
                "category": row.question_category
            }
            analytics_data.append(data_point)
            
            # Score trends over time
            score_trends.append({
                "attempt": i + 1,
                "score": row.score,
                "date": row.created_at.date().isoformat() if row.created_at else None
            })
            
            # Category performance aggregation
            category = row.question_category
            if category not in category_performance:
                category_performance[category] = {
                    "total_attempts": 0,
                    "total_score": 0,
                    "average_score": 0,
                    "best_score": 0,
                    "attempts": []
                }
            
            category_performance[category]["total_attempts"] += 1
            category_performance[category]["total_score"] += row.score
            category_performance[category]["best_score"] = max(
                category_performance[category]["best_score"], 
                row.score
            )
            category_performance[category]["attempts"].append(row.score)
            
            # Difficulty breakdown
            difficulty = row.difficulty or "Unknown"
            if difficulty not in difficulty_breakdown:
                difficulty_breakdown[difficulty] = {
                    "count": 0,
                    "total_score": 0,
                    "average_score": 0
                }
            
            difficulty_breakdown[difficulty]["count"] += 1
            difficulty_breakdown[difficulty]["total_score"] += row.score
            
            # Time vs performance
            if row.time_taken:
                time_performance.append({
                    "time_taken": row.time_taken,
                    "score": row.score,
                    "category": category
                })
        
        # Calculate averages for categories
        for category in category_performance:
            if category_performance[category]["total_attempts"] > 0:
                category_performance[category]["average_score"] = round(
                    category_performance[category]["total_score"] / 
                    category_performance[category]["total_attempts"], 
                    2
                )
        
        # Calculate averages for difficulty
        for difficulty in difficulty_breakdown:
            if difficulty_breakdown[difficulty]["count"] > 0:
                difficulty_breakdown[difficulty]["average_score"] = round(
                    difficulty_breakdown[difficulty]["total_score"] / 
                    difficulty_breakdown[difficulty]["count"], 
                    2
                )
        
        return {
            "analytics_data": analytics_data,
            "score_trends": score_trends,
            "category_performance": category_performance,
            "difficulty_breakdown": difficulty_breakdown,
            "time_performance": time_performance,
            "chapter_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching performance analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching performance analytics: {str(e)}")

# ✅ NEW ENDPOINT: Paginated solved questions
@router.get("/user/solved-questions/{board}/{class_level}/{subject}/{chapter}")
async def get_solved_questions(
    board: str,
    class_level: str,
    subject: str, 
    chapter: str,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    OPTIMIZED: Get detailed question attempts (potentially slower call)
    Returns full question details with pagination
    """
    try:
        logger.info(f"Fetching solved questions for {board}/{class_level}/{subject}/chapter-{chapter}")
        
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

        # Get detailed attempts with pagination
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
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        # Get total count for pagination
        total_count = (
            db.query(UserAttempt)
            .join(Question, UserAttempt.question_id == Question.id)
            .filter(
                UserAttempt.user_id == current_user['id'],
                Question.board == mapped_board,
                Question.class_level == mapped_class,
                Question.subject == mapped_subject,
                UserAttempt.chapter == base_chapter
            )
            .count()
        )
        
        # Format attempts data
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
            "attempts": formatted_attempts,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count,
                "next_offset": (offset + limit) if (offset + limit) < total_count else None
            },
            "chapter_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching solved questions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching solved questions: {str(e)}")

# ✅ ENHANCED: Performance summary + analytics in one call (alternative option)
@router.get("/user/performance-summary-enhanced/{board}/{class_level}/{subject}/{chapter}")
async def get_enhanced_performance_summary(
    board: str,
    class_level: str, 
    subject: str,
    chapter: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ENHANCED: Performance summary + lightweight analytics data in one call
    Combines summary stats with chart-ready data
    """
    try:
        # Get basic summary
        summary = await get_performance_summary(board, class_level, subject, chapter, current_user, db)
        
        # Get analytics data
        analytics = await get_performance_analytics(board, class_level, subject, chapter, current_user, db)
        
        # Combine both responses
        enhanced_summary = {
            **summary,  # All original summary data
            "analytics": {
                "score_trends": analytics["score_trends"],
                "category_performance": analytics["category_performance"], 
                "difficulty_breakdown": analytics["difficulty_breakdown"],
                "time_performance": analytics["time_performance"][:20],  # Limit for charts
            },
            "chart_ready": True
        }
        
        return enhanced_summary
        
    except Exception as e:
        logger.error(f"Error fetching enhanced performance summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching enhanced performance summary: {str(e)}")

# ✅ UPDATED: Original detailed report endpoint (backward compatible)
@router.get("/user/detailed-report/{board}/{class_level}/{subject}/{chapter}")
async def get_detailed_chapter_report(
    board: str,
    class_level: str,
    subject: str,
    chapter: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    LEGACY ENDPOINT: Maintain backward compatibility
    Combines both summary and questions for existing clients
    """
    try:
        logger.info(f"Generating legacy report for {board}/{class_level}/{subject}/chapter-{chapter}")
        
        # Get summary
        summary_response = await get_performance_summary(
            board, class_level, subject, chapter, current_user, db
        )
        
        # Get questions (first 50 for legacy compatibility)
        questions_response = await get_solved_questions(
            board, class_level, subject, chapter, 50, 0, current_user, db
        )
        
        # Return in original format for backward compatibility
        return {
            "total_attempts": summary_response["total_attempts"],
            "average_score": summary_response["average_score"],
            "total_time": summary_response["total_time"],
            "attempts": questions_response["attempts"],
            "performance_breakdown": summary_response.get("performance_breakdown"),
            "unique_questions": summary_response.get("unique_questions")
        }
        
    except Exception as e:
        logger.error(f"Error generating detailed report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating detailed report: {str(e)}"
        )

# ✅ FIXED: Section performance summary endpoint
@router.get("/user/performance-summary/{board}/{class_level}/{subject}/{chapter}/section/{section}")
async def get_section_performance_summary(
    board: str, 
    class_level: str, 
    subject: str, 
    chapter: str,
    section: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance summary for a section"""
    try:
        logger.info(f"Fetching section performance summary for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects (using existing function)
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        logger.info(f"Mapped to {mapped_board}/{mapped_class}/{mapped_subject}")
        
        # Clean and normalize input (consistent with other endpoints)
        try:
            base_chapter = int(chapter)
        except ValueError:
            base_chapter = int(chapter.replace('chapter-', ''))
        
        # Section-specific query using optimized approach like other endpoints
        section_query = text("""
            SELECT 
                COUNT(ua.id) as total_attempts,
                COALESCE(AVG(ua.score), 0) as average_score,
                COALESCE(SUM(ua.time_taken), 0) as total_time,
                COUNT(DISTINCT ua.question_id) as unique_questions,
                COUNT(CASE WHEN ua.score >= 8 THEN 1 END) as excellent_attempts,
                COUNT(CASE WHEN ua.score >= 6 AND ua.score < 8 THEN 1 END) as good_attempts,
                COUNT(CASE WHEN ua.score < 6 THEN 1 END) as needs_improvement_attempts,
                MAX(ua.created_at) as last_attempt_date,
                MIN(ua.created_at) as first_attempt_date
            FROM user_attempts ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = :user_id 
            AND ua.board = :board 
            AND ua.class_level = :class_level 
            AND ua.subject = :subject 
            AND ua.chapter = :chapter
            AND (q.section_id LIKE :section_pattern OR q.human_readable_id LIKE :section_pattern)
        """)
        
        # Create section pattern for filtering
        section_pattern = f"%section_{base_chapter}_{section}%"
        
        result = db.execute(section_query, {
            "user_id": current_user['id'],
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": base_chapter,
            "section_pattern": section_pattern
        }).fetchone()
        
        if not result or result.total_attempts == 0:
            return {
                "total_attempts": 0,
                "average_score": 0.0,
                "total_time": 0,
                "unique_questions": 0,
                "performance_breakdown": {
                    "excellent": 0,
                    "good": 0,
                    "needs_improvement": 0
                },
                "date_range": {
                    "first_attempt": None,
                    "last_attempt": None
                },
                "section_info": {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject,
                    "chapter": chapter,
                    "section": section
                }
            }
        
        return {
            "total_attempts": result.total_attempts,
            "average_score": round(float(result.average_score), 2),
            "total_time": result.total_time or 0,
            "unique_questions": result.unique_questions,
            "performance_breakdown": {
                "excellent": result.excellent_attempts or 0,
                "good": result.good_attempts or 0,
                "needs_improvement": result.needs_improvement_attempts or 0
            },
            "date_range": {
                "first_attempt": result.first_attempt_date.isoformat() if result.first_attempt_date else None,
                "last_attempt": result.last_attempt_date.isoformat() if result.last_attempt_date else None
            },
            "section_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter,
                "section": section
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting section performance summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section performance summary: {str(e)}"
        )

# ✅ FIXED: Section performance analytics endpoint
@router.get("/user/performance-analytics/{board}/{class_level}/{subject}/{chapter}/section/{section}")
async def get_section_performance_analytics(
    board: str, 
    class_level: str, 
    subject: str, 
    chapter: str,
    section: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance analytics data for section charts"""
    try:
        logger.info(f"Fetching section performance analytics for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects (using existing function)
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        # Clean and normalize input (consistent with other endpoints)
        try:
            base_chapter = int(chapter)
        except ValueError:
            base_chapter = int(chapter.replace('chapter-', ''))
        
        # Section-specific analytics query (similar to main analytics endpoint)
        section_pattern = f"%section_{base_chapter}_{section}%"
        
        analytics_query = text("""
            SELECT 
                ua.score,
                ua.time_taken,
                ua.created_at,
                q.difficulty,
                q.type,
                q.bloom_level,
                q.human_readable_id,
                -- Extract category from human_readable_id
                CASE 
                    WHEN q.human_readable_id ~ '_g\d+$' THEN 'Generated'
                    WHEN q.human_readable_id ~ '_ic\d+$' THEN 'In-Chapter' 
                    WHEN q.human_readable_id ~ '_ec\d+$' THEN 'Exercise'
                    WHEN q.human_readable_id LIKE :section_pattern THEN 'Section'
                    ELSE 'Unknown'
                END as question_category
            FROM user_attempts ua
            LEFT JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = :user_id 
            AND ua.board = :board 
            AND ua.class_level = :class_level 
            AND ua.subject = :subject 
            AND ua.chapter = :chapter
            AND (q.section_id LIKE :section_pattern OR q.human_readable_id LIKE :section_pattern)
            ORDER BY ua.created_at ASC
        """)
        
        results = db.execute(analytics_query, {
            "user_id": current_user['id'],
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": base_chapter,
            "section_pattern": section_pattern
        }).fetchall()
        
        if not results:
            return {
                "analytics_data": [],
                "score_trends": [],
                "category_performance": {},
                "difficulty_breakdown": {},
                "time_performance": [],
                "section_info": {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject,
                    "chapter": chapter,
                    "section": section
                }
            }
        
        # Process results for different chart types (same logic as main analytics)
        analytics_data = []
        score_trends = []
        category_performance = {}
        difficulty_breakdown = {}
        time_performance = []
        
        for i, row in enumerate(results):
            # Basic analytics data point
            data_point = {
                "attempt_number": i + 1,
                "score": row.score,
                "time_taken": row.time_taken or 0,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "difficulty": row.difficulty or "Unknown",
                "type": row.type or "Unknown",
                "bloom_level": row.bloom_level or "Unknown",
                "category": row.question_category
            }
            analytics_data.append(data_point)
            
            # Score trends over time
            score_trends.append({
                "attempt": i + 1,
                "score": row.score,
                "date": row.created_at.date().isoformat() if row.created_at else None
            })
            
            # Category performance aggregation
            category = row.question_category
            if category not in category_performance:
                category_performance[category] = {
                    "total_attempts": 0,
                    "total_score": 0,
                    "average_score": 0,
                    "best_score": 0,
                    "attempts": []
                }
            
            category_performance[category]["total_attempts"] += 1
            category_performance[category]["total_score"] += row.score
            category_performance[category]["best_score"] = max(
                category_performance[category]["best_score"], 
                row.score
            )
            category_performance[category]["attempts"].append(row.score)
            
            # Difficulty breakdown
            difficulty = row.difficulty or "Unknown"
            if difficulty not in difficulty_breakdown:
                difficulty_breakdown[difficulty] = {
                    "count": 0,
                    "total_score": 0,
                    "average_score": 0
                }
            
            difficulty_breakdown[difficulty]["count"] += 1
            difficulty_breakdown[difficulty]["total_score"] += row.score
            
            # Time vs performance
            if row.time_taken:
                time_performance.append({
                    "time_taken": row.time_taken,
                    "score": row.score,
                    "category": category
                })
        
        # Calculate averages for categories
        for category in category_performance:
            if category_performance[category]["total_attempts"] > 0:
                category_performance[category]["average_score"] = round(
                    category_performance[category]["total_score"] / 
                    category_performance[category]["total_attempts"], 
                    2
                )
        
        # Calculate averages for difficulty
        for difficulty in difficulty_breakdown:
            if difficulty_breakdown[difficulty]["count"] > 0:
                difficulty_breakdown[difficulty]["average_score"] = round(
                    difficulty_breakdown[difficulty]["total_score"] / 
                    difficulty_breakdown[difficulty]["count"], 
                    2
                )
        
        return {
            "analytics_data": analytics_data,
            "score_trends": score_trends,
            "category_performance": category_performance,
            "difficulty_breakdown": difficulty_breakdown,
            "time_performance": time_performance,
            "section_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter,
                "section": section
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting section performance analytics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section performance analytics: {str(e)}"
        )

# ✅ FIXED: Section solved questions endpoint
@router.get("/user/solved-questions/{board}/{class_level}/{subject}/{chapter}/section/{section}")
async def get_section_solved_questions(
    board: str, 
    class_level: str, 
    subject: str, 
    chapter: str,
    section: str,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed solved questions for a section"""
    try:
        logger.info(f"Fetching section solved questions for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects (using existing function)
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        logger.info(f"Mapped to {mapped_board}/{mapped_class}/{mapped_subject}")
        
        # Clean and normalize input (consistent with other endpoints)
        try:
            base_chapter = int(chapter)
        except ValueError:
            base_chapter = int(chapter.replace('chapter-', ''))
        
        # Create section pattern for filtering
        section_pattern = f"%section_{base_chapter}_{section}%"
        
        # Get detailed attempts with pagination (similar to main solved questions endpoint)
        attempts_query = (
            db.query(UserAttempt)
            .join(Question, UserAttempt.question_id == Question.id)
            .filter(
                UserAttempt.user_id == current_user['id'],
                Question.board == mapped_board,
                Question.class_level == mapped_class,
                Question.subject == mapped_subject,
                UserAttempt.chapter == base_chapter,
                or_(
                    Question.section_id.like(section_pattern),
                    Question.human_readable_id.like(section_pattern)
                )
            )
            .order_by(desc(UserAttempt.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        # Get total count for pagination
        total_count = (
            db.query(UserAttempt)
            .join(Question, UserAttempt.question_id == Question.id)
            .filter(
                UserAttempt.user_id == current_user['id'],
                Question.board == mapped_board,
                Question.class_level == mapped_class,
                Question.subject == mapped_subject,
                UserAttempt.chapter == base_chapter,
                or_(
                    Question.section_id.like(section_pattern),
                    Question.human_readable_id.like(section_pattern)
                )
            )
            .count()
        )
        
        # Format attempts data (same logic as main solved questions endpoint)
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
                question_number = f"S{section}.Q{len(formatted_attempts) + 1}"
                source = f"Section {section}"
                
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
                        source = category_mapping.get(category_code, f'Section {section}')
                        question_number = f"S{section}.{category_code.upper()}{number.zfill(3)}"

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
                        "section": section,
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
            "attempts": formatted_attempts,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count,
                "next_offset": (offset + limit) if (offset + limit) < total_count else None
            },
            "section_info": {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter,
                "section": section
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting section solved questions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section solved questions: {str(e)}"
        )

# Add this endpoint to your progress.py file (append to the existing content)

@router.get("/user/sections/{board}/{class_level}/{subject}/{chapter}")
async def get_user_sections_progress(
    board: str,
    class_level: str,
    subject: str,
    chapter: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user progress data per section for a specific chapter"""
    try:
        logger.info(f"Fetching sections progress for user {current_user['id']}: {board}/{class_level}/{subject}/chapter-{chapter}")
        
        # Map to source board/class/subject for shared subjects
        mapped_board, mapped_class, mapped_subject = get_mapped_subject_info(
            board.lower(), 
            class_level.lower(), 
            subject.lower()
        )
        
        logger.info(f"Mapped to: {mapped_board}/{mapped_class}/{mapped_subject}")
        
        clean_chapter = chapter.replace('chapter-', '')
        chapter_int = int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        
        # ================================
        # STEP 1: GET SECTIONS INFO
        # ================================
        sections_info = []
        
        # Try JSON file first (similar to main.py sections endpoint)
        try:
            import os
            import json
            
            formatted_subject = subject.lower()
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Go up from routes/ to root
            file_path = os.path.join(
                base_path,
                "questions",
                board.lower(),
                class_level.lower(),
                formatted_subject,
                f"chapter-{chapter}",
                "sections.json"
            )
            
            logger.info(f"Looking for sections JSON at: {file_path}")
            
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    sections_data = json.load(f)
                    sections_info = sections_data.get("sections", [])
                    logger.info(f"Loaded {len(sections_info)} sections from JSON")
            else:
                # Try alternative path with underscores
                alternative_subject = subject.lower().replace('-', '_')
                alternative_path = os.path.join(
                    base_path,
                    "questions",
                    board.lower(),
                    class_level.lower(),
                    alternative_subject,
                    f"chapter-{chapter}",
                    "sections.json"
                )
                
                if os.path.exists(alternative_path):
                    with open(alternative_path, 'r') as f:
                        sections_data = json.load(f)
                        sections_info = sections_data.get("sections", [])
                        logger.info(f"Loaded {len(sections_info)} sections from alternative JSON")
                        
        except Exception as json_error:
            logger.warning(f"Error reading sections JSON: {str(json_error)}")
        
        # Fallback to database if JSON not found
        if not sections_info:
            try:
                sections_query = text("""
                    SELECT section_number, section_name 
                    FROM sections 
                    WHERE board = :board 
                      AND class_level = :class_level 
                      AND subject = :subject 
                      AND chapter = :chapter 
                      AND is_active = true
                    ORDER BY section_number
                """)
                
                result = db.execute(sections_query, {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject,
                    "chapter": chapter_int
                }).fetchall()
                
                if result:
                    sections_info = [
                        {"number": row.section_number, "name": row.section_name}
                        for row in result
                    ]
                    logger.info(f"Loaded {len(sections_info)} sections from database")
                    
            except Exception as db_error:
                logger.warning(f"Error querying sections from database: {str(db_error)}")
        
        # Default sections if none found
        if not sections_info:
            sections_info = [
                {"number": 1, "name": "Section 1"},
                {"number": 2, "name": "Section 2"},
                {"number": 3, "name": "Section 3"}
            ]
            logger.info("Using default sections")
        
        # ================================
        # STEP 2: GET PROGRESS PER SECTION
        # ================================
        sections_progress = {}
        
        for section_info in sections_info:
            section_number = section_info["number"]
            section_name = section_info["name"]
            
            # Create section pattern for filtering questions
            # Use chapter % 100 for section pattern (as seen in main.py)
            chapter_for_section = chapter_int % 100 if isinstance(chapter_int, int) else chapter_int
            section_pattern = f"%section_{chapter_for_section}_{section_number}%"
            
            # Query user attempts for this section
            section_attempts_query = text("""
                SELECT 
                    COUNT(ua.id) as attempted,
                    AVG(ua.score) as average_score
                FROM user_attempts ua
                JOIN questions q ON ua.question_id = q.id
                WHERE ua.user_id = :user_id 
                AND ua.board = :board 
                AND ua.class_level = :class_level 
                AND ua.subject = :subject 
                AND ua.chapter = :chapter
                AND q.section_id LIKE :section_pattern
            """)
            
            section_result = db.execute(section_attempts_query, {
                "user_id": current_user['id'],
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter_int,
                "section_pattern": section_pattern
            }).fetchone()
            
            # Query total questions available for this section
            total_questions_query = text("""
                SELECT COUNT(q.id) as total_questions
                FROM questions q
                WHERE q.board = :board 
                AND q.class_level = :class_level 
                AND q.subject = :subject 
                AND q.chapter = :chapter
                AND q.section_id LIKE :section_pattern
            """)
            
            total_result = db.execute(total_questions_query, {
                "board": mapped_board,
                "class_level": mapped_class,
                "subject": mapped_subject,
                "chapter": chapter_int,
                "section_pattern": section_pattern
            }).fetchone()
            
            # Calculate progress for this section
            attempted = section_result.attempted or 0
            total_questions = total_result.total_questions or 0
            average_score = float(section_result.average_score or 0)
            
            sections_progress[str(section_number)] = {
                "section_name": section_name,
                "attempted": attempted,
                "total": max(total_questions, attempted),  # If we have attempts but no questions found, show at least the attempts
                "averageScore": round(average_score, 2)
            }
            
            logger.info(f"Section {section_number}: {attempted}/{total_questions} questions, avg score: {average_score:.2f}")
        
        # ================================
        # STEP 3: GET OVERALL CHAPTER PROGRESS
        # ================================
        # Also include overall chapter progress for context
        chapter_attempts_query = text("""
            SELECT 
                COUNT(ua.id) as attempted,
                AVG(ua.score) as average_score
            FROM user_attempts ua
            WHERE ua.user_id = :user_id 
            AND ua.board = :board 
            AND ua.class_level = :class_level 
            AND ua.subject = :subject 
            AND ua.chapter = :chapter
        """)
        
        chapter_result = db.execute(chapter_attempts_query, {
            "user_id": current_user['id'],
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": chapter_int
        }).fetchone()
        
        # Query total questions for entire chapter
        total_chapter_questions_query = text("""
            SELECT COUNT(q.id) as total_questions
            FROM questions q
            WHERE q.board = :board 
            AND q.class_level = :class_level 
            AND q.subject = :subject 
            AND q.chapter = :chapter
        """)
        
        total_chapter_result = db.execute(total_chapter_questions_query, {
            "board": mapped_board,
            "class_level": mapped_class,
            "subject": mapped_subject,
            "chapter": chapter_int
        }).fetchone()
        
        chapter_attempted = chapter_result.attempted or 0
        chapter_total = total_chapter_result.total_questions or 0
        chapter_average_score = float(chapter_result.average_score or 0)
        
        return {
            "sections_progress": sections_progress,
            "chapter_summary": {
                "attempted": chapter_attempted,
                "total": max(chapter_total, chapter_attempted),
                "averageScore": round(chapter_average_score, 2)
            },
            "chapter_info": {
                "board": board,
                "class_level": class_level,
                "subject": subject,
                "chapter": chapter,
                "mapped_to": {
                    "board": mapped_board,
                    "class_level": mapped_class,
                    "subject": mapped_subject
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching sections progress: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching sections progress: {str(e)}"
        )