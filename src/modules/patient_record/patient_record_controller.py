from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.modules.user.user_service import UserService
from src.modules.patient_record.patient_record_service import PatientRecordService
from pymongo import MongoClient
from constants import Constants

patient_record_controller = Blueprint("patient_records", __name__)
client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
rooms_collection = db["rooms"]


def _doctor_email():
    uid = get_jwt_identity()
    user = UserService.get_one(str(uid))
    return user.get("user_email") if user else None


@patient_record_controller.route("/", methods=["GET"])
@jwt_required()
def list_records():
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    return jsonify(PatientRecordService.list_for_doctor(email)), 200


@patient_record_controller.route("/<patient_personal_id>", methods=["GET"])
@jwt_required()
def get_record(patient_personal_id: str):
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    doc = PatientRecordService.get_one(email, patient_personal_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(doc), 200


@patient_record_controller.route("/note", methods=["POST"])
@jwt_required()
def add_note():
    data = request.get_json() or {}
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    pid = data.get("patient_personal_id")
    text = data.get("text")
    room_name = data.get("room_name")
    if not pid or not text:
        return jsonify({"error": "patient_personal_id and text required"}), 400
    PatientRecordService.add_note(email, pid, text, room_name)
    return jsonify({"message": "ok"}), 200


@patient_record_controller.route("/link-meeting", methods=["POST"])
@jwt_required()
def link_meeting():
    data = request.get_json() or {}
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    room_name = data.get("room_name")
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    room = rooms_collection.find_one({"room_name": room_name})
    if not room or room.get("email") != email:
        return jsonify({"error": "Room not found or access denied"}), 404
    pid = room.get("patient_personal_id") or ""
    if not pid:
        return jsonify({"error": "Room has no patient_personal_id"}), 400
    PatientRecordService.link_meeting(
        email,
        pid,
        room_name,
        room.get("patient_name"),
    )
    return jsonify({"message": "linked"}), 200


@patient_record_controller.route("/sync-room", methods=["POST"])
@jwt_required()
def sync_room():
    data = request.get_json() or {}
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    room_name = data.get("room_name")
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    room = rooms_collection.find_one({"room_name": room_name})
    if not room or room.get("email") != email:
        return jsonify({"error": "Room not found or access denied"}), 404
    doc = PatientRecordService.sync_from_room(room, email)
    if doc:
        doc["_id"] = str(doc["_id"])
    return jsonify(doc or {}), 200
