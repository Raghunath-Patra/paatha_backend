#  backend/services/mfa.py

import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import User, MFACode
from .email import email_service

class MFAService:
    def __init__(self):
        self.code_length = 6
        self.code_expiry_minutes = 10

    def generate_code(self) -> str:
        return ''.join(random.choices(string.digits, k=self.code_length))

    async def send_code(self, user: User, db: Session) -> None:
        # Generate new code
        code = self.generate_code()
        expires_at = datetime.utcnow() + timedelta(minutes=self.code_expiry_minutes)

        # Save code to database
        mfa_code = MFACode(
            user_id=user.id,
            code=code,
            expires_at=expires_at
        )
        db.add(mfa_code)
        db.commit()

        # Send email with code
        await email_service.send_mfa_code(user.email, code)

    def verify_code(self, user: User, code: str, db: Session) -> bool:
        # Find valid code
        db_code = db.query(MFACode).filter(
            MFACode.user_id == user.id,
            MFACode.code == code,
            MFACode.is_used == False,
            MFACode.expires_at > datetime.utcnow()
        ).first()

        if db_code:
            # Mark code as used
            db_code.is_used = True
            db.commit()
            return True

        return False

    def enable_mfa(self, user: User, db: Session) -> None:
        user.mfa_enabled = True
        db.commit()

    def disable_mfa(self, user: User, db: Session) -> None:
        user.mfa_enabled = False
        db.commit()

    def cleanup_old_codes(self, db: Session) -> None:
        # Remove expired codes
        db.query(MFACode).filter(
            MFACode.expires_at < datetime.utcnow()
        ).delete()
        db.commit()

mfa_service = MFAService()