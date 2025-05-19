#  backend/services/email.py

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
import os
from dotenv import load_dotenv
import time

load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

class EmailService:
    def __init__(self):
        self.fastmail = FastMail(conf)
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    async def send_verification_email(self, email: str, token: str):
        timestamp = int(time.time())
        verify_url = f"{self.frontend_url}/verify-email?token={token}&t={timestamp}"

        message = MessageSchema(
            subject="Verify your email - Learning Platform",
            recipients=[email],
            body=f"""
            <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Welcome to the Learning Platform!</h2>
                    <p>Thank you for registering. Please verify your email address by clicking the button below:</p>
                    <p style="margin: 25px 0;">
                        <a href="{verify_url}" 
                           style="background-color: #4F46E5; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 5px;">
                            Verify Email Address
                        </a>
                    </p>
                    <p>If you did not create an account, you can safely ignore this email.</p>
                    <p>This verification link will expire in 24 hours.</p>
                </body>
            </html>
            """,
            subtype="html"
        )
        
        try:
            await self.fastmail.send_message(message)
            return True
        except Exception as e:
            print(f"Error sending verification email: {str(e)}")
            return False

    async def resend_verification_email(self, email: str, token: str):
        """Resend verification email with new token"""
        verify_url = f"{self.frontend_url}/verify-email?token={token}"
        
        message = MessageSchema(
            subject="Verify your email - Learning Platform (Resent)",
            recipients=[email],
            body=f"""
            <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Email Verification Reminder</h2>
                    <p>You recently tried to log in to your account. Please verify your email address by clicking the button below:</p>
                    <p style="margin: 25px 0;">
                        <a href="{verify_url}" 
                           style="background-color: #4F46E5; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 5px;">
                            Verify Email Address
                        </a>
                    </p>
                    <p>If you did not try to log in, please ignore this email.</p>
                    <p>This verification link will expire in 24 hours.</p>
                </body>
            </html>
            """,
            subtype="html"
        )
        
        try:
            await self.fastmail.send_message(message)
            return True
        except Exception as e:
            print(f"Error sending verification reminder email: {str(e)}")
            return False

    async def send_password_reset_email(self, email: str, token: str):
        reset_url = f"{self.frontend_url}/reset-password?token={token}"
        
        message = MessageSchema(
            subject="Reset Your Password - Learning Platform",
            recipients=[email],
            body=f"""
            <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Password Reset Request</h2>
                    <p>You requested to reset your password. Click the button below to set a new password:</p>
                    <p style="margin: 25px 0;">
                        <a href="{reset_url}" 
                           style="background-color: #4F46E5; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 5px;">
                            Reset Password
                        </a>
                    </p>
                    <p>If you didn't request this, you can safely ignore this email.</p>
                    <p>This reset link will expire in 1 hour.</p>
                </body>
            </html>
            """,
            subtype="html"
        )
        
        try:
            await self.fastmail.send_message(message)
            return True
        except Exception as e:
            print(f"Error sending password reset email: {str(e)}")
            return False

email_service = EmailService()