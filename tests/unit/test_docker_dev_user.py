from __future__ import annotations

import pytest

from agent.core import skills
from backend import dependencies


@pytest.mark.asyncio
async def test_docker_restart_uses_cached_user_when_whoami_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("ML_INTERN_DOCKER", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    skills.write_docker_user_id_cache("alice")

    async def fail_whoami(_token: str):
        return None

    async def pro_plan(_token: str):
        return "pro"

    monkeypatch.setattr(dependencies, "fetch_whoami_v2", fail_whoami)
    monkeypatch.setattr(dependencies, "_fetch_user_plan", pro_plan)

    user = await dependencies._dev_user_from_env()
    assert user["user_id"] == "alice"
    assert user["plan"] == "pro"


@pytest.mark.asyncio
async def test_docker_prefers_cached_user_before_whoami(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    monkeypatch.setenv("ML_INTERN_DOCKER", "1")
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    skills.write_docker_user_id_cache("cached-user")

    async def other_whoami(_token: str):
        return {"name": "other-user"}

    async def free_plan(_token: str):
        return "free"

    monkeypatch.setattr(dependencies, "fetch_whoami_v2", other_whoami)
    monkeypatch.setattr(dependencies, "_fetch_user_plan", free_plan)

    user = await dependencies._dev_user_from_env()
    assert user["user_id"] == "cached-user"
