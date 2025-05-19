# backend/models.py
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, 
    DateTime, ForeignKey, JSON, Enum as SQLEnum, 
    Index, Date
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref
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
    
    # Relationships
    attempts = relationship("UserAttempt", 
                           primaryjoin="User.id == UserAttempt.user_id", 
                           back_populates="user", 
                           cascade="all, delete-orphan")
    marketing_redemptions = relationship("PromoCodeRedemption",
                                      primaryjoin="User.id == PromoCodeRedemption.marketing_partner_id",
                                      backref="marketing_partner")
    subscriber_redemptions = relationship("PromoCodeRedemption",
                                       primaryjoin="User.id == PromoCodeRedemption.subscriber_id",
                                       backref="subscriber")

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
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
    
    # Relationships
    attempts = relationship("UserAttempt", 
                            primaryjoin="Question.id == UserAttempt.question_id", 
                            back_populates="question", 
                            cascade="all, delete-orphan")

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

    # Relationships
    user = relationship("User", 
                        primaryjoin="UserAttempt.user_id == User.id", 
                        back_populates="attempts")
    question = relationship("Question", 
                            primaryjoin="UserAttempt.question_id == Question.id", 
                            back_populates="attempts")

    # Indexes
    __table_args__ = (
        Index('idx_user_attempts_created_at', 'created_at'),
        Index('idx_user_attempts_user_chapter', 'user_id', 'chapter'),
    )

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
    six_month_price = Column(Integer, nullable=True)  # Add this line
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
    carry_forward = Column(Boolean, default=False)
    
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
    
    # Subscription dates
    premium_start_date = Column(DateTime(timezone=True), nullable=True)
    premium_end_date = Column(DateTime(timezone=True), nullable=True)
    
    # Cancel data
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    canceled_reason = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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
    )