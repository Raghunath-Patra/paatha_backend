# backend/routes/try_routes.py

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta
import hashlib
import redis
import os
from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import get_db
from openai import OpenAI
import json
import traceback

router = APIRouter(prefix="/api/try", tags=["try"])

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Redis for rate limiting
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

# Models
class TryQuestion(BaseModel):
    id: str
    question_text: str
    type: str
    difficulty: str
    options: Optional[List[str]] = None
    category: str

class AnswerRequest(BaseModel):
    question_id: str
    answer: str
    time_taken: Optional[int] = None
    referral_share_id: Optional[str] = None

class GradeResponse(BaseModel):
    score: float
    feedback: str
    correct_answer: str
    explanation: Optional[str] = None

class ShareRequest(BaseModel):
    attempt_ids: List[str]
    share_method: str  # "whatsapp", "copy", "download"

# Helper functions
def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

def hash_ip(ip: str) -> str:
    # Use a secret key for hashing to ensure privacy
    secret = os.getenv("IP_HASH_SECRET", "paatha-secret-key")
    return hashlib.sha256((ip + secret).encode()).hexdigest()

def get_current_day_number() -> int:
    """Get the current day number based on Indian Standard Time (IST)"""
    import pytz
    from datetime import datetime
    
    # Define the Indian timezone
    ist_timezone = pytz.timezone('Asia/Kolkata')
    
    # Get current date in IST
    current_date_ist = datetime.now(ist_timezone).date()
    
    # Get the launch date and convert it to date object
    launch_date = datetime.strptime(
        os.getenv("TRY_FEATURE_LAUNCH_DATE", "2025-05-10"), "%Y-%m-%d"
    ).date()
    
    # Calculate days since launch
    days_since_launch = (current_date_ist - launch_date).days
    
    # Default to a week if no data
    total_days = 7
    
    # Return day number (1-indexed, cycling through the days)
    return (days_since_launch % total_days) + 1

# Updated check_rate_limit function with Redis error handling
def check_rate_limit(ip: str) -> bool:
    """Check if the IP has exceeded the daily rate limit"""
    try:
        hashed_ip = hash_ip(ip)
        key = f"try:rate_limit:{hashed_ip}"
        
        # Try to connect to Redis
        try:
            count = redis_client.get(key)
        except (redis.exceptions.ConnectionError, redis.exceptions.RedisError) as redis_error:
            # If Redis is unavailable, log it and continue without rate limiting
            print(f"[TRY] Redis connection error (skipping rate limit): {str(redis_error)}")
            return True
        
        if count is None:
            # Set initial count with 24-hour expiry
            try:
                redis_client.setex(key, 24 * 60 * 60, 1)
            except (redis.exceptions.ConnectionError, redis.exceptions.RedisError):
                # If Redis is unavailable for setting, just continue
                pass
            return True
        
        count = int(count)
        max_attempts = int(os.getenv("TRY_MAX_ATTEMPTS_PER_DAY", "5"))
        
        if count >= max_attempts:
            return False
        
        # Increment the count
        try:
            redis_client.incr(key)
        except (redis.exceptions.ConnectionError, redis.exceptions.RedisError):
            # If Redis is unavailable for incrementing, just continue
            pass
        return True
    except Exception as e:
        # For any other errors, log them and continue without rate limiting
        print(f"[TRY] Error in rate limiting (continuing anyway): {str(e)}")
        return True
    

