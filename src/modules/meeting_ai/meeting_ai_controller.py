from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from bson.errors import InvalidId

from src.modules.user.user_service import UserService
from src.modules.meeting_ai.meeting_ai_service import MeetingAIService, transcripts

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
    meeting_id = data.get("meeting_id")
    async_mode = data.get("async") is True
    if async_mode:
        tid = MeetingAIService.save_transcript(
            room_name,
            email,
            transcript,
            source="analyze",
            meeting_id=meeting_id,
        )
        MeetingAIService.run_pipeline_async(
            tid,
            patient_personal_id=patient_personal_id,
            custom_prompt=custom_prompt,
        )
        try:
            from src.modules.notification.notification_service import NotificationService

            uid = get_jwt_identity()
            NotificationService.create(
                str(uid),
                f"AI pipeline queued: {room_name}",
                "Processing transcript…",
                "report",
                {"transcript_job_id": tid, "room_name": room_name},
            )
        except Exception as e:
            print(f"Notification on queue: {e}")
        return jsonify({"transcript_job_id": tid, "status": "queued"}), 202

    report_id, summary, _struct = MeetingAIService.save_report(
        room_name,
        email,
        transcript,
        patient_personal_id,
        custom_prompt,
        meeting_id=meeting_id,
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


@meeting_ai_controller.route("/transcript", methods=["POST"])
@jwt_required()
def submit_transcript():
    """Store raw transcript and run async pipeline (capture → job → structured note → report)."""
    data = request.get_json() or {}
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    room_name = data.get("room_name")
    raw = (data.get("transcript") or data.get("raw_text") or "").strip()
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    meeting_id = data.get("meeting_id")
    tid = MeetingAIService.save_transcript(
        room_name,
        email,
        raw,
        source=data.get("source", "client"),
        meeting_id=meeting_id,
    )
    MeetingAIService.run_pipeline_async(
        tid,
        patient_personal_id=data.get("patient_personal_id"),
        custom_prompt=data.get("system_prompt"),
    )
    return jsonify({"transcript_job_id": tid, "status": "queued"}), 202


@meeting_ai_controller.route("/transcript/<job_id>", methods=["GET"])
@jwt_required()
def transcript_status(job_id):
    email = _doctor_email()
    if not email:
        return jsonify({"error": "User not found"}), 404
    try:
        doc = transcripts.find_one({"_id": ObjectId(job_id), "doctor_email": email})
    except (InvalidId, Exception):
        doc = None
    if not doc:
        return jsonify({"error": "Not found"}), 404
    doc["_id"] = str(doc["_id"])
    for k in ("created_at", "completed_at"):
        if doc.get(k) is not None and hasattr(doc[k], "isoformat"):
            doc[k] = doc[k].isoformat()
    return jsonify(doc), 200
