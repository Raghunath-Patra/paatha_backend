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
    started_at: datetime
    submitted_at: Optional[datetime]
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

# Modified submit_quiz endpoint to remove immediate grading
# Add this to replace the existing submit_quiz function in student_quizzes.py

@router.post("/{quiz_id}/submit", response_model=AttemptResultResponse)
async def submit_quiz(
    quiz_id: str,
    submission: QuizSubmission,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit quiz answers - saves responses for later auto-grading"""
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
        
        # Save responses WITHOUT grading (will be graded later by auto-grading service)
        max_possible_score = sum(q.marks for q in questions)
        questions_with_answers = []
        
        for question in questions:
            question_id = str(question.id)
            
            # Get student response
            student_response = responses_dict.get(question_id)
            student_answer = student_response.response if student_response else ""
            correct_answer = question.correct_answer
            
            # Create QuizResponse record WITHOUT scoring/grading
            quiz_response = QuizResponse(
                quiz_id=quiz_id,
                student_id=current_user['id'],
                question_id=question.id,
                attempt_id=attempt.id,
                response=student_answer,
                score=None,  # Will be set by auto-grading
                is_correct=None,  # Will be set by auto-grading
                feedback=None,  # Will be set by auto-grading
                time_spent=student_response.time_spent if student_response else None,   # Calculate time spent
                confidence_level=student_response.confidence_level if student_response else None,
                flagged_for_review=student_response.flagged_for_review if student_response else False,
                answered_at=get_india_time()
            )
            
            db.add(quiz_response)
            
            # Prepare response data for immediate return
            questions_with_answers.append({
                "question_id": question_id,
                "question_text": question.question_text,
                "question_type": question.question_type,
                "options": question.options,
                "student_answer": student_answer,
                "correct_answer": correct_answer,  # Show for immediate feedback
                "explanation": question.explanation,
                "marks": question.marks,
                "score": None,  # Not graded yet
                "is_correct": None,  # Not graded yet
                "feedback": "Your answer has been submitted and will be graded automatically.",
                "time_spent": student_response.time_spent if student_response else None,
                "confidence_level": student_response.confidence_level if student_response else None,
                "flagged_for_review": student_response.flagged_for_review if student_response else False
            })
        
        # Calculate time taken
        time_taken = None
        if attempt.started_at:
            started_at = ensure_india_timezone(attempt.started_at)
            now = get_india_time()
            time_taken = int((now - started_at).total_seconds() / 60)
        
        # Update attempt - mark as completed but not graded
        attempt.obtained_marks = 0.0  # Will be updated by auto-grading
        attempt.percentage = 0.0  # Will be updated by auto-grading
        attempt.submitted_at = get_india_time()
        attempt.time_taken = time_taken
        attempt.status = 'completed'
        attempt.is_auto_graded = False  # Will be set to True by auto-grading
        attempt.teacher_reviewed = False  # Will be set to True by auto-grading
        
        db.commit()
        db.refresh(attempt)
        
        # Update course enrollment stats
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == quiz.course_id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if enrollment:
            enrollment.total_quizzes_taken += 1
            db.commit()
        
        # Prepare response data for submission confirmation
        responses_data = [
            {
                "question_id": qa["question_id"],
                "response": qa["student_answer"],
                "score": None,  # Not graded yet
                "is_correct": None,  # Not graded yet
                "feedback": "Submitted - awaiting auto-grading",
                "time_spent": qa["time_spent"],
                "confidence_level": qa["confidence_level"],
                "flagged_for_review": qa["flagged_for_review"]
            }
            for qa in questions_with_answers
        ]
        
        # Prepare response
        attempt_response = format_attempt_response(attempt, quiz.title, responses_data)
        
        # Determine when grading will happen
        grading_message = "Your quiz has been submitted successfully!"
        if quiz.auto_grade:
            if quiz.end_time:
                grading_message += f" It will be automatically graded after the quiz ends on {quiz.end_time.strftime('%Y-%m-%d %H:%M')}."
            else:
                grading_message += " It will be automatically graded shortly."
        else:
            grading_message += " Your teacher will grade it manually."
        
        summary = {
            "total_questions": len(questions),
            "submitted_answers": len([qa for qa in questions_with_answers if qa["student_answer"].strip()]),
            "total_marks": max_possible_score,
            "obtained_marks": 0.0,  # Not graded yet, will be updated
            "percentage": 0.0,  # Not graded yet, will be updated
            "time_taken": time_taken,
            "grading_status": "pending",
            "grading_message": grading_message,
            "auto_grading_enabled": quiz.auto_grade
        }
        
        logger.info(f"Quiz submission completed by user {current_user['id']}: "
                   f"{len(responses_list)} responses submitted, awaiting auto-grading")
        
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

@router.get("/attempts/{attempt_id}/results", response_model=AttemptResultResponse)
async def get_attempt_results(
    attempt_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed results for a specific attempt - with auto-grading status handling"""
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
        
        # Get quiz with end time
        quiz = db.query(Quiz).filter(Quiz.id == attempt.quiz_id).first()
        
        # Check grading status and quiz timing
        now = get_india_time()
        quiz_ended = quiz.end_time and now > ensure_india_timezone(quiz.end_time)
        is_graded = attempt.is_auto_graded or attempt.teacher_reviewed
        
        # Determine current status
        if attempt.status != 'completed':
            # Quiz not submitted yet
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quiz not completed yet"
            )
        
        # Get responses count for basic info
        total_responses = db.query(QuizResponse).filter(
            QuizResponse.attempt_id == attempt.id
        ).count()
        
        # CASE 1: Quiz ended and graded - show full results
        if is_graded:
            return await _get_full_attempt_results(attempt_id, quiz, attempt, current_user, db)
        
        # CASE 2: Quiz ended but not graded yet - show waiting message
        elif quiz_ended and not is_graded:
            return _get_pending_grading_results(attempt, quiz, total_responses)
        
        # CASE 3: Quiz still active - show waiting message
        else:
            return _get_quiz_active_results(attempt, quiz, total_responses)
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting attempt results: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting attempt results: {str(e)}"
        )