def grade_answer_with_ai(user_answer: str, question: str, correct_answer: str) -> Dict:
    """Grade a short answer response using AI"""
    prompt = f"""
    Grade this answer for a secondary school student:

    Question: "{question}"
    User's Answer: "{user_answer}"
    Model's Answer: "{correct_answer}"

    Instructions:
    1. First, check if the user's answer is relevant and addresses the question at all. If it's completely irrelevant (e.g., some unrelated text or blank/empty content), assign 0/10 and say the answer does not attempt the question.
    2. Otherwise, assess how closely the user's answer matches the key ideas in the model's answer:
        - Assign a score out of 10 based on completeness and accuracy.
        - Deduct marks for missing key components.
        - Give a lower score for vague or partial answers.
    3. Provide brief, constructive feedback in the first person.

    Format your response exactly as follows:
    Score: [score]/10
    Feedback: [your feedback]
    """
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            temperature=0.7
        )

        
        result = response.choices[0].message.content.strip()
        
        # Parse the score and feedback
        score_match = result.split("Score:", 1)[1].split("\n", 1)[0].strip() if "Score:" in result else "0/10"
        score = float(score_match.replace("/10", ""))
        
        feedback = result.split("Feedback:", 1)[1].strip() if "Feedback:" in result else "No feedback available."
        
        return {
            "score": score,
            "feedback": feedback,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    except Exception as e:
        print(f"Error in AI grading: {str(e)}")
        return {
            "score": 0,
            "feedback": "Sorry, we couldn't grade your answer due to a technical issue.",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

# Debug endpoints
@router.get("/debug")
async def debug_try_endpoint():
    """Simple debug endpoint to verify the try router is working"""
    return {"status": "ok", "message": "Try feature API is working!"}

@router.get("/debug-questions")
async def debug_questions(db: Session = Depends(get_db)):
    """Debug endpoint to check questions in the database"""
    try:
        # Get the current day number
        day_number = get_current_day_number()
        
        # Check if the table exists
        table_check = db.execute(text("""
            SELECT EXISTS (
               SELECT FROM information_schema.tables 
               WHERE table_name = 'try_questions'
            );
        """)).scalar()
        
        if not table_check:
            return {"error": "try_questions table does not exist"}
        
        # Check table structure
        columns = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'try_questions';
        """)).fetchall()
        
        # Count total questions
        total_questions = db.execute(text("SELECT COUNT(*) FROM try_questions")).scalar()
        
        # Get questions for all days
        questions_by_day = db.execute(text("""
            SELECT day_number, COUNT(*) as count
            FROM try_questions
            WHERE active = true
            GROUP BY day_number
            ORDER BY day_number
        """)).fetchall()
        
        # Get a few sample questions
        sample_questions = db.execute(text("""
            SELECT id, question_text, type, difficulty, day_number, active, created_at
            FROM try_questions
            LIMIT 5
        """)).fetchall()
        
        # Format sample questions for response
        samples = []
        for q in sample_questions:
            samples.append({
                "id": str(q.id),
                "question_text": q.question_text[:50] + "..." if q.question_text and len(q.question_text) > 50 else q.question_text,
                "type": q.type,
                "day_number": q.day_number,
                "active": q.active,
                "created_at": q.created_at.isoformat() if q.created_at else None
            })
        
        return {
            "table_exists": table_check,
            "columns": [{"name": col.column_name, "type": col.data_type} for col in columns],
            "total_questions": total_questions,
            "current_day_number": day_number,
            "questions_by_day": [{"day": day.day_number, "count": day.count} for day in questions_by_day],
            "sample_questions": samples
        }
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@router.get("/test-query")
async def test_query(db: Session = Depends(get_db)):
    """Test SQL query execution"""
    try:
        day_number = 1  # Hardcode for testing
        
        # Query with error handling and detailed logging
        try:
            query_result = db.execute(text("""
                SELECT id, question_text, type, difficulty, options, category
                FROM try_questions
                WHERE day_number = :day_number AND active = true
                LIMIT 3
            """), {"day_number": day_number})
            
            # Fetch manually with detailed logging
            questions = []
            for row in query_result:
                questions.append({
                    "id": str(row.id) if row.id else "None",
                    "question_text": row.question_text[:50] + "..." if row.question_text and len(row.question_text) > 50 else row.question_text,
                    "type": row.type,
                    "difficulty": row.difficulty,
                    "options": row.options,
                    "category": row.category
                })
            
            return {
                "success": True,
                "day_number": day_number,
                "questions_found": len(questions),
                "questions": questions
            }
        except Exception as query_error:
            return {
                "success": False,
                "error": f"Query execution failed: {str(query_error)}",
                "traceback": traceback.format_exc()
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"General error: {str(e)}",
            "traceback": traceback.format_exc()
        }

# Main API endpoints
@router.get("/questions")
async def get_try_questions(
    request: Request,
    referral_share_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get the current day's questions for the try feature"""
    client_ip = get_client_ip(request)
    
    try:
        # Try rate limiting but continue even if it fails
        try:
            rate_limit_check = check_rate_limit(client_ip)
            if not rate_limit_check:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="You've reached the daily limit for the challenge. Please try again tomorrow."
                )
        except Exception as rate_limit_error:
            # Log rate limit error but continue
            print(f"[TRY] Rate limit check failed (continuing anyway): {str(rate_limit_error)}")
        
        # Get the current day number
        day_number = get_current_day_number()
        
        # Log for debugging
        print(f"[TRY] Fetching questions for day_number: {day_number}")
        
        # Get questions for the current day - no board/class filtering needed
        try:
            questions = db.execute(text("""
                SELECT id, question_text, type, difficulty, options, category
                FROM try_questions
                WHERE day_number = :day_number AND active = true
                LIMIT 3
            """), {"day_number": day_number}).fetchall()
            
            print(f"[TRY] SQL query executed, found {len(questions) if questions else 0} questions")
            
            # Debug: print first question if available
            if questions and len(questions) > 0:
                print(f"[TRY] First question ID: {questions[0].id}, Text: {questions[0].question_text[:30]}...")

                # Format response from database questions
                result = []
                for q in questions:
                    question_data = {
                        "id": str(q.id),
                        "question_text": q.question_text,
                        "type": q.type,
                        "difficulty": q.difficulty,
                        "category": q.category
                    }
                    
                    # Include options for MCQ
                    if q.type == "MCQ" and q.options:
                        question_data["options"] = q.options
                        
                    result.append(question_data)
                
                print(f"[TRY] Returning {len(result)} questions from database")
                return {"questions": result}
        except Exception as query_error:
            print(f"[TRY] Error executing SQL query: {str(query_error)}")
            print(traceback.format_exc())
        
        # If we reach here, there was an issue or no questions were found
        # Return default questions as fallback
        print(f"[TRY] No questions found in database or error occurred, using default questions")
        return {
            "questions": [
                {
                    "id": "1",
                    "question_text": "What is 2 + 2?",
                    "type": "MCQ",
                    "difficulty": "easy",
                    "options": ["3", "4", "5", "6"],
                    "category": "Mathematics"
                },
                {
                    "id": "2",
                    "question_text": "What is the capital of France?",
                    "type": "MCQ",
                    "difficulty": "easy",
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "category": "Geography"
                },
                {
                    "id": "3",
                    "question_text": "Explain how the water cycle works.",
                    "type": "short_answer",
                    "difficulty": "medium",
                    "category": "Science"
                }
            ]
        }
    except Exception as e:
        print(f"[TRY] Error getting questions: {str(e)}")
        print(traceback.format_exc())
        
        # Return simple questions as fallback
        return {
            "questions": [
                {
                    "id": "1",
                    "question_text": "What is 2 + 2?",
                    "type": "MCQ",
                    "difficulty": "easy",
                    "options": ["3", "4", "5", "6"],
                    "category": "Mathematics"
                },
                {
                    "id": "2",
                    "question_text": "What is the capital of France?",
                    "type": "MCQ",
                    "difficulty": "easy",
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "category": "Geography"
                },
                {
                    "id": "3",
                    "question_text": "Explain how the water cycle works.",
                    "type": "short_answer",
                    "difficulty": "medium",
                    "category": "Science"
                }
            ]
        }

@router.post("/grade")
async def grade_answer(
    answer_req: AnswerRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Grade a user's answer to a try question"""
    client_ip = get_client_ip(request)
    hashed_ip = hash_ip(client_ip)
    
    try:
        # Rate limiting check with Redis error handling
        try:
            rate_limit_check = check_rate_limit(client_ip)
            if not rate_limit_check:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="You've reached the daily limit for the challenge. Please try again tomorrow."
                )
        except Exception as rate_limit_error:
            # Log rate limit error but continue
            print(f"[TRY] Rate limit check failed (continuing anyway): {str(rate_limit_error)}")
        
        # For special case of the fallback questions
        if answer_req.question_id in ["1", "2", "3"]:
            # Hardcoded answers for fallback questions
            fallback_answers = {
                "1": {"answer": "4", "explanation": "Basic addition: 2 + 2 = 4"},
                "2": {"answer": "Paris", "explanation": "Paris is the capital city of France."},
                "3": {"answer": "The water cycle is the continuous movement of water on, above, and below Earth's surface through processes of evaporation, condensation, precipitation, and collection.", 
                      "explanation": "The water cycle involves water evaporating from bodies of water, condensing into clouds, precipitating as rain or snow, and collecting in bodies of water again."}
            }
            
            fallback = fallback_answers.get(answer_req.question_id)
            
            if answer_req.question_id in ["1", "2"]:  # MCQ questions
                is_correct = answer_req.answer.strip() == fallback["answer"].strip()
                score = 10.0 if is_correct else 0.0
                feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {fallback['answer']}"
            else:  # Short answer
                # Simple grading for fallback
                score = 7.0 if answer_req.answer and len(answer_req.answer) > 20 else 3.0
                feedback = "Good answer!" if score >= 7.0 else "Your answer needs more detail."
            
            return {
                "id": "fallback-" + answer_req.question_id,
                "score": score,
                "feedback": feedback,
                "correct_answer": fallback["answer"],
                "explanation": fallback["explanation"]
            }
        
        # Regular case - get question from database
        try:
            question = db.execute(text("""
                SELECT id, question_text, type, correct_answer, explanation 
                FROM try_questions
                WHERE id = :question_id
            """), {"question_id": uuid.UUID(answer_req.question_id)}).fetchone()
        except ValueError:
            # Handle invalid UUID
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid question ID format"
            )
        
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )
        
        # Debug information
        print(f"[TRY DEBUG] Question ID: {answer_req.question_id}")
        print(f"[TRY DEBUG] User Answer: '{answer_req.answer}'")
        print(f"[TRY DEBUG] Correct Answer from DB: '{question.correct_answer}'")
        
        # Process based on question type
        if question.type == "MCQ":
            # For MCQ, we need to compare exactly with the correct answer
            user_answer = str(answer_req.answer).strip()
            correct_answer = str(question.correct_answer).strip()
            
            # Very explicit comparison with detailed logging
            print(f"[TRY GRADING] Comparing: '{user_answer}' with '{correct_answer}'")
            
            # Try multiple comparison strategies
            exact_match = user_answer == correct_answer
            case_insensitive_match = user_answer.lower() == correct_answer.lower()
            
            # For cases where we have JSON or array format issues
            contains_match = correct_answer in user_answer or user_answer in correct_answer
            
            is_correct = exact_match or case_insensitive_match or contains_match
            print(f"[TRY GRADING] Match results - Exact: {exact_match}, Case-insensitive: {case_insensitive_match}, Contains: {contains_match}")
            
            score = 10.0 if is_correct else 0.0
            feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}"
            
            # No AI usage for MCQ
            ai_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        else:
            # For short answer, use AI grading
            grading_result = grade_answer_with_ai(
                answer_req.answer, 
                question.question_text, 
                question.correct_answer
            )
            
            score = grading_result["score"]
            feedback = grading_result["feedback"]
            ai_usage = grading_result.get("usage", {
                "prompt_tokens": 0, 
                "completion_tokens": 0, 
                "total_tokens": 0
            })
        
        # Generate a unique attempt ID for the response
        attempt_id = uuid.uuid4()
        
        # Skip database recording if table doesn't exist yet
        try:
            # Check if the try_attempts table exists
            table_exists = db.execute(text("""
                SELECT EXISTS (
                   SELECT FROM information_schema.tables 
                   WHERE table_name = 'try_attempts'
                );
            """)).scalar()
            
            if table_exists:
                # Record the attempt in the database
                db.execute(text("""
                    INSERT INTO try_attempts (
                        id, ip_address, user_agent, question_id, user_answer, 
                        is_correct, score, feedback, time_taken,
                        referral_share_id
                    ) VALUES (
                        :id, :ip_address, :user_agent, :question_id, :user_answer,
                        :is_correct, :score, :feedback, :time_taken,
                        :referral_share_id
                    )
                """), {
                    "id": attempt_id,
                    "ip_address": hashed_ip,
                    "user_agent": request.headers.get("User-Agent", ""),
                    "question_id": uuid.UUID(answer_req.question_id),
                    "user_answer": answer_req.answer,
                    "is_correct": score > 7.0 if question.type != "MCQ" else (score == 10.0),
                    "score": score,
                    "feedback": feedback,
                    "time_taken": answer_req.time_taken,
                    "referral_share_id": (
                        uuid.UUID(answer_req.referral_share_id) 
                        if answer_req.referral_share_id else None
                    )
                })
                db.commit()
                print(f"[TRY] Successfully recorded attempt in database")
            else:
                print(f"[TRY] try_attempts table doesn't exist yet, skipping attempt recording")
        except Exception as db_error:
            print(f"[TRY] Error recording attempt (continuing anyway): {str(db_error)}")
            db.rollback()
        
        # Return grading response
        return {
            "id": str(attempt_id),
            "score": score,
            "feedback": feedback,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "token_usage": ai_usage
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[TRY] Error grading answer: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing your answer"
        )
    
