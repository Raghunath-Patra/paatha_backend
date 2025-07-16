# Required imports for main.py
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, Dict, Tuple
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
import re
import random
from typing import Dict, Set
from routes import auth, user, progress, subjects  
from middleware.security import SecurityHeadersMiddleware
from config.subjects import SUBJECT_CONFIG, SubjectType
from config.database import engine, Base, get_db
from config.security import get_current_user
from models import User, UserAttempt, Question
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import or_
import uuid
import logging
from services.image_service import image_service
from services.question_service import check_token_limits, check_question_token_limit, update_token_usage, increment_question_usage
from routes import limits
from routes import payments
from routes import subscriptions
from services.subscription_service import subscription_service
from datetime import datetime, timedelta
from routes import chat
from typing import List, Dict, Tuple  
from services.token_service import token_service
from sqlalchemy import text
from routes import promo_code  
from routes import try_routes, teacher_courses, student_courses, teacher_quizzes, question_browser, student_quizzes
from routes import subjects_config
from services.consolidated_user_service import consolidated_service
from routes import image_upload
from routes import video_generation
from services.scheduler_service import scheduler_service
from services.auto_grading_service import auto_grading_service
import atexit


logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# In-memory storage for active questions
active_questions: Dict[str, dict] = {}
VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8001")  # Default to local service
# In main.py, update the CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://paathafrontend.vercel.app",  # Production
        "https://api.paatha.ai",
        "https://www.paatha.ai",
        "http://localhost:3000",  # Local development
        "http://localhost:3000/",  # Local development
        "http://0.0.0.0:3000/",  # Your frontend URL
        "http://0.0.0.0:3000",  # Your frontend URL
        "https://paatha-copy.vercel.app",
        VIDEO_SERVICE_URL

    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Include routers
app.include_router(subjects.router)
app.include_router(auth.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(limits.router, prefix="/api")
app.include_router(subscriptions.router)  # Note: This should be added
app.include_router(chat.router)
app.include_router(limits.router, prefix="/api")
app.include_router(payments.router)
app.include_router(promo_code.router)
app.include_router(try_routes.router)
app.include_router(video_generation.router)

# Teacher functionality routes
# from routes import teacher_courses, student_courses, teacher_quizzes, question_browser, student_quizzes
app.include_router(teacher_courses.router)
app.include_router(student_courses.router)
app.include_router(teacher_quizzes.router)
app.include_router(question_browser.router)
app.include_router(student_quizzes.router)
app.include_router(subjects_config.router)

app.include_router(image_upload.router)

# Add middleware
app.add_middleware(SecurityHeadersMiddleware)


# =====================================================================================
# SCHEDULER STARTUP/SHUTDOWN EVENTS
# =====================================================================================

@app.on_event("startup")
async def startup_event():
    """Start background services on application startup"""
    try:
        # Start the auto-grading scheduler
        if os.getenv("ENABLE_AUTO_GRADING", "true").lower() == "true":
            scheduler_service.start()
            logger.info("✅ Auto-grading scheduler started")
        else:
            logger.info("⚠️ Auto-grading scheduler disabled via environment variable")
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop background services on application shutdown"""
    try:
        scheduler_service.stop()
        logger.info("✅ Background services stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping services: {str(e)}")

# Register cleanup function for process termination
def cleanup_scheduler():
    """Cleanup function for graceful shutdown"""
    try:
        scheduler_service.stop()
    except:
        pass

atexit.register(cleanup_scheduler)

# =====================================================================================
# AUTO-GRADING MONITORING AND CONTROL ENDPOINTS
# =====================================================================================

@app.get("/api/admin/auto-grading/status")
async def get_auto_grading_status(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get auto-grading service status (admin only)"""
    try:
        # Check if user is admin or teacher
        if current_user.get('role') not in ['admin', 'teacher']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and teachers can access auto-grading status"
            )
        
        # Get scheduler status
        scheduler_status = scheduler_service.get_job_status()
        
        # Get pending quizzes count
        pending_quizzes = auto_grading_service.find_quizzes_to_grade(db)
        
        return {
            "scheduler": scheduler_status,
            "pending_quizzes": len(pending_quizzes),
            "quiz_details": [
                {
                    "quiz_id": quiz["quiz_id"],
                    "title": quiz["title"],
                    "course_name": quiz["course_name"],
                    "teacher_name": quiz["teacher_name"],
                    "end_time": quiz["end_time"].isoformat() if quiz["end_time"] else None
                }
                for quiz in pending_quizzes[:10]  # Show first 10
            ],
            "environment": {
                "auto_grading_enabled": os.getenv("ENABLE_AUTO_GRADING", "true"),
                "grading_interval": os.getenv("AUTO_GRADING_INTERVAL_MINUTES", "10")
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting auto-grading status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving auto-grading status: {str(e)}"
        )

@app.post("/api/admin/auto-grading/trigger")
async def trigger_auto_grading_manually(
    current_user: Dict = Depends(get_current_user)
):
    """Manually trigger auto-grading process (admin only)"""
    try:
        # Check if user is admin
        if current_user.get('role') != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can manually trigger auto-grading"
            )
        
        # Trigger auto-grading
        success = scheduler_service.trigger_auto_grading_now()
        
        if success:
            return {
                "message": "Auto-grading process triggered successfully",
                "triggered_at": datetime.utcnow().isoformat(),
                "estimated_start": (datetime.utcnow() + timedelta(seconds=5)).isoformat()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to trigger auto-grading process"
            )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error triggering auto-grading: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error triggering auto-grading: {str(e)}"
        )

