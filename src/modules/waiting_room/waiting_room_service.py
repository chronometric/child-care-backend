from pymongo import MongoClient
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
waiting = db["waiting_room_entries"]


class WaitingRoomService:

    @staticmethod
    def add_or_update(room_name: str, sid: str, username: str, role: str, status: str = "pending"):
        waiting.update_one(
            {"room_name": room_name, "sid": sid},
            {
                "$set": {
                    "room_name": room_name,
                    "sid": sid,
                    "username": username,
                    "role": role,
                    "status": status,
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

    @staticmethod
    def list_pending(room_name: str):
        cur = waiting.find({"room_name": room_name, "status": "pending"}).sort(
            "created_at", 1
        )
        return [WaitingRoomService._serialize(d) for d in cur]

    @staticmethod
    def set_status(room_name: str, sid: str, status: str):
        waiting.update_one(
            {"room_name": room_name, "sid": sid},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}},
        )

    @staticmethod
    def remove(room_name: str, sid: str):
        waiting.delete_one({"room_name": room_name, "sid": sid})

    @staticmethod
    def remove_by_sid(sid: str):
        waiting.delete_many({"sid": sid})

    @staticmethod
    def _serialize(d):
        d = dict(d)
        d["_id"] = str(d["_id"])
        return d
