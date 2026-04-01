from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from constants import Constants
from src.modules.admin.admin_dtos import CreateAdminBody, UpdateAdminBody
import bcrypt
import jwt
from flask_jwt_extended import create_access_token



client = MongoClient(Constants.DATABASE_URL)
db = client['CC-database']

class AdminService:

    @staticmethod
    def count_admins() -> int:
        try:
            return db.admins.count_documents({})
        except Exception as e:
            print(f"Error counting admins: {e}")
            return 0

    @staticmethod
    def create(body: CreateAdminBody):
        # Hash the password before storing it
        hashed_password = bcrypt.hashpw(body.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create admin dict with hashed password
        admin = {
            "admin_name": body.admin_name,
            "email": body.email,
            "password_hash": hashed_password,  # Store hashed password
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = db.admins.insert_one(admin)
        return str(result.inserted_id)

    @staticmethod
    def get_one(admin_id: str):
        try:
            admin = db.admins.find_one({"_id": ObjectId(admin_id)})
            if admin:
                admin['_id'] = str(admin['_id'])  # Convert ObjectId to string
            return admin
        except Exception as e:
            print(f"Error fetching admin: {e}")
            return None

    @staticmethod
    def get_all():
        try:
            admins = list(db.admins.find())
            for admin in admins:
                admin['_id'] = str(admin['_id'])  # Convert ObjectId to string
            return admins
        except Exception as e:
            print(f"Error fetching admins: {e}")
            return []

    @staticmethod
    def update_one(admin_id: str, body: UpdateAdminBody):
        try:
            updates = {k: v for k, v in body.dict().items() if v is not None}

            # If password is being updated, hash the new password
            if updates.get("password"):
                updates["password_hash"] = bcrypt.hashpw(updates["password"].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                del updates["password"]  # Remove the plain text password

            updates["updated_at"] = datetime.utcnow()
            result = db.admins.update_one({"_id": ObjectId(admin_id)}, {"$set": updates})

            if result.matched_count > 0:
                updated_admin = db.admins.find_one({"_id": ObjectId(admin_id)})
                if updated_admin:
                    updated_admin['_id'] = str(updated_admin['_id'])
                return updated_admin

            return None
        except Exception as e:
            print(f"Error updating admin: {e}")
            return None

    @staticmethod
    def delete_one(admin_id: str):
        db.admins.delete_one({"_id": ObjectId(admin_id)})
        return True

    @staticmethod
    def delete_all():
        db.admins.delete_many({})
        return True

    @staticmethod
    def login(email, password):
        try:
            # Find the admin by email
            admin = db.admins.find_one({"email": email})
            if not admin:
                return None, "Admin not found"

            # Verify the password
            if not bcrypt.checkpw(password.encode('utf-8'), admin['password_hash'].encode('utf-8')):
                return None, "Invalid password"

            # Generate JWT token with admin_id as the identity
            token = create_access_token(identity=str(admin['_id']))  # Use Flask-JWT-Extended to create a token

            return token, None

        except Exception as e:
            print(f"Error during admin login: {e}")
            return None, "Internal server error"
    
    @staticmethod
    def get_total_rooms_by_admin_email(admin_email: str):
        try:
            # Find companies managed by the admin
            companies = list(db.companies.find({"company_admin_email": admin_email}))
            # print(f"Found companies: {companies}")  # Debugging log

            total_rooms = 0

            # Collect all user emails associated with the admin's companies
            user_emails = []
            for company in companies:
                # print(f"Processing company: {company}")  # Debugging log
                users = list(db.users.find({"user_company_id": company["_id"]}))
                # print(f"Users for company {company['_id']}: {users}")  # Debugging log

                # Add user emails to the list
                user_emails.extend([user.get("user_email") for user in users if "user_email" in user])

            # print(f"User emails: {user_emails}")  # Debugging log

            # Query the rooms collection to count rooms associated with the collected user emails
            if user_emails:
                total_rooms = db.rooms.count_documents({"email": {"$in": user_emails}})
                # print(f"Total rooms found: {total_rooms}")  # Debugging log

            return total_rooms

        except Exception as e:
            print(f"Error calculating total rooms: {e}")
            return None
    
    @staticmethod
    def find_company_code_by_user_email(user_email: str):
        try:
            # Find the user's company ID
            user = db.users.find_one({"user_email": user_email})
            if not user:
                return None

            company_id = user.get("user_company_id")
            if not company_id:
                return None

            # Find the company code using the company ID
            company = db.companies.find_one({"_id": ObjectId(company_id)})
            if not company:
                return None

            return company.get("company_code")
        except Exception as e:
            print(f"Error finding company code: {e}")
            return None