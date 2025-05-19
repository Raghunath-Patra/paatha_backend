# backend/scripts/cleanup_attempts.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import UserAttempt, Question
from config.database import SessionLocal
from sqlalchemy import exists
from sqlalchemy.orm import Session

def clean_orphaned_attempts(db: Session):
    try:
        # Find attempts without corresponding questions
        orphaned = db.query(UserAttempt).filter(
            ~exists().where(Question.id == UserAttempt.question_id)
        ).all()
        
        print(f"\nFound {len(orphaned)} orphaned attempts")
        
        if not orphaned:
            print("No orphaned attempts found. Database is clean!")
            return
            
        # Print details of orphaned attempts
        print("\nOrphaned attempts details:")
        for attempt in orphaned:
            print(f"ID: {attempt.id}")
            print(f"Subject: {attempt.subject}")
            print(f"Chapter: {attempt.chapter}")
            print(f"Score: {attempt.score}")
            print("---")
        
        # Ask for confirmation
        confirm = input("\nDo you want to delete these orphaned attempts? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled.")
            return
            
        # Delete orphaned attempts
        for attempt in orphaned:
            db.delete(attempt)
        db.commit()
        
        print(f"\nSuccessfully deleted {len(orphaned)} orphaned attempts!")
        
    except Exception as e:
        print(f"Error cleaning orphaned attempts: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting cleanup of orphaned attempts...")
    db = SessionLocal()
    clean_orphaned_attempts(db)