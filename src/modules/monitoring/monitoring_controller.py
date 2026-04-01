"""Health and admin-only monitoring (errors hook via Sentry in connector; Metered usage here)."""

from __future__ import annotations

import os
import time

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.modules.admin.admin_service import AdminService
from src.modules.monitoring.monitoring_service import fetch_metered_usage_charges

monitoring_controller = Blueprint("monitoring", __name__)

_start_time = time.monotonic()


@monitoring_controller.route("/health", methods=["GET"])
def health():
    """Liveness/readiness — no auth."""
    return (
        jsonify(
            {
                "status": "ok",
                "service": "child-care-backend",
                "sentry_enabled": bool(os.environ.get("SENTRY_DSN")),
            }
        ),
        200,
    )


@monitoring_controller.route("/ready", methods=["GET"])
def ready():
    """Optional: extend with DB ping later."""
    return jsonify({"ready": True}), 200


@monitoring_controller.route("/overview", methods=["GET"])
@jwt_required()
def monitoring_overview():
    """Admin JWT only: Metered usage snapshot + uptime."""
    admin_id = get_jwt_identity()
    if not AdminService.get_one(str(admin_id)):
        return jsonify({"error": "Forbidden"}), 403

    uptime_s = int(time.monotonic() - _start_time)
    metered = fetch_metered_usage_charges()

    return (
        jsonify(
            {
                "uptime_seconds": uptime_s,
                "metered_usage_30d": metered,
                "errors": {
                    "note": "Configure SENTRY_DSN in connector for error tracking and performance traces.",
                },
            }
        ),
        200,
    )
