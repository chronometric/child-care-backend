from pymongo import MongoClient
from bson.objectid import ObjectId
import gridfs
from datetime import datetime
from constants import Constants
import xml.etree.ElementTree as ET
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
from flask import send_file
from xml.etree.ElementTree import fromstring
from xml.etree.ElementTree import ElementTree


client = MongoClient(Constants.DATABASE_URL)
db = client['CC-database']
fs = gridfs.GridFS(db)

class FileSystemService:

    @staticmethod
    def save_as_docx(file_id: str, content_xml: str) -> bool:
        try:
            doc = Document()
            doc.add_paragraph(content_xml)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            fs.delete(ObjectId(file_id))
            fs.put(buffer, _id=ObjectId(file_id), filename="document.docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            return True
        except Exception as e:
            print(f"Error saving document: {e}")
            return False

    @staticmethod
    def get_file(file_id: str):
        try:
            file = fs.get(ObjectId(file_id))
            return file
        except Exception as e:
            print(f"Error fetching file: {e}")
            return None

    @staticmethod
    def determine_file_type(filename: str) -> str:
        video_extensions = ['.mp4']
        document_extensions = ['.txt', '.doc', '.docx', '.pdf', '.xls', '.xlsx']

        extension = filename.split('.')[-1].lower()
        if f".{extension}" in video_extensions:
            return extension
        elif f".{extension}" in document_extensions:
            if extension in ['txt', 'docx', 'doc']:
                return 'doc'
            if extension == 'pdf':
                return 'pdf'
            if extension == 'xlsx':
                return 'xls'
            return extension
        return "unknown"

    @staticmethod
    def upload_file(
        user_id: str,
        folder_name: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        patient_personal_id=None,
        room_name=None,
        shared_with_patient: bool = False,
    ):
        try:
            # Calculate file size in bytes
            file_size = len(file_data)

            # Determine file type
            file_type = FileSystemService.determine_file_type(filename)

            # Metadata for file tracking, including file size and type
            metadata = {
                "user_id": user_id,
                "folder_name": folder_name,
                "file_size": file_size,  # New file size field
                "file_directory": folder_name,  # Store directory name
                "file_type": file_type,  # Store file type
                "upload_date": datetime.utcnow(),
                "shared_with_patient": bool(shared_with_patient),
            }
            if patient_personal_id:
                metadata["patient_personal_id"] = str(patient_personal_id).strip()
            if room_name:
                metadata["room_name"] = str(room_name).strip()

            # Store file in GridFS with metadata
            file_id = fs.put(file_data, filename=filename, metadata=metadata, content_type=content_type)
            return str(file_id)

        except Exception as e:
            print(f"Error uploading file: {e}")
            return None

    @staticmethod
    def get_files_by_user_and_folder(user_id: str, folder_name: str):
        # Query GridFS for files matching user_id and folder_name
        files = fs.find({"metadata.user_id": user_id, "metadata.folder_name": folder_name})
        return [{
            "file_id": str(file._id),
            "filename": file.filename,
            "file_size": file.metadata.get("file_size", 0),  # Retrieve file size
            "upload_date": file.metadata["upload_date"],
            "file_directory": file.metadata.get("file_directory", ""),
            "file_type": file.metadata.get("file_type", "unknown"),
            "patient_personal_id": file.metadata.get("patient_personal_id"),
            "room_name": file.metadata.get("room_name"),
            "shared_with_patient": file.metadata.get("shared_with_patient", False),
        } for file in files]

    @staticmethod
    def download_file(file_id: str):
        try:
            # Retrieve file from GridFS by ID
            file = fs.get(ObjectId(file_id))
            print(f"File retrieved successfully: {file.filename}, Content-Type: {file.content_type}")
            return file
        except Exception as e:
            print(f"Error retrieving file: {e}")
            return None

    
    
    
    @staticmethod
    def get_pdf_file(file_id: str):
        try:
            # Retrieve the file from GridFS
            file = fs.get(ObjectId(file_id))
            if file.content_type == "application/pdf" or file.filename.lower().endswith(".pdf"):
                return file
            return None
        except Exception as e:
            print(f"Error retrieving PDF file: {e}")
            return None

    @staticmethod
    def get_recent_files_by_user(user_id: str, limit: int = 5):
        try:
            # Query GridFS for files matching the user_id and sort by upload_date (descending)
            files = fs.find({"metadata.user_id": user_id}).sort("metadata.upload_date", -1).limit(limit)
            return [{
                "file_id": str(file._id),
                "filename": file.filename,
                "file_size": file.metadata.get("file_size", 0),  # Retrieve file size
                "upload_date": file.metadata["upload_date"],
                "file_directory": file.metadata.get("file_directory", ""),
                "file_type": file.metadata.get("file_type", "unknown")
            } for file in files]

        except Exception as e:
            print(f"Error retrieving recent files: {e}")
            return []
    

    @staticmethod
    def create_folder(user_id: str, folder_name: str):
        try:
            # Check if the folder already exists for the user
            existing_folder = db['folders'].find_one({"user_id": user_id, "folder_name": folder_name})
            if existing_folder:
                return "Folder already exists"

            # Insert a new folder document
            db['folders'].insert_one({
                "user_id": user_id,
                "folder_name": folder_name,
                "created_date": datetime.utcnow()
            })
            return "Folder created successfully"

        except Exception as e:
            print(f"Error creating folder: {e}")
            return None

    @staticmethod
    def get_user_folders(user_id: str):
        try:
            # Retrieve all folders for the user
            folders = db['folders'].find({"user_id": user_id})
            return [{
                "folder_name": folder["folder_name"],
                "created_date": folder["created_date"]
            } for folder in folders]

        except Exception as e:
            print(f"Error retrieving folders: {e}")
            return []

    @staticmethod
    def get_files_by_type(user_id: str, file_type: str):
        try:
            # Query GridFS for files matching user_id and file_type
            files = fs.find({"metadata.user_id": user_id, "metadata.file_type": file_type})
            return [{
                "file_id": str(file._id),
                "filename": file.filename,
                "file_size": file.metadata.get("file_size", 0),  # Retrieve file size
                "upload_date": file.metadata["upload_date"],
                "file_directory": file.metadata.get("file_directory", ""),
                "file_type": file.metadata.get("file_type", "unknown")
            } for file in files]
        except Exception as e:
            print(f"Error retrieving files of type {file_type}: {e}")
            return []
        
    
