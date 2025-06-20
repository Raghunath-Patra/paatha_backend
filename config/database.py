# backend/config/database.py - Updated configuration
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database connection details from environment variables
DB_USER = os.getenv('SUPABASE_DB_USER')
DB_PASSWORD = os.getenv('SUPABASE_DB_PASSWORD')
DB_HOST = os.getenv('SUPABASE_DB_HOST')
DB_PORT = os.getenv('SUPABASE_DB_PORT', '6543')  # Default Supabase port
DB_NAME = os.getenv('SUPABASE_DB_NAME', 'postgres')  # Default Supabase database name

# Construct DATABASE_URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    # Updated engine configuration for better production stability
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,           # Increased from 5
        max_overflow=20,        # Increased from 10
        pool_pre_ping=True,     # Test connections before use
        pool_recycle=3600,      # Recycle connections every hour (was 300 seconds)
        poolclass=NullPool if os.getenv('RAILWAY_ENVIRONMENT') else None,  # Use NullPool in Railway
        connect_args={
            "sslmode": "require",
            "connect_timeout": 60,
            "application_name": "paatha_ai_backend"  # For connection tracking
        },
        echo=False,  # Set to True for SQL debugging
        future=True  # Use SQLAlchemy 2.0 style
    )
    
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False  # Keep objects usable after commit
    )

    Base = declarative_base()
    
    logger.info("Database engine created successfully")

except Exception as e:
    logger.error(f"Failed to create database engine: {str(e)}")
    raise

def get_db():
    """Get database session with proper cleanup"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            logger.info("Database connection test successful")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False