@router.post("/record-share")
async def record_share(
    share_req: ShareRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Record when a user shares their try results"""
    client_ip = get_client_ip(request)
    hashed_ip = hash_ip(client_ip)
    
    try:
        # Generate a unique share ID
        share_id = uuid.uuid4()
        
        # Check if the try_attempts table exists
        try:
            table_exists = db.execute(text("""
                SELECT EXISTS (
                   SELECT FROM information_schema.tables 
                   WHERE table_name = 'try_attempts'
                );
            """)).scalar()
            
            if table_exists:
                # Update all the specified attempts with the share ID
                for attempt_id in share_req.attempt_ids:
                    # Skip fallback IDs
                    if attempt_id.startswith("fallback-"):
                        continue
                        
                    try:
                        db.execute(text("""
                            UPDATE try_attempts
                            SET share_id = :share_id
                            WHERE id = :attempt_id AND ip_address = :ip_address
                        """), {
                            "share_id": share_id,
                            "attempt_id": uuid.UUID(attempt_id),
                            "ip_address": hashed_ip
                        })
                    except ValueError:
                        # Skip invalid UUIDs
                        continue
                
                db.commit()
                print(f"[TRY] Successfully recorded share in database")
            else:
                print(f"[TRY] try_attempts table doesn't exist yet, skipping share recording")
        except Exception as db_error:
            print(f"[TRY] Error recording share (continuing anyway): {str(db_error)}")
            db.rollback()
        
        # Return the share ID for tracking
        return {"share_id": str(share_id)}
        
    except Exception as e:
        print(f"[TRY] Error recording share: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error recording share"
        )