"""Optional Metered usage fetch for admin monitoring (server-side secret only)."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, Optional

import requests


def fetch_metered_usage_charges() -> Optional[Dict[str, Any]]:
    """
    Calls Metered payment usage API when METERED_DOMAIN + METERED_SECRET_KEY are set.
    See: https://www.metered.ca/docs/turn-rest-api/get-usage-charges/
    """
    domain = (os.environ.get("METERED_DOMAIN") or "").strip()
    secret = (os.environ.get("METERED_SECRET_KEY") or "").strip()
    if not domain or not secret:
        return None
    end = date.today()
    start = end - timedelta(days=30)
    url = f"https://{domain}/api/v2/payment/usage-charges"
    try:
        r = requests.get(
            url,
            params={
                "secretKey": secret,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "metered_fetch": "failed"}
