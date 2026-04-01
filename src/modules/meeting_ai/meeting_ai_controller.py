from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.modules.user.user_service import UserService
from src.modules.meeting_ai.meeting_ai_service import MeetingAIService

meeting_ai_controller = Blueprint("meeting_ai", __name__)


def _doctor_email():
    uid = get_jwt_identity()
    user = UserService.get_one(str(uid))
    return user.get("user_email") if user else None


@meeting_ai_controller.route("/analyze", methods=["POST"])
@jwt_required()
def analyze():
    data = request.get_json() or {}
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    room_name = data.get("room_name")
    transcript = data.get("transcript") or ""
    patient_personal_id = data.get("patient_personal_id")
    custom_prompt = data.get("system_prompt")
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    report_id, summary = MeetingAIService.save_report(
        room_name, email, transcript, patient_personal_id, custom_prompt
    )
    try:
        from src.modules.notification.notification_service import NotificationService
        uid = get_jwt_identity()
        NotificationService.create(
            str(uid),
            f"Session report ready: {room_name}",
            summary[:400] + ("…" if len(summary) > 400 else ""),
            "report",
            {"report_id": report_id, "room_name": room_name},
        )
    except Exception as e:
        print(f"Notification on report: {e}")
    return jsonify({"report_id": report_id, "summary": summary}), 201


@meeting_ai_controller.route("/reports", methods=["GET"])
@jwt_required()
def list_reports():
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    room_name = request.args.get("room_name")
    if room_name:
        return jsonify(MeetingAIService.list_for_room(room_name, email)), 200
    return jsonify(MeetingAIService.list_for_doctor(email)), 200
