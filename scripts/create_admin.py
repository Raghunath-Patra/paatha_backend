# backend/scripts/create_admin.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User
from database import SessionLocal
from config.security import get_password_hash
from dotenv import load_dotenv

load_dotenv()

def create_admin():
    db = SessionLocal()
    try:
        # Check if admin already exists
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if admin:
            print("Admin user already exists")
            return

        # Create admin user
        admin = User(
            email="admin@example.com",
            password_hash=get_password_hash("admin_password"),  # Change this password!
            full_name="Admin User",
            is_verified=True
        )
        db.add(admin)
        db.commit()
        print("Admin user created successfully")
    except Exception as e:
        print(f"Error creating admin user: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()