async def _get_full_attempt_results(attempt_id: str, quiz, attempt, current_user: Dict, db: Session):
    """Get complete results when grading is finished"""
    
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
            "feedback": resp.feedback,
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
            "feedback": resp.feedback,
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
        "passed": attempt.obtained_marks >= quiz.passing_marks,
        "time_taken": attempt.time_taken,
        "ai_grading_used": attempt.is_auto_graded,
        "grading_status": "completed",
        "grading_message": f"Quiz graded! You scored {attempt.obtained_marks}/{attempt.total_marks} ({attempt.percentage:.1f}%)"
    }
    
    return AttemptResultResponse(
        attempt=attempt_response,
        questions_with_answers=questions_with_answers,
        summary=summary
    )

def _get_pending_grading_results(attempt, quiz, total_responses: int):
    """Return waiting message when quiz ended but grading is pending"""
    
    # Estimate grading completion
    now = get_india_time()
    
    # Create minimal attempt response
    attempt_response = AttemptResponse(
        id=str(attempt.id),
        quiz_id=str(attempt.quiz_id),
        quiz_title=quiz.title,
        attempt_number=attempt.attempt_number,
        obtained_marks=0.0,  # Hidden until graded
        total_marks=attempt.total_marks,
        percentage=0.0,  # Hidden until graded
        started_at=attempt.started_at.isoformat(),
        submitted_at=attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        time_taken=attempt.time_taken,
        status=attempt.status,
        is_auto_graded=attempt.is_auto_graded,
        teacher_reviewed=attempt.teacher_reviewed,
        responses=[]  # Hide responses until graded
    )
    
    # Create waiting message
    grading_message = "🤖 Your quiz is being graded automatically! "
    if quiz.auto_grade:
        grading_message += "Results will be available shortly. The AI is currently reviewing your answers."
    else:
        grading_message += "Your teacher will grade it manually."
    
    questions_with_answers = [{
        "message": "Quiz submitted successfully! ✅",
        "details": f"Your {total_responses} answers have been submitted and are currently being graded.",
        "status": "pending_grading",
        "estimated_completion": "Results typically available within 10-15 minutes after quiz ends"
    }]
    
    summary = {
        "total_questions": total_responses,
        "submitted_answers": total_responses,
        "total_marks": attempt.total_marks,
        "obtained_marks": "⏳ Grading in progress...",
        "percentage": "⏳ Grading in progress...",
        "time_taken": attempt.time_taken,
        "grading_status": "pending",
        "grading_message": grading_message,
        "auto_grading_enabled": quiz.auto_grade,
        "show_results": False
    }
    
    return AttemptResultResponse(
        attempt=attempt_response,
        questions_with_answers=questions_with_answers,
        summary=summary
    )

