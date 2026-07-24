"""Procedural skill tools for local web sessions."""

from __future__ import annotations

import json
from typing import Any

from agent.core import skills

SKILLS_LIST_TOOL_SPEC = {
    "name": "skills_list",
    "description": (
        "List enabled procedural skills available to this user. Use this when "
        "you need to discover reusable workflows before starting a task."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


SKILL_VIEW_TOOL_SPEC = {
    "name": "skill_view",
    "description": (
        "Load the full content of one enabled procedural skill by name. Call "
        "this before relying on a skill's procedure beyond its summary."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill slug, for example 'deploy-model'.",
            }
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}


SKILL_MANAGE_TOOL_SPEC = {
    "name": "skill_manage",
    "description": (
        "Create or update reusable procedural skills for future web sessions. "
        "Use this automatically after discovering a non-trivial reusable workflow. "
        "Do not store secrets, credentials, or one-off task facts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "edit", "patch"],
                "description": "create/edit writes full content; patch replaces one exact string.",
            },
            "name": {
                "type": "string",
                "description": "Skill slug using lowercase letters, digits, hyphens, or underscores.",
            },
            "description": {
                "type": "string",
                "description": (
                    "Short selection summary; required for create/edit. This is "
                    "what future sessions match against when picking a skill."
                ),
            },
            "content": {
                "type": "string",
                "description": "Full SKILL.md body content for create/edit.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact existing content to replace for patch.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement content for patch.",
            },
        },
        "required": ["action", "name"],
        "additionalProperties": False,
    },
}


def _user_id(session: Any) -> str | None:
    return getattr(session, "user_id", None)


async def skills_list_handler(
    _params: dict[str, Any], *, session: Any = None
) -> tuple[str, bool]:
    summaries = skills.enabled_skill_summaries(_user_id(session))
    return json.dumps({"skills": summaries}, indent=2), True


async def skill_view_handler(
    params: dict[str, Any], *, session: Any = None
) -> tuple[str, bool]:
    name = str(params.get("name") or "")
    try:
        skill = skills.get_skill(_user_id(session), name, require_enabled=True)
        if skill is None:
            return f"Skill '{name}' was not found or is disabled.", False
        skills.record_skill_used(_user_id(session), name)
        return (
            f"# Skill: {skill.name}\n\n"
            f"Description: {skill.description}\n\n"
            f"{skill.content}",
            True,
        )
    except skills.SkillError as e:
        return f"Skill error: {e}", False


async def skill_manage_handler(
    params: dict[str, Any], *, session: Any = None
) -> tuple[str, bool]:
    action = str(params.get("action") or "")
    name = str(params.get("name") or "")
    try:
        if action in {"create", "edit"}:
            content = str(params.get("content") or "")
            description = str(params.get("description") or "")
            if not content.strip():
                return "Skill content is required for create/edit.", False
            if not description.strip():
                # The description is the only thing a future session sees when
                # deciding whether to open a skill; defaulting it to
                # "No description provided." makes the skill unfindable.
                return (
                    "A description is required — it is what future sessions "
                    "match against when choosing a skill.",
                    False,
                )
            skill = skills.upsert_skill(
                _user_id(session),
                name=name,
                description=description,
                content=content,
                created_by="agent",
            )
        elif action == "patch":
            skill = skills.patch_skill(
                _user_id(session),
                name=name,
                old_string=str(params.get("old_string") or ""),
                new_string=str(params.get("new_string") or ""),
            )
        else:
            return "Unsupported skill_manage action. Use create, edit, or patch.", False

        if session is not None:
            refresh = getattr(session, "refresh_system_prompt", None)
            if callable(refresh):
                refresh()
            send_event = getattr(session, "send_event", None)
            if callable(send_event):
                from agent.core.session import Event

                await send_event(
                    Event(
                        event_type="skills_updated",
                        data={
                            "name": skill.name,
                            "action": action,
                            "enabled": skill.enabled,
                        },
                    )
                )

        return json.dumps({"skill": skill.summary(), "action": action}, indent=2), True
    except skills.SkillError as e:
        return f"Skill error: {e}", False
