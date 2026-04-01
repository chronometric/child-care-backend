import os
import requests
from typing import Optional
from pymongo import MongoClient
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
reports = db["meeting_reports"]


def _generate_summary(transcript: str, system_prompt: Optional[str] = None) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    prompt = system_prompt or (
        "You are a clinical documentation assistant for child-care telehealth. "
        "Summarize the session transcript into: Key topics, Observed behaviors, "
        "Recommendations, Follow-up. Use neutral, professional language. If content is empty, say so."
    )
    if key and transcript and transcript.strip():
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": transcript[:12000]},
                    ],
                    "temperature": 0.3,
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"OpenAI summary failed: {e}")
    # Draft fallback
    snippet = (transcript or "").strip()[:2000]
    if not snippet:
        return "No transcript text was provided. Add session notes manually."
    return (
        "[Draft summary — configure OPENAI_API_KEY for AI-generated analysis]\n\n"
        f"Transcript excerpt:\n{snippet}"
    )


class MeetingAIService:

    @staticmethod
    def save_report(
        room_name: str,
        doctor_email: str,
        transcript: str,
        patient_personal_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ):
        summary = _generate_summary(transcript, custom_prompt)
        doc = {
            "room_name": room_name,
            "doctor_email": doctor_email,
            "patient_personal_id": patient_personal_id,
            "transcript": transcript,
            "summary": summary,
            "created_at": datetime.utcnow(),
        }
        result = reports.insert_one(doc)
        return str(result.inserted_id), summary

    @staticmethod
    def list_for_room(room_name: str, doctor_email: str):
        cur = reports.find(
            {"room_name": room_name, "doctor_email": doctor_email}
        ).sort("created_at", -1)
        out = []
        for r in cur:
            r["_id"] = str(r["_id"])
            out.append(r)
        return out

    @staticmethod
    def list_for_doctor(doctor_email: str, limit: int = 30):
        cur = reports.find({"doctor_email": doctor_email}).sort("created_at", -1).limit(limit)
        out = []
        for r in cur:
            r["_id"] = str(r["_id"])
            out.append(r)
        return out
