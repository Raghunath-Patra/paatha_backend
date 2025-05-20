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
from datetime import datetime
from routes import chat
from typing import List, Dict, Tuple  
from services.token_service import token_service
from sqlalchemy import text
from routes import promo_code  
from routes import try_routes



logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# In-memory storage for active questions
active_questions: Dict[str, dict] = {}

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
        "https://paatha-copy.vercel.app"

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

# Add middleware
app.add_middleware(SecurityHeadersMiddleware)

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
    try:
        # Check token limits
        token_limits = check_token_limits(current_user['id'], db)
        
        if token_limits["limit_reached"]:
            raise HTTPException(
                status_code=402, # Payment Required
                detail=f"You've reached your daily token limit. Upgrade to Premium for more tokens."
            )
        
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        print(f"Searching for random question with:")
        print(f"Original request: {board}/{class_}/{subject}")
        print(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
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
        
        # First try the exact query
        query = db.query(Question).filter(
            Question.board == clean_board,
            Question.class_level == clean_class,
            Question.subject == clean_subject,
            or_(*chapter_conditions)
        )
        
        # Check count before random selection to avoid empty results
        count = query.count()
        print(f"Found {count} questions matching exact criteria")
        
        if count > 0:
            question = query.order_by(func.random()).first()
        else:
            # Fallback: try just with subject and chapter
            fallback_query = db.query(Question).filter(
                Question.subject == clean_subject,
                or_(*chapter_conditions)
            )
            
            fallback_count = fallback_query.count()
            print(f"Fallback query found {fallback_count} questions")
            
            if fallback_count > 0:
                question = fallback_query.order_by(func.random()).first()
                print(f"Using fallback question with ID: {question.id}")
            else:
                # No questions found, return placeholder
                print(f"No questions found for {clean_board}/{clean_class}/{clean_subject}/chapter-{clean_chapter}")
                return create_placeholder_question(clean_board, clean_class, clean_subject, clean_chapter)
        
        # *** HERE IS THE IMPORTANT CHANGE: 
        # Reset token usage for this question whenever it's loaded
        check_question_token_limit(current_user['id'], str(question.id), db, reset_tokens=True)
        
        # Get statistics and prepare response
        stats = get_question_statistics(db, question.id)
        question_data = prepare_question_response(question, stats, clean_board, clean_class, clean_subject, clean_chapter)
        active_questions[str(question.id)] = question_data
        
        return question_data
                
    except Exception as e:
        print(f"Detailed error getting random question: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving question: {str(e)}"
        )
    
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
    try:
        # Map to source board/class/subject for shared subjects
        actual_board, actual_class, actual_subject = get_subject_mapping(
            board.lower(), 
            class_.lower(), 
            subject.lower()
        )
        
        print(f"Fetching specific question:")
        print(f"Original request: {board}/{class_}/{subject}/chapter-{chapter}/q/{question_id}")
        print(f"Mapped to: {actual_board}/{actual_class}/{actual_subject}")
        
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
            or_(*chapter_conditions)  # Use or_ for chapter conditions
        ).first()

        if not question:
            # First fallback: try with just the question ID and subject
            print(f"Question not found with exact criteria, trying with just ID and subject")
            question = db.query(Question).filter(
                Question.id == question_id,
                Question.subject == actual_subject
            ).first()
            
            if not question:
                # Second fallback: try with just the question ID
                print(f"Question not found with subject, trying with just ID")
                question = db.query(Question).filter(
                    Question.id == question_id
                ).first()
                
                if not question:
                    print(f"Question not found with ID: {question_id}")
                    raise HTTPException(
                        status_code=404, 
                        detail="Question not found"
                    )

        # Reset token usage for this question whenever it's loaded
        check_question_token_limit(current_user['id'], question_id, db, reset_tokens=True)

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
    1. First, determine the question type:
       "numerical": "- ANY mathematically equivalent form of the correct answer should receive FULL credit (e.g., 21/3 = 7 = 7.0)\n- For decimal approximations of irrational numbers (like π, √2, etc.), accept answers within a reasonable margin (±0.05 or 2% difference)\n- For example, if the answer is 2√2 ≈ 2.8284, accept answers like 2.82, 2.83, or even 2.8\n- Start with 10/10 for a mathematically correct answer, regardless of format\n- Only deduct points if the numerical value is incorrect beyond acceptable margins\n- If the question explicitly asks for exact form (e.g., 'leave in terms of π'), then check if the form is as requested\n- If no explanation is requested, a correct numerical answer alone deserves 10/10",
        "conceptual": "- Focus on understanding of key concepts\n- Evaluate completeness and accuracy of the explanation\n- Recognize valid alternative ways of expressing the same concept\n- Look for demonstration of conceptual understanding rather than exact wording",
        "problem-solving": "- Evaluate both method/approach and final answer\n- For numerical final answers, apply the same margin of error rules as numerical questions\n- Award partial credit for correct process even if final answer has errors\n- Recognize valid alternative solution methods\n- Consider clarity and logic of the problem-solving steps",
        "descriptive": "- Evaluate completeness, accuracy and relevance of the explanation\n- Consider organization and clarity of ideas\n- Look for key points that should be included\n- Recognize valid alternative perspectives or explanations"
    
    2. For numerical questions:
        - ANY mathematically equivalent form of the correct answer should receive FULL credit (e.g., 21/3 = 7 = 7.0)
        - Only deduct points if the numerical value is incorrect
        - If the question explicitly asks for explanation/working, then consider this in scoring
        - When comparing numerical values, ALWAYS check if they are mathematically equivalent or within acceptable margin of error
        - If explanation is not asked and you are expecting that then cut some marks but interpret that as a correct answer if it matches with the final answer
    
    3. For all question types:
        - Start from 10/10 and deduct points only for specific errors
        - Give partial credit for partially correct solutions
        - Recognize valid alternative approaches
        - Be lenient about formatting or notation differences
        - If the user's answer is same as final answer of a question, then don't interpret it as incorrect answer directly, instead give partial marks
    4.  When grading any answer:
        - Accept all equivalent answers (mathematical, scientific, or conceptual) unless a specific format is explicitly required (e.g., "simplify", "express in lowest terms", "write in p/q form where p and q are coprime")
        - For math: Accept all mathematically equivalent forms, even if not simplified, as long as the interpretation matches the expected answer; minor deductions may apply if simplification was expected but not done
        - When simplification or specific format is required and not followed (e.g., answer not in coprime p/q form), give partial credit if the value is correct upon parsing
        - For science: Accept synonymous terminology and alternative valid notations (e.g., chemical symbols, units)
        - For conceptual or descriptive answers: Accept synonymous expressions and phrasing that preserve the original meaning, unless a specific phrase or wording is explicitly required
        - Focus on the correctness and meaning of the answer rather than exact formatting or form, unless precision in form is explicitly asked for
    
    5. If the user's answer is completely irrelevant or blank, assign 0/10
    
    6. Provide brief, encouraging feedback in the first person
    
    7. Suggest TWO specific follow-up questions to guide the student to improve their understanding

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



