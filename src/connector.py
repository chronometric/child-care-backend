import os
from typing import Optional
from datetime import timedelta
from flask import Flask
from flask_jwt_extended import JWTManager
from flask_openapi3 import OpenAPI, Info
from pymongo import MongoClient
from constants import Constants

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import uuid
from flask import jsonify, request
from datetime import datetime

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
rooms_collection = db["rooms"]
messages_collection = db["messages"]
meetings_collection = db["meetings"]
# Realtime presence separate from `users` to avoid deleting doctor accounts on disconnect
socket_sessions = db["socket_sessions"]
private_dm_channels = db["private_dm_channels"]

info = Info(title="Your API", version="1.0.0")
app = OpenAPI(__name__, info=info)

app.config["DEBUG"] = False
app.config["CACHE_TYPE"] = "null"
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY") or getattr(
    Constants, "JWT_SECRET", None
) or "dev-only-set-JWT_SECRET_KEY-in-production"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

connected_users = {}

jwt = JWTManager(app)

# BP REG
from src.modules.user.user_controller import user_controller
app.register_blueprint(user_controller, url_prefix="/api/users")

from src.modules.admin.admin_controller import admin_controller
app.register_blueprint(admin_controller, url_prefix="/api/admins")

from src.modules.company.company_controller import company_controller
app.register_blueprint(company_controller, url_prefix="/api/companys")

from src.modules.invoice.invoice_controller import invoice_controller
app.register_blueprint(invoice_controller, url_prefix="/api/invoices")

from src.modules.statistics.statistics_controller import statistics_controller
app.register_blueprint(statistics_controller, url_prefix="/api/statistics")

from src.modules.room.room_controller import room_controller
app.register_blueprint(room_controller, url_prefix="/api/room")

from src.modules.system_usage.system_usage_controller import system_usage_controller
app.register_blueprint(system_usage_controller, url_prefix='/api/system_usages')

from src.modules.event.event_controller import event_controller
app.register_blueprint(event_controller, url_prefix='/api/events')

from src.modules.file_system.file_system_controller import file_system_controller
app.register_blueprint(file_system_controller, url_prefix='/api/file_system')

from src.modules.patient_record.patient_record_controller import patient_record_controller
app.register_blueprint(patient_record_controller, url_prefix="/api/patient_records")

from src.modules.notification.notification_controller import notification_controller
app.register_blueprint(notification_controller, url_prefix="/api/notifications")

from src.modules.meeting_ai.meeting_ai_controller import meeting_ai_controller
app.register_blueprint(meeting_ai_controller, url_prefix="/api/meeting_ai")

from src.modules.meetings_ai.meetings_ai_controller import meetings_ai_controller
app.register_blueprint(meetings_ai_controller, url_prefix="/api/meetings_ai")

from src.modules.waiting_room.waiting_room_controller import waiting_room_controller
app.register_blueprint(waiting_room_controller, url_prefix="/api/waiting_room")

from src.modules.waiting_room.waiting_room_service import WaitingRoomService
from src.utils.socket_tokens import decode_socket_token, is_room_token

@app.route("/")
def index():
    return "Backend"

###################################


@app.route("/http-call")
def http_call():
    """Return JSON with string data as the value"""
    data = {"data": "This text was fetched using an HTTP call to server on render"}
    return jsonify(data)


