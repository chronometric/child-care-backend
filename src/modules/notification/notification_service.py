from typing import Optional, Dict, Any
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
coll = db["notifications"]


class NotificationService:

    @staticmethod
    def create(user_id: str, title: str, body: str, n_type: str = "info", metadata: Optional[Dict[str, Any]] = None):
        doc = {
            "user_id": str(user_id),
            "title": title,
            "body": body,
            "type": n_type,
            "read": False,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
        }
        result = coll.insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def list_for_user(user_id: str, limit: int = 50):
        cur = coll.find({"user_id": str(user_id)}).sort("created_at", -1).limit(limit)
        out = []
        for n in cur:
            n["_id"] = str(n["_id"])
            out.append(n)
        return out

    @staticmethod
    def mark_read(notification_id: str, user_id: str):
        try:
            r = coll.update_one(
                {"_id": ObjectId(notification_id), "user_id": str(user_id)},
                {"$set": {"read": True}},
            )
            return r.modified_count > 0
        except Exception:
            return False

    @staticmethod
    def mark_all_read(user_id: str):
        coll.update_many({"user_id": str(user_id), "read": False}, {"$set": {"read": True}})
        return True