def _get_quiz_active_results(attempt, quiz, total_responses: int):
    """Return waiting message when quiz is still active"""
    
    now = get_india_time()
    time_until_end = None
    
    if quiz.end_time:
        end_time = ensure_india_timezone(quiz.end_time)
        if now < end_time:
            time_until_end = int((end_time - now).total_seconds() / 60)
    
    # Create minimal attempt response
    attempt_response = AttemptResponse(
        id=str(attempt.id),
        quiz_id=str(attempt.quiz_id),
        quiz_title=quiz.title,
        attempt_number=attempt.attempt_number,
        obtained_marks=0.0,  # Hidden until quiz ends and graded
        total_marks=attempt.total_marks,
        percentage=0.0,  # Hidden until quiz ends and graded
        started_at=attempt.started_at.isoformat(),
        submitted_at=attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        time_taken=attempt.time_taken,
        status=attempt.status,
        is_auto_graded=False,
        teacher_reviewed=False,
        responses=[]  # Hide responses until quiz ends
    )
    
    # Create waiting message based on quiz timing
    if time_until_end:
        grading_message = f"⏰ Quiz is still active! Results will be available after the quiz ends in {time_until_end} minutes."
        if quiz.auto_grade:
            grading_message += " Your quiz will be automatically graded once the time limit expires."
    else:
        grading_message = "⏰ Quiz is still active! Results will be available after the quiz ends."
    
    questions_with_answers = [{
        "message": "Quiz submitted successfully! ✅",
        "details": f"Your {total_responses} answers have been saved.",
        "status": "quiz_active",
        "waiting_reason": f"Quiz ends on {quiz.end_time.strftime('%Y-%m-%d at %H:%M')} (India time)" if quiz.end_time else "Quiz has no end time set",
        "time_remaining": f"{time_until_end} minutes" if time_until_end else "Unknown"
    }]
    
    summary = {
        "total_questions": total_responses,
        "submitted_answers": total_responses,
        "total_marks": attempt.total_marks,
        "obtained_marks": "⏰ Quiz still active",
        "percentage": "⏰ Quiz still active",
        "time_taken": attempt.time_taken,
        "grading_status": "quiz_active",
        "grading_message": grading_message,
        "auto_grading_enabled": quiz.auto_grade,
        "show_results": False,
        "time_until_end": time_until_end
    }
    
    return AttemptResultResponse(
        attempt=attempt_response,
        questions_with_answers=questions_with_answers,
        summary=summary
    )

