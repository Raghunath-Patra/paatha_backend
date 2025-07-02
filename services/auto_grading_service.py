# services/auto_grading_service.py - Automatic Quiz Grading Service

from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, List, Tuple
import logging
import traceback
from openai import OpenAI
import os
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

class AutoGradingService:
    """Service to automatically grade quizzes after end time using teacher's tokens"""
    
    @staticmethod
    def find_quizzes_to_grade(db: Session) -> List[Dict]:
        """Find quizzes that have ended and need auto-grading"""
        try:
            current_time = get_india_time()
            
            # Find quizzes that:
            # 1. Have ended (end_time < current_time)
            # 2. Have auto_grade = true
            # 3. Are published
            # 4. Haven't been auto-graded yet (we'll track this with a flag)
            query = text("""
                SELECT 
                    q.id as quiz_id,
                    q.title,
                    q.course_id,
                    q.teacher_id,
                    q.end_time,
                    q.auto_grade,
                    q.total_marks,
                    c.course_name,
                    u.full_name as teacher_name,
                    u.email as teacher_email,
                    COALESCE(q.auto_graded_at, NULL) as auto_graded_at
                FROM quizzes q
                JOIN courses c ON q.course_id = c.id
                JOIN profiles u ON q.teacher_id = u.id
                WHERE q.end_time < :current_time
                  AND q.auto_grade = true
                  AND q.is_published = true
                  AND q.auto_graded_at IS NULL
                ORDER BY q.end_time ASC
            """)
            
            result = db.execute(query, {"current_time": current_time}).fetchall()
            
            quizzes_to_grade = []
            for row in result:
                quizzes_to_grade.append({
                    "quiz_id": str(row.quiz_id),
                    "title": row.title,
                    "course_id": str(row.course_id),
                    "teacher_id": str(row.teacher_id),
                    "teacher_name": row.teacher_name,
                    "teacher_email": row.teacher_email,
                    "course_name": row.course_name,
                    "end_time": row.end_time,
                    "total_marks": row.total_marks
                })
            
            logger.info(f"Found {len(quizzes_to_grade)} quizzes that need auto-grading")
            return quizzes_to_grade
            
        except Exception as e:
            logger.error(f"Error finding quizzes to grade: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    @staticmethod
    def find_ungraded_submissions(quiz_id: str, db: Session) -> List[Dict]:
        """Find quiz submissions that need grading"""
        try:
            # Find attempts that are completed but not yet graded by teacher
            query = text("""
                SELECT 
                    qa.id as attempt_id,
                    qa.student_id,
                    qa.quiz_id,
                    qa.submitted_at,
                    qa.status,
                    qa.is_auto_graded,
                    qa.teacher_reviewed,
                    s.full_name as student_name,
                    s.email as student_email
                FROM quiz_attempts qa
                JOIN profiles s ON qa.student_id = s.id
                WHERE qa.quiz_id = :quiz_id
                  AND qa.status = 'completed'
                  AND qa.submitted_at IS NOT NULL
                  AND (qa.is_auto_graded = false OR qa.is_auto_graded IS NULL)
                ORDER BY qa.submitted_at ASC
            """)
            
            result = db.execute(query, {"quiz_id": quiz_id}).fetchall()
            
            submissions = []
            for row in result:
                submissions.append({
                    "attempt_id": str(row.attempt_id),
                    "student_id": str(row.student_id),
                    "student_name": row.student_name,
                    "student_email": row.student_email,
                    "submitted_at": row.submitted_at
                })
            
            logger.info(f"Found {len(submissions)} ungraded submissions for quiz {quiz_id}")
            return submissions
            
        except Exception as e:
            logger.error(f"Error finding ungraded submissions for quiz {quiz_id}: {str(e)}")
            return []
    
    @staticmethod
    def grade_quiz_submission(attempt_id: str, teacher_id: str, db: Session) -> Dict:
        """Grade a single quiz submission using teacher's tokens"""
        try:
            # Get all responses for this attempt with question details
            query = text("""
                SELECT 
                    qr.id as response_id,
                    qr.question_id,
                    qr.response,
                    qr.score,
                    qr.is_correct,
                    qr.feedback,
                    qq.marks,
                    COALESCE(q.correct_answer, qq.custom_correct_answer) as correct_answer,
                    COALESCE(q.question_text, qq.custom_question_text) as question_text,
                    COALESCE(q.type, qq.custom_question_type) as question_type,
                    COALESCE(q.explanation, qq.custom_explanation) as explanation
                FROM quiz_responses qr
                JOIN quiz_questions qq ON qr.question_id = qq.id
                LEFT JOIN questions q ON qq.ai_question_id = q.id
                WHERE qr.attempt_id = :attempt_id
                  AND (qr.score IS NULL OR qr.is_correct IS NULL)
                ORDER BY qq.order_index
            """)
            
            responses = db.execute(query, {"attempt_id": attempt_id}).fetchall()
            
            if not responses:
                logger.info(f"No ungraded responses found for attempt {attempt_id}")
                return {"graded_count": 0, "total_score": 0, "token_usage": 0}
            
            total_score = 0
            graded_count = 0
            total_ai_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
            
            for response in responses:
                student_answer = response.response or ""
                correct_answer = response.correct_answer
                question_text = response.question_text
                question_type = response.question_type
                max_marks = response.marks
                
                # Grade based on question type
                if question_type.lower() in ['mcq', 'multiple_choice', 'true/false']:
                    # MCQ/True-False: Direct comparison
                    is_correct = AutoGradingService._grade_mcq_answer(student_answer, correct_answer)
                    score = max_marks if is_correct else 0
                    feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {correct_answer}"
                    ai_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
                else:
                    # Text answers: Use AI grading with teacher's tokens
                    if student_answer.strip():
                        try:
                            score, feedback, ai_usage = AutoGradingService._grade_text_answer_with_ai(
                                student_answer, question_text, correct_answer, max_marks
                            )
                            is_correct = score >= (max_marks * 0.4) # 40% threshold for correctness
                            
                            # Accumulate AI token usage
                            total_ai_usage['prompt_tokens'] += ai_usage.get('prompt_tokens', 0)
                            total_ai_usage['completion_tokens'] += ai_usage.get('completion_tokens', 0)
                            total_ai_usage['total_tokens'] += ai_usage.get('total_tokens', 0)
                            
                        except Exception as ai_error:
                            logger.error(f"AI grading error for response {response.response_id}: {str(ai_error)}")
                            # Fallback to basic comparison
                            is_correct = AutoGradingService._grade_mcq_answer(student_answer, correct_answer)
                            score = max_marks if is_correct else 0
                            feedback = f"Auto-grading completed. Score: {score}/{max_marks}"
                            ai_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
                    else:
                        score = 0
                        feedback = "No answer provided"
                        is_correct = False
                        ai_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
                
                # Update quiz response with grade
                update_query = text("""
                    UPDATE quiz_responses
                    SET 
                        score = :score,
                        is_correct = :is_correct,
                        feedback = :feedback,
                        auto_graded_at = :graded_at
                    WHERE id = :response_id
                """)
                
                db.execute(update_query, {
                    "score": score,
                    "is_correct": is_correct,
                    "feedback": feedback,
                    "graded_at": get_india_time(),
                    "response_id": response.response_id
                })
                
                total_score += score
                graded_count += 1
            
            # Update teacher's token usage using existing consolidated service
            if total_ai_usage['total_tokens'] > 0:
                from services.consolidated_user_service import consolidated_service
                success = consolidated_service.update_user_usage(
                    user_id=teacher_id,
                    question_id=str(attempt_id),  # Use attempt_id as reference
                    input_tokens=total_ai_usage.get('prompt_tokens', 0),
                    output_tokens=total_ai_usage.get('completion_tokens', 0),
                    question_submitted=False  # This is grading, not a new question
                )
                
                if not success:
                    logger.warning(f"Failed to update token usage for teacher {teacher_id}")
                else:
                    logger.info(f"Updated teacher {teacher_id} tokens: input={total_ai_usage.get('prompt_tokens', 0)}, output={total_ai_usage.get('completion_tokens', 0)}")
            
            logger.info(f"Graded {graded_count} responses for attempt {attempt_id}, total score: {total_score}")
            
            return {
                "graded_count": graded_count,
                "total_score": total_score,
                "token_usage": total_ai_usage['total_tokens']
            }
            
        except Exception as e:
            logger.error(f"Error grading submission {attempt_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return {"graded_count": 0, "total_score": 0, "token_usage": 0}
    
    @staticmethod
    def _grade_mcq_answer(student_answer: str, correct_answer: str) -> bool:
        """Grade MCQ answer with multiple comparison strategies"""
        if not student_answer or not correct_answer:
            return False
        
        student_clean = str(student_answer).strip().lower()
        correct_clean = str(correct_answer).strip().lower()
        
        # Multiple comparison strategies
        exact_match = student_clean == correct_clean
        contains_match = correct_clean in student_clean or student_clean in correct_clean
        
        return exact_match or contains_match
    
    @staticmethod
    def _grade_text_answer_with_ai(student_answer: str, question_text: str, correct_answer: str, max_marks: int) -> Tuple[float, str, dict]:
        """Grade text answer using AI with specific marks allocation"""
        prompt = f"""
        Grade this quiz answer for a student:

        Question: "{question_text}"
        Student's Answer: "{student_answer}"
        Correct/Sample Answer: "{correct_answer}"
        Maximum Marks: {max_marks}

        Instructions:
        1. Evaluate the student's answer against the correct answer
        2. Consider partial credit for partially correct answers
        3. Be fair but accurate in grading
        4. Give marks out of {max_marks}
        
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
                temperature=0.3  # Lower temperature for consistent grading
            )

            content = response.choices[0].message.content.strip()
            score, feedback = AutoGradingService._parse_ai_grading_response(content, max_marks)
            
            # Convert usage to dict format
            usage_dict = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            
            return score, feedback, usage_dict
            
        except Exception as e:
            logger.error(f"Error in AI grading: {str(e)}")
            return 0.0, f"Auto-grading error: {str(e)}", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    
    @staticmethod
    def _parse_ai_grading_response(response_content: str, max_marks: int) -> Tuple[float, str]:
        """Parse AI grading response"""
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
                score = min(score, max_marks)  # Ensure score doesn't exceed max_marks
            except (ValueError, IndexError):
                score = 0.0
        
        # Extract feedback
        feedback_match = re.search(r"Feedback:\s*(.*?)(?:\n|$)", response_content, re.IGNORECASE | re.DOTALL)
        if feedback_match:
            feedback = feedback_match.group(1).strip()
        else:
            feedback = response_content
        
        return score, feedback
    
    @staticmethod
    def update_attempt_final_score(attempt_id: str, db: Session):
        """Calculate and update final score for quiz attempt"""
        try:
            # Calculate total score from all responses
            score_query = text("""
                SELECT 
                    SUM(COALESCE(qr.score, 0)) as total_score,
                    COUNT(qr.id) as total_responses,
                    qa.total_marks
                FROM quiz_responses qr
                JOIN quiz_attempts qa ON qr.attempt_id = qa.id
                WHERE qr.attempt_id = :attempt_id
                GROUP BY qa.total_marks
            """)
            
            result = db.execute(score_query, {"attempt_id": attempt_id}).fetchone()
            
            if result:
                total_score = result.total_score or 0
                total_marks = result.total_marks
                percentage = (total_score / total_marks * 100) if total_marks > 0 else 0
                
                # Update quiz attempt
                update_query = text("""
                    UPDATE quiz_attempts
                    SET 
                        obtained_marks = :obtained_marks,
                        percentage = :percentage,
                        is_auto_graded = true,
                        teacher_reviewed = true,
                        auto_graded_at = :graded_at
                    WHERE id = :attempt_id
                """)
                
                db.execute(update_query, {
                    "obtained_marks": total_score,
                    "percentage": percentage,
                    "graded_at": get_india_time(),
                    "attempt_id": attempt_id
                })
                
                logger.info(f"Updated final score for attempt {attempt_id}: {total_score}/{total_marks} ({percentage:.1f}%)")
                
                return {"total_score": total_score, "percentage": percentage}
            
        except Exception as e:
            logger.error(f"Error updating final score for attempt {attempt_id}: {str(e)}")
            return None
    
    @staticmethod
    def mark_quiz_as_graded(quiz_id: str, db: Session):
        """Mark quiz as auto-graded"""
        try:
            update_query = text("""
                UPDATE quizzes
                SET auto_graded_at = :graded_at
                WHERE id = :quiz_id
            """)
            
            db.execute(update_query, {
                "graded_at": get_india_time(),
                "quiz_id": quiz_id
            })
            
            # Commit all changes
            db.commit()
            logger.info(f"Marked quiz {quiz_id} as auto-graded")
            
        except Exception as e:
            logger.error(f"Error marking quiz {quiz_id} as graded: {str(e)}")
    
    @staticmethod
    def process_quiz_auto_grading(quiz_info: Dict, db: Session) -> Dict:
        """Process auto-grading for a single quiz"""
        try:
            quiz_id = quiz_info["quiz_id"]
            teacher_id = quiz_info["teacher_id"]
            
            logger.info(f"Starting auto-grading for quiz {quiz_id} ({quiz_info['title']})")
            
            # Find ungraded submissions
            submissions = AutoGradingService.find_ungraded_submissions(quiz_id, db)
            
            if not submissions:
                logger.info(f"No ungraded submissions found for quiz {quiz_id}")
                AutoGradingService.mark_quiz_as_graded(quiz_id, db)
                return {"quiz_id": quiz_id, "graded_submissions": 0, "total_tokens": 0}
            
            total_tokens_used = 0
            graded_submissions = 0
            
            for submission in submissions:
                attempt_id = submission["attempt_id"]
                
                # Grade the submission
                grading_result = AutoGradingService.grade_quiz_submission(attempt_id, teacher_id, db)
                
                if grading_result["graded_count"] > 0:
                    # Update final score
                    AutoGradingService.update_attempt_final_score(attempt_id, db)
                    graded_submissions += 1
                    total_tokens_used += grading_result["token_usage"]
            
            # Mark quiz as graded
            AutoGradingService.mark_quiz_as_graded(quiz_id, db)
            
            # Commit all changes
            db.commit()
            
            logger.info(f"Completed auto-grading for quiz {quiz_id}: {graded_submissions} submissions graded, {total_tokens_used} tokens used")
            
            return {
                "quiz_id": quiz_id,
                "quiz_title": quiz_info["title"],
                "teacher_name": quiz_info["teacher_name"],
                "graded_submissions": graded_submissions,
                "total_tokens": total_tokens_used
            }
            
        except Exception as e:
            logger.error(f"Error processing auto-grading for quiz {quiz_info['quiz_id']}: {str(e)}")
            logger.error(traceback.format_exc())
            db.rollback()
            return {"quiz_id": quiz_info["quiz_id"], "graded_submissions": 0, "total_tokens": 0, "error": str(e)}
    
    @staticmethod
    def run_auto_grading_batch(db: Session) -> Dict:
        """Run auto-grading for all eligible quizzes"""
        try:
            logger.info("Starting auto-grading batch process")
            
            # Find quizzes to grade
            quizzes_to_grade = AutoGradingService.find_quizzes_to_grade(db)
            
            if not quizzes_to_grade:
                logger.info("No quizzes found that need auto-grading")
                return {"processed_quizzes": 0, "total_submissions": 0, "total_tokens": 0}
            
            results = []
            total_submissions = 0
            total_tokens = 0
            
            for quiz_info in quizzes_to_grade:
                try:
                    result = AutoGradingService.process_quiz_auto_grading(quiz_info, db)
                    results.append(result)
                    total_submissions += result.get("graded_submissions", 0)
                    total_tokens += result.get("total_tokens", 0)
                    
                except Exception as e:
                    logger.error(f"Error processing quiz {quiz_info['quiz_id']}: {str(e)}")
                    results.append({
                        "quiz_id": quiz_info["quiz_id"],
                        "graded_submissions": 0,
                        "total_tokens": 0,
                        "error": str(e)
                    })
            
            logger.info(f"Auto-grading batch completed: {len(quizzes_to_grade)} quizzes processed, {total_submissions} submissions graded, {total_tokens} tokens used")
            
            return {
                "processed_quizzes": len(quizzes_to_grade),
                "total_submissions": total_submissions,
                "total_tokens": total_tokens,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in auto-grading batch process: {str(e)}")
            logger.error(traceback.format_exc())
            return {"processed_quizzes": 0, "total_submissions": 0, "total_tokens": 0, "error": str(e)}

# Singleton instance
auto_grading_service = AutoGradingService()