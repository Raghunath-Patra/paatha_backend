# backend/routes/student_quizzes.py - Updated with AI grading for text answers

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Dict, Optional, Any, Tuple
from pydantic import BaseModel
from config.database import get_db
from config.security import get_current_user
from models import Quiz, QuizQuestion, QuizAttempt, QuizResponse, CourseEnrollment, Question, User
from datetime import datetime, timezone, timedelta
import json
import logging
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables and initialize OpenAI client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter(prefix="/api/student/quizzes", tags=["student-quizzes"])

logger = logging.getLogger(__name__)

# Pydantic models
class QuizDetailResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    instructions: Optional[str]
    time_limit: Optional[int]
    total_marks: int
    passing_marks: int
    attempts_allowed: int
    start_time: Optional[str]
    end_time: Optional[str]
    is_published: bool
    auto_grade: bool
    course_name: str
    teacher_name: Optional[str]
    my_attempts: int
    best_score: Optional[float]
    can_attempt: bool
    time_remaining: Optional[int]  # Minutes until end_time

class QuizQuestionResponse(BaseModel):
    id: str
    question_text: str
    question_type: str
    options: Optional[List[str]]
    marks: int
    order_index: int

class QuizAttemptCreate(BaseModel):
    quiz_id: str

class QuestionResponse(BaseModel):
    question_id: str
    response: str
    time_spent: Optional[int] = None
    confidence_level: Optional[int] = None
    flagged_for_review: Optional[bool] = False

class QuizSubmission(BaseModel):
    # Support both old and new formats
    answers: Optional[Dict[str, Any]] = None  # Old format: question_id -> answer
    responses: Optional[List[QuestionResponse]] = None  # New format
    
    def get_responses(self) -> List[QuestionResponse]:
        """Convert old format to new format if needed"""
        if self.responses:
            return self.responses
        elif self.answers:
            # Convert old format to new format
            return [
                QuestionResponse(
                    question_id=question_id,
                    response=str(answer),
                    time_spent=None,
                    confidence_level=None,
                    flagged_for_review=False
                )
                for question_id, answer in self.answers.items()
            ]
        else:
            return []

class AttemptResponse(BaseModel):
    id: str
    quiz_id: str
    quiz_title: str
    attempt_number: int
    obtained_marks: float
    total_marks: int
    percentage: float
    started_at: str
    submitted_at: Optional[str]
    time_taken: Optional[int]
    status: str
    is_auto_graded: bool
    teacher_reviewed: bool
    responses: Optional[List[Dict[str, Any]]] = None  # Changed from answers to responses

class AttemptResultResponse(BaseModel):
    attempt: AttemptResponse
    questions_with_answers: List[Dict[str, Any]]
    summary: Dict[str, Any]

# FIXED: India timezone utilities
def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

def get_india_date():
    """Get current date in India timezone"""
    return get_india_time().date()

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

def check_student_permission(user: Dict):
    """Check if user is a student"""
    if user.get('role') != 'student':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this endpoint"
        )

def verify_enrollment(course_id: str, student_id: str, db: Session):
    """Verify that student is enrolled in the course"""
    enrollment = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course_id,
        CourseEnrollment.student_id == student_id,
        CourseEnrollment.status == 'active'
    ).first()
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not enrolled in this course"
        )
    
    return enrollment

def format_attempt_response(attempt, quiz_title: str, responses: List = None):
    """Helper function to format attempt response"""
    return AttemptResponse(
        id=str(attempt.id),
        quiz_id=str(attempt.quiz_id),
        quiz_title=quiz_title,
        attempt_number=attempt.attempt_number,
        obtained_marks=attempt.obtained_marks,
        total_marks=attempt.total_marks,
        percentage=attempt.percentage,
        started_at=attempt.started_at.isoformat(),
        submitted_at=attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        time_taken=attempt.time_taken,
        status=attempt.status,
        is_auto_graded=attempt.is_auto_graded,
        teacher_reviewed=attempt.teacher_reviewed,
        responses=responses
    )