@router.get("/attempts/my-attempts", response_model=List[AttemptResponse])
async def get_my_attempts(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all quiz attempts for the current student - with grading status awareness"""
    try:
        check_student_permission(current_user)
        
        # Get attempts with quiz info and grading status
        query = text("""
            SELECT 
                qa.*,
                q.title as quiz_title,
                q.end_time,
                q.auto_grade,
                q.passing_marks
            FROM quiz_attempts qa
            JOIN quizzes q ON qa.quiz_id = q.id
            WHERE qa.student_id = :student_id
            ORDER BY qa.started_at DESC
        """)
        
        attempts = db.execute(query, {"student_id": current_user['id']}).fetchall()
        
        result = []
        now = get_india_time()
        
        for attempt in attempts:
            # Check grading status
            quiz_ended = attempt.end_time and now > ensure_india_timezone(attempt.end_time)
            is_graded = attempt.is_auto_graded or attempt.teacher_reviewed
            
            # Get response count for this attempt
            response_count = db.query(QuizResponse).filter(
                QuizResponse.attempt_id == attempt.id
            ).count()
            
            # Determine what to show based on status
            if attempt.status != 'completed':
                # Incomplete attempt
                display_marks = 0.0
                display_percentage = 0.0
                responses_data = []
                status_message = "Incomplete"
                
            elif is_graded:
                # Fully graded - show real results
                display_marks = attempt.obtained_marks
                display_percentage = attempt.percentage
                
                # Get actual responses for graded attempts
                responses = db.query(QuizResponse).filter(
                    QuizResponse.attempt_id == attempt.id
                ).all()
                
                responses_data = [
                    {
                        "question_id": str(resp.question_id),
                        "response": resp.response,
                        "score": resp.score,
                        "is_correct": resp.is_correct,
                        "feedback": resp.feedback,
                        "time_spent": resp.time_spent,
                        "confidence_level": resp.confidence_level,
                        "flagged_for_review": resp.flagged_for_review
                    }
                    for resp in responses
                ]
                
                # Check if passed
                passed = attempt.obtained_marks >= attempt.passing_marks
                status_message = f"Graded - {'Passed' if passed else 'Failed'} ({attempt.percentage:.1f}%)"
                
            elif quiz_ended and not is_graded:
                # Quiz ended but grading pending
                display_marks = 0.0
                display_percentage = 0.0
                responses_data = []
                status_message = "⏳ Grading in progress..."
                
            else:
                # Quiz still active
                display_marks = 0.0
                display_percentage = 0.0
                responses_data = []
                if attempt.end_time:
                    time_left = int((ensure_india_timezone(attempt.end_time) - now).total_seconds() / 60)
                    status_message = f"⏰ Quiz active ({time_left}min left)" if time_left > 0 else "⏰ Quiz ended, grading soon"
                else:
                    status_message = "⏰ Quiz active"
            
            attempt_response = AttemptResponse(
                id=str(attempt.id),
                quiz_id=str(attempt.quiz_id),
                quiz_title=attempt.quiz_title,
                attempt_number=attempt.attempt_number,
                obtained_marks=display_marks,
                total_marks=attempt.total_marks,
                percentage=display_percentage,
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at if attempt.submitted_at else None,
                time_taken=attempt.time_taken,
                status=status_message,  # Enhanced status with grading info
                is_auto_graded=attempt.is_auto_graded,
                teacher_reviewed=attempt.teacher_reviewed,
                responses=responses_data
            )
            
            result.append(attempt_response)
        
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting student attempts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting student attempts: {str(e)}"
        )

# Enhanced grading status endpoint
@router.get("/attempts/{attempt_id}/grading-status")
async def get_grading_status(
    attempt_id: str,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check the grading status of a quiz attempt - enhanced version"""
    try:
        check_student_permission(current_user)
        
        # Get attempt with quiz info
        query = text("""
            SELECT 
                qa.*,
                q.title as quiz_title,
                q.end_time,
                q.auto_grade,
                q.passing_marks
            FROM quiz_attempts qa
            JOIN quizzes q ON qa.quiz_id = q.id
            WHERE qa.id = :attempt_id AND qa.student_id = :student_id
        """)
        
        result = db.execute(query, {
            "attempt_id": attempt_id,
            "student_id": current_user['id']
        }).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attempt not found"
            )
        
        # Check timing and grading status
        now = get_india_time()
        quiz_ended = result.end_time and now > ensure_india_timezone(result.end_time)
        is_graded = result.is_auto_graded or result.teacher_reviewed
        
        # Calculate time estimates
        time_until_end = None
        estimated_grading_completion = None
        
        if result.end_time:
            end_time = ensure_india_timezone(result.end_time)
            if now < end_time:
                time_until_end = int((end_time - now).total_seconds() / 60)
            elif not is_graded:
                # Quiz ended, estimate grading completion (10-15 minutes after end)
                estimated_completion = end_time + timedelta(minutes=15)
                if now < estimated_completion:
                    estimated_grading_completion = int((estimated_completion - now).total_seconds() / 60)
        
        # Determine status and message
        if result.status != 'completed':
            status = "incomplete"
            message = "Quiz not submitted yet"
        elif quiz_ended and is_graded:
            status = "graded"
            passed = result.obtained_marks >= result.passing_marks
            message = f"✅ Graded! Score: {result.obtained_marks}/{result.total_marks} ({result.percentage:.1f}%) - {'Passed' if passed else 'Failed'}"
        elif quiz_ended and not is_graded:
            status = "pending_grading"
            if result.auto_grade:
                message = "🤖 Auto-grading in progress... Results will be available soon!"
            else:
                message = "👨‍🏫 Waiting for teacher to grade manually"
        else:
            status = "quiz_active"
            if time_until_end:
                message = f"⏰ Quiz is still active. Results will be available {time_until_end} minutes after quiz ends."
            else:
                message = "⏰ Quiz is still active. Results will be available after quiz ends."
        
        grading_status = {
            "attempt_id": attempt_id,
            "quiz_title": result.quiz_title,
            "status": status,
            "submitted_at": result.submitted_at.isoformat() if result.submitted_at else None,
            "is_graded": is_graded,
            "auto_graded": result.is_auto_graded,
            "teacher_reviewed": result.teacher_reviewed,
            "obtained_marks": result.obtained_marks if is_graded else None,
            "percentage": result.percentage if is_graded else None,
            "total_marks": result.total_marks,
            "message": message,
            "quiz_ended": quiz_ended,
            "time_until_end": time_until_end,
            "estimated_grading_completion": estimated_grading_completion,
            "can_view_results": quiz_ended and is_graded,
            "quiz_end_time": result.end_time if result.end_time else None
        }
        
        return grading_status
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting grading status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting grading status: {str(e)}"
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