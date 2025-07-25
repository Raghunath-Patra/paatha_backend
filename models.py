# backend/models.py - Fixed version to resolve SQLAlchemy recursion issues
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, 
    DateTime, ForeignKey, JSON, Enum as SQLEnum, 
    Index, Date, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
from config.database import Base

class User(Base):
    __tablename__ = "profiles"  # Using "profiles" to match Supabase naming

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True)
    
    # Basic Info
    email = Column(String)
    full_name = Column(String)
    
    # Academic Info
    board = Column(String, nullable=True)
    class_level = Column(String, nullable=True)
    
    # Role and Teacher Info
    role = Column(String(20), default='student', nullable=False)  # 'student' or 'teacher'
    teaching_experience = Column(Integer, nullable=True)
    qualification = Column(String(255), nullable=True)
    subjects_taught = Column(JSON, nullable=True)
    teacher_verified = Column(Boolean, default=False)
    
    # Additional Profile Fields
    institution_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    mother_tongue = Column(String, nullable=True)
    primary_language = Column(String, nullable=True)
    location = Column(String, nullable=True)
    join_purpose = Column(String, nullable=True)
    
    # Flags and Status
    is_active = Column(Boolean, server_default='true', nullable=False)
    is_verified = Column(Boolean, server_default='false', nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Subscription info
    is_premium = Column(Boolean, default=False)
    premium_start_date = Column(DateTime(timezone=True), nullable=True)
    premium_expires_at = Column(DateTime(timezone=True), nullable=True)
    subscription_plan_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Promo code fields
    promo_code = Column(String(20), unique=True, nullable=True)
    is_marketing_partner = Column(Boolean, default=False)
    token_bonus = Column(Integer, default=0)
    projects = relationship("Project", back_populates="user")    
    # Indexes
    __table_args__ = (
        Index('idx_profiles_role', 'role'),
        Index('idx_profiles_email', 'email'),
        Index('idx_profiles_promo_code', 'promo_code'),
    )

class Question(Base):
    __tablename__ = "questions"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    human_readable_id = Column(String, unique=True, nullable=False)
    file_source = Column(String, nullable=False)
    
    # Question content
    question_text = Column(Text, nullable=False)
    type = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    options = Column(JSON)
    correct_answer = Column(Text, nullable=False)
    explanation = Column(Text)
    topic = Column(String)
    bloom_level = Column(String)
    
    # Classification fields
    board = Column(String, nullable=False)
    class_level = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    chapter = Column(Integer, nullable=False)
    category = Column(String, nullable=False)  # 'generated', 'in_chapter', 'exercise'
    section_id = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
    
    # Enhanced indexes for teacher question browsing
    __table_args__ = (
        Index('idx_questions_board_class_subject', 'board', 'class_level', 'subject'),
        Index('idx_questions_chapter', 'chapter'),
        Index('idx_questions_difficulty', 'difficulty'),
        Index('idx_questions_type', 'type'),
        Index('idx_questions_category', 'category'),
        Index('idx_questions_bloom_level', 'bloom_level'),
        Index('idx_questions_topic', 'topic'),
    )

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    course_name = Column(String(255), nullable=False)
    course_code = Column(String(10), unique=True, nullable=False)
    description = Column(Text)
    board = Column(String(100), nullable=False)
    class_level = Column(String(50), nullable=False)
    subject = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    max_students = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_courses_teacher', 'teacher_id'),
        Index('idx_courses_active', 'is_active'),
        Index('idx_courses_board_class_subject', 'board', 'class_level', 'subject'),
        Index('idx_courses_code', 'course_code'),
    )
    # Relationships with cascade delete
    enrollments = relationship("CourseEnrollment", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", cascade="all, delete-orphan")

class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default='active')
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())
    total_quizzes_taken = Column(Integer, default=0)
    average_score = Column(Float, default=0.0)
    
    # Indexes and constraints
    __table_args__ = (
        Index('idx_course_enrollments_course', 'course_id'),
        Index('idx_course_enrollments_student', 'student_id'),
        UniqueConstraint('course_id', 'student_id', name='unique_course_student'),
    )