def grade_quiz_answer_with_ai(user_answer: str, question_text: str, correct_answer: str, max_marks: int) -> Tuple[float, str, dict]:
    """Grade quiz answer using AI with specific marks allocation"""
    prompt = f"""
    Grade this quiz answer for a student:

    Question: "{question_text}"
    Student's Answer: "{user_answer}"
    Correct/Sample Answer: "{correct_answer}"
    Maximum Marks: {max_marks}

    Instructions:
    1. Evaluate the student's answer against the correct answer
    2. Consider partial credit for partially correct answers
    3. Be fair but accurate in grading
    4. Give marks out of {max_marks} (not out of 10)
    
    Grading Criteria:
    - Full marks ({max_marks}) for completely correct answers
    - Partial marks for answers showing understanding but with minor errors
    - Zero marks for completely incorrect or irrelevant answers
    - Accept equivalent expressions, synonyms, and alternative valid approaches
    
    For numerical answers:
    - Accept mathematically equivalent forms
    - Allow reasonable approximations
    - Consider significant figures appropriately
    
    For descriptive answers:
    - Focus on key concepts and understanding
    - Accept alternative wording that conveys correct meaning
    - Award partial credit for incomplete but correct information

    Format your response exactly as follows:
    Score: [score]/{max_marks}
    Feedback: [brief feedback explaining the grade]
    """
    
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            temperature=0.3  # Lower temperature for more consistent grading
        )

        content = response.choices[0].message.content.strip()
        score, feedback = parse_quiz_grading_response(content, max_marks)
        
        # Convert usage to dict format
        usage_dict = {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
        
        return score, feedback, usage_dict
        
    except Exception as e:
        logger.error(f"Error in AI quiz grading: {str(e)}")
        # Return zero score with error feedback
        return 0.0, f"Error in grading: {str(e)}", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}

def parse_quiz_grading_response(response_content: str, max_marks: int) -> Tuple[float, str]:
    """Parse AI grading response for quiz answers"""
    score = 0.0
    feedback = "Unable to parse feedback"
    
    # Look for score pattern with flexible formatting
    score_patterns = [
        rf"Score:\s*([\d.]+)\s*/{max_marks}",
        rf"Score:\s*([\d.]+)\s*/\s*{max_marks}",
        rf"Score:\s*([\d.]+)",
        rf"Marks:\s*([\d.]+)"
    ]
    
    score_match = None
    for pattern in score_patterns:
        score_match = re.search(pattern, response_content, re.IGNORECASE)
        if score_match:
            break
    
    if score_match:
        try:
            score = float(score_match.group(1).strip())
            # Ensure score doesn't exceed max_marks
            score = min(score, max_marks)
        except (ValueError, IndexError):
            score = 0.0
    
    # Extract feedback
    feedback_match = re.search(r"Feedback:\s*(.*?)(?:\n|$)", response_content, re.IGNORECASE | re.DOTALL)
    if feedback_match:
        feedback = feedback_match.group(1).strip()
    else:
        # If no explicit feedback found, use the whole response as feedback
        feedback = response_content
    
    return score, feedback

