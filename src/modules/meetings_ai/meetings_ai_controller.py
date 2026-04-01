from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.modules.user.user_service import UserService
from src.modules.room.room_service import RoomService
from src.modules.meetings_ai.meetings_ai_service import MeetingsAIService
from src.modules.meetings_ai import governance_service as gov

meetings_ai_controller = Blueprint("meetings_ai", __name__)


def _doctor_context():
    uid = get_jwt_identity()
    user = UserService.get_one(str(uid))
    if not user:
        return None, None, None
    return str(uid), user.get("user_email"), user


@meetings_ai_controller.route("/generate", methods=["POST"])
@jwt_required()
def generate_report():
    """Create clinical documentation (Markdown + PDF in GridFS)."""
    ctx = _doctor_context()
    if not ctx[0]:
        return jsonify({"error": "User not found"}), 404
    user_id, email, _ = ctx
    data = request.get_json() or {}
    room_name = data.get("room_name")
    transcript = (data.get("transcript") or "").strip()
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    if not transcript:
        return jsonify({"error": "transcript required"}), 400

    consent = data.get("consent_documentation") is True
    visible = data.get("visible_to_patient") is True
    patient_personal_id = (data.get("patient_personal_id") or "").strip() or None
    async_mode = data.get("async") is True

    try:
        if async_mode:
            MeetingsAIService.run_generate_async(
                user_id=user_id,
                doctor_email=email,
                room_name=room_name,
                transcript=transcript,
                patient_personal_id=patient_personal_id,
                consent_acknowledged=consent,
                visible_to_patient=visible,
            )
            return jsonify({"status": "queued"}), 202
        report_id, rep = MeetingsAIService.generate_and_store_report(
            user_id=user_id,
            doctor_email=email,
            room_name=room_name,
            transcript=transcript,
            patient_personal_id=patient_personal_id,
            consent_acknowledged=consent,
            visible_to_patient=visible,
        )
        return (
            jsonify(
                {
                    "report_id": report_id,
                    "markdown_file_id": rep.get("markdown_file_id"),
                    "pdf_file_id": rep.get("pdf_file_id"),
                    "retention_until": rep.get("retention_until").isoformat()
                    if rep.get("retention_until")
                    else None,
                }
            ),
            201,
        )
    except ValueError as e:
        if str(e) == "documentation_consent_required":
            return jsonify({"error": "consent_documentation must be true"}), 400
        raise


@meetings_ai_controller.route("/reports", methods=["GET"])
@jwt_required()
def list_reports():
    ctx = _doctor_context()
    if not ctx[1]:
        return jsonify({"error": "User not found"}), 404
    _, email, _ = ctx
    return jsonify(MeetingsAIService.list_reports_for_doctor(email)), 200


@meetings_ai_controller.route("/transcript", methods=["POST"])
@jwt_required()
def store_transcript_only():
    """Store raw transcript (e.g. from Web Speech); optional server STT later."""
    ctx = _doctor_context()
    if not ctx[0]:
        return jsonify({"error": "User not found"}), 404
    user_id, email, _ = ctx
    data = request.get_json() or {}
    room_name = data.get("room_name")
    raw = (data.get("transcript") or "").strip()
    source = data.get("source", "manual")
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    tid = MeetingsAIService.store_transcript(room_name, email, user_id, raw, source=source)
    gov.append_audit(
        "meetings_ai.transcript_stored",
        user_id,
        email,
        "meetings_ai_transcript",
        tid,
        {"room_name": room_name, "source": source},
    )
    return jsonify({"transcript_id": tid}), 201


@meetings_ai_controller.route("/stt", methods=["POST"])
@jwt_required()
def server_stt_placeholder():
    """Reserved for Whisper / cloud STT upload — not implemented."""
    return (
        jsonify(
            {
                "error": "not_implemented",
                "message": "Server-side STT: integrate OpenAI Whisper or Azure Speech in production.",
            }
        ),
        501,
    )


@meetings_ai_controller.route("/patient-visible", methods=["POST"])
def patient_visible_reports():
    """Reports marked visible_to_patient for this patient's room password."""
    data = request.get_json() or {}
    password = data.get("patient_password")
    if not password:
        return jsonify({"error": "patient_password required"}), 400
    room = RoomService.get_room_by_patient_password(password)
    if not room:
        return jsonify({"error": "Unauthorized"}), 401
    pid = room.get("patient_personal_id")
    reports = MeetingsAIService.list_visible_for_patient(
        pid if pid else None,
    )
    return jsonify({"reports": reports}), 200
