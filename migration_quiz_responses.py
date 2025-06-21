# migration_quiz_responses.py
# Migration script to convert existing JSONB answers to QuizResponse table

from sqlalchemy.orm import Session
from sqlalchemy import text
from config.database import engine, SessionLocal
from models import QuizAttempt, QuizResponse, Quiz, QuizQuestion
import json
import uuid
from datetime import datetime, timedelta

def get_india_time():
    """Get current datetime in India timezone (UTC+5:30)"""
    utc_now = datetime.utcnow()
    offset = timedelta(hours=5, minutes=30)
    return utc_now + offset

def migrate_quiz_responses():
    """
    Migrate existing quiz attempts with JSONB answers to QuizResponse table
    """
    db = SessionLocal()
    
    try:
        print("Starting migration of quiz responses...")
        
        # Get all completed quiz attempts that have answers in JSONB format
        attempts_with_answers = db.query(QuizAttempt).filter(
            QuizAttempt.status == 'completed',
            QuizAttempt.answers.isnot(None),
            QuizAttempt.answers != {}
        ).all()
        
        print(f"Found {len(attempts_with_answers)} attempts to migrate")
        
        migrated_count = 0
        error_count = 0
        
        for attempt in attempts_with_answers:
            try:
                # Check if this attempt already has QuizResponse records
                existing_responses = db.query(QuizResponse).filter(
                    QuizResponse.attempt_id == attempt.id
                ).count()
                
                if existing_responses > 0:
                    print(f"Attempt {attempt.id} already has QuizResponse records, skipping...")
                    continue
                
                # Get quiz questions for this quiz
                questions = db.query(QuizQuestion).filter(
                    QuizQuestion.quiz_id == attempt.quiz_id
                ).all()
                
                if not questions:
                    print(f"No questions found for quiz {attempt.quiz_id}, skipping attempt {attempt.id}")
                    continue
                
                # Parse the JSONB answers
                if isinstance(attempt.answers, str):
                    answers_dict = json.loads(attempt.answers)
                else:
                    answers_dict = attempt.answers or {}
                
                # Get correct answers for grading
                question_details = {}
                for question in questions:
                    # Get correct answer - this would need to be adjusted based on your question structure
                    query = text("""
                        SELECT 
                            COALESCE(q.correct_answer, qq.custom_correct_answer) as correct_answer,
                            COALESCE(q.type, qq.custom_question_type) as question_type
                        FROM quiz_questions qq
                        LEFT JOIN questions q ON qq.ai_question_id = q.id
                        WHERE qq.id = :question_id
                    """)
                    
                    result = db.execute(query, {"question_id": question.id}).fetchone()
                    if result:
                        question_details[str(question.id)] = {
                            'correct_answer': result.correct_answer,
                            'question_type': result.question_type,
                            'marks': question.marks
                        }
                
                # Create QuizResponse records
                total_score = 0
                
                for question in questions:
                    question_id = str(question.id)
                    student_answer = answers_dict.get(question_id, "")
                    
                    # Determine if answer is correct
                    is_correct = False
                    score = 0
                    
                    if question_id in question_details:
                        detail = question_details[question_id]
                        correct_answer = detail['correct_answer']
                        question_type = detail['question_type']
                        
                        if question_type and question_type.lower() in ['mcq', 'multiple_choice']:
                            is_correct = str(student_answer).strip().lower() == str(correct_answer).strip().lower()
                        else:
                            is_correct = str(student_answer).strip().lower() == str(correct_answer).strip().lower()
                        
                        if is_correct:
                            score = detail['marks']
                        
                        total_score += score
                    
                    # Create QuizResponse record
                    quiz_response = QuizResponse(
                        quiz_id=attempt.quiz_id,
                        student_id=attempt.student_id,
                        question_id=question.id,
                        attempt_id=attempt.id,
                        response=student_answer,
                        score=score,
                        is_correct=is_correct,
                        answered_at=attempt.submitted_at or attempt.started_at or get_india_time()
                    )
                    
                    db.add(quiz_response)
                
                # Update the attempt with calculated scores if they don't match
                if abs(attempt.obtained_marks - total_score) > 0.01:  # Allow for small floating point differences
                    print(f"Score mismatch for attempt {attempt.id}: stored={attempt.obtained_marks}, calculated={total_score}")
                    # Optionally update the attempt score
                    # attempt.obtained_marks = total_score
                    # attempt.percentage = (total_score / attempt.total_marks * 100) if attempt.total_marks > 0 else 0
                
                migrated_count += 1
                
                # Commit every 10 attempts to avoid large transactions
                if migrated_count % 10 == 0:
                    db.commit()
                    print(f"Migrated {migrated_count} attempts so far...")
                
            except Exception as e:
                error_count += 1
                print(f"Error migrating attempt {attempt.id}: {str(e)}")
                db.rollback()
                continue
        
        # Final commit
        db.commit()
        
        print(f"Migration completed!")
        print(f"Successfully migrated: {migrated_count} attempts")
        print(f"Errors encountered: {error_count} attempts")
        
        # Verify migration
        total_responses = db.query(QuizResponse).count()
        print(f"Total QuizResponse records created: {total_responses}")
        
    except Exception as e:
        print(f"Migration failed with error: {str(e)}")
        db.rollback()
    finally:
        db.close()

def verify_migration():
    """
    Verify that the migration was successful by comparing data
    """
    db = SessionLocal()
    
    try:
        print("Verifying migration...")
        
        # Check attempts that have both old and new format
        query = text("""
            SELECT 
                qa.id,
                qa.obtained_marks,
                qa.percentage,
                COUNT(qr.id) as response_count,
                SUM(qr.score) as calculated_score
            FROM quiz_attempts qa
            LEFT JOIN quiz_responses qr ON qa.id = qr.attempt_id
            WHERE qa.status = 'completed' AND qa.answers IS NOT NULL
            GROUP BY qa.id, qa.obtained_marks, qa.percentage
            HAVING COUNT(qr.id) > 0
        """)
        
        results = db.execute(query).fetchall()
        
        mismatches = 0
        for result in results:
            if abs(result.obtained_marks - result.calculated_score) > 0.01:
                mismatches += 1
                print(f"Score mismatch for attempt {result.id}: "
                      f"stored={result.obtained_marks}, calculated={result.calculated_score}")
        
        print(f"Verification completed. Found {mismatches} score mismatches out of {len(results)} attempts.")
        
    except Exception as e:
        print(f"Verification failed: {str(e)}")
    finally:
        db.close()

def cleanup_old_answers():
    """
    OPTIONAL: Clean up the old JSONB answers field after successful migration
    WARNING: Only run this after confirming the migration was successful
    """
    db = SessionLocal()
    
    try:
        print("WARNING: This will remove the old JSONB answers data!")
        confirmation = input("Type 'YES' to confirm: ")
        
        if confirmation == 'YES':
            # Update all attempts to set answers to NULL
            updated = db.query(QuizAttempt).filter(
                QuizAttempt.answers.isnot(None)
            ).update({"answers": None}, synchronize_session=False)
            
            db.commit()
            print(f"Cleaned up answers field for {updated} attempts")
        else:
            print("Cleanup cancelled")
            
    except Exception as e:
        print(f"Cleanup failed: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Quiz Response Migration Script")
    print("1. Run migration")
    print("2. Verify migration")
    print("3. Cleanup old data (DESTRUCTIVE)")
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        migrate_quiz_responses()
    elif choice == "2":
        verify_migration()
    elif choice == "3":
        cleanup_old_answers()
    else:
        print("Invalid choice")