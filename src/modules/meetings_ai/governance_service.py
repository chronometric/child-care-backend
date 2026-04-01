"""Audit log and governance helpers for care / AI features."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pymongo import MongoClient
from constants import Constants

client = MongoClient(Constants.DATABASE_URL)
db = client["CC-database"]
audit_collection = db["care_audit_log"]


def append_audit(
    action: str,
    actor_id: Optional[str],
    actor_email: Optional[str],
    resource_type: str,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    doc = {
        "action": action,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata or {},
        "created_at": datetime.utcnow(),
    }
    return str(audit_collection.insert_one(doc).inserted_id)


def list_audit(limit: int = 100) -> list:
    cur = audit_collection.find().sort("created_at", -1).limit(min(limit, 500))
    out = []
    for row in cur:
        row["_id"] = str(row["_id"])
        if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
            row["created_at"] = row["created_at"].isoformat()
        out.append(row)
    return out


def retention_days() -> int:
    try:
        return int(os.environ.get("MEETINGS_AI_RETENTION_DAYS", "2555"))
    except ValueError:
        return 2555


def retention_until() -> datetime:
    return datetime.utcnow() + timedelta(days=retention_days())


def require_documentation_consent() -> bool:
    return os.environ.get("MEETINGS_AI_REQUIRE_CONSENT", "true").lower() in (
        "1",
        "true",
        "yes",
    )
