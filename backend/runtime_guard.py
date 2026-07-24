"""Refuse to boot in the one configuration that is remotely exploitable.

``AGENT_LOCAL_MODE=1`` gives the agent ``bash``/``read``/``write`` on the machine
running uvicorn — that is the whole point of local mode, and it is fine on a
developer laptop. It stops being fine when it is combined with the other two
defaults of ``docker compose up``:

* Auth is off. ``backend.dependencies.AUTH_ENABLED`` is
  ``bool(os.environ["OAUTH_CLIENT_ID"])``, and neither docker-compose.yaml nor
  .env.example sets ``OAUTH_CLIENT_ID``. Every request is served as the ``dev``
  user, at the Pro quota tier.
* The port is published on every interface. ``ports: "7860:7860"`` binds
  0.0.0.0 on the host.

Together those three mean anyone who can reach the host on 7860 can ask the
agent to run ``env`` and read ``HF_TOKEN``, ``ANTHROPIC_API_KEY``,
``GITHUB_TOKEN`` and ``ZULIP_API_KEY`` straight out of the container.

The process cannot see how uvicorn was told to bind (that is decided by the
``--host`` argument, which is not exposed to the app), so rather than guessing we
require the operator to say out loud that the exposure is understood and bounded:
set ``ML_INTERN_ALLOW_UNAUTHENTICATED_LOCAL_MODE=1``. docker-compose.yaml sets it
alongside loopback-only port bindings.
"""

from __future__ import annotations

import os

TRUTHY = ("1", "true", "yes", "on")

LOCAL_MODE_ENV = "AGENT_LOCAL_MODE"
OVERRIDE_ENV = "ML_INTERN_ALLOW_UNAUTHENTICATED_LOCAL_MODE"
OAUTH_ENV = "OAUTH_CLIENT_ID"


class UnsafeRuntimeConfigError(RuntimeError):
    """Raised at startup for a remotely exploitable env combination."""


def _is_truthy(env: dict[str, str], name: str) -> bool:
    return (env.get(name) or "").strip().lower() in TRUTHY


def unsafe_runtime_reason(env: dict[str, str] | None = None) -> str | None:
    """Return an operator-facing reason to refuse startup, or None if safe."""
    env = os.environ if env is None else env  # type: ignore[assignment]

    if not _is_truthy(env, LOCAL_MODE_ENV):
        return None
    if (env.get(OAUTH_ENV) or "").strip():
        return None
    if _is_truthy(env, OVERRIDE_ENV):
        return None

    return (
        f"{LOCAL_MODE_ENV}=1 grants the agent shell access on this machine, but "
        f"{OAUTH_ENV} is unset, so authentication is disabled and every request "
        "is served as the 'dev' user. Anyone who can reach this port can run "
        "arbitrary commands and read the API keys in this process's environment."
        "\n\nPick one:\n"
        f"  * Set {OAUTH_ENV} (and the rest of the HF OAuth config) to require "
        "a real login.\n"
        f"  * Unset {LOCAL_MODE_ENV} to run tools in a remote sandbox instead.\n"
        f"  * If, and only if, this port is bound to loopback and the host is "
        f"trusted, set {OVERRIDE_ENV}=1 to acknowledge the exposure."
    )


def assert_safe_runtime(env: dict[str, str] | None = None) -> None:
    """Raise :class:`UnsafeRuntimeConfigError` for an unsafe env combination."""
    reason = unsafe_runtime_reason(env)
    if reason is not None:
        raise UnsafeRuntimeConfigError(reason)
