from flask import Blueprint, request, jsonify
from src.modules.admin.admin_service import AdminService
from src.modules.admin.admin_dtos import CreateAdminBody, UpdateAdminBody
from pydantic import ValidationError
from src.modules.user.user_service import UserService
from src.modules.admin.email_service import send_email  # Import email sending function
from flask_jwt_extended import jwt_required, get_jwt_identity
from constants import Constants
from src.modules.company.company_service import CompanyService
from src.modules.admin.admin_system_service import AdminSystemService
from pymongo import MongoClient


admin_controller = Blueprint('admins', __name__)
client = MongoClient(Constants.DATABASE_URL)
db = client['CC-database']

@admin_controller.route('/', methods=['POST'])
def create_admin():
    try:
        data = request.get_json()
        body = CreateAdminBody(**data)
        admin_id = AdminService.create(body)
        return jsonify({"_id": admin_id}), 201
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

@admin_controller.route('/', methods=['GET'])
def get_admins():
    admins = AdminService.get_all()
    return jsonify(admins), 200

@admin_controller.route('/<admin_id>', methods=['GET'])
def get_admin(admin_id):
    admin = AdminService.get_one(admin_id)
    if admin:
        return jsonify(admin), 200
    return jsonify({"error": "Admin not found"}), 404

@admin_controller.route('/<admin_id>', methods=['PUT'])
def update_admin(admin_id):
    try:
        data = request.get_json()
        body = UpdateAdminBody(**data)
        updated_admin = AdminService.update_one(admin_id, body)
        if updated_admin:
            return jsonify(updated_admin), 200
        return jsonify({"error": "Admin not found"}), 404
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

@admin_controller.route('/<admin_id>', methods=['DELETE'])
def delete_admin(admin_id):
    success = AdminService.delete_one(admin_id)
    if success:
        return jsonify({"message": "Admin deleted successfully"}), 200
    return jsonify({"error": "Admin not found"}), 404

@admin_controller.route('/delete-all', methods=['DELETE'])
def delete_all_admins():
    AdminService.delete_all()
    return jsonify({"message": "All admins deleted successfully"}), 200

@admin_controller.route('/login', methods=['POST'])
def login_admin():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        # Validate email and password
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        # Call the AdminService to handle the login
        token, error = AdminService.login(email, password)
        if error:
            return jsonify({"error": error}), 401

        return jsonify({"token": token}), 200

    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400
    

@admin_controller.route('/users', methods=['GET'])
def get_users():
    # Extract pagination parameters (default: page 1, page size 10)
    try:
        page = int(request.args.get('page', 1))  # Default to page 1
        page_size = int(request.args.get('page_size', 10))  # Default to page size 10

        # Fetch paginated users from UserService
        result = UserService.get_all(page=page, page_size=page_size)
        
        return jsonify(result), 200
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters"}), 400

@admin_controller.route('/me', methods=['GET'])
@jwt_required()  # Enforce JWT authentication
def get_current_admin():
    try:
        # Extract the admin_id from the JWT token
        admin_id = get_jwt_identity()

        # Fetch the admin details from the database
        admin = AdminService.get_one(admin_id)
        if admin:
            # Prepare the response with the necessary fields
            response = {
                'email': admin.get('email')
            }
            return jsonify(response), 200
        else:
            return jsonify({"error": "Admin not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_controller.route('/send-company-code', methods=['POST'])
@jwt_required()
def send_company_code():
    try:
        # Parse request JSON
        data = request.get_json()
        user_email = data.get('user_email')

        if not user_email:
            return jsonify({"error": "user_email is required"}), 400

        # Find the company code associated with the user
        company_code = AdminService.find_company_code_by_user_email(user_email)
        if not company_code:
            return jsonify({"error": "Company code not found for the provided user email"}), 404

        # Send email with the company code
        email_subject = "Your Company Code"
        email_body = f"Dear User,\n\nYour company code is: {company_code}\n\nBest regards,\nAdmin Team"

        # Use the predefined sender email in Constants
        send_email(user_email, email_subject, email_body)
        return jsonify({"message": "Email sent successfully"}), 200

    except Exception as e:
        print(f"Error sending company code: {e}")
        return jsonify({"error": "Internal server error"}), 500



@admin_controller.route('/companies-and-users', methods=['POST'])
def get_companies_and_users():
    try:
        # Parse request body
        data = request.get_json()
        company_admin_email = data.get('company_admin_email')

        # Fetch companies by admin email
        companies = CompanyService.get_by_admin_email(company_admin_email)

        # If no companies found, return an empty response
        if not companies:
            return jsonify([]), 200

        # Prepare the result with companies and their users
        companies_and_users_data = []
        user_emails = []
        for company in companies:
            # Fetch users associated with the company
            users = UserService.get_users_by_company_id(company['_id'])

            company_usage_time = 0
            company_status = "Inactive"
            for user in users:
                user_emails.append(user.get('user_email'))
                company_usage_time += user.get('use_time')
                if user.get('status') == 'Active':
                    company_status = 'Active'

            # Add the users to the company data
            companies_and_users_data.append({
                "company_name": company.get('company_name'),
                "company_description": company.get('company_description'),
                "company_email": company.get('company_email'),
                "created_at": company.get('created_at').strftime("%d-%m-%Y"),
                "use_time": round(company_usage_time, 3),
                "status": company_status,
                "users": users
            })
        
         # Calculate total rooms using the service
        total_rooms = db.rooms.count_documents({"email": {"$in": user_emails}})

        return jsonify({'companies_and_users_data' : companies_and_users_data, "total_rooms": total_rooms}), 200

    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_controller.route('/system-overview', methods=['GET'])
@jwt_required()
def system_overview():
    return jsonify(AdminSystemService.system_overview()), 200


@admin_controller.route('/ai-config', methods=['GET'])
@jwt_required()
def get_ai_config():
    return jsonify(AdminSystemService.get_ai_config()), 200


@admin_controller.route('/ai-config', methods=['PUT'])
@jwt_required()
def put_ai_config():
    data = request.get_json() or {}
    allowed = {k: data[k] for k in ('openai_model', 'system_prompt_override', 'waiting_room_enabled') if k in data}
    return jsonify(AdminSystemService.set_ai_config(allowed)), 200
