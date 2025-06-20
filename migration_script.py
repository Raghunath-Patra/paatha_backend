# migration_script.py - Run this to ensure database schema matches
import os
from sqlalchemy import create_engine, text
from config.database import DATABASE_URL, engine
from models import Base

def run_migration():
    """Run database migration to sync schema"""
    print("Starting database migration...")
    
    try:
        # Create all tables (will only create missing ones)
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created/updated successfully")
        
        # Add any missing indexes
        with engine.connect() as conn:
            # Add missing indexes if they don't exist
            indexes_to_add = [
                "CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);",
                "CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);",
                "CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(course_code);",
                "CREATE INDEX IF NOT EXISTS idx_quiz_attempts_student_quiz ON quiz_attempts(student_id, quiz_id);",
                "CREATE INDEX IF NOT EXISTS idx_user_attempts_timestamp ON user_attempts(timestamp);",
                "CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);",
            ]
            
            for index_sql in indexes_to_add:
                try:
                    conn.execute(text(index_sql))
                    print(f"✅ Index added: {index_sql.split('idx_')[1].split(' ')[0] if 'idx_' in index_sql else 'unnamed'}")
                except Exception as idx_error:
                    print(f"⚠️  Index may already exist: {str(idx_error)}")
            
            conn.commit()
        
        print("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = run_migration()
    if not success:
        exit(1)