@router.get("/{quiz_id}", response_model=QuizDetailResponse)
async def get_quiz_details(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get quiz details for a student"""
    try:
        check_student_permission(current_user)
        
        # Get quiz with course and teacher info
        query = text("""
            SELECT 
                q.*,
                c.course_name,
                u.full_name as teacher_name
            FROM quizzes q
            JOIN courses c ON q.course_id = c.id
            JOIN profiles u ON q.teacher_id = u.id
            WHERE q.id = :quiz_id AND q.is_published = true
        """)
        
        quiz_result = db.execute(query, {"quiz_id": quiz_id}).fetchone()
        
        if not quiz_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found or not published"
            )
        
        # Verify enrollment
        verify_enrollment(str(quiz_result.course_id), current_user['id'], db)
        
        # Get attempt statistics
        my_attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id']
        ).count()
        
        best_score_result = db.query(func.max(QuizAttempt.percentage)).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == 'completed'
        ).scalar()
        
        best_score = float(best_score_result) if best_score_result else None
        
        # Check if student can attempt with proper India timezone handling
        can_attempt = True
        time_remaining = None
        
        # Check attempt limit
        if my_attempts >= quiz_result.attempts_allowed:
            can_attempt = False
        
        # Check time constraints with India timezone comparisons
        now = get_india_time()
        start_time = ensure_india_timezone(quiz_result.start_time)
        end_time = ensure_india_timezone(quiz_result.end_time)
        
        if start_time and now < start_time:
            can_attempt = False
        elif end_time:
            if now > end_time:
                can_attempt = False
            else:
                time_remaining = int((end_time - now).total_seconds() / 60)
        
        return QuizDetailResponse(
            id=str(quiz_result.id),
            title=quiz_result.title,
            description=quiz_result.description,
            instructions=quiz_result.instructions,
            time_limit=quiz_result.time_limit,
            total_marks=quiz_result.total_marks,
            passing_marks=quiz_result.passing_marks,
            attempts_allowed=quiz_result.attempts_allowed,
            start_time=quiz_result.start_time.isoformat() if quiz_result.start_time else None,
            end_time=quiz_result.end_time.isoformat() if quiz_result.end_time else None,
            is_published=quiz_result.is_published,
            auto_grade=quiz_result.auto_grade,
            course_name=quiz_result.course_name,
            teacher_name=quiz_result.teacher_name,
            my_attempts=my_attempts,
            best_score=best_score,
            can_attempt=can_attempt,
            time_remaining=time_remaining
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting quiz details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting quiz details: {str(e)}"
        )

@router.post("/{quiz_id}/start", response_model=AttemptResponse)
async def start_quiz_attempt(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new quiz attempt"""
    try:
        check_student_permission(current_user)
        
        # Get quiz
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.is_published == True
        ).first()
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found or not published"
            )
        
        # Verify enrollment
        verify_enrollment(str(quiz.course_id), current_user['id'], db)
        
        # Check if student can attempt
        existing_attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id']
        ).count()
        
        if existing_attempts >= quiz.attempts_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have reached the maximum number of attempts for this quiz"
            )
        
        # Check time constraints with proper India timezone handling
        now = get_india_time()
        start_time = ensure_india_timezone(quiz.start_time)
        end_time = ensure_india_timezone(quiz.end_time)
        
        if start_time and now < start_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quiz has not started yet"
            )
        
        if end_time and now > end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quiz has ended"
            )
        
        # Check for existing in-progress attempt
        existing_in_progress = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == 'in_progress'
        ).first()
        
        if existing_in_progress:
            # Get existing responses for this attempt
            existing_responses = db.query(QuizResponse).filter(
                QuizResponse.attempt_id == existing_in_progress.id
            ).all()
            
            responses_data = [
                {
                    "question_id": str(resp.question_id),
                    "response": resp.response,
                    "time_spent": resp.time_spent,
                    "confidence_level": resp.confidence_level,
                    "flagged_for_review": resp.flagged_for_review
                }
                for resp in existing_responses
            ]
            
            return format_attempt_response(existing_in_progress, quiz.title, responses_data)
        
        # Create new attempt
        new_attempt = QuizAttempt(
            quiz_id=quiz_id,
            student_id=current_user['id'],
            attempt_number=existing_attempts + 1,
            answers={},  # Empty dict for backward compatibility
            total_marks=quiz.total_marks,
            started_at=get_india_time(),
            status='in_progress'
        )
        
        db.add(new_attempt)
        db.commit()
        db.refresh(new_attempt)
        
        return format_attempt_response(new_attempt, quiz.title, [])
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error starting quiz attempt: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting quiz attempt: {str(e)}"
        )

