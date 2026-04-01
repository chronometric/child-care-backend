from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.modules.notification.notification_service import NotificationService

notification_controller = Blueprint("notifications", __name__)


@notification_controller.route("/", methods=["GET"])
@jwt_required()
def list_notifications():
    uid = get_jwt_identity()
    items = NotificationService.list_for_user(str(uid))
    return jsonify(items), 200


@notification_controller.route("/read-all", methods=["POST"])
@jwt_required()
def read_all():
    uid = get_jwt_identity()
    NotificationService.mark_all_read(str(uid))
    return jsonify({"message": "ok"}), 200


@notification_controller.route("/<nid>/read", methods=["POST"])
@jwt_required()
def read_one(nid: str):
    uid = get_jwt_identity()
    ok = NotificationService.mark_read(nid, str(uid))
    if ok:
        return jsonify({"message": "ok"}), 200
    return jsonify({"error": "Not found"}), 404
