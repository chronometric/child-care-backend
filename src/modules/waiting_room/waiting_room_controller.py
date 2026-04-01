from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from pymongo import MongoClient
from constants import Constants
from src.modules.user.user_service import UserService
from src.modules.waiting_room.waiting_room_service import WaitingRoomService

waiting_room_controller = Blueprint("waiting_room", __name__)
client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
rooms_collection = db["rooms"]


@waiting_room_controller.route("/queue", methods=["GET"])
@jwt_required()
def get_queue():
    room_name = request.args.get("room_name")
    if not room_name:
        return jsonify({"error": "room_name required"}), 400
    uid = get_jwt_identity()
    user = UserService.get_one(str(uid))
    if not user:
        return jsonify({"error": "User not found"}), 404
    room = rooms_collection.find_one({"room_name": room_name})
    if not room or room.get("email") != user.get("user_email"):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(WaitingRoomService.list_pending(room_name)), 200
