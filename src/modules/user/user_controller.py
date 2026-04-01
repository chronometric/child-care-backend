from flask import Blueprint, request, jsonify, send_file, url_for
from src.modules.user.user_service import UserService
from src.modules.user.user_dtos import RegisterUserBody, UpdateUserBody
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from io import BytesIO

from src.extensions import limiter

user_controller = Blueprint('users', __name__)

@user_controller.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register_user():
    try:        
        data = request.get_json()
        body = RegisterUserBody(**data)
        user_id, token = UserService.register(body)
        if not user_id:
            return jsonify({"error": token}), 400

        return jsonify({"_id": user_id, "message": "Registration successful!", "token": token}), 201
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

@user_controller.route('/change-profile-info', methods=['PUT'])
@jwt_required()  # Requires user authentication via JWT
def change_profile_info():
    try:
        # Get the current user's ID from the JWT token
        user_id = get_jwt_identity()

        # Parse the request JSON
        data = request.get_json()
        user_name = data.get('user_name')
        user_email = data.get('user_email')
        account_description = data.get('account_description')

        # Validate that the required fields are provided
        if not all([user_name, user_email, account_description]):
            return jsonify({"error": "Missing required fields"}), 400

        # Call the service method to change profile info
        success, message = UserService.change_profile_info(
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            account_description=account_description
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@user_controller.route('/change-password', methods=['PUT'])
@jwt_required()  # Requires user authentication via JWT
def change_password():
    try:
        # Get the current user's ID from the JWT token
        user_id = get_jwt_identity()

        # Parse the request JSON
        data = request.get_json()
        old_password = data.get('old_user_password')
        new_password = data.get('new_user_password')

        # Validate that the required fields are provided
        if not all([old_password, new_password]):
            return jsonify({"error": "Missing required fields"}), 400

        # Call the service method to change the password
        success, message = UserService.change_password(
            user_id=user_id,
            old_password=old_password,
            new_password=new_password
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_controller.route('/change-profile-picture', methods=['PUT'])
@jwt_required()  # Requires user authentication via JWT
def change_profile_picture():
    try:
        # Get the current user's ID from the JWT token
        user_id = get_jwt_identity()

        # Check if the request contains the file
        if 'profile_picture' not in request.files:
            return jsonify({"error": "No profile picture uploaded"}), 400

        # Get the profile picture file
        file = request.files['profile_picture']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Secure the filename
        filename = secure_filename(file.filename)

        # Read the file data
        picture_data = file.read()

        # Call the service to change the profile picture
        success, picture_id = UserService.change_profile_picture(user_id, picture_data, filename)

        if success:
            return jsonify({"message": "Profile picture updated successfully", "picture_id": picture_id}), 200
        else:
            return jsonify({"error": "Failed to update profile picture"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_controller.route('/profile-picture/<picture_id>', methods=['GET'])
def get_profile_picture(picture_id):
    """
    This endpoint serves the profile picture associated with the given picture_id
    from GridFS. If the picture is found, it streams the content to the client.
    """
    try:
        # Call the service to fetch the picture
        picture = UserService.get_profile_picture(picture_id)
        if picture:
            return send_file(BytesIO(picture.read()), mimetype=picture.content_type)
        else:
            return jsonify({"error": "Profile picture not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_controller.route('/profile-picture/email/<email>', methods=['GET'])
def get_profile_picture_by_email(email):
    """
    This endpoint fetches the profile picture associated with a user email and 
    returns the public URL where the picture can be accessed.
    """
    try:
        # Call the service method to get the profile picture by email
        picture, error = UserService.get_profile_picture_by_email(email)

        if error:
            return jsonify({"error": error}), 404

        # Generate and return a public URL for the profile picture
        picture_url = url_for('users.get_profile_picture', picture_id=picture._id, _external=True)
        return jsonify({"picture_url": picture_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_controller.route('/', methods=['GET'])
def get_users():
    users = UserService.get_all()
    return jsonify(users), 200

@user_controller.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    user = UserService.get_one(user_id)
    if user:
        return jsonify(user), 200
    return jsonify({"error": "User not found"}), 404

@user_controller.route('/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        data = request.get_json()
        body = UpdateUserBody(**data)
        updated_user = UserService.update_one(user_id, body)
        if updated_user:
            updated_user['_id'] = str(updated_user['_id'])
            return jsonify(updated_user), 200
        return jsonify({"error": "User not found"}), 404
    except ValidationError as e:
        # Log or print the specific validation error
        print(f"ValidationError: {e}")
        return jsonify({"error": e.errors()}), 400
    except ValueError as e:
        # Handle ObjectId validation errors here
        return jsonify({"error": str(e)}), 400


@user_controller.route('/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    success = UserService.delete_one(user_id)
    if success:
        return jsonify({"message": "User deleted successfully"}), 200
    return jsonify({"error": "User not found"}), 404

@user_controller.route('/delete-all', methods=['DELETE'])
def delete_all_users():
    UserService.delete_all()
    return jsonify({"message": "All users deleted successfully"}), 200


@user_controller.route('/login', methods=['POST'])
@limiter.limit("20 per minute")
def login_user():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        token, error, user = UserService.login(email, password)
        if error:
            return jsonify({"error": error}), 401

        return jsonify({
            "token": token,
            'user_name': user.get('user_name'),
            'user_email': user.get('user_email'),
            'account_description': user.get('account_description'),
            'picture_id': user.get('profile_picture')
        }), 200

    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

@user_controller.route('/logout/<user_id>', methods=['POST'])
def logout_user(user_id):
    try:
        message = UserService.logout(user_id)
        if "successful" in message:
            return jsonify({"message": message}), 200
        return jsonify({"error": message}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@user_controller.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    try:
        user_id = get_jwt_identity()
        user = UserService.get_one(user_id)
        if user:
            try:
                response = {
                    'user_name': user.get('user_name'),
                    'user_email': user.get('user_email'),
                    'account_description': user.get('account_description'),
                    'picture_id': user.get('profile_picture')
                }
            except:
                response = {
                    'user_name': user.get('user_name'),
                    'user_email': user.get('user_email'),
                    'account_description': user.get('account_description'),
                    'picture_id': 'f854995e19599136b75e1dcefa17184a'
                }
            return jsonify(response), 200
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
