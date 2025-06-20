# backend/routes/student.py - Updated for mixed question types

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from config.database import get_db
from config.security import require_student, get_current_user
from models import User, Course, CourseEnrollment, Quiz, QuizQuestion, QuizAttempt
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel

router = APIRouter(prefix="/student", tags=["student"])

# Pydantic models
class EnrollCourseRequest(BaseModel):
    course_code: str

class QuizSubmissionRequest(BaseModel):
    answers: Dict[str, str]  # question_id -> answer

# Course enrollment routes (same as before)
@router.post("/enroll")
async def enroll_in_course(
    request: EnrollCourseRequest,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Enroll in a course using course code"""
    try:
        # Find course by code
        course = db.query(Course).filter(
            Course.course_code == request.course_code,
            Course.is_active == True
        ).first()
        
        if not course:
            raise HTTPException(404, "Course not found or inactive")
        
        # Check if already enrolled
        existing_enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if existing_enrollment:
            if existing_enrollment.status == "active":
                raise HTTPException(400, "Already enrolled in this course")
            else:
                # Reactivate enrollment
                existing_enrollment.status = "active"
                existing_enrollment.enrolled_at = datetime.utcnow()
                db.commit()
                
                return {
                    "message": "Successfully re-enrolled in course",
                    "course": {
                        "id": str(course.id),
                        "course_name": course.course_name,
                        "course_code": course.course_code,
                        "teacher_name": course.teacher.full_name,
                        "board": course.board,
                        "class_level": course.class_level,
                        "subject": course.subject
                    }
                }
        
        # Check course capacity
        current_enrollments = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.status == "active"
        ).count()
        
        if current_enrollments >= course.max_students:
            raise HTTPException(400, "Course is full")
        
        # Create new enrollment
        enrollment = CourseEnrollment(
            course_id=course.id,
            student_id=current_user['id'],
            status="active"
        )
        
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)
        
        return {
            "message": "Successfully enrolled in course",
            "course": {
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "teacher_name": course.teacher.full_name,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "enrolled_at": enrollment.enrolled_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error enrolling in course: {str(e)}")

@router.get("/courses")
async def get_enrolled_courses(
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get all courses the student is enrolled in"""
    try:
        enrollments = db.query(CourseEnrollment).filter(
            CourseEnrollment.student_id == current_user['id'],
            CourseEnrollment.status == "active"
        ).order_by(desc(CourseEnrollment.enrolled_at)).all()
        
        courses = []
        for enrollment in enrollments:
            course = enrollment.course
            if course and course.is_active:
                # Get quiz count
                quiz_count = db.query(Quiz).filter(
                    Quiz.course_id == course.id,
                    Quiz.is_published == True
                ).count()
                
                # Get completed quizzes count
                completed_quizzes = db.query(QuizAttempt).filter(
                    QuizAttempt.quiz_id.in_(
                        db.query(Quiz.id).filter(Quiz.course_id == course.id)
                    ),
                    QuizAttempt.student_id == current_user['id'],
                    QuizAttempt.status == "submitted"
                ).count()
                
                courses.append({
                    "id": str(course.id),
                    "course_name": course.course_name,
                    "course_code": course.course_code,
                    "description": course.description,
                    "teacher_name": course.teacher.full_name,
                    "board": course.board,
                    "class_level": course.class_level,
                    "subject": course.subject,
                    "enrolled_at": enrollment.enrolled_at.isoformat(),
                    "total_quizzes": quiz_count,
                    "completed_quizzes": completed_quizzes,
                    "average_score": enrollment.average_score
                })
        
        return {"courses": courses}
    except Exception as e:
        raise HTTPException(500, f"Error fetching enrolled courses: {str(e)}")

@router.get("/courses/{course_id}")
async def get_course_details(
    course_id: str,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific enrolled course"""
    try:
        # Verify enrollment
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == current_user['id'],
            CourseEnrollment.status == "active"
        ).first()
        
        if not enrollment:
            raise HTTPException(404, "Course not found or not enrolled")
        
        course = enrollment.course
        
        # Get published quizzes
        quizzes = db.query(Quiz).filter(
            Quiz.course_id == course_id,
            Quiz.is_published == True
        ).order_by(desc(Quiz.created_at)).all()
        
        quiz_list = []
        for quiz in quizzes:
            # Check if student has attempted this quiz
            attempts = db.query(QuizAttempt).filter(
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.student_id == current_user['id']
            ).order_by(desc(QuizAttempt.attempt_number)).all()
            
            # Check if quiz is available (time constraints)
            is_available = True
            if quiz.start_time and datetime.utcnow() < quiz.start_time:
                is_available = False
            if quiz.end_time and datetime.utcnow() > quiz.end_time:
                is_available = False
            
            # Check if student can attempt (attempts limit)
            can_attempt = len(attempts) < quiz.attempts_allowed and is_available
            
            best_score = max([attempt.percentage for attempt in attempts]) if attempts else None
            
            quiz_list.append({
                "id": str(quiz.id),
                "title": quiz.title,
                "description": quiz.description,
                "instructions": quiz.instructions,
                "total_marks": quiz.total_marks,
                "passing_marks": quiz.passing_marks,
                "time_limit": quiz.time_limit,
                "attempts_allowed": quiz.attempts_allowed,
                "attempts_taken": len(attempts),
                "can_attempt": can_attempt,
                "is_available": is_available,
                "best_score": best_score,
                "start_time": quiz.start_time.isoformat() if quiz.start_time else None,
                "end_time": quiz.end_time.isoformat() if quiz.end_time else None
            })
        
        return {
            "course": {
                "id": str(course.id),
                "course_name": course.course_name,
                "course_code": course.course_code,
                "description": course.description,
                "teacher_name": course.teacher.full_name,
                "board": course.board,
                "class_level": course.class_level,
                "subject": course.subject,
                "enrolled_at": enrollment.enrolled_at.isoformat()
            },
            "quizzes": quiz_list,
            "performance": {
                "total_quizzes_taken": enrollment.total_quizzes_taken,
                "average_score": enrollment.average_score
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching course details: {str(e)}")

# Updated quiz taking routes to handle mixed question types
@router.get("/quizzes/{quiz_id}")
async def get_quiz_for_attempt(
    quiz_id: str,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get quiz details for taking the quiz - handles both AI and custom questions"""
    try:
        # Get quiz and verify access
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.is_published == True
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found or not published")
        
        # Verify enrollment in course
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == quiz.course_id,
            CourseEnrollment.student_id == current_user['id'],
            CourseEnrollment.status == "active"
        ).first()
        
        if not enrollment:
            raise HTTPException(403, "Not enrolled in this course")
        
        # Check time constraints
        now = datetime.utcnow()
        if quiz.start_time and now < quiz.start_time:
            raise HTTPException(400, "Quiz not yet started")
        if quiz.end_time and now > quiz.end_time:
            raise HTTPException(400, "Quiz has ended")
        
        # Check attempt limits
        attempts = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id']
        ).count()
        
        if attempts >= quiz.attempts_allowed:
            raise HTTPException(400, "Maximum attempts reached")
        
        # Check for ongoing attempt
        ongoing_attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == "in_progress"
        ).first()
        
        if ongoing_attempt:
            # Calculate remaining time
            elapsed_time = (datetime.utcnow() - ongoing_attempt.started_at).total_seconds() / 60
            remaining_time = quiz.time_limit - elapsed_time if quiz.time_limit else None
            
            if remaining_time and remaining_time <= 0:
                # Auto-submit expired quiz
                ongoing_attempt.status = "submitted"
                ongoing_attempt.submitted_at = datetime.utcnow()
                ongoing_attempt.time_taken = quiz.time_limit
                db.commit()
                raise HTTPException(400, "Quiz time expired")
        
        # Get questions (both AI and custom)
        quiz_questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz_id
        ).order_by(QuizQuestion.order_index).all()
        
        question_list = []
        for qq in quiz_questions:
            question_data = {
                "id": str(qq.id),
                "marks": qq.marks,
                "order_index": qq.order_index
            }
            
            # Handle AI questions vs custom questions
            if qq.question_source == 'ai_generated' and qq.ai_question:
                # AI-generated question
                question_data.update({
                    "question_text": qq.ai_question.question_text,
                    "question_type": qq.ai_question.type,
                    "source": "ai_generated"
                })
                
                # Include options for MCQ
                if qq.ai_question.type == "mcq" and qq.ai_question.options:
                    question_data["options"] = qq.ai_question.options
                    
            else:
                # Custom question
                question_data.update({
                    "question_text": qq.custom_question_text,
                    "question_type": qq.custom_question_type,
                    "source": "custom"
                })
                
                # Include options for MCQ
                if qq.custom_question_type == "mcq" and qq.custom_options:
                    question_data["options"] = qq.custom_options
            
            question_list.append(question_data)
        
        return {
            "quiz": {
                "id": str(quiz.id),
                "title": quiz.title,
                "description": quiz.description,
                "instructions": quiz.instructions,
                "total_marks": quiz.total_marks,
                "time_limit": quiz.time_limit,
                "attempts_taken": attempts,
                "attempts_allowed": quiz.attempts_allowed
            },
            "questions": question_list,
            "ongoing_attempt_id": str(ongoing_attempt.id) if ongoing_attempt else None
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching quiz: {str(e)}")

@router.post("/quizzes/{quiz_id}/start")
async def start_quiz_attempt(
    quiz_id: str,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Start a new quiz attempt"""
    try:
        # Verify quiz exists and is accessible
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.is_published == True
        ).first()
        
        if not quiz:
            raise HTTPException(404, "Quiz not found")
        
        # Verify enrollment
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == quiz.course_id,
            CourseEnrollment.student_id == current_user['id'],
            CourseEnrollment.status == "active"
        ).first()
        
        if not enrollment:
            raise HTTPException(403, "Not enrolled in this course")
        
        # Check if there's already an ongoing attempt
        ongoing = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == "in_progress"
        ).first()
        
        if ongoing:
            return {
                "message": "Quiz attempt already in progress",
                "attempt_id": str(ongoing.id),
                "started_at": ongoing.started_at.isoformat()
            }
        
        # Create new attempt
        attempt_number = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id']
        ).count() + 1
        
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            student_id=current_user['id'],
            attempt_number=attempt_number,
            answers={},
            total_marks=quiz.total_marks,
            status="in_progress"
        )
        
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        
        return {
            "message": "Quiz attempt started",
            "attempt_id": str(attempt.id),
            "attempt_number": attempt_number,
            "started_at": attempt.started_at.isoformat(),
            "time_limit": quiz.time_limit
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error starting quiz attempt: {str(e)}")

@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz_attempt(
    quiz_id: str,
    submission: QuizSubmissionRequest,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Submit quiz answers - handles auto-grading for both AI and custom questions"""
    try:
        # Get ongoing attempt
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == "in_progress"
        ).first()
        
        if not attempt:
            raise HTTPException(404, "No ongoing quiz attempt found")
        
        quiz = attempt.quiz
        
        # Calculate time taken
        time_taken = (datetime.utcnow() - attempt.started_at).total_seconds() / 60
        
        # Check time limit
        if quiz.time_limit and time_taken > quiz.time_limit:
            raise HTTPException(400, "Quiz time limit exceeded")
        
        # Update attempt with answers
        attempt.answers = submission.answers
        attempt.submitted_at = datetime.utcnow()
        attempt.time_taken = int(time_taken)
        attempt.status = "submitted"
        
        # Auto-grade if enabled
        if quiz.auto_grade:
            quiz_questions = db.query(QuizQuestion).filter(
                QuizQuestion.quiz_id == quiz_id
            ).all()
            
            total_score = 0
            
            for qq in quiz_questions:
                student_answer = submission.answers.get(str(qq.id), "").strip()
                
                # Get correct answer based on question source
                if qq.question_source == 'ai_generated' and qq.ai_question:
                    correct_answer = qq.ai_question.correct_answer.strip()
                    question_type = qq.ai_question.type
                else:
                    correct_answer = qq.custom_correct_answer.strip()
                    question_type = qq.custom_question_type
                
                # Auto-grade based on question type
                if question_type == "mcq":
                    # Exact match for MCQ
                    if student_answer.lower() == correct_answer.lower():
                        total_score += qq.marks
                elif question_type == "short_answer":
                    # Simple text matching for short answers
                    if student_answer.lower() == correct_answer.lower():
                        total_score += qq.marks
                # Essay questions need manual grading, so they get 0 for auto-grading
            
            attempt.obtained_marks = total_score
            attempt.percentage = (total_score / quiz.total_marks) * 100 if quiz.total_marks > 0 else 0
            attempt.is_auto_graded = True
        
        db.commit()
        
        # Update enrollment statistics
        enrollment = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == quiz.course_id,
            CourseEnrollment.student_id == current_user['id']
        ).first()
        
        if enrollment:
            enrollment.total_quizzes_taken += 1
            
            # Recalculate average score
            all_attempts = db.query(QuizAttempt).filter(
                QuizAttempt.student_id == current_user['id'],
                QuizAttempt.quiz_id.in_(
                    db.query(Quiz.id).filter(Quiz.course_id == quiz.course_id)
                ),
                QuizAttempt.status == "submitted"
            ).all()
            
            if all_attempts:
                total_percentage = sum(a.percentage for a in all_attempts if a.percentage is not None)
                enrollment.average_score = total_percentage / len(all_attempts)
            
            db.commit()
        
        return {
            "message": "Quiz submitted successfully",
            "attempt": {
                "id": str(attempt.id),
                "obtained_marks": attempt.obtained_marks,
                "total_marks": attempt.total_marks,
                "percentage": attempt.percentage,
                "time_taken": attempt.time_taken,
                "is_auto_graded": attempt.is_auto_graded,
                "submitted_at": attempt.submitted_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error submitting quiz: {str(e)}")

@router.get("/quiz-attempts")
async def get_quiz_attempts(
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db),
    course_id: Optional[str] = None
):
    """Get all quiz attempts by the student"""
    try:
        query = db.query(QuizAttempt).filter(
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == "submitted"
        )
        
        if course_id:
            query = query.join(Quiz).filter(Quiz.course_id == course_id)
        
        attempts = query.order_by(desc(QuizAttempt.submitted_at)).all()
        
        attempt_list = []
        for attempt in attempts:
            quiz = attempt.quiz
            attempt_list.append({
                "id": str(attempt.id),
                "quiz_title": quiz.title,
                "course_name": quiz.course.course_name,
                "attempt_number": attempt.attempt_number,
                "obtained_marks": attempt.obtained_marks,
                "total_marks": attempt.total_marks,
                "percentage": attempt.percentage,
                "time_taken": attempt.time_taken,
                "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
                "is_auto_graded": attempt.is_auto_graded,
                "teacher_reviewed": attempt.teacher_reviewed
            })
        
        return {"attempts": attempt_list}
    except Exception as e:
        raise HTTPException(500, f"Error fetching quiz attempts: {str(e)}")

@router.get("/quiz-attempts/{attempt_id}")
async def get_quiz_attempt_details(
    attempt_id: str,
    current_user: dict = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get detailed results of a specific quiz attempt with mixed question types"""
    try:
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.id == attempt_id,
            QuizAttempt.student_id == current_user['id'],
            QuizAttempt.status == "submitted"
        ).first()
        
        if not attempt:
            raise HTTPException(404, "Quiz attempt not found")
        
        quiz = attempt.quiz
        quiz_questions = db.query(QuizQuestion).filter(
            QuizQuestion.quiz_id == quiz.id
        ).order_by(QuizQuestion.order_index).all()
        
        question_results = []
        for qq in quiz_questions:
            student_answer = attempt.answers.get(str(qq.id), "")
            
            # Build question result based on source type
            if qq.question_source == 'ai_generated' and qq.ai_question:
                # AI-generated question
                question_result = {
                    "question_text": qq.ai_question.question_text,
                    "question_type": qq.ai_question.type,
                    "marks": qq.marks,
                    "student_answer": student_answer,
                    "source": "ai_generated",
                    "correct_answer": qq.ai_question.correct_answer if attempt.is_auto_graded or attempt.teacher_reviewed else None,
                    "explanation": qq.ai_question.explanation if attempt.is_auto_graded or attempt.teacher_reviewed else None
                }
                
                if qq.ai_question.type == "mcq" and qq.ai_question.options:
                    question_result["options"] = qq.ai_question.options
                    
            else:
                # Custom question
                question_result = {
                    "question_text": qq.custom_question_text,
                    "question_type": qq.custom_question_type,
                    "marks": qq.marks,
                    "student_answer": student_answer,
                    "source": "custom",
                    "correct_answer": qq.custom_correct_answer if attempt.is_auto_graded or attempt.teacher_reviewed else None,
                    "explanation": qq.custom_explanation if attempt.is_auto_graded or attempt.teacher_reviewed else None
                }
                
                if qq.custom_question_type == "mcq" and qq.custom_options:
                    question_result["options"] = qq.custom_options
            
            question_results.append(question_result)
        
        return {
            "attempt": {
                "id": str(attempt.id),
                "quiz_title": quiz.title,
                "course_name": quiz.course.course_name,
                "teacher_name": quiz.teacher.full_name,
                "attempt_number": attempt.attempt_number,
                "obtained_marks": attempt.obtained_marks,
                "total_marks": attempt.total_marks,
                "percentage": attempt.percentage,
                "time_taken": attempt.time_taken,
                "submitted_at": attempt.submitted_at.isoformat(),
                "is_auto_graded": attempt.is_auto_graded,
                "teacher_reviewed": attempt.teacher_reviewed
            },
            "questions": question_results
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching attempt details: {str(e)}")