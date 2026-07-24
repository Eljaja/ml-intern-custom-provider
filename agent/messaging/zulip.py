import base64

import httpx

from agent.messaging.base import (
    NotificationError,
    NotificationProvider,
    RetryableNotificationError,
)
from agent.messaging.models import (
    NotificationRequest,
    NotificationResult,
    ZulipDestinationConfig,
)

_SEVERITY_PREFIX = {
    "info": "INFO",
    "success": "SUCCESS",
    "warning": "WARNING",
    "error": "ERROR",
}


def _format_text(request: NotificationRequest) -> str:
    lines: list[str] = []
    prefix = _SEVERITY_PREFIX[request.severity]
    if request.title:
        lines.append(f"**[{prefix}] {request.title}**")
    else:
        lines.append(f"**[{prefix}]**")
    lines.append(request.message)
    for key, value in request.metadata.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def _basic_auth_header(email: str, api_key: str) -> str:
    token = base64.b64encode(f"{email}:{api_key}".encode()).decode("ascii")
    return f"Basic {token}"


class ZulipProvider(NotificationProvider):
    provider_name = "zulip"

    async def send(
        self,
        client: httpx.AsyncClient,
        destination_name: str,
        destination: ZulipDestinationConfig,
        request: NotificationRequest,
    ) -> NotificationResult:
        site = destination.site.rstrip("/")
        payload: dict[str, str] = {
            "type": destination.message_type,
            "content": _format_text(request),
        }
        if destination.message_type == "stream":
            payload["to"] = destination.stream or ""
            payload["topic"] = destination.topic
        else:
            payload["to"] = destination.to or ""

        try:
            response = await client.post(
                f"{site}/api/v1/messages",
                headers={
                    "Authorization": _basic_auth_header(
                        destination.email, destination.api_key
                    ),
                },
                data=payload,
            )
        except httpx.TimeoutException as exc:
            raise RetryableNotificationError("Zulip request timed out") from exc
        except httpx.TransportError as exc:
            raise RetryableNotificationError("Zulip transport error") from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableNotificationError(f"Zulip HTTP {response.status_code}")
        if response.status_code >= 400:
            detail = response.text[:200]
            raise NotificationError(f"Zulip HTTP {response.status_code}: {detail}")

        try:
            data = response.json()
        except ValueError as exc:
            raise RetryableNotificationError("Zulip returned invalid JSON") from exc

        if data.get("result") != "success":
            error = str(data.get("msg") or data.get("code") or "unknown_error")
            if "rate" in error.lower():
                raise RetryableNotificationError(error)
            raise NotificationError(error)

        message_id = data.get("id")
        return NotificationResult(
            destination=destination_name,
            ok=True,
            provider=self.provider_name,
            external_id=str(message_id) if message_id is not None else None,
            error=None,
        )
