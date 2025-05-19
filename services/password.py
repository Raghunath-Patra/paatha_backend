# backend/services/password.py

# backend/services/password.py
import re
from datetime import datetime, timedelta
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from models import User
from config.security import check_lockout

class PasswordService:
    def __init__(self):
        self.min_length = 8
        self.max_length = 128
        self.max_failed_attempts = 5
        self.lockout_duration = timedelta(minutes=15)
    
    def validate_password(self, password: str) -> Tuple[bool, str]:
        """
        Validates password complexity requirements.
        Returns (is_valid, message).
        """
        if len(password) < self.min_length:
            return False, f"Password must be at least {self.min_length} characters long"
        
        if len(password) > self.max_length:
            return False, f"Password cannot be longer than {self.max_length} characters"

        # Check for minimum complexity requirements
        checks = [
            (r'[A-Z]', "uppercase letter"),
            (r'[a-z]', "lowercase letter"),
            (r'\d', "number"),
            (r'[!@#$%^&*(),.?":{}|<>]', "special character")
        ]
        
        failed_checks = []
        for pattern, desc in checks:
            if not re.search(pattern, password):
                failed_checks.append(desc)
        
        if failed_checks:
            if len(failed_checks) == 1:
                return False, f"Password must contain at least one {failed_checks[0]}"
            return False, f"Password must contain at least one {', one '.join(failed_checks[:-1])}, and one {failed_checks[-1]}"
        
        return True, "Password meets requirements"
    
    def check_account_lockout(self, user: User) -> Optional[timedelta]:
        """
        Check if account is locked. Returns lockout duration if locked, None otherwise.
        """
        if user.failed_login_attempts >= self.max_failed_attempts:
            if user.last_failed_login:
                lockout_end = user.last_failed_login + self.lockout_duration
                if datetime.utcnow() < lockout_end:
                    return lockout_end - datetime.utcnow()
        
        return None
    
    def record_failed_attempt(self, user: User, db: Session):
        """
        Record a failed login attempt and update lockout status.
        """
        user.failed_login_attempts += 1
        user.last_failed_login = datetime.utcnow()
        
        if user.failed_login_attempts >= self.max_failed_attempts:
            user.account_locked_until = datetime.utcnow() + self.lockout_duration
            
        db.commit()
    
    def reset_failed_attempts(self, user: User, db: Session):
        """
        Reset failed login attempts after successful login.
        """
        user.failed_login_attempts = 0
        user.last_failed_login = None
        user.account_locked_until = None
        db.commit()

# Create a singleton instance
password_service = PasswordService()