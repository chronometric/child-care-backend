from pymongo import MongoClient
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
settings_coll = db["system_settings"]


DEFAULT_AI = {
    "openai_model": "gpt-4o-mini",
    "system_prompt_override": "",
    "waiting_room_enabled": True,
}


class AdminSystemService:

    @staticmethod
    def get_ai_config():
        doc = settings_coll.find_one({"_id": "ai_config"})
        if not doc:
            return {**DEFAULT_AI}
        out = {k: v for k, v in doc.items() if k != "_id"}
        return {**DEFAULT_AI, **out}

    @staticmethod
    def set_ai_config(updates: dict):
        updates["updated_at"] = datetime.utcnow()
        settings_coll.update_one(
            {"_id": "ai_config"},
            {"$set": updates, "$setOnInsert": {"_id": "ai_config"}},
            upsert=True,
        )
        return AdminSystemService.get_ai_config()

    @staticmethod
    def system_overview():
        return {
            "users_count": db.users.count_documents({}),
            "rooms_count": db.rooms.count_documents({}),
            "events_count": db.events.count_documents({}),
            "patient_profiles_count": db.patient_profiles.count_documents({}),
            "meeting_reports_count": db.meeting_reports.count_documents({}),
            "notifications_count": db.notifications.count_documents({}),
        }