class Quiz(Base):
    __tablename__ = "quizzes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    instructions = Column(Text)
    time_limit = Column(Integer)  # Minutes
    total_marks = Column(Integer, default=100)
    passing_marks = Column(Integer, default=50)
    attempts_allowed = Column(Integer, default=1)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    is_published = Column(Boolean, default=False)
    auto_grade = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    auto_graded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_quizzes_teacher', 'teacher_id'),
        Index('idx_quizzes_course', 'course_id'),
        Index('idx_quizzes_published', 'is_published'),
        Index('idx_quizzes_active_time', 'start_time', 'end_time'),
    )
    questions = relationship("QuizQuestion", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", cascade="all, delete-orphan")
    responses = relationship("QuizResponse", cascade="all, delete-orphan")

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    
    # Reference to existing AI-generated question (optional)
    ai_question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id', ondelete='SET NULL'))
    
    # Custom question fields (used when ai_question_id is NULL)
    custom_question_text = Column(Text)
    custom_question_type = Column(String(20))  # mcq, short_answer, essay
    custom_options = Column(JSON)
    custom_correct_answer = Column(Text)
    custom_explanation = Column(Text)
    
    # Common fields for both types
    marks = Column(Integer, default=1)
    order_index = Column(Integer, nullable=False)
    
    # Source tracking
    question_source = Column(String(20), default='custom')  # 'ai_generated' or 'custom'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Constraint to ensure either ai_question_id exists OR custom fields are filled
    __table_args__ = (
        CheckConstraint(
            """(ai_question_id IS NOT NULL AND custom_question_text IS NULL) OR
               (ai_question_id IS NULL AND custom_question_text IS NOT NULL AND 
                custom_question_type IS NOT NULL AND custom_correct_answer IS NOT NULL)""",
            name='check_question_source'
        ),
        Index('idx_quiz_questions_quiz', 'quiz_id'),
        Index('idx_quiz_questions_ai_question', 'ai_question_id'),
        Index('idx_quiz_questions_source', 'question_source'),
        Index('idx_quiz_questions_order', 'quiz_id', 'order_index'),
    )

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, default=1)
    answers = Column(JSON, nullable=False)
    total_marks = Column(Integer, default=0)
    obtained_marks = Column(Float, default=0.0)
    percentage = Column(Float, default=0.0)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))
    time_taken = Column(Integer)  # Minutes
    status = Column(String(20), default='in_progress')
    is_auto_graded = Column(Boolean, default=False)
    teacher_reviewed = Column(Boolean, default=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_quiz_attempts_quiz', 'quiz_id'),
        Index('idx_quiz_attempts_student', 'student_id'),
        Index('idx_quiz_attempts_status', 'status'),
        Index('idx_quiz_attempts_student_quiz', 'student_id', 'quiz_id'),
    )

class QuestionSearchFilter(Base):
    __tablename__ = "question_search_filters"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    filter_name = Column(String(255), nullable=False)
    board = Column(String(100))
    class_level = Column(String(50))
    subject = Column(String(100))
    chapter = Column(Integer)
    difficulty = Column(String(50))
    question_type = Column(String(50))
    topic = Column(String(255))
    bloom_level = Column(String(50))
    category = Column(String(100))
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_search_filters_teacher', 'teacher_id'),
        Index('idx_search_filters_default', 'is_default'),
    )