@app.get("/api/teacher/my-quizzes/auto-grading-status")
async def get_teacher_quiz_grading_status(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get auto-grading status for teacher's quizzes"""
    try:
        # Check if user is teacher
        if current_user.get('role') != 'teacher':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only teachers can access this endpoint"
            )
        
        # Get teacher's quizzes that are eligible for auto-grading
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                q.id,
                q.title,
                q.end_time,
                q.auto_grade,
                q.auto_graded_at,
                c.course_name,
                COUNT(qa.id) as total_submissions,
                COUNT(CASE WHEN qa.is_auto_graded = true THEN 1 END) as graded_submissions,
                COUNT(CASE WHEN qa.is_auto_graded = false OR qa.is_auto_graded IS NULL THEN 1 END) as pending_submissions
            FROM quizzes q
            JOIN courses c ON q.course_id = c.id
            LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id AND qa.status = 'completed'
            WHERE q.teacher_id = :teacher_id
              AND q.is_published = true
              AND q.auto_grade = true
            GROUP BY q.id, q.title, q.end_time, q.auto_grade, q.auto_graded_at, c.course_name
            ORDER BY q.end_time DESC
            LIMIT 20
        """)
        
        result = db.execute(query, {"teacher_id": current_user['id']}).fetchall()
        
        quizzes = []
        for row in result:
            quiz_ended = row.end_time and row.end_time < get_india_time()
            
            quizzes.append({
                "quiz_id": str(row.id),
                "title": row.title,
                "course_name": row.course_name,
                "end_time": row.end_time.isoformat() if row.end_time else None,
                "quiz_ended": quiz_ended,
                "auto_graded": row.auto_graded_at is not None,
                "auto_graded_at": row.auto_graded_at.isoformat() if row.auto_graded_at else None,
                "submissions": {
                    "total": row.total_submissions or 0,
                    "graded": row.graded_submissions or 0,
                    "pending": row.pending_submissions or 0
                },
                "status": "graded" if row.auto_graded_at else ("pending" if quiz_ended else "active")
            })
        
        return {
            "quizzes": quizzes,
            "summary": {
                "total_quizzes": len(quizzes),
                "graded_quizzes": len([q for q in quizzes if q["auto_graded"]]),
                "pending_quizzes": len([q for q in quizzes if not q["auto_graded"] and q["quiz_ended"]])
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting teacher quiz grading status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving quiz grading status: {str(e)}"
        )

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

# Update the AnswerModel class
class AnswerModel(BaseModel):
    answer: str
    question_id: str
    time_taken: Optional[int] = None
    image_data: Optional[str] = None  # Base64 encoded image

def get_subject_mapping(board: str, class_: str, subject: str) -> Tuple[str, str, str]:
    """Get actual board/class/subject to use, considering shared subjects and handling code/display name variations"""
    try:
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
        # Query for shared subject mapping
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

@app.get("/api/questions/{board}/{class_}/{subject}/{chapter_num}/random")
async def get_random_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter_num: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """OPTIMIZED: Get random question with single status check"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        logger.info(f"Searching for random question with:")
        logger.info(f"Original request: {board}/{class_}/{subject}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
        clean_board = actual_board
        clean_class = actual_class
        clean_subject = actual_subject.replace('-', '_')
        clean_chapter = chapter_num.replace('chapter-', '')
        
        try:
            chapter_int = int(clean_chapter)
            base_chapter = chapter_int
            
            if chapter_int > 100:
                base_chapter = chapter_int % 100
            
            chapter_conditions = [
                Question.chapter == base_chapter,
                Question.chapter == (100 + base_chapter)
            ]
        except ValueError:
            chapter_conditions = [
                Question.chapter == clean_chapter
            ]
        
        # Query for questions
        query = db.query(Question).filter(
            Question.board == clean_board,
            Question.class_level == clean_class,
            Question.subject == clean_subject,
            or_(*chapter_conditions)
        )
        
        count = query.count()
        logger.info(f"Found {count} questions matching exact criteria")
        
        if count > 0:
            question = query.order_by(func.random()).first()
        else:
            # Fallback: try just with subject and chapter
            fallback_query = db.query(Question).filter(
                Question.subject == clean_subject,
                or_(*chapter_conditions)
            )
            
            fallback_count = fallback_query.count()
            logger.info(f"Fallback query found {fallback_count} questions")
            
            if fallback_count > 0:
                question = fallback_query.order_by(func.random()).first()
                logger.info(f"Using fallback question with ID: {question.id}")
            else:
                logger.warning(f"No questions found for {clean_board}/{clean_class}/{clean_subject}/chapter-{clean_chapter}")
                return create_placeholder_question(clean_board, clean_class, clean_subject, clean_chapter)
        
        # Reset per-question token usage when new question is loaded (background task)
        if question:
            reset_query = text("""
                UPDATE user_attempts
                SET input_tokens_used = 0, output_tokens_used = 0
                WHERE user_id = :user_id AND question_id = :question_id
            """)
            try:
                db.execute(reset_query, {"user_id": current_user['id'], "question_id": str(question.id)})
                db.commit()
            except Exception as reset_error:
                logger.error(f"Error resetting question tokens: {str(reset_error)}")
                db.rollback()
        
        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(question, stats, clean_board, clean_class, clean_subject, clean_chapter)
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update (non-blocking)
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=str(question.id),
            input_tokens=50,  # Token cost for fetching question
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved question {question.id} for user {current_user['id']}")
        return question_data
                
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting random question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving question: {str(e)}"
        )


