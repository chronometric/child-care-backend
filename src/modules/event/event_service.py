from typing import List, Optional

from src.modules.event.event_dtos import CreateEventBody, UpdateEventBody
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from constants import Constants

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
            "patient_personal_id": (
                body.patient_personal_id.strip() if body.patient_personal_id else None
            ),
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
        """Fetch events for a user overlapping [start_date, end_date)."""
        try:
            def _parse(d: str) -> datetime:
                s = d.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt

            start_datetime = _parse(start_date)
            end_datetime = _parse(end_date)

            events = list(
                db.events.find(
                    {
                        "user_id": user_id,
                        "start_time": {"$lt": end_datetime},
                        "end_time": {"$gt": start_datetime},
                    }
                ).sort("start_time", 1)
            )

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
        if hasattr(body, "model_dump"):
            raw = body.model_dump(exclude_none=True)
        else:
            raw = body.dict(exclude_none=True)
        updates = {k: v for k, v in raw.items()}
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

    @staticmethod
    def get_upcoming_for_patient(patient_personal_id: Optional[str], patient_name: Optional[str]) -> List[dict]:
        """Sessions scheduled from now, matched by stable id and/or display name."""
        now = datetime.utcnow()
        or_clauses = []
        if patient_personal_id and str(patient_personal_id).strip():
            or_clauses.append({"patient_personal_id": patient_personal_id.strip()})
        if patient_name and str(patient_name).strip():
            or_clauses.append({"patient_name": patient_name.strip()})
        if not or_clauses:
            return []
        cur = (
            db.events.find({"$or": or_clauses, "start_time": {"$gte": now}})
            .sort("start_time", 1)
            .limit(100)
        )
        out = []
        for event in cur:
            event["_id"] = str(event["_id"])
            if event.get("start_time") and hasattr(event["start_time"], "isoformat"):
                event["start_time"] = event["start_time"].isoformat()
            if event.get("end_time") and hasattr(event["end_time"], "isoformat"):
                event["end_time"] = event["end_time"].isoformat()
            if event.get("created_at") and hasattr(event["created_at"], "isoformat"):
                event["created_at"] = event["created_at"].isoformat()
            if event.get("updated_at") and hasattr(event["updated_at"], "isoformat"):
                event["updated_at"] = event["updated_at"].isoformat()
            out.append(event)
        return out