class UserAttempt(Base):
    __tablename__ = "user_attempts"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"))
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    
    # Attempt data
    answer = Column(String)
    score = Column(Float)
    feedback = Column(String, nullable=True)
    time_taken = Column(Integer, nullable=True)
    board = Column(String)
    class_level = Column(String)
    subject = Column(String)
    chapter = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Image processing fields
    transcribed_text = Column(Text, nullable=True)
    combined_answer = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    
    # OCR token usage
    ocr_prompt_tokens = Column(Integer, nullable=True)
    ocr_completion_tokens = Column(Integer, nullable=True)
    ocr_total_tokens = Column(Integer, nullable=True)
    
    # Grading token usage
    grading_prompt_tokens = Column(Integer, nullable=True)
    grading_completion_tokens = Column(Integer, nullable=True)
    grading_total_tokens = Column(Integer, nullable=True)

    # Chat token usage
    chat_prompt_tokens = Column(Integer, nullable=True)
    chat_completion_tokens = Column(Integer, nullable=True)
    chat_total_tokens = Column(Integer, nullable=True)
    
    # Total token usage
    total_prompt_tokens = Column(Integer, nullable=True)
    total_completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    
    # Token-based tracking
    input_tokens_used = Column(Integer, default=0)
    output_tokens_used = Column(Integer, default=0)
    is_token_limit_reached = Column(Boolean, default=False)

    # Indexes
    __table_args__ = (
        Index('idx_user_attempts_user', 'user_id'),
        Index('idx_user_attempts_question', 'question_id'),
        Index('idx_user_attempts_created_at', 'created_at'),
        Index('idx_user_attempts_user_chapter', 'user_id', 'chapter'),
    )

# Keep all other existing models
class ChapterDefinition(Base):
    __tablename__ = "chapter_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    board = Column(String, nullable=False)
    class_level = Column(String, nullable=False)
    subject_code = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    chapter_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Create indexes for faster lookups
    __table_args__ = (
        Index('idx_chapter_lookup', 'board', 'class_level', 'subject_code'),
    )

class QuestionFollowUp(Base):
    __tablename__ = "question_follow_ups"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Create index for faster lookups
    __table_args__ = (
        Index('idx_follow_ups_user_question', 'user_id', 'question_id'),
    )

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    # Pricing
    monthly_price = Column(Integer, nullable=False)  # In paise (1/100 of rupee)
    six_month_price = Column(Integer, nullable=True)
    yearly_price = Column(Integer, nullable=True)
    
    # Limits
    monthly_question_limit = Column(Integer, nullable=False)
    daily_question_limit = Column(Integer, nullable=False)
    monthly_chat_limit = Column(Integer, nullable=True)
    requests_per_question = Column(Integer, default=1)
    follow_up_questions_per_day = Column(Integer, default=1)
    follow_up_questions_per_answer = Column(Integer, default=3)
    
    # Token limits
    input_tokens_per_question = Column(Integer, default=6000)
    output_tokens_per_question = Column(Integer, default=4000)
    daily_input_token_limit = Column(Integer, default=18000)
    daily_output_token_limit = Column(Integer, default=12000)
    
    # Features
    features = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class SubscriptionUserData(Base):
    __tablename__ = "subscription_user_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=True)
    is_yearly = Column(Boolean, default=False)
    
    # Usage tracking
    questions_used_this_month = Column(Integer, default=0)
    questions_used_today = Column(Integer, default=0)
    chat_requests_used_this_month = Column(Integer, default=0)
    follow_up_questions_used_today = Column(Integer, default=0)
    
    # Reset dates
    monthly_reset_date = Column(Date, nullable=True)
    daily_reset_date = Column(Date, nullable=True)
    tokens_reset_date = Column(Date, nullable=True)
    
    # Subscription timing
    subscription_start_date = Column(DateTime(timezone=True), nullable=True)
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Token-based usage tracking
    daily_input_tokens_used = Column(Integer, default=0)
    daily_output_tokens_used = Column(Integer, default=0)
    
    # Add this line for token bonus
    token_bonus = Column(Integer, default=0)

    # Create indexes for faster lookups
    __table_args__ = (
        Index('idx_subscription_user_lookup', 'user_id'),
        Index('idx_subscription_plan_lookup', 'plan_id'),
    )

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)  # In paise
    currency = Column(String, nullable=False, default="INR")
    
    # Razorpay details
    razorpay_payment_id = Column(String, nullable=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_signature = Column(String, nullable=True)
    razorpay_subscription_id = Column(String, nullable=True)
    
    # Status
    status = Column(String, nullable=False)  # created, completed, failed, canceled
    
    notes = Column(JSON, nullable=True)  # Store plan_duration, service_type, etc.
    
    # Subscription dates
    premium_start_date = Column(DateTime(timezone=True), nullable=True)
    premium_end_date = Column(DateTime(timezone=True), nullable=True)
    
    # Cancel data
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    canceled_reason = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_payments_user', 'user_id'),
        Index('idx_payments_status', 'status'),
        Index('idx_payments_razorpay_order', 'razorpay_order_id'),
    )

