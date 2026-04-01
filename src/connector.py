from datetime import timedelta
from flask import Flask
from flask_jwt_extended import JWTManager
from flask_openapi3 import OpenAPI, Info
from pymongo import MongoClient
from constants import Constants

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import uuid
from bson.objectid import ObjectId
import uuid
from flask import jsonify, request
from datetime import datetime

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
rooms_collection = db["rooms"]
users_collection = db["users"]
messages_collection = db["messages"]
meetings_collection = db["meetings"]

info = Info(title="Your API", version="1.0.0")
app = OpenAPI(__name__, info=info)

app.config["DEBUG"] = False
app.config["CACHE_TYPE"] = "null"
app.config["JWT_SECRET_KEY"] = "super-secret"
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

from src.modules.waiting_room.waiting_room_controller import waiting_room_controller
app.register_blueprint(waiting_room_controller, url_prefix="/api/waiting_room")

from src.modules.waiting_room.waiting_room_service import WaitingRoomService

@app.route("/")
def index():
    return "Backend"

###################################


@app.route("/http-call")
def http_call():
    """Return JSON with string data as the value"""
    data = {"data": "This text was fetched using an HTTP call to server on render"}
    return jsonify(data)


@socketio.on("init")
def handle_init(data):
    """
    Initialize the connection with user details.
    Expected data: {'username': 'name', 'role': 'role'}
    """
    username = data.get("username")
    role = data.get("role")
    sid = request.sid
    roomName = data.get("roomName")

    user_uuid = str(uuid.uuid4())
    # Update the participants list and increment the count
    if role != 'creator':
        result = rooms_collection.find_one_and_update(
            { "room_name": roomName,
                "participants": {
                    "$not": {
                        "$elemMatch": {
                            "username": username,
                            "role": role
                        }
                    }
                }
            },
            {
                "$addToSet": {
                    "participants": {"username": username, "role": role, "user_id": str(user_uuid)}
                },  # Add user to participants list if not already present
                "$inc": {"participants_count": 1},  # Increment participants count
            },
        )

    room = rooms_collection.find_one({"room_name": roomName})
    all_users = []
    if room:
    # Fetch all users except the current one
        all_users_cursor = room["participants"]
        all_users = [
            {"userid": user["user_id"], "username": user["username"], "role": user["role"]}
            for user in all_users_cursor
        ]

    emit(
        "init_response",
        {"msg": f"Welcome {username}!", "users": all_users},
        broadcast=True,
    )
    print(f"{username} ({role}) connected with SID: {sid}")


@socketio.on("private_message")
def handle_private_message(data):
    """
    Handle private messages between Room Creator and Participants.
    Expected data: {'to': 'recipient_sid', 'message': 'text'}
    """
    from_sid = request.sid
    to_sid = data.get("to")
    message_text = data.get("message")

    sender = users_collection.find_one({"sid": from_sid})
    recipient = users_collection.find_one({"sid": to_sid})

    if sender and recipient:
        # Find or create a private room
        room_id = find_private_room(sender["_id"], recipient["_id"])
        if not room_id:
            room_id = create_room(sender["_id"], recipient["_id"])

        # Join both users to the room
        join_room(room_id, from_sid)
        join_room(room_id, to_sid)

        # Save message to the database
        messages_collection.insert_one(
            {
                "room_id": room_id,
                "sender_id": sender["_id"],
                "message": message_text,
                "timestamp": datetime.datetime.utcnow(),
            }
        )

        # Emit the message to the recipient
        emit(
            "room_message",
            {
                "from": from_sid,
                "message": message_text,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            },
            room=room_id,
        )
        print(f"Private message from {from_sid} to {to_sid}: {message_text}")


def find_private_room(user1_id, user2_id):
    """
    Find a room that includes exactly these two users.
    """
    room = rooms_collection.find_one(
        {"participants": {"$all": [user1_id, user2_id]}, "participants": {"$size": 2}}
    )
    return room["room_id"] if room else None


def create_chat_room(creator_id, participant_id):
    """
    Create a new room for private communication.
    """
    room_id = str(uuid.uuid4())
    rooms_collection.insert_one(
        {
            "room_id": room_id,
            "creator_id": creator_id,
            "participants": [creator_id, participant_id],
            "created_at": datetime.datetime.utcnow(),
        }
    )
    return room_id


users = {}


@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")
    emit("init_response", {"msg": "Connected to server", "users": list(users.values())})


@socketio.on("chat_request")
def handle_chat_request(data):
    """
    Handle chat requests from Guests to Patients.
    Expected data: {'patient_sid': 'patient_socket_id'}
    """
    guest_sid = request.sid
    patient_sid = data.get("patient_sid")

    guest = users_collection.find_one({"sid": guest_sid})
    patient = users_collection.find_one({"sid": patient_sid})

    if guest and patient and patient["role"] == "patient":
        # Notify the Room Creator about the chat request
        creator = users_collection.find_one({"role": "creator"})
        if creator:
            emit(
                "chat_request",
                {
                    "guest_sid": guest_sid,
                    "guest_username": guest["username"],
                    "patient_sid": patient_sid,
                    "patient_username": patient["username"],
                },
                room=creator["sid"],
            )
            print(f"Chat request from {guest_sid} to {patient_sid}")
        else:
            emit("error", {"msg": "Room Creator not connected."}, room=guest_sid)