@router.get("/{quiz_id}/questions", response_model=List[QuizQuestionResponse])
async def get_quiz_questions(
    quiz_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get questions for a quiz (only for active attempts)"""
    try:
        check_student_permission(current_user)
        
        # Verify student has an active attempt
        active_attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == 'in_progress'
        ).first()
        
        if not active_attempt:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active attempt found for this quiz"
            )
        
        # Get quiz questions
        query = text("""
            SELECT 
                qq.id,
                qq.marks,
                qq.order_index,
                COALESCE(q.question_text, qq.custom_question_text) as question_text,
                COALESCE(q.type, qq.custom_question_type) as question_type,
                CASE 
                    WHEN q.options IS NOT NULL THEN q.options::json
                    WHEN qq.custom_options IS NOT NULL THEN qq.custom_options::json
                    ELSE NULL
                END as options
            FROM quiz_questions qq
            LEFT JOIN questions q ON qq.ai_question_id = q.id
            WHERE qq.quiz_id = :quiz_id
            ORDER BY qq.order_index
        """)
        
        questions = db.execute(query, {"quiz_id": quiz_id}).fetchall()
        
        return [
            QuizQuestionResponse(
                id=str(q.id),
                question_text=q.question_text,
                question_type=q.question_type,
                options=q.options if q.options else None,
                marks=q.marks,
                order_index=q.order_index
            )
            for q in questions
        ]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting quiz questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting quiz questions: {str(e)}"
        )

@router.post("/{quiz_id}/submit", response_model=AttemptResultResponse)
async def submit_quiz(
    quiz_id: str,
    submission: QuizSubmission,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit quiz answers using QuizResponse table with AI grading for text answers"""
    try:
        check_student_permission(current_user)
        
        # Get active attempt
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == 'in_progress'
        ).first()
        
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active attempt found"
            )
        
        # Get quiz and questions
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        
        # Get questions with correct answers
        query = text("""
            SELECT 
                qq.id,
                qq.marks,
                COALESCE(q.correct_answer, qq.custom_correct_answer) as correct_answer,
                COALESCE(q.question_text, qq.custom_question_text) as question_text,
                COALESCE(q.type, qq.custom_question_type) as question_type,
                CASE 
                    WHEN q.options IS NOT NULL THEN q.options::json
                    WHEN qq.custom_options IS NOT NULL THEN qq.custom_options::json
                    ELSE NULL
                END as options,
                COALESCE(q.explanation, qq.custom_explanation) as explanation
            FROM quiz_questions qq
            LEFT JOIN questions q ON qq.ai_question_id = q.id
            WHERE qq.quiz_id = :quiz_id
            ORDER BY qq.order_index
        """)
        
        questions = db.execute(query, {"quiz_id": quiz_id}).fetchall()
        questions_dict = {str(q.id): q for q in questions}
        
        # Create response lookup from submission
        responses_list = submission.get_responses()
        responses_dict = {resp.question_id: resp for resp in responses_list}
        
        # Delete existing responses for this attempt (in case of resubmission)
        db.query(QuizResponse).filter(
            QuizResponse.attempt_id == attempt.id
        ).delete()
        
        # Grade the quiz and create QuizResponse records
        total_score = 0
        max_possible_score = 0
        questions_with_answers = []
        total_ai_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        
        for question in questions:
            max_possible_score += question.marks
            question_id = str(question.id)
            
            # Get student response
            student_response = responses_dict.get(question_id)
            student_answer = student_response.response if student_response else ""
            correct_answer = question.correct_answer
            
            # Initialize grading variables
            is_correct = False
            score = 0
            feedback = ""
            
            # Grading logic based on question type
            if question.question_type.lower() in ['mcq', 'multiple_choice', 'true/false']:
                # MCQ/True-False: Direct comparison
                is_correct = str(student_answer).strip().lower() == str(correct_answer).strip().lower()
                score = question.marks if is_correct else 0
                feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}"
            else:
                # Text answers: Use AI grading
                if student_answer.strip():  # Only grade if student provided an answer
                    try:
                        score, feedback, ai_usage = grade_quiz_answer_with_ai(
                            student_answer,
                            question.question_text,
                            correct_answer,
                            question.marks
                        )
                        
                        # Accumulate AI token usage
                        total_ai_usage['prompt_tokens'] += ai_usage.get('prompt_tokens', 0)
                        total_ai_usage['completion_tokens'] += ai_usage.get('completion_tokens', 0)
                        total_ai_usage['total_tokens'] += ai_usage.get('total_tokens', 0)
                        
                        # Determine if correct based on score (consider > 80% as correct)
                        is_correct = score >= (question.marks * 0.8)
                        
                    except Exception as ai_error:
                        logger.error(f"AI grading error for question {question_id}: {str(ai_error)}")
                        # Fallback to basic comparison on AI error
                        is_correct = str(student_answer).strip().lower() == str(correct_answer).strip().lower()
                        score = question.marks if is_correct else 0
                        feedback = f"Grading error occurred. Basic check: {'Correct' if is_correct else 'Incorrect'}"
                else:
                    # No answer provided
                    score = 0
                    feedback = "No answer provided"
                    is_correct = False
            
            total_score += score
            
            # Create QuizResponse record
            quiz_response = QuizResponse(
                quiz_id=quiz_id,
                student_id=current_user['id'],
                question_id=question.id,
                attempt_id=attempt.id,
                response=student_answer,
                score=score,
                is_correct=is_correct,
                feedback=feedback,  # Store the feedback in database
                time_spent=student_response.time_spent if student_response else None,
                confidence_level=student_response.confidence_level if student_response else None,
                flagged_for_review=student_response.flagged_for_review if student_response else False,
                answered_at=get_india_time()
            )
            
            db.add(quiz_response)
            
            questions_with_answers.append({
                "question_id": question_id,
                "question_text": question.question_text,
                "question_type": question.question_type,
                "options": question.options,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "explanation": question.explanation,
                "marks": question.marks,
                "score": score,
                "is_correct": is_correct,
                "feedback": feedback,
                "time_spent": student_response.time_spent if student_response else None,
                "confidence_level": student_response.confidence_level if student_response else None,
                "flagged_for_review": student_response.flagged_for_review if student_response else False
            })
        
        # Calculate percentage
        percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        # Calculate time taken with India timezone datetime
        time_taken = None
        if attempt.started_at:
            started_at = ensure_india_timezone(attempt.started_at)
            now = get_india_time()
            time_taken = int((now - started_at).total_seconds() / 60)
        
        # Update attempt
        attempt.obtained_marks = total_score
        attempt.percentage = percentage
        attempt.submitted_at = get_india_time()
        attempt.time_taken = time_taken
        attempt.status = 'completed'
        attempt.is_auto_graded = quiz.auto_grade if quiz else True
        
        db.commit()
        db.refresh(attempt)
        
        # Update course enrollment stats
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == quiz.course_id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if enrollment:
            enrollment.total_quizzes_taken += 1
            # Update average score
            avg_score = db.query(func.avg(QuizAttempt.percentage)).filter(
                QuizAttempt.student_id == current_user['id'],
                QuizAttempt.quiz_id.in_(
                    db.query(Quiz.id).filter(Quiz.course_id == quiz.course_id)
                ),
                QuizAttempt.status == 'completed'
            ).scalar()
            enrollment.average_score = float(avg_score) if avg_score else 0
            db.commit()
        
        # Get all responses for the response data
        responses_data = [
            {
                "question_id": qa["question_id"],
                "response": qa["student_answer"],
                "score": qa["score"],
                "is_correct": qa["is_correct"],
                "feedback": qa["feedback"],  # Include feedback
                "time_spent": qa["time_spent"],
                "confidence_level": qa["confidence_level"],
                "flagged_for_review": qa["flagged_for_review"]
            }
            for qa in questions_with_answers
        ]
        
        # Prepare response
        attempt_response = format_attempt_response(attempt, quiz.title, responses_data)
        
        summary = {
            "total_questions": len(questions),
            "correct_answers": sum(1 for q in questions_with_answers if q["is_correct"]),
            "total_marks": max_possible_score,
            "obtained_marks": total_score,
            "percentage": percentage,
            "passed": percentage >= quiz.passing_marks,
            "time_taken": time_taken,
            "ai_grading_used": total_ai_usage['total_tokens'] > 0,
            "ai_token_usage": total_ai_usage
        }
        
        logger.info(f"Quiz submitted successfully by user {current_user['id']}: "
                   f"Score={total_score}/{max_possible_score}, AI tokens used={total_ai_usage['total_tokens']}")
        
        return AttemptResultResponse(
            attempt=attempt_response,
            questions_with_answers=questions_with_answers,
            summary=summary
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error submitting quiz: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting quiz: {str(e)}"
        )