class PromoCodeRedemption(Base):
    __tablename__ = "promo_code_redemptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    marketing_partner_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    subscriber_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    subscription_amount = Column(Integer, nullable=False)
    subscription_type = Column(String(20), nullable=False)
    commission_amount = Column(Integer, nullable=False)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Create indexes for faster lookups
    __table_args__ = (
        Index('idx_promo_redemptions_partner', 'marketing_partner_id'),
        Index('idx_promo_redemptions_subscriber', 'subscriber_id'),
        Index('idx_promo_redemptions_paid', 'is_paid'),
    )

# Add this new model to your models.py file

class QuizResponse(Base):
    __tablename__ = "quiz_responses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False)
    
    # Response data
    response = Column(Text, nullable=True)  # Student's answer
    score = Column(Float, default=0.0)  # Score for this specific question
    is_correct = Column(Boolean, nullable=True)  # Whether the answer is correct
    feedback = Column(Text, nullable=True)  # AI or manual feedback for the answer
    
    # Metadata
    time_spent = Column(Integer, nullable=True)  # Seconds spent on this question
    confidence_level = Column(Integer, nullable=True)  # 1-5 scale of student confidence
    flagged_for_review = Column(Boolean, default=False)  # If student flagged this question
    
    # Timestamps
    answered_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Indexes and constraints
    __table_args__ = (
        Index('idx_quiz_responses_quiz', 'quiz_id'),
        Index('idx_quiz_responses_student', 'student_id'),
        Index('idx_quiz_responses_question', 'question_id'),
        Index('idx_quiz_responses_attempt', 'attempt_id'),
        Index('idx_quiz_responses_quiz_student_question', 'quiz_id', 'student_id', 'question_id'),
        UniqueConstraint('attempt_id', 'question_id', name='unique_attempt_question'),
    )

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    input_content = Column(Text, nullable=True)
    status = Column(String, nullable=False, default='input_only')  # input_only, script_ready, completed
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="projects")
    credit_usage = relationship("CreditUsage", back_populates="project")
    
    # Constraints
    __table_args__ = (
        Index('idx_projects_user', 'user_id'),
        Index('idx_projects_status', 'status'),
        CheckConstraint("status IN ('input_only', 'script_ready', 'completed')", name='check_project_status'),
    )

class CreditPackage(Base):
    __tablename__ = "credit_packages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_name = Column(String(100), nullable=False)
    credits_amount = Column(Integer, nullable=False)
    price_inr = Column(Integer, nullable=False)  # In paise, 0 for free
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user_credits = relationship("UserCredits", back_populates="package")

class UserCredits(Base):
    __tablename__ = "user_credits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    available_credits = Column(Integer, nullable=False, default=0)
    pack_id = Column(UUID(as_uuid=True), ForeignKey("credit_packages.id"), nullable=True)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="video_credits")
    package = relationship("CreditPackage", back_populates="user_credits")
    usage_records = relationship("CreditUsage", back_populates="user_credits")
    
    # Constraints
    __table_args__ = (
        Index('idx_user_credits_user', 'user_id'),
        UniqueConstraint('user_id', name='unique_user_credits'),
    )