@socketio.on("chat_response")
def handle_chat_response(data):
    """
    Handle the Room Creator's response to a chat request.
    Expected data: {'guest_sid': 'guest_socket_id', 'patient_sid': 'patient_socket_id', 'approve': True/False}
    """
    guest_sid = data.get("guest_sid")
    patient_sid = data.get("patient_sid")
    approve = data.get("approve")

    guest = users_collection.find_one({"sid": guest_sid})
    patient = users_collection.find_one({"sid": patient_sid})

    if approve:
        # Create a unique room for the Guest and Patient
        room_id = str(uuid.uuid4())
        rooms_collection.insert_one(
            {
                "room_id": room_id,
                "creator_id": guest["_id"],  # Assuming creator manages all rooms
                "participants": [guest["_id"], patient["_id"]],
                "created_at": datetime.datetime.utcnow(),
            }
        )

        # Update users with the room_id
        users_collection.update_one(
            {"_id": guest["_id"]}, {"$set": {"room_id": room_id}}
        )
        users_collection.update_one(
            {"_id": patient["_id"]}, {"$set": {"room_id": room_id}}
        )

        # Join both users to the room
        join_room(room_id, guest_sid)
        join_room(room_id, patient_sid)

        # Notify both users
        emit(
            "chat_approved",
            {"room_id": room_id, "patient_sid": patient_sid, "guest_sid": guest_sid},
            room=guest_sid,
        )

        emit(
            "chat_started",
            {"room_id": room_id, "guest_sid": guest_sid},
            room=patient_sid,
        )

        print(f"Chat approved between {guest_sid} and {patient_sid} in room {room_id}")
    else:
        emit(
            "chat_denied",
            {"msg": "Your chat request was denied by the Room Creator."},
            room=guest_sid,
        )
        print(f"Chat denied for {guest_sid} to chat with {patient_sid}")


@socketio.on("room_message")
def handle_room_message(data):
    """
    Handle messages within a specific room.
    Expected data: {'room_id': 'room_id', 'message': 'text'}
    """
    room_id = data.get("room_id")
    message_text = data.get("message")
    from_name = data.get("from")
    to = data.get("to")
    role = data.get("role")

    sender = users_collection.find_one({"sid": from_name})
    room = rooms_collection.find_one({"room_id": room_id})

    # if sender and room and ObjectId(sender["_id"]) in room["participants"]:
        # Save message to the database
        # messages_collection.insert_one(
        #     {
        #         "room_id": room_id,
        #         "sender_id": sender["_id"],
        #         "message": message_text,
        #         "timestamp": datetime.datetime.utcnow(),
        #     }
        # )

        # Emit the message to the room
    emit(
        "room_message",
        {
            "room": room_id,                
            "from": from_name,
            "to": to,
            "role": role,
            "message": message_text,
            "timestamp": datetime.now().isoformat(),
        },
        # room=room_id,
        broadcast=True
    )
    print(f"Room {room_id}: {from_name} says {message_text} to {to}")


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    try:
        WaitingRoomService.remove_by_sid(sid)
    except Exception:
        pass
    user = users_collection.find_one({"sid": sid})
    if user:
        username = user.get("username", "Unknown")
        role = user.get("role", "Unknown")

        print(f"{username} ({role}) disconnected.")

        # Notify others about the disconnection
        emit("user_disconnected", {"sid": sid, "username": username}, broadcast=True)

        # Leave any rooms the user was part of
        room_id = user.get("room_id")
        if room_id:
            leave_room(room_id, sid)

        # Remove from connected users
        users_collection.delete_one({"_id": user["_id"]})


@socketio.on("get_chat_history")
def handle_get_chat_history(data):
    """
    Retrieve chat history for a specific room.
    Expected data: {'room_id': 'room_id'}
    """
    room_id = data.get("room_id")
    messages_cursor = messages_collection.find({"room_id": room_id}).sort(
        "timestamp", 1
    )
    messages = [
        {
            "sender_id": str(msg["sender_id"]),
            "message": msg["message"],
            "timestamp": msg["timestamp"].isoformat(),
        }
        for msg in messages_cursor
    ]
    emit("chat_history", {"room_id": room_id, "messages": messages})


@socketio.on("join_waiting_room")
def handle_join_waiting(data):
    """Participant (patient/guest) requests to enter the session; host admits via admit_waiting."""
    room_name = data.get("roomName")
    username = data.get("username")
    role = data.get("role")
    sid = request.sid
    if not room_name or not username or not role:
        return
    WaitingRoomService.add_or_update(room_name, sid, username, role, "pending")
    emit(
        "waiting_room_update",
        {
            "room_name": room_name,
            "queue": WaitingRoomService.list_pending(room_name),
        },
        broadcast=True,
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
        broadcast=True,
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
        broadcast=True,
    )


def get_creator_sid():
    """Return the SID of the Room Creator."""
    creator = users_collection.find_one({"role": "creator"})
    return creator["sid"] if creator else None

