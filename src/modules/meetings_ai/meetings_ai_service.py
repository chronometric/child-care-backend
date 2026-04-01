"""Phase 3: clinical documentation reports (Markdown + PDF in GridFS)."""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import requests
from pymongo import MongoClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

from constants import Constants
from src.modules.file_system.file_system_service import FileSystemService
from src.modules.meetings_ai.clinical_prompts import CLINICAL_SESSION_REPORT_SYSTEM
from src.modules.meetings_ai import governance_service as gov

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
meetings_ai_reports = db["meetings_ai_reports"]
meetings_ai_transcripts = db["meetings_ai_transcripts"]


def _openai_generate(transcript: str, system_prompt: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key or not (transcript or "").strip():
        snippet = (transcript or "").strip()[:2000]
        if not snippet:
            return "No transcript text was provided. Documentation cannot be generated."
        return (
            "[Draft — configure OPENAI_API_KEY]\n\n"
            + CLINICAL_SESSION_REPORT_SYSTEM[:200]
            + "\n\n---\n\nTranscript excerpt:\n"
            + snippet
        )
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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (transcript or "")[:14000]},
                ],
                "temperature": 0.2,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"meetings_ai OpenAI error: {e}")
        return f"[Generation failed: {e}]\n\nTranscript excerpt:\n{(transcript or '')[:1500]}"


def _markdown_report(
    room_name: str,
    doctor_email: str,
    patient_personal_id: Optional[str],
    body: str,
) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"# Session documentation (draft)\n\n"
        f"- **Room:** `{room_name}`\n"
        f"- **Clinician / account:** {doctor_email}\n"
        f"- **Patient identifier (if provided):** {patient_personal_id or '—'}\n"
        f"- **Generated:** {ts}\n\n"
        f"> This text is documentation support only. It is not a diagnosis or legal record.\n\n"
        f"---\n\n"
    )
    return header + body.strip()


def _text_to_pdf_bytes(text: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    margin = 2 * cm
    y = h - margin
    c.setFont("Helvetica", 10)
    lines = text.replace("\r\n", "\n").split("\n")
    line_height = 12
    max_width = w - 2 * margin
    for line in lines:
        if y < margin + 20:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - margin
        # simple wrap by character chunks for long lines
        chunk = line
        while len(chunk) > 90:
            c.drawString(margin, y, chunk[:90])
            chunk = chunk[90:]
            y -= line_height
            if y < margin + 20:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = h - margin
        try:
            c.drawString(margin, y, chunk[:200])
        except Exception:
            c.drawString(margin, y, chunk.encode("ascii", "replace").decode("ascii")[:200])
        y -= line_height
    c.save()
    buf.seek(0)
    return buf.read()


class MeetingsAIService:

    @staticmethod
    def store_transcript(
        room_name: str,
        doctor_email: str,
        user_id: str,
        raw_text: str,
        source: str = "manual",
    ) -> str:
        doc = {
            "room_name": room_name,
            "doctor_email": doctor_email,
            "user_id": user_id,
            "raw_text": raw_text,
            "source": source,
            "created_at": datetime.utcnow(),
        }
        return str(meetings_ai_transcripts.insert_one(doc).inserted_id)

    @staticmethod
    def generate_and_store_report(
        user_id: str,
        doctor_email: str,
        room_name: str,
        transcript: str,
        patient_personal_id: Optional[str],
        consent_acknowledged: bool,
        visible_to_patient: bool,
    ) -> Tuple[str, Dict[str, Any]]:
        if gov.require_documentation_consent() and not consent_acknowledged:
            raise ValueError("documentation_consent_required")

        body = _openai_generate(transcript, CLINICAL_SESSION_REPORT_SYSTEM)
        md_content = _markdown_report(
            room_name, doctor_email, patient_personal_id, body
        )
        md_bytes = md_content.encode("utf-8")
        safe_room = re.sub(r"[^\w\-]+", "_", room_name)[:40]
        md_name = f"session_doc_{safe_room}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.md"
        md_id = FileSystemService.upload_file(
            user_id=user_id,
            folder_name="meetings_ai",
            file_data=md_bytes,
            filename=md_name,
            content_type="text/markdown",
            patient_personal_id=patient_personal_id,
            room_name=room_name,
            shared_with_patient=visible_to_patient,
        )
        pdf_bytes = _text_to_pdf_bytes(md_content)
        pdf_name = md_name.replace(".md", ".pdf")
        pdf_id = FileSystemService.upload_file(
            user_id=user_id,
            folder_name="meetings_ai",
            file_data=pdf_bytes,
            filename=pdf_name,
            content_type="application/pdf",
            patient_personal_id=patient_personal_id,
            room_name=room_name,
            shared_with_patient=visible_to_patient,
        )
        ret = gov.retention_until()
        rep = {
            "room_name": room_name,
            "doctor_email": doctor_email,
            "user_id": user_id,
            "patient_personal_id": patient_personal_id,
            "summary_text": body[:8000],
            "markdown_file_id": md_id,
            "pdf_file_id": pdf_id,
            "visible_to_patient": visible_to_patient,
            "consent_acknowledged": consent_acknowledged,
            "retention_until": ret,
            "created_at": datetime.utcnow(),
        }
        rid = str(meetings_ai_reports.insert_one(rep).inserted_id)
        gov.append_audit(
            "meetings_ai.report_generated",
            user_id,
            doctor_email,
            "meetings_ai_report",
            rid,
            {"room_name": room_name, "visible_to_patient": visible_to_patient},
        )
        return rid, rep

    @staticmethod
    def list_reports_for_doctor(doctor_email: str, limit: int = 30) -> List[dict]:
        cur = meetings_ai_reports.find({"doctor_email": doctor_email}).sort(
            "created_at", -1
        ).limit(limit)
        out = []
        for r in cur:
            r["_id"] = str(r["_id"])
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            if r.get("retention_until") and hasattr(r["retention_until"], "isoformat"):
                r["retention_until"] = r["retention_until"].isoformat()
            out.append(r)
        return out

    @staticmethod
    def list_visible_for_patient(patient_personal_id: Optional[str]) -> List[dict]:
        if not patient_personal_id or not str(patient_personal_id).strip():
            return []
        cur = (
            meetings_ai_reports.find(
                {
                    "visible_to_patient": True,
                    "patient_personal_id": patient_personal_id.strip(),
                }
            )
            .sort("created_at", -1)
            .limit(50)
        )
        out = []
        for r in cur:
            r["_id"] = str(r["_id"])
            r.pop("summary_text", None)
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            if r.get("retention_until") and hasattr(r["retention_until"], "isoformat"):
                r["retention_until"] = r["retention_until"].isoformat()
            out.append(r)
        return out

    @staticmethod
    def run_generate_async(**kwargs) -> None:
        def _run():
            try:
                MeetingsAIService.generate_and_store_report(**kwargs)
            except Exception as e:
                print(f"meetings_ai async generate failed: {e}")

        threading.Thread(target=_run, daemon=True).start()