# 3. REPLACE your existing get_specific_question endpoint with this:
@app.get("/api/questions/{board}/{class_}/{subject}/{chapter}/q/{question_id}") 
async def get_specific_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    question_id: str,  # UUID
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """OPTIMIZED: Get specific question with single status check"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        logger.info(f"Fetching specific question:")
        logger.info(f"Original request: {board}/{class_}/{subject}/chapter-{chapter}/q/{question_id}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
        clean_chapter = chapter.replace('chapter-', '')
        
        try:
            chapter_int = int(clean_chapter)
            base_chapter = chapter_int
            
            if chapter_int > 100:
                base_chapter = chapter_int % 100
            
            chapter_conditions = [
                Question.chapter == base_chapter,
                Question.chapter == (100 + base_chapter)
            ]
        except ValueError:
            chapter_conditions = [
                Question.chapter == clean_chapter
            ]

        # Find question by UUID with mapped subject
        question = db.query(Question).filter(
            Question.id == question_id,
            Question.board == actual_board,
            Question.class_level == actual_class,
            Question.subject == actual_subject,
            or_(*chapter_conditions)
        ).first()

        if not question:
            # Fallback searches
            logger.info(f"Question not found with exact criteria, trying fallbacks for {question_id}")
            question = db.query(Question).filter(
                Question.id == question_id,
                Question.subject == actual_subject
            ).first()
            
            if not question:
                question = db.query(Question).filter(
                    Question.id == question_id
                ).first()
                
                if not question:
                    logger.warning(f"Question not found with ID: {question_id}")
                    raise HTTPException(
                        status_code=404, 
                        detail="Question not found"
                    )

        # Reset per-question token usage when question is loaded (background task)
        reset_query = text("""
            UPDATE user_attempts
            SET input_tokens_used = 0, output_tokens_used = 0
            WHERE user_id = :user_id AND question_id = :question_id
        """)
        try:
            db.execute(reset_query, {"user_id": current_user['id'], "question_id": question_id})
            db.commit()
        except Exception as reset_error:
            logger.error(f"Error resetting question tokens: {str(reset_error)}")
            db.rollback()

        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(
            question, 
            stats, 
            actual_board, 
            actual_class, 
            actual_subject, 
            clean_chapter
        )
        
        # Store in active_questions for grading
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update (non-blocking)
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=question_id,
            input_tokens=50,  # Token cost for fetching question
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved specific question {question_id} for user {current_user['id']}")
        return question_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting specific question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving question: {str(e)}"
        )


# 4. REPLACE your existing grade_answer endpoint with this:
@app.post("/api/grade")
async def grade_answer(
    answer: AnswerModel,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """OPTIMIZED: Grade answer with consolidated service and background updates"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can submit answers
        permission_check = consolidated_service.check_can_perform_action(user_status, "submit_answer")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot submit answer: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Check per-question token limits (single additional query)
        question_limits = check_question_token_limit(
            current_user['id'], 
            answer.question_id,
            db
        )
        
        if question_limits["limit_reached"]:
            logger.info(f"User {current_user['id']} has reached token limit for question {answer.question_id}")
            raise HTTPException(
                status_code=429,  # Too Many Requests
                detail="You've reached the usage limit for this question. Please move to another question."
            )
            
        # Get question from database using UUID
        try:
            db_question = db.query(Question).filter(
                Question.id == uuid.UUID(answer.question_id)
            ).first()

            if not db_question:
                raise HTTPException(
                    status_code=404,
                    detail="Question not found. Please fetch a new question."
                )

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid question ID format"
            )
        
        # Process image if provided
        transcribed_text = None
        ocr_usage = {}
        combined_answer = answer.answer
        
        if answer.image_data:
            logger.info(f"Processing image for question {answer.question_id}")
            transcribed_text, ocr_usage = image_service.process_image(answer.image_data)
            if transcribed_text:
                combined_answer = f"Typed part of the answer: {answer.answer}\n\nContent from image:\n{transcribed_text}"
        
        # Track input tokens
        input_tokens = token_service.count_tokens(combined_answer)
        input_tokens += ocr_usage.get('ocr_prompt_tokens', 0)
        
        # Get input limits from user status (already fetched)
        input_limit = user_status["input_tokens_per_question"]
        input_buffer = user_status["input_token_buffer"]

        # Validate input length
        is_valid, token_count = token_service.validate_input(
            answer.answer, 
            input_limit,
            buffer=input_buffer
        )
        
        if not is_valid:
            logger.warning(f"Answer too long for user {current_user['id']}: {token_count} tokens")
            raise HTTPException(
                status_code=413,  # Payload Too Large
                detail=f"Your answer is too long. Please shorten it to stay within the usage limit."
            )

        # Grade the answer
        follow_up_questions = []
        
        # MCQ questions - direct comparison
        if db_question.type in ["MCQ", "True/False"]:
            user_answer = str(combined_answer).strip()
            correct_answer = str(db_question.correct_answer).strip()
            
            # Multiple comparison strategies
            exact_match = user_answer == correct_answer
            case_insensitive_match = user_answer.lower() == correct_answer.lower()
            contains_match = correct_answer in user_answer or user_answer in correct_answer
            
            is_correct = exact_match or case_insensitive_match or contains_match
            
            score = 10.0 if is_correct else 0.0
            feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}"
            
            # No AI usage for MCQ
            grading_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            logger.info(f"MCQ graded for user {current_user['id']}: score={score}")
        else:
            # Non-MCQ questions - use AI grading
            logger.info(f"AI grading answer for user {current_user['id']}, question {answer.question_id}")
            grading_result, grading_usage = grade_answer_with_ai(
                combined_answer,
                db_question.question_text,
                db_question.correct_answer
            )

            score, feedback, follow_up_questions = parse_grading_response(grading_result)
            logger.info(f"AI grading completed: score={score}")
        
        # Calculate output tokens
        output_tokens = grading_usage.get('completion_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.completion_tokens if hasattr(grading_usage, 'completion_tokens') else 0)
        output_tokens += ocr_usage.get('ocr_completion_tokens', 0)

        # Create attempt record (synchronous - needed for response)
        user_attempt = UserAttempt(
            user_id=current_user['id'],
            question_id=db_question.id,
            answer=answer.answer,
            score=score,
            feedback=feedback,
            board=db_question.board,
            class_level=db_question.class_level,
            subject=db_question.subject,
            chapter=normalize_chapter(db_question.chapter),
            time_taken=getattr(answer, 'time_taken', None),
            transcribed_text=transcribed_text,
            combined_answer=combined_answer,
            ocr_prompt_tokens=ocr_usage.get('ocr_prompt_tokens', 0),
            ocr_completion_tokens=ocr_usage.get('ocr_completion_tokens', 0),
            ocr_total_tokens=ocr_usage.get('ocr_total_tokens', 0),
            grading_prompt_tokens=grading_usage.get('prompt_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.prompt_tokens if hasattr(grading_usage, 'prompt_tokens') else 0),
            grading_completion_tokens=grading_usage.get('completion_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.completion_tokens if hasattr(grading_usage, 'completion_tokens') else 0),
            grading_total_tokens=grading_usage.get('total_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.total_tokens if hasattr(grading_usage, 'total_tokens') else 0),
            chat_prompt_tokens=0,
            chat_completion_tokens=0,
            chat_total_tokens=0,
            total_prompt_tokens=(ocr_usage.get('ocr_prompt_tokens', 0) + 
                                (grading_usage.get('prompt_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.prompt_tokens if hasattr(grading_usage, 'prompt_tokens') else 0))),
            total_completion_tokens=(ocr_usage.get('ocr_completion_tokens', 0) + 
                                    (grading_usage.get('completion_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.completion_tokens if hasattr(grading_usage, 'completion_tokens') else 0))),
            total_tokens=(ocr_usage.get('ocr_total_tokens', 0) + 
                        (grading_usage.get('total_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.total_tokens if hasattr(grading_usage, 'total_tokens') else 0))),
            input_tokens_used=input_tokens,
            output_tokens_used=output_tokens
        )
        
        try:
            db.add(user_attempt)
            db.commit()
            logger.info(f"Attempt record saved for user {current_user['id']}, question {answer.question_id}")
        except Exception as db_err:
            db.rollback()
            logger.error(f"Error adding attempt record: {str(db_err)}")
            raise HTTPException(
                status_code=500,
                detail="Error saving your answer. Please try again."
            )
            
        # BACKGROUND UPDATE: Schedule all usage updates (non-blocking)
        # This allows immediate response to user while updating counters in background
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=answer.question_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            question_submitted=True  # This will increment questions_used_today
        )
        
        logger.info(f"Background usage update scheduled for user {current_user['id']}: "
                   f"input={input_tokens}, output={output_tokens}")
        
        # Prepare response with current status (no additional database calls needed)
        response_data = {
            "score": score,
            "feedback": feedback,
            "model_answer": db_question.correct_answer,
            "explanation": db_question.explanation,
            "transcribed_text": transcribed_text,
            "user_answer": answer.answer,
            "follow_up_questions": follow_up_questions,
            "plan_info": {
                "plan_name": user_status["plan_name"],
                "display_name": user_status["display_name"]
            },
            "token_info": {
                "input_used": input_tokens,
                "output_used": output_tokens,
                "input_remaining": max(0, user_status["input_remaining"] - input_tokens),
                "output_remaining": max(0, user_status["output_remaining"] - output_tokens),
                "input_limit": user_status["input_limit"],
                "output_limit": user_status["output_limit"]
            }
        }
        
        logger.info(f"Answer graded successfully for user {current_user['id']}: score={score}")
        return response_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error in grade_answer: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
def prepare_question_response(question, stats, board, class_level, subject, chapter):
    """Helper function to prepare question response data with improved category detection"""
    question_number = "N/A"
    category_display = "Unknown"
    
    if question.human_readable_id:
        # Try multiple regex patterns to match both formats
        match = re.search(r'_(g|ic|ec|gen|ex|in)(\d+)$', question.human_readable_id)
        if match:
            category_code = match.group(1)
            number = match.group(2)
            
            # Expanded category mapping
            category_mapping = {
                'g': 'Generated',
                'gen': 'Generated',
                'ic': 'In-Chapter',
                'in': 'In-Chapter',
                'ec': 'Exercise',
                'ex': 'Exercise'
            }
            category_display = category_mapping.get(category_code, 'Unknown')
            question_number = f"{category_display} #{number}"

    return {
        "id": str(question.id),
        "question_text": question.question_text,
        "type": question.type,
        "difficulty": question.difficulty,
        "options": question.options or [],
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
        "metadata": {
            "board": board,
            "class_level": class_level,
            "subject": subject,
            "chapter": chapter,
            "bloom_level": question.bloom_level,
            "category": category_display,
            "question_number": question_number
        },
        "statistics": stats
    }

def create_placeholder_question(board, class_level, subject, chapter):
    """Helper function to create placeholder question"""
    question_id = str(uuid.uuid4())
    placeholder = {
        "id": question_id,
        "question_text": f"No questions found for Chapter {chapter}. Please check back later.",
        "type": "Information",
        "difficulty": "N/A",
        "options": [],
        "correct_answer": "No answer available",
        "explanation": "Questions for this chapter are being prepared.",
        "metadata": {
            "board": board,
            "class_level": class_level,
            "subject": subject,
            "chapter": chapter,
            "category": "N/A",
            "question_number": "N/A"
        },
        "statistics": {
            "total_attempts": 0,
            "average_score": 0
        }
    }
    active_questions[question_id] = placeholder
    return placeholder

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        print(f"Error handling request: {str(e)}")
        raise

@app.get("/api/debug/question-details")
async def debug_question_details(
    board: str = 'cbse', 
    class_: str = 'x', 
    subject: str = 'science', 
    chapter: int = 1,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Log the exact query parameters
        print("Query Parameters:")
        print(f"Board: '{board.lower()}'")
        print(f"Class Level: '{class_.lower()}'")
        print(f"Subject: '{subject.lower()}'")
        print(f"Chapter: {chapter}")

        # Execute detailed queries
        query = db.query(Question).filter(
            Question.board == board.lower(),
            Question.class_level == class_.lower(),
            Question.subject == subject.lower(),
            Question.chapter == chapter
        )

        # Count of questions
        count = query.count()
        print(f"Total Questions Found: {count}")

        # If questions exist, fetch details
        if count > 0:
            questions_details = query.all()
            detailed_info = [{
                "id": str(q.id),
                "human_readable_id": q.human_readable_id,
                "board": q.board,
                "class_level": q.class_level,
                "subject": q.subject,
                "chapter": q.chapter,
                "type": q.type,
                "difficulty": q.difficulty,
                "question_text_preview": q.question_text[:200] + "..." if len(q.question_text) > 200 else q.question_text
            } for q in questions_details]

            return {
                "total_questions": count,
                "questions": detailed_info
            }
        else:
            # Fetch all unique values to help diagnose the issue
            all_boards = db.query(Question.board).distinct().all()
            all_class_levels = db.query(Question.class_level).distinct().all()
            all_subjects = db.query(Question.subject).distinct().all()
            all_chapters = db.query(Question.chapter).distinct().all()

            return {
                "total_questions": 0,
                "message": "No questions found matching the criteria",
                "diagnostic_info": {
                    "searched_params": {
                        "board": board.lower(),
                        "class_level": class_.lower(),
                        "subject": subject.lower(),
                        "chapter": chapter
                    },
                    "available_values": {
                        "boards": [b[0] for b in all_boards],
                        "class_levels": [cl[0] for cl in all_class_levels],
                        "subjects": [s[0] for s in all_subjects],
                        "chapters": [c[0] for c in all_chapters]
                    }
                }
            }
    except Exception as e:
        print(f"Detailed debug error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Debug error: {str(e)}"
        )

def parse_grading_response(response_content: str) -> Tuple[float, str, List[str]]:
    score = 0.0
    feedback = "Unable to parse feedback"
    follow_up_questions = []
    
    score_match = re.search(r"Score:\s*([\d.]+)(?:/10)?", response_content, re.IGNORECASE)
    feedback_match = re.search(r"Feedback:\s*(.*?)(?:\n|$)", response_content, re.IGNORECASE | re.DOTALL)
    
    # Extract follow-up questions
    follow_up_matches = re.findall(r"Follow-up Question \d+:\s*(.*?)(?:\n|$)", response_content, re.IGNORECASE | re.DOTALL)
    
    if score_match:
        try:
            score = float(score_match.group(1).strip())
        except ValueError:
            score = 0.0
    
    if feedback_match:
        feedback = feedback_match.group(1).strip()
    
    # Add follow-up questions
    if follow_up_matches:
        follow_up_questions = [q.strip() for q in follow_up_matches]
    
    return score, feedback, follow_up_questions

def get_question_statistics(db: Session, question_id: uuid.UUID):
    """Get average performance statistics for a question"""
    try:
        stats = db.query(
            func.count(UserAttempt.id).label('total_attempts'),
            func.avg(UserAttempt.score).label('average_score')
        ).filter(
            UserAttempt.question_id == question_id
        ).first()
        
        return {
            'total_attempts': stats.total_attempts if stats else 0,
            'average_score': round(float(stats.average_score), 1) if stats and stats.average_score else 0
        }
    except Exception as e:
        print(f"Error getting question statistics: {str(e)}")
        return {
            'total_attempts': 0,
            'average_score': 0
        }


@app.get("/api/boards")
async def get_boards(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get board structure from database"""
    # Query all active boards
    query = text("""
        SELECT b.code, b.display_name, cl.code as class_code, cl.display_name as class_display_name
        FROM boards b
        JOIN class_levels cl ON b.id = cl.board_id
        WHERE b.active = TRUE AND cl.active = TRUE
        ORDER BY b.display_name, cl.display_name
    """)
    
    result = db.execute(query).fetchall()
    
    # Format response to match the old structure
    boards_dict = {}
    for row in result:
        if row.code not in boards_dict:
            boards_dict[row.code] = {
                "display_name": row.display_name,
                "classes": {}
            }
        
        boards_dict[row.code]["classes"][row.class_code] = {
            "display_name": row.class_display_name
        }
    
    return {"boards": boards_dict}

@app.get("/api/subjects/{board}/{class_}/{subject}/chapters")
async def get_chapter_info(
    board: str, 
    class_: str, 
    subject: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get chapter information for a subject"""
    try:
        print(f"Fetching chapters for board: {board}, class: {class_}, subject: {subject}")
        
        # Keep the hyphenated format instead of converting to underscores
        formatted_subject = subject.lower()  # Just lowercase, maintain hyphens
        base_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(
            base_path,
            "questions",
            board.lower(),
            class_.lower(),
            formatted_subject,
            "chapters.json"
        )
        
        print(f"Looking for chapters at: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"File not found at: {file_path}")
            # Try alternative path with underscores (for backwards compatibility)
            alternative_subject = subject.lower().replace('-', '_')
            alternative_path = os.path.join(
                base_path,
                "questions",
                board.lower(),
                class_.lower(),
                alternative_subject,
                "chapters.json"
            )
            print(f"Trying alternative path: {alternative_path}")
            
            if os.path.exists(alternative_path):
                file_path = alternative_path
            else:
                raise HTTPException(
                    status_code=404, 
                    detail="Chapters not found"
                )
            
        with open(file_path, 'r') as f:
            chapters_data = json.load(f)
            print(f"Successfully loaded chapters data: {chapters_data}")
            return chapters_data
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error getting chapter info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting chapter info"
        )


def grade_answer_with_ai(user_answer: str, question: str, model_answer: str) -> Tuple[str, dict]:
    prompt = f"""
    Grade this answer for a secondary school student:

    Question: "{question}"
    User's Answer: "{user_answer}"
    Correct Answer: "{model_answer}"

    Instructions:
    1. Determine the question type:

        - "numerical":
        - Accept any mathematically equivalent form of the correct answer (e.g., 21/3 = 7 = 7.0).
        - For irrational numbers like π, √2, etc., accept reasonable approximations (±0.05 or within 2%).
        - Start with 10/10 for a mathematically correct answer, even if not simplified.
        - If exact form is explicitly requested (e.g., “leave in terms of π”), deduct points for wrong format.
        - If only the correct number is requested (no explanation), a numerically correct answer alone earns full marks.

        - "conceptual":
        - Focus on understanding and accuracy of the explanation.
        - Accept valid alternate wording or synonymous concepts.
        - Evaluate based on clarity, completeness, and correctness.

        - "problem-solving":
        - Evaluate both the process/method and final result.
        - Apply same rules as numerical questions for final answers.
        - Award partial credit for correct steps even if the final answer is wrong.
        - Accept alternate valid methods and logical reasoning.

        - "descriptive":
        - Judge on clarity, completeness, and correctness of the explanation.
        - Accept alternative phrasing or perspectives that convey the correct ideas.
        - Emphasize organization and understanding, not rigid format.

    2. Always Simplify the User’s Answer First

        - If the user's answer doesn’t match the expected answer exactly, attempt to simplify or evaluate it before grading.
        - Examples: 2^3, 16/2, or √64 should be interpreted as 8.
        - Try to get the correct answer from user's answer if simplification is possible 
        - If simplification matches the correct answer, award full (10/10) or near-full (8–9/10) depending on whether format matters.
        - Do not penalize for valid alternate formats unless the question explicitly asks for a particular form (like simplified fractions or radical form).
        
        - Matching and Equivalent Forms

            - Accept:
            - Equivalent mathematical expressions
            - Correct answers with different valid notations (e.g., 7.0 instead of 7)
            - Synonyms or alternate phrases in science or conceptual answers

            - Only deduct points if:
            - The mathematical value is incorrect
            - The format is wrong when format is explicitly required
            - The reasoning or explanation is incorrect or incomplete

        - Strict Rule for Incorrect or Irrelevant Answers

            - If the answer is:
            - Mathematically or conceptually incorrect
            - Irrelevant to the question
            - Blank 
            
            ➤ Assign 0/10.

            - Do not award marks just for attempting or writing any answer blindly. Effort alone is not sufficient for credit.
            - Only assign partial marks if the answer demonstrates partial understanding, correct steps, or closeness to the correct idea.

    3. Summary of Scoring Approach

        - Begin at 10/10, and deduct only for:
        - Incorrect value or reasoning
        - Required format not followed
        - Missing explanation (if required)
        - Simplify before scoring — parse and interpret expressions logically
        - No credit for wrong or irrelevant answers, even if effort is shown
        - After simplifying user's answer if it matches the correct solution then award partial marks
            
    4. Provide brief, encouraging feedback in the first person
    
    5. Suggest TWO specific follow-up questions to guide the student to improve their understanding

    Format your response exactly as follows:
    Score: [score]/10
    Feedback: [your feedback]
    Follow-up Question 1: [first question]
    Follow-up Question 2: [second question]
    """
    
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            temperature=0.7
        )

        return response.choices[0].message.content.strip(), response.usage
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in AI grading: {str(e)}")

def normalize_chapter(chapter: int) -> int:
    """Convert chapter numbers like 101, 1001 to base chapter number"""
    if chapter >= 1000:
        return chapter % 1000
    if chapter >= 100:
        return chapter % 100
    return chapter

@app.get("/api/debug/file-paths")
async def debug_file_paths(
    board: str = "cbse", 
    class_: str = "xi",
    current_user: Dict = Depends(get_current_user)
):
    """Debug endpoint to check file paths"""
    try:
        results = {}
        
        # Check the current working directory and module location
        results["cwd"] = os.getcwd()
        results["__file__"] = __file__
        results["dirname"] = os.path.dirname(__file__)
        
        # Try to construct paths in different ways
        base_paths = [
            os.getcwd(),
            os.path.dirname(__file__),
            os.path.dirname(os.path.dirname(__file__)),
            "/app"  # Common base path in containerized environments like Railway
        ]
        
        results["path_checks"] = {}
        
        for base in base_paths:
            path = os.path.join(base, "questions", board, class_)
            results["path_checks"][base] = {
                "full_path": path,
                "exists": os.path.exists(path)
            }
            
            if os.path.exists(path):
                results["path_checks"][base]["contents"] = os.listdir(path)
        
        # Check specifically for kebo1dd
        results["subject_checks"] = {}
        for base in base_paths:
            for subject_code in ["kebo1dd", "keph1dd", "kech1dd"]:
                subject_path = os.path.join(base, "questions", board, class_, subject_code)
                chapters_path = os.path.join(subject_path, "chapters.json")
                
                results["subject_checks"][f"{base}_{subject_code}"] = {
                    "subject_path": subject_path,
                    "subject_exists": os.path.exists(subject_path),
                    "chapters_path": chapters_path,
                    "chapters_exists": os.path.exists(chapters_path)
                }
        
        return results
    except Exception as e:
        return {"error": str(e)}



# Add these endpoints to main.py (append to existing content)

# =====================================================================================
# SECTION & EXERCISE QUESTION ENDPOINTS
# Database structure note: 
# - Question.chapter: integer (1, 2, 3, etc.)
# - Question.section_id: string ("06_section_2_3" where:
#   * "06" = useless prefix (ignore)
#   * "section_2_3" = chapter 2, section 3)
# =====================================================================================

@app.get("/api/questions/{board}/{class_}/{subject}/{chapter}/exercise/random")
async def get_random_exercise_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get random exercise question from entire chapter"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch exercise question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        logger.info(f"Searching for random exercise question with:")
        logger.info(f"Original request: {board}/{class_}/{subject}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
        clean_board = actual_board
        clean_class = actual_class
        clean_subject = actual_subject.replace('-', '_')
        clean_chapter = chapter.replace('chapter-', '')
        
        try:
            chapter_int = int(clean_chapter)
            base_chapter = chapter_int
            
            if chapter_int > 100:
                base_chapter = chapter_int % 100
            
            chapter_conditions = [
                Question.chapter == base_chapter,
                Question.chapter == (100 + base_chapter)
            ]
        except ValueError:
            chapter_conditions = [
                Question.chapter == clean_chapter
            ]
        
        # Query for exercise questions (typically chapter > 100 indicates exercise questions)
        query = db.query(Question).filter(
            Question.board == clean_board,
            Question.class_level == clean_class,
            Question.subject == clean_subject,
            or_(*chapter_conditions)
        )
        
        count = query.count()
        logger.info(f"Found {count} exercise questions matching criteria")
        
        if count > 0:
            question = query.order_by(func.random()).first()
        else:
            # Fallback: try just with subject and chapter
            fallback_query = db.query(Question).filter(
                Question.subject == clean_subject,
                or_(*chapter_conditions)
            )
            
            fallback_count = fallback_query.count()
            logger.info(f"Exercise fallback query found {fallback_count} questions")
            
            if fallback_count > 0:
                question = fallback_query.order_by(func.random()).first()
                logger.info(f"Using fallback exercise question with ID: {question.id}")
            else:
                logger.warning(f"No exercise questions found for {clean_board}/{clean_class}/{clean_subject}/chapter-{clean_chapter}")
                return create_placeholder_question(clean_board, clean_class, clean_subject, clean_chapter)
        
        # Reset per-question token usage when new question is loaded
        if question:
            reset_query = text("""
                UPDATE user_attempts
                SET input_tokens_used = 0, output_tokens_used = 0
                WHERE user_id = :user_id AND question_id = :question_id
            """)
            try:
                db.execute(reset_query, {"user_id": current_user['id'], "question_id": str(question.id)})
                db.commit()
            except Exception as reset_error:
                logger.error(f"Error resetting question tokens: {str(reset_error)}")
                db.rollback()
        
        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(question, stats, clean_board, clean_class, clean_subject, clean_chapter)
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=str(question.id),
            input_tokens=50,
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved exercise question {question.id} for user {current_user['id']}")
        return question_data
                
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting random exercise question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving exercise question: {str(e)}"
        )


@app.get("/api/questions/{board}/{class_}/{subject}/{chapter}/exercise/q/{question_id}")
async def get_specific_exercise_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    question_id: str,  # UUID
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific exercise question"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch exercise question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        logger.info(f"Fetching specific exercise question:")
        logger.info(f"Original request: {board}/{class_}/{subject}/chapter-{chapter}/exercise/q/{question_id}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
        clean_chapter = chapter.replace('chapter-', '')
        
        try:
            chapter_int = int(clean_chapter)
            base_chapter = chapter_int
            
            if chapter_int > 100:
                base_chapter = chapter_int % 100
            
            chapter_conditions = [
                Question.chapter == base_chapter,
                Question.chapter == (100 + base_chapter)
            ]
        except ValueError:
            chapter_conditions = [
                Question.chapter == clean_chapter
            ]

        # Find exercise question by UUID
        question = db.query(Question).filter(
            Question.id == question_id,
            Question.board == actual_board,
            Question.class_level == actual_class,
            Question.subject == actual_subject,
            or_(*chapter_conditions)
        ).first()

        if not question:
            # Fallback searches
            logger.info(f"Exercise question not found with exact criteria, trying fallbacks for {question_id}")
            question = db.query(Question).filter(
                Question.id == question_id,
                Question.subject == actual_subject
            ).first()
            
            if not question:
                question = db.query(Question).filter(
                    Question.id == question_id
                ).first()
                
                if not question:
                    logger.warning(f"Exercise question not found with ID: {question_id}")
                    raise HTTPException(
                        status_code=404, 
                        detail="Exercise question not found"
                    )

        # Reset per-question token usage when question is loaded
        reset_query = text("""
            UPDATE user_attempts
            SET input_tokens_used = 0, output_tokens_used = 0
            WHERE user_id = :user_id AND question_id = :question_id
        """)
        try:
            db.execute(reset_query, {"user_id": current_user['id'], "question_id": question_id})
            db.commit()
        except Exception as reset_error:
            logger.error(f"Error resetting question tokens: {str(reset_error)}")
            db.rollback()

        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(
            question, 
            stats, 
            actual_board, 
            actual_class, 
            actual_subject, 
            clean_chapter
        )
        
        # Store in active_questions for grading
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=question_id,
            input_tokens=50,
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved specific exercise question {question_id} for user {current_user['id']}")
        return question_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting specific exercise question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving exercise question: {str(e)}"
        )


# =====================================================================================
# SECTION QUESTION ENDPOINTS
# =====================================================================================

# FIXED SECTION ENDPOINTS FOR main.py
# Replace the existing section endpoints with these corrected versions

@app.get("/api/questions/{board}/{class_}/{subject}/{chapter}/section/{section}/random")
async def get_random_section_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    section: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get random question from specific section"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch section question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_board = actual_board
        clean_class = actual_class
        clean_subject = actual_subject.replace('-', '_')
        clean_chapter = chapter.replace('chapter-', '')
        clean_section = section
        
        # Create section pattern FIRST, before logging
        try:
            chapter_int = int(clean_chapter)
            section_int = int(clean_section)
            
            # Use chapter % 100 for section pattern as requested
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
        
        # NOW we can safely log with section_pattern defined
        logger.info(f"Searching for random section question with:")
        logger.info(f"Original request: {board}/{class_}/{subject}/chapter-{chapter}/section-{section}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        logger.info(f"Section pattern for section_id: {section_pattern}")
        
        # Query for section questions using both chapter and section_id filters
        query = db.query(Question).filter(
            Question.board == clean_board,
            Question.class_level == clean_class,
            Question.subject == clean_subject,
            or_(*chapter_conditions),
            Question.section_id.like(section_pattern)
        )
        
        count = query.count()
        logger.info(f"Found {count} section questions matching criteria")
        
        if count > 0:
            question = query.order_by(func.random()).first()
        else:
            # Fallback: try just with subject and section pattern
            fallback_query = db.query(Question).filter(
                Question.subject == clean_subject,
                Question.section_id.like(section_pattern)
            )
            
            fallback_count = fallback_query.count()
            logger.info(f"Section fallback query found {fallback_count} questions")
            
            if fallback_count > 0:
                question = fallback_query.order_by(func.random()).first()
                logger.info(f"Using fallback section question with ID: {question.id}")
            else:
                logger.warning(f"No section questions found for {clean_board}/{clean_class}/{clean_subject}/chapter-{clean_chapter}/section-{clean_section}")
                return create_placeholder_question(clean_board, clean_class, clean_subject, f"{clean_chapter}.{clean_section}")
        
        # Reset per-question token usage when new question is loaded
        if question:
            reset_query = text("""
                UPDATE user_attempts
                SET input_tokens_used = 0, output_tokens_used = 0
                WHERE user_id = :user_id AND question_id = :question_id
            """)
            try:
                db.execute(reset_query, {"user_id": current_user['id'], "question_id": str(question.id)})
                db.commit()
            except Exception as reset_error:
                logger.error(f"Error resetting question tokens: {str(reset_error)}")
                db.rollback()
        
        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(question, stats, clean_board, clean_class, clean_subject, f"{clean_chapter}.{clean_section}")
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=str(question.id),
            input_tokens=50,
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved section question {question.id} for user {current_user['id']}")
        return question_data
                
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting random section question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section question: {str(e)}"
        )


@app.get("/api/questions/{board}/{class_}/{subject}/{chapter}/section/{section}/q/{question_id}")
async def get_specific_section_question(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    section: str,
    question_id: str,  # UUID
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific section question"""
    try:
        # SINGLE COMPREHENSIVE STATUS CHECK
        user_status = consolidated_service.get_comprehensive_user_status(current_user['id'], db)
        
        # Check if user can fetch questions
        permission_check = consolidated_service.check_can_perform_action(user_status, "fetch_question")
        
        if not permission_check["allowed"]:
            logger.info(f"User {current_user['id']} cannot fetch section question: {permission_check['reason']}")
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=permission_check["reason"]
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        clean_section = section
        
        # Create section pattern FIRST, before logging
        try:
            chapter_int = int(clean_chapter)
            section_int = int(clean_section)
            
            # Use chapter % 100 for section pattern as requested
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

        logger.info(f"Fetching specific section question:")
        logger.info(f"Original request: {board}/{class_}/{subject}/chapter-{chapter}/section-{section}/q/{question_id}")
        logger.info(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        logger.info(f"Section pattern for section_id: {section_pattern}")

        # Find section question by UUID using both chapter and section_id filters
        question = db.query(Question).filter(
            Question.id == question_id,
            Question.board == actual_board,
            Question.class_level == actual_class,
            Question.subject == actual_subject,
            or_(*chapter_conditions),
            Question.section_id.like(section_pattern)
        ).first()

        if not question:
            # Fallback searches with section pattern
            logger.info(f"Section question not found with exact criteria, trying fallbacks for {question_id}")
            question = db.query(Question).filter(
                Question.id == question_id,
                Question.subject == actual_subject,
                Question.section_id.like(section_pattern)
            ).first()
            
            if not question:
                question = db.query(Question).filter(
                    Question.id == question_id
                ).first()
                
                if not question:
                    logger.warning(f"Section question not found with ID: {question_id}")
                    raise HTTPException(
                        status_code=404, 
                        detail="Section question not found"
                    )

        # Reset per-question token usage when question is loaded
        reset_query = text("""
            UPDATE user_attempts
            SET input_tokens_used = 0, output_tokens_used = 0
            WHERE user_id = :user_id AND question_id = :question_id
        """)
        try:
            db.execute(reset_query, {"user_id": current_user['id'], "question_id": question_id})
            db.commit()
        except Exception as reset_error:
            logger.error(f"Error resetting question tokens: {str(reset_error)}")
            db.rollback()

        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(
            question, 
            stats, 
            actual_board, 
            actual_class, 
            actual_subject, 
            f"{clean_chapter}.{clean_section}"
        )
        
        # Store in active_questions for grading
        active_questions[str(question.id)] = question_data
        
        # Schedule background token usage update
        consolidated_service.update_user_usage(
            user_id=current_user['id'],
            question_id=question_id,
            input_tokens=50,
            output_tokens=0,
            question_submitted=False
        )
        
        logger.info(f"Successfully retrieved specific section question {question_id} for user {current_user['id']}")
        return question_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting specific section question: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section question: {str(e)}"
        )

# =====================================================================================
# SECTIONS INFO ENDPOINT (HYBRID: JSON FILE → DATABASE → DEFAULT)
# =====================================================================================

@app.get("/api/subjects/{board}/{class_}/{subject}/{chapter}/sections")
async def get_sections_info_hybrid(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get sections information - tries JSON file first, then database, then default"""
    try:
        logger.info(f"Fetching sections for board: {board}, class: {class_}, subject: {subject}, chapter: {chapter}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # ================================
        # STEP 1: TRY JSON FILE FIRST
        # ================================
        formatted_subject = subject.lower()  # Just lowercase, maintain hyphens
        base_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(
            base_path,
            "questions",
            board.lower(),
            class_.lower(),
            formatted_subject,
            f"chapter-{chapter}",
            "sections.json"
        )
        
        logger.info(f"Step 1: Looking for JSON file at: {file_path}")
        
        json_found = False
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    sections_data = json.load(f)
                    logger.info(f"✅ Successfully loaded sections from JSON file: {sections_data}")
                    return sections_data
            except Exception as json_error:
                logger.warning(f"⚠️ Error reading JSON file: {str(json_error)}")
        else:
            # Try alternative path with underscores (for backwards compatibility)
            alternative_subject = subject.lower().replace('-', '_')
            alternative_path = os.path.join(
                base_path,
                "questions",
                board.lower(),
                class_.lower(),
                alternative_subject,
                f"chapter-{chapter}",
                "sections.json"
            )
            logger.info(f"Step 1b: Trying alternative JSON path: {alternative_path}")
            
            if os.path.exists(alternative_path):
                try:
                    with open(alternative_path, 'r') as f:
                        sections_data = json.load(f)
                        logger.info(f"✅ Successfully loaded sections from alternative JSON file: {sections_data}")
                        return sections_data
                except Exception as json_error:
                    logger.warning(f"⚠️ Error reading alternative JSON file: {str(json_error)}")
        
        # ================================
        # STEP 2: FALLBACK TO DATABASE
        # ================================
        logger.info(f"Step 2: JSON file not found, trying database...")
        
        try:
            chapter_int = int(clean_chapter) if clean_chapter.isdigit() else None
            
            if chapter_int:
                # Query sections from database
                from sqlalchemy import text
                
                # First check if sections table exists
                table_exists_query = text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'sections'
                    );
                """)
                
                table_exists = db.execute(table_exists_query).scalar()
                
                if table_exists:
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
                        "board": actual_board,
                        "class_level": actual_class,
                        "subject": actual_subject,
                        "chapter": chapter_int
                    }).fetchall()
                    
                    if result:
                        sections_data = {
                            "sections": [
                                {
                                    "number": row.section_number,
                                    "name": row.section_name
                                }
                                for row in result
                            ]
                        }
                        logger.info(f"✅ Successfully loaded {len(result)} sections from database")
                        return sections_data
                    else:
                        logger.info(f"⚠️ No sections found in database for {actual_board}/{actual_class}/{actual_subject}/chapter-{chapter_int}")
                else:
                    logger.info(f"⚠️ Sections table does not exist in database")
            else:
                logger.warning(f"⚠️ Invalid chapter number for database query: {clean_chapter}")
                
        except Exception as db_error:
            logger.warning(f"⚠️ Database query failed: {str(db_error)}")
        
        # ================================
        # STEP 3: RETURN DEFAULT SECTIONS
        # ================================
        logger.info(f"Step 3: Returning default sections")
        return {
            "sections": [
                {"number": 1, "name": f"Section 1"},
                {"number": 2, "name": f"Section 2"},
                {"number": 3, "name": f"Section 3"}
            ]
        }
            
    except Exception as e:
        logger.error(f"Error getting sections info: {str(e)}")
        # Return default sections on error
        return {
            "sections": [
                {"number": 1, "name": f"Section 1"},
                {"number": 2, "name": f"Section 2"},
                {"number": 3, "name": f"Section 3"}
            ]
        }


# =====================================================================================
# PERFORMANCE ENDPOINTS
# =====================================================================================

@app.get("/api/progress/user/performance-summary/{board}/{class_}/{subject}/{chapter}")
async def get_chapter_performance_summary(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance summary for a chapter"""
    try:
        logger.info(f"Fetching performance summary for user {current_user['id']}, chapter {chapter}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # Query user attempts for this chapter
        attempts_query = db.query(UserAttempt).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        )
        
        attempts = attempts_query.all()
        
        if not attempts:
            return {
                "total_attempts": 0,
                "average_score": 0,
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
                "chapter_info": {
                    "board": board,
                    "class_level": class_,
                    "subject": subject,
                    "chapter": chapter
                }
            }
        
        # Calculate summary statistics
        total_attempts = len(attempts)
        total_score = sum(attempt.score for attempt in attempts)
        average_score = round(total_score / total_attempts, 1) if total_attempts > 0 else 0
        total_time = sum(attempt.time_taken or 0 for attempt in attempts)
        unique_questions = len(set(attempt.question_id for attempt in attempts))
        
        # Performance breakdown
        excellent = sum(1 for attempt in attempts if attempt.score >= 8)
        good = sum(1 for attempt in attempts if 6 <= attempt.score < 8)
        needs_improvement = sum(1 for attempt in attempts if attempt.score < 6)
        
        # Date range
        timestamps = [attempt.timestamp for attempt in attempts if attempt.timestamp]
        first_attempt = min(timestamps).isoformat() if timestamps else None
        last_attempt = max(timestamps).isoformat() if timestamps else None
        
        return {
            "total_attempts": total_attempts,
            "average_score": average_score,
            "total_time": total_time,
            "unique_questions": unique_questions,
            "performance_breakdown": {
                "excellent": excellent,
                "good": good,
                "needs_improvement": needs_improvement
            },
            "date_range": {
                "first_attempt": first_attempt,
                "last_attempt": last_attempt
            },
            "chapter_info": {
                "board": board,
                "class_level": class_,
                "subject": subject,
                "chapter": chapter
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting chapter performance summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving performance summary: {str(e)}"
        )


@app.get("/api/progress/user/performance-summary/{board}/{class_}/{subject}/{chapter}/section/{section}")
async def get_section_performance_summary(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    section: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance summary for a section"""
    try:
        logger.info(f"Fetching section performance summary for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # For section queries, filter by section-specific questions using join with Question table
        clean_chapter_int = int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        section_pattern = f"%section_{clean_chapter}_{section}%"
        
        attempts_query = db.query(UserAttempt).join(Question, UserAttempt.question_id == Question.id).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == clean_chapter_int,
            Question.section_id.like(section_pattern)
        )
        
        attempts = attempts_query.all()
        
        # Now properly filtered by section using the section pattern
        
        if not attempts:
            return {
                "total_attempts": 0,
                "average_score": 0,
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
                    "board": board,
                    "class_level": class_,
                    "subject": subject,
                    "chapter": chapter,
                    "section": section
                }
            }
        
        # Calculate summary statistics (same as chapter)
        total_attempts = len(attempts)
        total_score = sum(attempt.score for attempt in attempts)
        average_score = round(total_score / total_attempts, 1) if total_attempts > 0 else 0
        total_time = sum(attempt.time_taken or 0 for attempt in attempts)
        unique_questions = len(set(attempt.question_id for attempt in attempts))
        
        # Performance breakdown
        excellent = sum(1 for attempt in attempts if attempt.score >= 8)
        good = sum(1 for attempt in attempts if 6 <= attempt.score < 8)
        needs_improvement = sum(1 for attempt in attempts if attempt.score < 6)
        
        # Date range
        timestamps = [attempt.timestamp for attempt in attempts if attempt.timestamp]
        first_attempt = min(timestamps).isoformat() if timestamps else None
        last_attempt = max(timestamps).isoformat() if timestamps else None
        
        return {
            "total_attempts": total_attempts,
            "average_score": average_score,
            "total_time": total_time,
            "unique_questions": unique_questions,
            "performance_breakdown": {
                "excellent": excellent,
                "good": good,
                "needs_improvement": needs_improvement
            },
            "date_range": {
                "first_attempt": first_attempt,
                "last_attempt": last_attempt
            },
            "section_info": {
                "board": board,
                "class_level": class_,
                "subject": subject,
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


@app.get("/api/progress/user/performance-analytics/{board}/{class_}/{subject}/{chapter}")
async def get_chapter_performance_analytics(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance analytics data for charts"""
    try:
        logger.info(f"Fetching performance analytics for user {current_user['id']}, chapter {chapter}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # Query user attempts for this chapter
        attempts_query = db.query(UserAttempt).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        ).order_by(UserAttempt.timestamp)
        
        attempts = attempts_query.all()
        
        if not attempts:
            return {
                "analytics_data": [],
                "score_trends": [],
                "category_performance": {},
                "difficulty_breakdown": {},
                "time_performance": []
            }
        
        # Analytics data points
        analytics_data = []
        for i, attempt in enumerate(attempts, 1):
            analytics_data.append({
                "attempt_number": i,
                "score": attempt.score,
                "time_taken": attempt.time_taken or 0,
                "timestamp": attempt.timestamp.isoformat() if attempt.timestamp else "",
                "difficulty": "Medium",  # Default if not stored
                "type": "Practice",     # Default if not stored
                "bloom_level": "Apply", # Default if not stored
                "category": "General"   # Default if not stored
            })
        
        # Score trends
        score_trends = []
        for i, attempt in enumerate(attempts, 1):
            score_trends.append({
                "attempt": i,
                "score": attempt.score,
                "date": attempt.timestamp.isoformat() if attempt.timestamp else ""
            })
        
        # Category performance (simplified)
        category_performance = {
            "General": {
                "total_attempts": len(attempts),
                "average_score": round(sum(a.score for a in attempts) / len(attempts), 1),
                "best_score": max(a.score for a in attempts)
            }
        }
        
        # Difficulty breakdown (simplified)
        difficulty_breakdown = {
            "Easy": len([a for a in attempts if a.score >= 8]),
            "Medium": len([a for a in attempts if 6 <= a.score < 8]),
            "Hard": len([a for a in attempts if a.score < 6])
        }
        
        # Time performance
        time_performance = []
        for attempt in attempts:
            time_performance.append({
                "time_taken": attempt.time_taken or 0,
                "score": attempt.score,
                "category": "General"
            })
        
        return {
            "analytics_data": analytics_data,
            "score_trends": score_trends,
            "category_performance": category_performance,
            "difficulty_breakdown": difficulty_breakdown,
            "time_performance": time_performance
        }
        
    except Exception as e:
        logger.error(f"Error getting chapter performance analytics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving performance analytics: {str(e)}"
        )


@app.get("/api/progress/user/performance-analytics/{board}/{class_}/{subject}/{chapter}/section/{section}")
async def get_section_performance_analytics(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    section: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance analytics data for section charts"""
    try:
        logger.info(f"Fetching section performance analytics for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # Query user attempts for this section with section pattern filtering
        clean_chapter_int = int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        section_pattern = f"%section_{clean_chapter}_{section}%"
        
        attempts_query = db.query(UserAttempt).join(Question, UserAttempt.question_id == Question.id).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == clean_chapter_int,
            Question.section_id.like(section_pattern)
        ).order_by(UserAttempt.timestamp)
        
        attempts = attempts_query.all()
        
        # Now properly filtered by section using the section pattern
        
        if not attempts:
            return {
                "analytics_data": [],
                "score_trends": [],
                "category_performance": {},
                "difficulty_breakdown": {},
                "time_performance": []
            }
        
        # Same analytics structure as chapter
        analytics_data = []
        for i, attempt in enumerate(attempts, 1):
            analytics_data.append({
                "attempt_number": i,
                "score": attempt.score,
                "time_taken": attempt.time_taken or 0,
                "timestamp": attempt.timestamp.isoformat() if attempt.timestamp else "",
                "difficulty": "Medium",
                "type": "Section",
                "bloom_level": "Apply",
                "category": f"Section {section}"
            })
        
        score_trends = []
        for i, attempt in enumerate(attempts, 1):
            score_trends.append({
                "attempt": i,
                "score": attempt.score,
                "date": attempt.timestamp.isoformat() if attempt.timestamp else ""
            })
        
        category_performance = {
            f"Section {section}": {
                "total_attempts": len(attempts),
                "average_score": round(sum(a.score for a in attempts) / len(attempts), 1),
                "best_score": max(a.score for a in attempts)
            }
        }
        
        difficulty_breakdown = {
            "Easy": len([a for a in attempts if a.score >= 8]),
            "Medium": len([a for a in attempts if 6 <= a.score < 8]),
            "Hard": len([a for a in attempts if a.score < 6])
        }
        
        time_performance = []
        for attempt in attempts:
            time_performance.append({
                "time_taken": attempt.time_taken or 0,
                "score": attempt.score,
                "category": f"Section {section}"
            })
        
        return {
            "analytics_data": analytics_data,
            "score_trends": score_trends,
            "category_performance": category_performance,
            "difficulty_breakdown": difficulty_breakdown,
            "time_performance": time_performance
        }
        
    except Exception as e:
        logger.error(f"Error getting section performance analytics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving section performance analytics: {str(e)}"
        )


@app.get("/api/progress/user/solved-questions/{board}/{class_}/{subject}/{chapter}")
async def get_chapter_solved_questions(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    limit: int = 20,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed solved questions for a chapter"""
    try:
        logger.info(f"Fetching solved questions for user {current_user['id']}, chapter {chapter}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # Query user attempts for this chapter with pagination
        attempts_query = db.query(UserAttempt).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        ).order_by(UserAttempt.timestamp.desc())
        
        total_count = attempts_query.count()
        attempts = attempts_query.offset(offset).limit(limit).all()
        
        # Get question details for each attempt
        detailed_attempts = []
        for attempt in attempts:
            # Get question details
            question = db.query(Question).filter(Question.id == attempt.question_id).first()
            
            if question:
                detailed_attempts.append({
                    "question_id": str(attempt.question_id),
                    "question_text": question.question_text,
                    "user_answer": attempt.answer,
                    "transcribed_text": attempt.transcribed_text,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation,
                    "score": attempt.score,
                    "time_taken": attempt.time_taken or 0,
                    "timestamp": attempt.timestamp.isoformat() if attempt.timestamp else "",
                    "feedback": attempt.feedback,
                    "metadata": {
                        "questionNumber": f"Q{len(detailed_attempts) + 1}",
                        "source": "Practice",
                        "level": question.difficulty or "Medium",
                        "type": question.type or "Practice",
                        "bloomLevel": question.bloom_level or "Apply",
                        "statistics": {
                            "totalAttempts": 1,  # Could be calculated from all users
                            "averageScore": attempt.score  # Could be calculated from all users
                        }
                    }
                })
        
        # Pagination info
        has_more = (offset + limit) < total_count
        next_offset = (offset + limit) if has_more else None
        
        return {
            "attempts": detailed_attempts,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset
            },
            "chapter_info": {
                "board": board,
                "class_level": class_,
                "subject": subject,
                "chapter": chapter
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting chapter solved questions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving solved questions: {str(e)}"
        )


@app.get("/api/progress/user/solved-questions/{board}/{class_}/{subject}/{chapter}/section/{section}")
async def get_section_solved_questions(
    board: str, 
    class_: str, 
    subject: str, 
    chapter: str,
    section: str,
    limit: int = 20,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed solved questions for a section"""
    try:
        logger.info(f"Fetching section solved questions for user {current_user['id']}, chapter {chapter}, section {section}")
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        clean_chapter = chapter.replace('chapter-', '')
        
        # Query user attempts for this section with pagination and section pattern filtering
        clean_chapter_int = int(clean_chapter) if clean_chapter.isdigit() else clean_chapter
        section_pattern = f"%section_{clean_chapter}_{section}%"
        
        attempts_query = db.query(UserAttempt).join(Question, UserAttempt.question_id == Question.id).filter(
            UserAttempt.user_id == current_user['id'],
            UserAttempt.board == actual_board,
            UserAttempt.class_level == actual_class,
            UserAttempt.subject == actual_subject,
            UserAttempt.chapter == clean_chapter_int,
            Question.section_id.like(section_pattern)
        ).order_by(UserAttempt.timestamp.desc())
        
        # Filter by section if needed (depends on your data structure)
        # For now, using all chapter attempts
        
        total_count = attempts_query.count()
        attempts = attempts_query.offset(offset).limit(limit).all()
        
        # Get question details for each attempt
        detailed_attempts = []
        for attempt in attempts:
            question = db.query(Question).filter(Question.id == attempt.question_id).first()
            
            if question:
                detailed_attempts.append({
                    "question_id": str(attempt.question_id),
                    "question_text": question.question_text,
                    "user_answer": attempt.answer,
                    "transcribed_text": attempt.transcribed_text,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation,
                    "score": attempt.score,
                    "time_taken": attempt.time_taken or 0,
                    "timestamp": attempt.timestamp.isoformat() if attempt.timestamp else "",
                    "feedback": attempt.feedback,
                    "metadata": {
                        "questionNumber": f"S{section}.Q{len(detailed_attempts) + 1}",
                        "source": f"Section {section}",
                        "level": question.difficulty or "Medium",
                        "type": question.type or "Section",
                        "bloomLevel": question.bloom_level or "Apply",
                        "statistics": {
                            "totalAttempts": 1,
                            "averageScore": attempt.score
                        }
                    }
                })
        
        # Pagination info
        has_more = (offset + limit) < total_count
        next_offset = (offset + limit) if has_more else None
        
        return {
            "attempts": detailed_attempts,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset
            },
            "section_info": {
                "board": board,
                "class_level": class_,
                "subject": subject,
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