@router.get("/attempts/my-attempts", response_model=List[AttemptResponse])
async def get_my_attempts(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quiz attempts for the current student"""
    try:
        check_student_permission(current_user)
        
        # Get attempts with quiz info
        attempts = db.query(QuizAttempt, Quiz.title).join(
            Quiz, QuizAttempt.quiz_id == Quiz.id
        ).filter(
            QuizAttempt.student_id == current_user['id']
        ).order_by(QuizAttempt.started_at.desc()).all()
        
        result = []
        for attempt, quiz_title in attempts:
            # Get responses for each attempt
            responses = db.query(QuizResponse).filter(
                QuizResponse.attempt_id == attempt.id
            ).all()
            
            responses_data = [
                {
                    "question_id": str(resp.question_id),
                    "response": resp.response,
                    "score": resp.score,
                    "is_correct": resp.is_correct,
                    "feedback": resp.feedback,  # Include feedback
                    "time_spent": resp.time_spent,
                    "confidence_level": resp.confidence_level,
                    "flagged_for_review": resp.flagged_for_review
                }
                for resp in responses
            ]
            
            result.append(format_attempt_response(attempt, quiz_title, responses_data))
        
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting student attempts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting student attempts: {str(e)}"
        )

@router.get("/attempts/{attempt_id}/results", response_model=AttemptResultResponse)
async def get_attempt_results(
    attempt_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed results for a specific attempt using QuizResponse table"""
    try:
        check_student_permission(current_user)
        
        # Get attempt
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.id == attempt_id,
            QuizAttempt.student_id == current_user['id']
        ).first()
        
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attempt not found"
            )
        
        # Get quiz
        quiz = db.query(Quiz).filter(Quiz.id == attempt.quiz_id).first()
        
        # Get responses with question details
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
            ORDER BY qq.order_index
        """)
        
        responses_with_questions = db.execute(query, {"attempt_id": attempt_id}).fetchall()
        
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
                "feedback": resp.feedback,  # Include stored feedback
                "time_spent": resp.time_spent,
                "confidence_level": resp.confidence_level,
                "flagged_for_review": resp.flagged_for_review
            })
        
        # Get all responses for the attempt response
        responses_data = [
            {
                "question_id": str(resp.question_id),
                "response": resp.response,
                "score": resp.score,
                "is_correct": resp.is_correct,
                "feedback": resp.feedback,  # Include stored feedback
                "time_spent": resp.time_spent,
                "confidence_level": resp.confidence_level,
                "flagged_for_review": resp.flagged_for_review
            }
            for resp in responses_with_questions
        ]
        
        attempt_response = format_attempt_response(attempt, quiz.title, responses_data)
        
        summary = {
            "total_questions": len(responses_with_questions),
            "correct_answers": correct_count,
            "total_marks": attempt.total_marks,
            "obtained_marks": attempt.obtained_marks,
            "percentage": attempt.percentage,
            "passed": attempt.percentage >= quiz.passing_marks,
            "time_taken": attempt.time_taken,
            "ai_grading_used": attempt.is_auto_graded
        }
        
        return AttemptResultResponse(
            attempt=attempt_response,
            questions_with_answers=questions_with_answers,
            summary=summary
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting attempt results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting attempt results: {str(e)}"
        )

# Additional endpoint for saving partial responses (useful for auto-save functionality)
@router.post("/{quiz_id}/save-response")
async def save_partial_response(
    quiz_id: str,
    response: QuestionResponse,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save a single question response (for auto-save functionality)"""
    try:
        check_student_permission(current_user)
        
        # Get active attempt
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == 'in_progress'
        ).first()
        
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active attempt found"
            )
        
        # Check if response already exists
        existing_response = db.query(QuizResponse).filter(
            QuizResponse.attempt_id == attempt.id,
            QuizResponse.question_id == response.question_id
        ).first()
        
        if existing_response:
            # Update existing response
            existing_response.response = response.response
            existing_response.time_spent = response.time_spent
            existing_response.confidence_level = response.confidence_level
            existing_response.flagged_for_review = response.flagged_for_review
            existing_response.updated_at = get_india_time()
        else:
            # Create new response
            new_response = QuizResponse(
                quiz_id=quiz_id,
                student_id=current_user['id'],
                question_id=response.question_id,
                attempt_id=attempt.id,
                response=response.response,
                time_spent=response.time_spent,
                confidence_level=response.confidence_level,
                flagged_for_review=response.flagged_for_review,
                answered_at=get_india_time()
            )
            db.add(new_response)
        
        db.commit()
        
        return {"message": "Response saved successfully"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error saving partial response: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving partial response: {str(e)}"
        )