class CreditUsage(Base):
    __tablename__ = "credit_usage"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_credits_id = Column(UUID(as_uuid=True), ForeignKey("user_credits.id", ondelete="CASCADE"), nullable=True)
    credits_used = Column(Integer, nullable=False)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    project = relationship("Project", back_populates="credit_usage")
    user_credits = relationship("UserCredits", back_populates="usage_records")
    
    # Indexes
    __table_args__ = (
        Index('idx_credit_usage_user', 'user_id'),
        Index('idx_credit_usage_project', 'project_id'),
        Index('idx_credit_usage_user_credits', 'user_credits_id'),
        Index('idx_credit_usage_date', 'used_at'),
    )

# Add these relationships to existing User model
User.video_credits = relationship("UserCredits", back_populates="user", uselist=False)
User.credit_usage = relationship("CreditUsage", back_populates="user")
User.projects = relationship("Project", back_populates="user")

Quiz.responses = relationship("QuizResponse", back_populates="quiz", cascade="all, delete-orphan")
QuizQuestion.responses = relationship("QuizResponse", back_populates="question", cascade="all, delete-orphan")
QuizAttempt.responses = relationship("QuizResponse", back_populates="attempt", cascade="all, delete-orphan")
User.quiz_responses = relationship("QuizResponse", back_populates="student", cascade="all, delete-orphan")

QuizResponse.quiz = relationship("Quiz", back_populates="responses")
QuizResponse.student = relationship("User", back_populates="quiz_responses")
QuizResponse.question = relationship("QuizQuestion", back_populates="responses")
QuizResponse.attempt = relationship("QuizAttempt", back_populates="responses")

# IMPORTANT: Add relationships AFTER all classes are defined to avoid circular imports
# This prevents the recursion issue we were experiencing

# Add relationships to User
User.attempts = relationship("UserAttempt", back_populates="user", cascade="all, delete-orphan")
User.taught_courses = relationship("Course", back_populates="teacher", cascade="all, delete-orphan")
User.created_quizzes = relationship("Quiz", back_populates="teacher", cascade="all, delete-orphan")
User.search_filters = relationship("QuestionSearchFilter", back_populates="teacher", cascade="all, delete-orphan")
User.course_enrollments = relationship("CourseEnrollment", back_populates="student", cascade="all, delete-orphan")
User.quiz_attempts = relationship("QuizAttempt", back_populates="student", cascade="all, delete-orphan")
User.marketing_redemptions = relationship("PromoCodeRedemption", 
                                        foreign_keys=[PromoCodeRedemption.marketing_partner_id],
                                        back_populates="marketing_partner")
User.subscriber_redemptions = relationship("PromoCodeRedemption",
                                         foreign_keys=[PromoCodeRedemption.subscriber_id], 
                                         back_populates="subscriber")

# Add relationships to other models
Question.attempts = relationship("UserAttempt", back_populates="question", cascade="all, delete-orphan")

Course.teacher = relationship("User", back_populates="taught_courses")
Course.enrollments = relationship("CourseEnrollment", back_populates="course", cascade="all, delete-orphan")
Course.quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")

CourseEnrollment.course = relationship("Course", back_populates="enrollments")
CourseEnrollment.student = relationship("User", back_populates="course_enrollments")

Quiz.teacher = relationship("User", back_populates="created_quizzes")
Quiz.course = relationship("Course", back_populates="quizzes")
Quiz.questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
Quiz.attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")

QuizQuestion.quiz = relationship("Quiz", back_populates="questions")
QuizQuestion.ai_question = relationship("Question")

QuizAttempt.quiz = relationship("Quiz", back_populates="attempts")
QuizAttempt.student = relationship("User", back_populates="quiz_attempts")

QuestionSearchFilter.teacher = relationship("User", back_populates="search_filters")

UserAttempt.user = relationship("User", back_populates="attempts")
UserAttempt.question = relationship("Question", back_populates="attempts")

PromoCodeRedemption.marketing_partner = relationship("User", foreign_keys=[PromoCodeRedemption.marketing_partner_id])
PromoCodeRedemption.subscriber = relationship("User", foreign_keys=[PromoCodeRedemption.subscriber_id])