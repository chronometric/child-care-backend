from flask import Blueprint, request, jsonify, send_file, url_for
from src.modules.file_system.file_system_service import FileSystemService
from src.modules.file_system.file_system_dtos import UploadFileBody
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from io import BytesIO
from flask import Response

file_system_controller = Blueprint('file_system', __name__)

@file_system_controller.route('/save-document/<file_id>', methods=['POST'])
def save_document(file_id):
    try:
        content_xml = request.data.decode("utf-8")
        if FileSystemService.save_as_docx(file_id, content_xml):
            return jsonify({"message": "Document saved successfully"}), 200
        else:
            return jsonify({"error": "Failed to save document"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_system_controller.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    try:
        # Get user ID from the JWT token
        user_id = get_jwt_identity()

        # Parse JSON data for folder_name
        folder_name = request.form.get("folder_name", "default")
        patient_personal_id = request.form.get("patient_personal_id") or None
        room_name = request.form.get("room_name") or None
        shared_raw = (request.form.get("shared_with_patient") or "").lower()
        shared_with_patient = shared_raw in ("1", "true", "yes", "on")

        # Get the file from the form data
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        filename = secure_filename(file.filename)

        # Upload the file
        file_id = FileSystemService.upload_file(
            user_id=user_id,
            folder_name=folder_name,
            file_data=file.read(),
            filename=filename,
            content_type=file.content_type,
            patient_personal_id=patient_personal_id,
            room_name=room_name,
            shared_with_patient=shared_with_patient,
        )

        if file_id:
            return jsonify({"message": "File uploaded successfully", "file_id": file_id}), 201
        else:
            return jsonify({"error": "File upload failed"}), 500

    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

@file_system_controller.route('/list-files', methods=['GET'])
@jwt_required()
def list_files():
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()
        
        # Get folder_name from query parameters (optional)
        folder_name = request.args.get("folder_name", "default")

        # Retrieve files by user ID and folder name
        files = FileSystemService.get_files_by_user_and_folder(user_id, folder_name)
        return jsonify(files), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# @jwt_required()
@file_system_controller.route('/download/<file_id>', methods=['GET'])
def download_file(file_id):
    try:
        # Fetch the file from GridFS
        file = FileSystemService.download_file(file_id)
        if file:
            # Prepare file for streaming response
            return send_file(
                BytesIO(file.read()), 
                as_attachment=True,
                download_name=file.filename, 
                mimetype=file.content_type
            )
        else:
            return jsonify({"error": "File not found"}), 404

    except Exception as e:
        print(f"Error during file download: {e}")  # Add debugging
        return jsonify({"error": str(e)}), 500


@file_system_controller.route('/file/<file_id>', methods=['GET'])
def get_file_by_id(file_id):
    """
    Provides direct access to a file using its file_id and supports video streaming.
    """
    try:
        # Fetch the file from GridFS
        file = FileSystemService.download_file(file_id)
        if not file:
            return jsonify({"error": "File not found"}), 404

        # Get the file size
        file_size = file.length
        range_header = request.headers.get('Range', None)
        if range_header:
            # Parse the range header
            byte_range = range_header.split('=')[1]
            start, end = byte_range.split('-')
            start = int(start)
            end = int(end) if end else file_size - 1
            chunk_size = (end - start) + 1

            # Read the requested byte range from the file
            file.seek(start)
            data = file.read(chunk_size)

            # Create a partial response for the requested range
            response = Response(data, status=206, mimetype=file.content_type)
            response.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
            response.headers.add('Accept-Ranges', 'bytes')
            return response
        else:
            # Serve the entire file if no range is specified
            return Response(file.read(), mimetype=file.content_type)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# @jwt_required()
@file_system_controller.route('/file-as-pdf/<file_id>', methods=['GET'])
def get_pdf_file(file_id):
    """
    Serves the PDF file directly.
    """
    try:
        pdf_file = FileSystemService.get_pdf_file(file_id)
        if pdf_file:
            return send_file(
                BytesIO(pdf_file.read()), 
                mimetype='application/pdf', 
                as_attachment=False, 
                download_name=pdf_file.filename
            )
        return jsonify({"error": "PDF file not found or invalid type"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_system_controller.route('/recent-files', methods=['GET'])
@jwt_required()
def get_recent_files():
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()

        # Retrieve the top 5 most recent files for the user
        recent_files = FileSystemService.get_recent_files_by_user(user_id)
        return jsonify(recent_files), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@file_system_controller.route('/create-folder', methods=['POST'])
@jwt_required()
def create_folder():
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()

        # Get folder_name from request data
        folder_name = request.json.get("folder_name")
        if not folder_name:
            return jsonify({"error": "Folder name is required"}), 400

        # Create the folder
        result = FileSystemService.create_folder(user_id, folder_name)
        if result == "Folder created successfully":
            return jsonify({"message": result}), 201
        elif result == "Folder already exists":
            return jsonify({"message": result}), 409
        else:
            return jsonify({"error": "Failed to create folder"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_system_controller.route('/list-folders', methods=['GET'])
@jwt_required()
def list_folders():
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()

        # Retrieve the user's folder list
        folders = FileSystemService.get_user_folders(user_id)
        return jsonify(folders), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_system_controller.route('/list-documents', methods=['GET'])
@jwt_required()
def list_documents():
    """
    Retrieves the list of document files for the authenticated user.
    """
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()

        # Retrieve document files
        document_files = FileSystemService.get_files_by_type(user_id, file_type="doc") + FileSystemService.get_files_by_type(user_id, file_type="pdf")
        return jsonify(document_files), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_system_controller.route('/list-videos', methods=['GET'])
@jwt_required()
def list_videos():
    """
    Retrieves the list of video files for the authenticated user.
    """
    try:
        # Get user ID from JWT
        user_id = get_jwt_identity()

        # Retrieve video files
        video_files = FileSystemService.get_files_by_type(user_id, file_type="mp4")
        return jsonify(video_files), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


