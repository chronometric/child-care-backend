from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from constants import Constants
from src.modules.room.room_dtos import CreateRoomBody, UpdateRoomBody

client = MongoClient(Constants.DATABASE_URL)
db = client['CC-database']

class RoomService:

    @staticmethod
    def create(body: CreateRoomBody):
        try:
            room = body.dict()
            room["created_at"] = datetime.utcnow()
            room["updated_at"] = datetime.utcnow()
            result = db.rooms.insert_one(room)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating room: {e}")
            return None

    @staticmethod
    def get_one(room_name: str):
        try:
            room = db.rooms.find_one({"room_name": room_name})
            if room:
                room['_id'] = str(room['_id'])  # Convert ObjectId to string
                room['participants'] = [str(participant) for participant in room.get('participants', [])]
            return room
        except Exception as e:
            print(f"Error fetching room: {e}")
            return None

    @staticmethod
    def get_all(email: str):
        try:
            rooms = list(db.rooms.find({"email": email}))
            return rooms
        except Exception as e:
            print(f"Error fetching rooms: {e}")
            return []

    @staticmethod
    def update_one(room_id: str, body: UpdateRoomBody):
        try:
            updates = {k: v for k, v in body.dict().items() if v is not None}
            updates["updated_at"] = datetime.utcnow()
            result = db.rooms.update_one({"_id": ObjectId(room_id)}, {"$set": updates})
            if result.matched_count > 0:
                updated_room = db.rooms.find_one({"_id": ObjectId(room_id)})
                if updated_room:
                    updated_room['_id'] = str(updated_room['_id'])
                    updated_room['user_id'] = str(updated_room['user_id'])
                    updated_room['participants'] = [str(participant) for participant in updated_room.get('participants', [])]
                return updated_room
            return None
        except Exception as e:
            print(f"Error updating room: {e}")
            return None

    @staticmethod
    def delete_one(room_id: str):
        try:
            db.rooms.delete_one({"_id": ObjectId(room_id)})
            return True
        except Exception as e:
            print(f"Error deleting room: {e}")
            return False

    @staticmethod
    def delete_all():
        try:
            db.rooms.delete_many({})
            return True
        except Exception as e:
            print(f"Error deleting all rooms: {e}")
            return False
        
    @staticmethod
    def check_patient_authentication(password):
        try:
            room = db.rooms.find_one({"patient_password": password})
            is_patient_present = any(participant['role'] == 'patient' for participant in room.get('participants', []))

            if is_patient_present:
                return False
            else:
                return room['room_name']
        except Exception as e:
            print(f"Error authenticating patient: {e}")
            return False
    
    @staticmethod
    def check_guest_authentication(password):
        try:
            room = db.rooms.find_one({"guest_password": password})
            if room:
                return room['room_name']
            return False
        except Exception as e:
            print(f"Error authenticating patient: {e}")
            return False

    @staticmethod
    def get_room_by_patient_password(password: str):
        """Resolve room by patient password without enforcing one-patient-in-room (used for portal APIs)."""
        try:
            room = db.rooms.find_one({"patient_password": password})
            if room:
                room["_id"] = str(room["_id"])
            return room
        except Exception as e:
            print(f"Error resolving room by patient password: {e}")
            return None

