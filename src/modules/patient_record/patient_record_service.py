from typing import Optional
from pymongo import MongoClient
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
profiles = db["patient_profiles"]


class PatientRecordService:
    """Longitudinal patient records keyed by doctor + national id / personal id."""

    @staticmethod
    def _key(doctor_email: str, patient_personal_id: str) -> dict:
        return {"doctor_email": doctor_email.strip().lower(), "patient_personal_id": patient_personal_id.strip()}

    @staticmethod
    def upsert_profile(doctor_email: str, patient_personal_id: str, display_name: Optional[str] = None):
        filt = PatientRecordService._key(doctor_email, patient_personal_id)
        now = datetime.utcnow()
        update = {
            "$setOnInsert": {
                **filt,
                "display_name": display_name or "",
                "notes": [],
                "meetings": [],
                "created_at": now,
            },
            "$set": {"updated_at": now},
        }
        if display_name:
            update["$set"]["display_name"] = display_name
        profiles.update_one(filt, update, upsert=True)
        return profiles.find_one(filt)

    @staticmethod
    def add_note(
        doctor_email: str,
        patient_personal_id: str,
        text: str,
        room_name: Optional[str] = None,
    ):
        doc = PatientRecordService.upsert_profile(doctor_email, patient_personal_id)
        note = {
            "text": text,
            "room_name": room_name,
            "at": datetime.utcnow().isoformat(),
        }
        profiles.update_one(
            PatientRecordService._key(doctor_email, patient_personal_id),
            {"$push": {"notes": note}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return True

    @staticmethod
    def link_meeting(
        doctor_email: str,
        patient_personal_id: str,
        room_name: str,
        patient_display_name: Optional[str] = None,
    ):
        PatientRecordService.upsert_profile(
            doctor_email, patient_personal_id, patient_display_name
        )
        ref = {
            "room_name": room_name,
            "at": datetime.utcnow().isoformat(),
        }
        profiles.update_one(
            PatientRecordService._key(doctor_email, patient_personal_id),
            {"$push": {"meetings": ref}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return True

    @staticmethod
    def list_for_doctor(doctor_email: str):
        cur = profiles.find({"doctor_email": doctor_email.strip().lower()}).sort(
            "updated_at", -1
        )
        out = []
        for p in cur:
            p["_id"] = str(p["_id"])
            out.append(p)
        return out

    @staticmethod
    def get_one(doctor_email: str, patient_personal_id: str):
        doc = profiles.find_one(PatientRecordService._key(doctor_email, patient_personal_id))
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    @staticmethod
    def sync_from_room(room: dict, doctor_email: str):
        """Create/update profile from a room document (patient_name, patient_personal_id)."""
        pid = room.get("patient_personal_id") or ""
        if not pid:
            return None
        name = room.get("patient_name") or ""
        return PatientRecordService.upsert_profile(doctor_email, pid, name)
