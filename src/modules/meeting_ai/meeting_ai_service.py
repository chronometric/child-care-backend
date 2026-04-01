import os
import re
import threading
import requests
from typing import Any, Dict, Optional, Tuple
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
reports = db["meeting_reports"]
transcripts = db["meeting_transcripts"]


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


def _structure_summary_text(text: str) -> Dict[str, Any]:
    """Lightweight structured sections from model output (headings or numbered lines)."""
    out: Dict[str, Any] = {"full_text": text}
    sections = re.split(r"\n(?=#{1,3}\s|\*\*[A-Za-z])", text)
    if len(sections) > 1:
        out["sections"] = [s.strip() for s in sections if s.strip()]
    return out


class MeetingAIService:

    @staticmethod
    def save_report(
        room_name: str,
        doctor_email: str,
        transcript: str,
        patient_personal_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        meeting_id: Optional[str] = None,
        transcript_job_id: Optional[str] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        summary = _generate_summary(transcript, custom_prompt)
        structured = _structure_summary_text(summary)
        doc = {
            "room_name": room_name,
            "doctor_email": doctor_email,
            "patient_personal_id": patient_personal_id,
            "meeting_id": meeting_id,
            "transcript_job_id": transcript_job_id,
            "transcript": transcript,
            "summary": summary,
            "structured_note": structured,
            "created_at": datetime.utcnow(),
        }
        result = reports.insert_one(doc)
        return str(result.inserted_id), summary, structured

    @staticmethod
    def save_transcript(
        room_name: str,
        doctor_email: str,
        raw_text: str,
        source: str = "client",
        meeting_id: Optional[str] = None,
    ) -> str:
        doc = {
            "room_name": room_name,
            "doctor_email": doctor_email,
            "meeting_id": meeting_id,
            "raw_text": raw_text,
            "source": source,
            "status": "pending",
            "created_at": datetime.utcnow(),
        }
        return str(transcripts.insert_one(doc).inserted_id)

    @staticmethod
    def run_pipeline_async(
        transcript_oid: str,
        patient_personal_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> None:
        """Fire-and-forget: transcript row → summary → meeting_reports."""

        def _run():
            try:
                doc = transcripts.find_one({"_id": ObjectId(transcript_oid)})
                if not doc:
                    return
                room_name = doc["room_name"]
                doctor_email = doc["doctor_email"]
                raw = doc.get("raw_text") or ""
                meeting_id = doc.get("meeting_id")
                report_id, _summary, _struct = MeetingAIService.save_report(
                    room_name,
                    doctor_email,
                    raw,
                    patient_personal_id=patient_personal_id,
                    custom_prompt=custom_prompt,
                    meeting_id=meeting_id,
                    transcript_job_id=transcript_oid,
                )
                transcripts.update_one(
                    {"_id": ObjectId(transcript_oid)},
                    {
                        "$set": {
                            "status": "complete",
                            "report_id": report_id,
                            "completed_at": datetime.utcnow(),
                        }
                    },
                )
            except Exception as e:
                print(f"AI pipeline job failed: {e}")
                try:
                    transcripts.update_one(
                        {"_id": ObjectId(transcript_oid)},
                        {"$set": {"status": "error", "error": str(e)}},
                    )
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def list_for_room(room_name: str, doctor_email: str):
        cur = reports.find(
            {"room_name": room_name, "doctor_email": doctor_email}
        ).sort("created_at", -1)
        out = []
        for r in cur:
            out.append(MeetingAIService._serialize_report_doc(r))
        return out

    @staticmethod
    def list_for_doctor(doctor_email: str, limit: int = 30):
        cur = reports.find({"doctor_email": doctor_email}).sort("created_at", -1).limit(limit)
        out = []
        for r in cur:
            out.append(MeetingAIService._serialize_report_doc(r))
        return out

    @staticmethod
    def _serialize_report_doc(r: dict) -> dict:
        doc = dict(r)
        doc["_id"] = str(doc["_id"])
        ca = doc.get("created_at")
        if ca is not None and hasattr(ca, "isoformat"):
            doc["created_at"] = ca.isoformat()
        return doc
