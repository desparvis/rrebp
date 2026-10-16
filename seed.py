from app import app
from models import db, SuperAdmin
from werkzeug.security import generate_password_hash
import os
from dotenv import load_dotenv

load_dotenv()

# Get variables from .env file
admin_email = os.getenv("SUPERADMIN_EMAIL")
admin_password = os.getenv("SUPERADMIN_PASSWORD")

with app.app_context():
    if not admin_email or not admin_password:
        print("Error: SUPERADMIN_EMAIL or SUPERADMIN_PASSWORD not found in .env file.")
    
    # Check if admin already exists
    elif not SuperAdmin.query.first():
        admin = SuperAdmin(
            email=admin_email, 
            password_hash=generate_password_hash(admin_password)
        )
        db.session.add(admin)
        db.session.commit()
        print("Super Admin created successfully. You can now log in.")
    else:
        print("A Super Admin already exists in the database.")