@app.post("/api/grade")
async def grade_answer(
    answer: AnswerModel,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Grade a user's answer using AI for short answers, direct comparison for MCQs"""
    try:
        # First check if user has reached daily usage limits
        token_limits = check_token_limits(current_user['id'], db)
        
        if token_limits["limit_reached"]:
            raise HTTPException(
                status_code=402, # Payment Required
                detail=f"You've reached your daily usage limit. Upgrade to Premium for more tokens."
            )
        
        # Check if question-specific usage limit is reached
        question_limits = check_question_token_limit(
            current_user['id'], 
            answer.question_id,
            db
        )
        
        if question_limits["limit_reached"]:
            raise HTTPException(
                status_code=429, # Too Many Requests
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
            transcribed_text, ocr_usage = image_service.process_image(answer.image_data)
            if transcribed_text:
                combined_answer = f"Typed part of the answer: {answer.answer}\n\nContent from image:\n{transcribed_text}"
        
        # Track input tokens
        input_tokens = token_service.count_tokens(combined_answer)
        input_tokens += ocr_usage.get('ocr_prompt_tokens', 0)
        
        # Get subscription data for usage limits
        subscription = subscription_service.get_user_subscription_data(db, current_user['id'])
        plan = subscription_service.get_plan_details(db, subscription.get("plan_name", "free"))
        input_limit = plan.get("input_tokens_per_question", 6000)
        
        # Get token buffer from the plan
        input_buffer = plan.get("input_token_buffer", 1000)  # Default to 1000 if not set

        # Validate with the configurable buffer
        is_valid, token_count = token_service.validate_input(
            answer.answer, 
            input_limit,
            buffer=input_buffer
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=413, # Payload Too Large
                detail=f"Your answer is too long. Please shorten it to stay within the usage limit."
            )

        # Different grading methods based on question type
        follow_up_questions = []
        
        # Direct grading for MCQ questions
        if db_question.type in ["MCQ", "True/False"]:

            # For MCQ, compare exactly with the correct answer
            user_answer = str(combined_answer).strip()
            correct_answer = str(db_question.correct_answer).strip()
            
            # Try multiple comparison strategies
            exact_match = user_answer == correct_answer
            case_insensitive_match = user_answer.lower() == correct_answer.lower()
            
            # For cases where we have JSON or array format issues
            contains_match = correct_answer in user_answer or user_answer in correct_answer
            
            is_correct = exact_match or case_insensitive_match or contains_match
            
            score = 10.0 if is_correct else 0.0
            feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}"
            
            # No AI usage for MCQ
            grading_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        else:
            # For non-MCQ questions, use AI grading
            grading_result, grading_usage = grade_answer_with_ai(
                combined_answer,
                db_question.question_text,
                db_question.correct_answer
            )

            score, feedback, follow_up_questions = parse_grading_response(grading_result)
        
        # Track output tokens - only for non-MCQ questions
        output_tokens = grading_usage.get('completion_tokens', 0) if isinstance(grading_usage, dict) else (grading_usage.completion_tokens if hasattr(grading_usage, 'completion_tokens') else 0)
        output_tokens += ocr_usage.get('ocr_completion_tokens', 0)

        # Create attempt record
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
            transcribed_text=transcribed_text,  # This now includes both text and image descriptions
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
        except Exception as db_err:
            db.rollback()
            logger.error(f"Error adding attempt record: {str(db_err)}")
            raise HTTPException(
                status_code=500,
                detail="Error saving your answer. Please try again."
            )
            
        # Increment questions_used_today for display purposes
        try:
            increment_question_usage(current_user['id'], db)
        except Exception as usage_err:
            logger.error(f"Error incrementing question usage: {str(usage_err)}")
            
        # Update token usage
        try:
            update_token_usage(
                current_user['id'],
                answer.question_id,
                input_tokens,
                output_tokens,
                db
            )
        except Exception as token_err:
            logger.error(f"Error updating token usage: {str(token_err)}")
        
        # Get updated token status
        updated_token_limits = check_token_limits(current_user['id'], db)
        
        # Get plan features
        plan = subscription_service.get_plan_details(db, updated_token_limits["plan_name"])
        
        # Prepare response
        response_data = {
            "score": score,
            "feedback": feedback,
            "model_answer": db_question.correct_answer,
            "explanation": db_question.explanation,
            "transcribed_text": transcribed_text,  # This includes both text and image descriptions
            "user_answer": answer.answer,
            "follow_up_questions": follow_up_questions,
            "plan_info": {
                "plan_name": updated_token_limits["plan_name"],
                "display_name": updated_token_limits["display_name"]
            },
            "token_info": {
                "input_used": input_tokens,
                "output_used": output_tokens,
                "input_remaining": updated_token_limits["input_remaining"],
                "output_remaining": updated_token_limits["output_remaining"],
                "input_limit": updated_token_limits["input_limit"],
                "output_limit": updated_token_limits["output_limit"]
            }
        }
        
        return response_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error in grade_answer: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

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
