"""Shared Hugging Face HTTP helpers (auth / whoami)."""

from __future__ import annotations

import os
from typing import Any

import httpx

OPENID_PROVIDER_URL = os.environ.get("OPENID_PROVIDER_URL", "https://huggingface.co")


async def fetch_whoami_v2(token: str, timeout: float = 5.0) -> dict[str, Any] | None:
    if not token:
        return None
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(
                f"{OPENID_PROVIDER_URL}/api/whoami-v2",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except (httpx.HTTPError, ValueError):
            return None