def _apply_socket_identity(data, sid):
    """
    Resolve username, role, roomName, participant_key, mongo_user_id from body + optional JWT.
    Returns (roomName, username, role, participant_key, mongo_user_id) or (None, ...) on error.
    """
    token = data.get("token")
    username = data.get("username")
    role = data.get("role")
    roomName = data.get("roomName")
    participant_key = None
    mongo_user_id = None

    if token:
        payload = decode_socket_token(token)
        if not payload:
            return None
        if is_room_token(payload):
            roomName = payload.get("room_name") or roomName
            username = payload.get("username") or username
            role = payload.get("role") or role
            participant_key = str(payload.get("sub") or "")
        else:
            mongo_user_id = str(payload.get("sub") or "")
            participant_key = f"user:{mongo_user_id}"
    if not roomName:
        return None
    if not participant_key:
        participant_key = str(uuid.uuid4())

    socket_sessions.update_one(
        {"sid": sid},
        {
            "$set": {
                "username": username,
                "role": role,
                "room_name": roomName,
                "participant_key": participant_key,
                "mongo_user_id": mongo_user_id,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    return roomName, username, role, participant_key, mongo_user_id


@socketio.on("init")
def handle_init(data):
    """
    Initialize the connection with user details.
    Optional `token`: staff JWT (Flask-JWT) or `room_token` from check_*_authentication.
    Legacy: username, role, roomName without token (ephemeral participant_key).
    """
    sid = request.sid
    resolved = _apply_socket_identity(data, sid)
    if not resolved:
        emit("error", {"msg": "roomName is required or invalid token"})
        return

    roomName, username, role, participant_key, mongo_user_id = resolved
    join_room(roomName)

    user_uuid = str(uuid.uuid4())
    if role != "creator":
        rooms_collection.find_one_and_update(
            {
                "room_name": roomName,
                "participants": {
                    "$not": {
                        "$elemMatch": {
                            "username": username,
                            "role": role,
                        }
                    }
                },
            },
            {
                "$addToSet": {
                    "participants": {
                        "username": username,
                        "role": role,
                        "user_id": str(user_uuid),
                    }
                },
                "$inc": {"participants_count": 1},
            },
        )

    room = rooms_collection.find_one({"room_name": roomName})
    all_users = []
    if room:
        all_users_cursor = room.get("participants") or []
        all_users = [
            {
                "userid": user["user_id"],
                "username": user["username"],
                "role": user["role"],
            }
            for user in all_users_cursor
        ]

    emit(
        "init_response",
        {"msg": f"Welcome {username}!", "users": all_users},
        room=roomName,
    )
    print(f"{username} ({role}) connected with SID: {sid} room={roomName}")


def _find_or_create_dm_channel_key(participant_key_a: str, participant_key_b: str) -> str:
    """Stable DM channel id from two participant keys (not socket_sessions ObjectIds)."""
    a, b = sorted([participant_key_a, participant_key_b])
    doc = private_dm_channels.find_one({"participant_keys": [a, b]})
    if doc:
        return doc["channel_id"]
    channel_id = str(uuid.uuid4())
    private_dm_channels.insert_one(
        {
            "channel_id": channel_id,
            "participant_keys": [a, b],
            "created_at": datetime.utcnow(),
        }
    )
    return channel_id


@socketio.on("private_message")
def handle_private_message(data):
    """
    DM between two sockets; channel key is stable `participant_key` (room JWT sub or user:userId).
    Expected data: {'to': 'recipient_sid', 'message': 'text'}
    """
    from_sid = request.sid
    to_sid = data.get("to")
    message_text = data.get("message")

    sender = socket_sessions.find_one({"sid": from_sid})
    recipient = socket_sessions.find_one({"sid": to_sid})

    if sender and recipient and message_text is not None:
        sk_a = sender.get("participant_key")
        sk_b = recipient.get("participant_key")
        if not sk_a or not sk_b:
            emit("error", {"msg": "Missing participant identity"}, to=from_sid)
            return

        channel_id = _find_or_create_dm_channel_key(sk_a, sk_b)

        join_room(channel_id, sid=from_sid)
        join_room(channel_id, sid=to_sid)

        messages_collection.insert_one(
            {
                "room_id": channel_id,
                "sender_key": str(sk_a),
                "message": message_text,
                "timestamp": datetime.utcnow(),
            }
        )

        emit(
            "room_message",
            {
                "from": from_sid,
                "message": message_text,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=channel_id,
        )
        print(f"Private message from {from_sid} to {to_sid}: {message_text}")


@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")
    emit("server_ready", {"sid": request.sid})


@socketio.on("chat_request")
def handle_chat_request(data):
    """
    Guest requests chat with patient; notify creator in the same metered room.
    Expected data: {'patient_sid', 'roomName' (optional but recommended)}
    """
    guest_sid = request.sid
    patient_sid = data.get("patient_sid")
    room_name = data.get("roomName")

    guest = socket_sessions.find_one({"sid": guest_sid})
    patient = socket_sessions.find_one({"sid": patient_sid})

    if guest and patient and patient.get("role") == "patient":
        q = {"role": "creator"}
        if room_name:
            q["room_name"] = room_name
        creator = socket_sessions.find_one(q)
        if creator:
            emit(
                "chat_request",
                {
                    "guest_sid": guest_sid,
                    "guest_username": guest.get("username"),
                    "patient_sid": patient_sid,
                    "patient_username": patient.get("username"),
                },
                to=creator["sid"],
            )
            print(f"Chat request from {guest_sid} to {patient_sid}")
        else:
            emit("error", {"msg": "Room Creator not connected."}, to=guest_sid)


@socketio.on("chat_response")
def handle_chat_response(data):
    """
    Handle the Room Creator's response to a chat request.
    Expected data: {'guest_sid', 'patient_sid', 'approve'}
    """
    guest_sid = data.get("guest_sid")
    patient_sid = data.get("patient_sid")
    approve = data.get("approve")

    guest = socket_sessions.find_one({"sid": guest_sid})
    patient = socket_sessions.find_one({"sid": patient_sid})

    if approve and guest and patient:
        gk = guest.get("participant_key")
        pk = patient.get("participant_key")
        if not gk or not pk:
            emit("error", {"msg": "Missing participant identity"}, to=guest_sid)
            return
        channel_id = _find_or_create_dm_channel_key(gk, pk)

        socket_sessions.update_one(
            {"_id": guest["_id"]}, {"$set": {"dm_channel_id": channel_id}}
        )
        socket_sessions.update_one(
            {"_id": patient["_id"]}, {"$set": {"dm_channel_id": channel_id}}
        )

        join_room(channel_id, sid=guest_sid)
        join_room(channel_id, sid=patient_sid)

        emit(
            "chat_approved",
            {"room_id": channel_id, "patient_sid": patient_sid, "guest_sid": guest_sid},
            to=guest_sid,
        )

        emit(
            "chat_started",
            {"room_id": channel_id, "guest_sid": guest_sid},
            to=patient_sid,
        )

        print(f"Chat approved between {guest_sid} and {patient_sid} in channel {channel_id}")
    elif not approve:
        emit(
            "chat_denied",
            {"msg": "Your chat request was denied by the Room Creator."},
            to=guest_sid,
        )
        print(f"Chat denied for {guest_sid} to chat with {patient_sid}")


@socketio.on("room_message")
def handle_room_message(data):
    """
    In-room chat for a metered session. Client sends room_id = metered room name.
    Sender identity is taken from socket_sessions (request.sid), not client 'from'.
    """
    room_name = data.get("room_id")
    message_text = data.get("message")
    to = data.get("to")
    role = data.get("role")
    from_sid = request.sid

    if not room_name or message_text is None:
        return

    sess = socket_sessions.find_one({"sid": from_sid})
    from_username = (sess or {}).get("username") or data.get("from") or "unknown"

    messages_collection.insert_one(
        {
            "room_name": room_name,
            "from_sid": from_sid,
            "from_username": from_username,
            "message": message_text,
            "to": to,
            "role": role,
            "timestamp": datetime.utcnow(),
        }
    )

    emit(
        "room_message",
        {
            "room": room_name,
            "from": from_username,
            "to": to,
            "role": role,
            "message": message_text,
            "timestamp": datetime.utcnow().isoformat(),
        },
        room=room_name,
        skip_sid=from_sid,
    )
    print(f"Room {room_name}: {from_username} says {message_text} to {to}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    try:
        WaitingRoomService.remove_by_sid(sid)
    except Exception:
        pass
    doc = socket_sessions.find_one({"sid": sid})
    if doc:
        username = doc.get("username", "Unknown")
        role = doc.get("role", "Unknown")
        room_name = doc.get("room_name")
        dm_channel = doc.get("dm_channel_id")

        print(f"{username} ({role}) disconnected.")

        if room_name:
            try:
                leave_room(room_name, sid=sid)
            except Exception:
                pass
            emit(
                "user_disconnected",
                {"sid": sid, "username": username},
                room=room_name,
            )
        if dm_channel:
            try:
                leave_room(dm_channel, sid=sid)
            except Exception:
                pass

        socket_sessions.delete_one({"sid": sid})


@socketio.on("get_chat_history")
def handle_get_chat_history(data):
    """
    Retrieve chat history: DM channel id (room_id) or metered room name (group messages use room_name).
    """
    room_id = data.get("room_id")
    if not room_id:
        return
    messages_cursor = messages_collection.find(
        {"$or": [{"room_id": room_id}, {"room_name": room_id}]}
    ).sort("timestamp", 1)
    messages = []
    for msg in messages_cursor:
        entry = {
            "message": msg["message"],
            "timestamp": msg["timestamp"].isoformat(),
        }
        if msg.get("sender_id") is not None:
            entry["sender_id"] = str(msg["sender_id"])
        if msg.get("sender_key") is not None:
            entry["sender_key"] = str(msg["sender_key"])
        if msg.get("from_username"):
            entry["from_username"] = msg["from_username"]
        messages.append(entry)
    emit("chat_history", {"room_id": room_id, "messages": messages})


@socketio.on("join_waiting_room")
def handle_join_waiting(data):
    """Participant (patient/guest) requests to enter the session; host admits via admit_waiting."""
    room_name = data.get("roomName")
    username = data.get("username")
    role = data.get("role")
    token = data.get("token")
    sid = request.sid
    if not room_name or not username or not role:
        return
    participant_key = None
    mongo_user_id = None
    if token:
        payload = decode_socket_token(token)
        if payload and is_room_token(payload):
            if payload.get("room_name") and payload.get("room_name") != room_name:
                emit("error", {"msg": "Token room mismatch"}, to=sid)
                return
            participant_key = str(payload.get("sub") or "")
            username = payload.get("username") or username
            role = payload.get("role") or role
        elif payload:
            mongo_user_id = str(payload.get("sub") or "")
            participant_key = f"user:{mongo_user_id}"
    if not participant_key:
        participant_key = str(uuid.uuid4())
    socket_sessions.update_one(
        {"sid": sid},
        {
            "$set": {
                "username": username,
                "role": role,
                "room_name": room_name,
                "participant_key": participant_key,
                "mongo_user_id": mongo_user_id,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    join_room(room_name)
    WaitingRoomService.add_or_update(room_name, sid, username, role, "pending")
    emit(
        "waiting_room_update",
        {
            "room_name": room_name,
            "queue": WaitingRoomService.list_pending(room_name),
        },
        room=room_name,
    )


@socketio.on("admit_waiting")
def handle_admit_waiting(data):
    room_name = data.get("roomName")
    target_sid = data.get("targetSid")
    if not room_name or not target_sid:
        return
    WaitingRoomService.set_status(room_name, target_sid, "admitted")
    emit("admission_granted", {"room_name": room_name}, to=target_sid)
    emit(
        "waiting_room_update",
        {
            "room_name": room_name,
            "queue": WaitingRoomService.list_pending(room_name),
        },
        room=room_name,
    )


@socketio.on("reject_waiting")
def handle_reject_waiting(data):
    room_name = data.get("roomName")
    target_sid = data.get("targetSid")
    if not room_name or not target_sid:
        return
    WaitingRoomService.set_status(room_name, target_sid, "rejected")
    emit(
        "admission_denied",
        {"room_name": room_name, "reason": "Host declined entry"},
        to=target_sid,
    )
    WaitingRoomService.remove(room_name, target_sid)
    emit(
        "waiting_room_update",
        {
            "room_name": room_name,
            "queue": WaitingRoomService.list_pending(room_name),
        },
        room=room_name,
    )


def get_creator_sid(room_name: Optional[str] = None):
    """Return the SID of a room creator in the given metered room (if room_name set)."""
    q = {"role": "creator"}
    if room_name:
        q["room_name"] = room_name
    creator = socket_sessions.find_one(q)
    return creator["sid"] if creator else None

