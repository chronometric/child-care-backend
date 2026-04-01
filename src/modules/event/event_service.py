from src.modules.event.event_dtos import CreateEventBody, UpdateEventBody
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from constants import Constants
from datetime import datetime, timezone

client = MongoClient(Constants.DATABASE_URL)
db = client['CC-database']

class EventService:

    @staticmethod
    def create(body: CreateEventBody):
        user_id = str(get_jwt_identity())  # Store as a string to match query type
        event_data = {
            "user_id": user_id,
            "event_name": body.event_name,
            "patient_name": body.patient_name,
            "start_time": body.start_time,
            "end_time": body.end_time,
            "description": body.description,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = db.events.insert_one(event_data)
        event_id = str(result.inserted_id)
        try:
            from src.modules.notification.notification_service import NotificationService
            NotificationService.create(
                user_id,
                f"Session scheduled: {body.event_name}",
                (body.description or "")[:500],
                "calendar",
                {"event_id": event_id, "patient_name": body.patient_name or ""},
            )
        except Exception as e:
            print(f"Notification on event create failed: {e}")
        return event_id
    
    @staticmethod
    def get_user_events(user_id: str, start_date: str, end_date: str):
        """Fetch all events for a user within a date range."""
        try:
            start_datetime = datetime.fromisoformat(start_date)
            end_datetime = datetime.fromisoformat(end_date)

            # Query events based on user ID and date range
            events = list(db.events.find({
                "user_id": user_id,  # Match as string to the stored format
                "start_time": {"$gte": start_datetime},
                "end_time": {"$lte": end_datetime}
            }).sort("start_time", -1))

            # Convert fields for JSON response
            for event in events:
                event['_id'] = str(event['_id'])
                event['user_id'] = str(event['user_id'])

            return events
        except Exception as e:
            print(f"Error fetching events: {e}")
            return []

    @staticmethod
    def get_one(event_id: str):
        event = db.events.find_one({"_id": ObjectId(event_id)})
        if event:
            event["_id"] = str(event["_id"])
            return event
        return None

    @staticmethod
    def get_all(user_id: str):
        events = list(db.events.find({"user_id": user_id}).sort("start_time", -1))
        for event in events:
            event["_id"] = str(event["_id"])
        return events

    @staticmethod
    def update_one(event_id: str, body: UpdateEventBody):
        updates = {k: v for k, v in body.dict(exclude_none=True).items()}
        updates["updated_at"] = datetime.utcnow()
        result = db.events.update_one({"_id": ObjectId(event_id)}, {"$set": updates})
        return result.matched_count > 0

    @staticmethod
    def delete_one(event_id: str):
        result = db.events.delete_one({"_id": ObjectId(event_id)})
        return result.deleted_count > 0

    @staticmethod
    def delete_all(user_id: str):
        result = db.events.delete_many({"user_id": user_id})
        return result.deleted_count
