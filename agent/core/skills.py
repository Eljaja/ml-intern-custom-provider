"""Filesystem-backed procedural skills for local web sessions."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from agent.core.redact import scrub_string

_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,80}$")
_SAFE_USER_RE = re.compile(r"[^a-zA-Z0-9_.@-]+")
_FRONTMATTER_DELIM = "---"
_DEFAULT_SKILLS_DIR = Path.home() / ".config" / "ml-intern" / "skills"


class SkillError(ValueError):
    """Raised for invalid skill storage operations."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    content: str
    enabled: bool
    created_by: str
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    use_count: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
        }

    def detail(self) -> dict[str, Any]:
        return {**self.summary(), "content": self.content}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_timestamp(value: Any) -> str | None:
    """Normalize YAML frontmatter timestamps to ISO strings for API models."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()
    text = str(value).strip()
    return text or None


def _skill_name_from_storage(dir_name: str, meta_name: Any) -> str:
    """Resolve a skill slug from on-disk layout, including legacy folder names."""
    candidates: list[str] = []
    if meta_name is not None and str(meta_name).strip():
        candidates.append(str(meta_name).strip().lower())
    candidates.append(dir_name.strip().lower())
    for candidate in candidates:
        try:
            return validate_skill_name(candidate)
        except SkillError:
            slug = re.sub(r"[^a-z0-9_-]+", "-", candidate).strip("-")
            if not slug:
                continue
            try:
                return validate_skill_name(slug)
            except SkillError:
                continue
    raise SkillError(f"Invalid skill name for directory {dir_name!r}")


def skills_root() -> Path:
    configured = os.environ.get("ML_INTERN_SKILLS_DIR")
    root = Path(configured).expanduser() if configured else _DEFAULT_SKILLS_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_docker_deploy() -> bool:
    return os.environ.get("ML_INTERN_DOCKER", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def docker_user_id_cache_path() -> Path | None:
    if not is_docker_deploy():
        return None
    return skills_root() / ".last-user-id"


def read_docker_user_id_cache() -> str | None:
    path = docker_user_id_cache_path()
    if path is None or not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def migrate_dev_skills_if_needed(user_id: str) -> int:
    """Move skills created under the fallback ``dev`` user into the real HF namespace."""
    target = safe_user_id(user_id)
    if target == "dev":
        return 0
    dev_dir = _user_dir("dev")
    user_dir = _user_dir(user_id)
    if not dev_dir.is_dir():
        return 0
    user_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for skill_dir in sorted(dev_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        destination = user_dir / skill_dir.name
        if destination.exists():
            continue
        skill_dir.rename(destination)
        moved += 1
    return moved


def write_docker_user_id_cache(user_id: str) -> None:
    path = docker_user_id_cache_path()
    if path is None:
        return
    migrate_dev_skills_if_needed(user_id)
    path.write_text(safe_user_id(user_id), encoding="utf-8")


def validate_skill_name(name: str) -> str:
    normalized = (name or "").strip().lower()
    if not _SKILL_NAME_RE.fullmatch(normalized):
        raise SkillError(
            "Skill name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, hyphens, or underscores."
        )
    return normalized


def safe_user_id(user_id: str | None) -> str:
    raw = (user_id or "dev").strip() or "dev"
    safe = _SAFE_USER_RE.sub("_", raw).strip("._")
    return safe or "dev"


def _user_dir(user_id: str | None) -> Path:
    root = skills_root().resolve()
    user_dir = (root / safe_user_id(user_id)).resolve()
    if root not in user_dir.parents and user_dir != root:
        raise SkillError("Invalid user skills path.")
    return user_dir


def _skill_dir(user_id: str | None, name: str) -> Path:
    user_dir = _user_dir(user_id)
    skill_dir = (user_dir / validate_skill_name(name)).resolve()
    if user_dir not in skill_dir.parents:
        raise SkillError("Invalid skill path.")
    return skill_dir


def _skill_path(user_id: str | None, name: str) -> Path:
    return _skill_dir(user_id, name) / "SKILL.md"


def _redact_secrets(text: str) -> str:
    """Scrub secrets before a skill is written to disk.

    Delegates to :mod:`agent.core.redact`, the scrubber already used for
    uploaded session trajectories. This module used to carry its own weaker
    copy of the patterns (hf_ from 20 chars instead of 30, sk- from 20 instead
    of 40, no GitHub PAT / AWS / Bearer coverage); two copies could only drift.
    """
    return scrub_string(text)


def _parse_skill_markdown(path: Path) -> Skill:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith(f"{_FRONTMATTER_DELIM}\n"):
        raise SkillError(f"Skill {path} is missing YAML frontmatter.")
    end = raw.find(f"\n{_FRONTMATTER_DELIM}\n", len(_FRONTMATTER_DELIM) + 1)
    if end == -1:
        raise SkillError(f"Skill {path} has malformed YAML frontmatter.")

    frontmatter_raw = raw[len(_FRONTMATTER_DELIM) + 1 : end]
    body = raw[end + len(f"\n{_FRONTMATTER_DELIM}\n") :]
    meta = yaml.safe_load(frontmatter_raw) or {}
    if not isinstance(meta, dict):
        raise SkillError(f"Skill {path} frontmatter must be a YAML object.")

    name = _skill_name_from_storage(path.parent.name, meta.get("name"))
    description = str(meta.get("description") or "").strip()
    if not description:
        description = "No description provided."

    return Skill(
        name=name,
        description=description,
        content=body.strip(),
        enabled=bool(meta.get("enabled", True)),
        created_by=str(meta.get("created_by") or "agent"),
        created_at=_coerce_timestamp(meta.get("created_at")) or utc_now_iso(),
        updated_at=_coerce_timestamp(meta.get("updated_at")) or utc_now_iso(),
        last_used_at=_coerce_timestamp(meta.get("last_used_at")),
        use_count=int(meta.get("use_count") or 0),
    )


def _skill_markdown(skill: Skill) -> str:
    meta = {
        "name": skill.name,
        "description": skill.description,
        "enabled": skill.enabled,
        "created_by": skill.created_by,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }
    if skill.last_used_at:
        meta["last_used_at"] = skill.last_used_at
    if skill.use_count:
        meta["use_count"] = skill.use_count
    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=False).strip()
    body = skill.content.strip()
    return f"{_FRONTMATTER_DELIM}\n{frontmatter}\n{_FRONTMATTER_DELIM}\n\n{body}\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def list_skills(user_id: str | None, *, enabled_only: bool = False) -> list[Skill]:
    user_dir = _user_dir(user_id)
    if not user_dir.exists():
        return []

    skills: list[Skill] = []
    for skill_file in sorted(user_dir.glob("*/SKILL.md")):
        try:
            skill = _parse_skill_markdown(skill_file)
        except Exception:
            continue
        if enabled_only and not skill.enabled:
            continue
        skills.append(skill)
    return skills


def get_skill(
    user_id: str | None, name: str, *, require_enabled: bool = False
) -> Skill | None:
    path = _skill_path(user_id, name)
    if not path.exists():
        return None
    skill = _parse_skill_markdown(path)
    if require_enabled and not skill.enabled:
        return None
    return skill


def upsert_skill(
    user_id: str | None,
    *,
    name: str,
    description: str,
    content: str,
    created_by: str = "agent",
    enabled: bool | None = None,
) -> Skill:
    skill_name = validate_skill_name(name)
    existing = get_skill(user_id, skill_name)
    now = utc_now_iso()
    enabled_value = existing.enabled if enabled is None and existing else bool(enabled)
    if enabled is None and existing is None:
        enabled_value = True

    skill = Skill(
        name=skill_name,
        description=(description or "").strip() or "No description provided.",
        content=_redact_secrets(content or ""),
        enabled=enabled_value,
        created_by=existing.created_by if existing else created_by,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        last_used_at=existing.last_used_at if existing else None,
        use_count=existing.use_count if existing else 0,
    )
    _atomic_write(_skill_path(user_id, skill_name), _skill_markdown(skill))
    return skill


def patch_skill(
    user_id: str | None,
    *,
    name: str,
    old_string: str,
    new_string: str,
) -> Skill:
    skill_name = validate_skill_name(name)
    existing = get_skill(user_id, skill_name)
    if existing is None:
        raise SkillError(f"Skill '{skill_name}' does not exist.")
    if not old_string:
        raise SkillError("old_string is required for patch.")
    if existing.content.count(old_string) != 1:
        raise SkillError("old_string must match exactly one location in the skill.")
    content = existing.content.replace(old_string, _redact_secrets(new_string), 1)
    updated = Skill(
        name=existing.name,
        description=existing.description,
        content=content,
        enabled=existing.enabled,
        created_by=existing.created_by,
        created_at=existing.created_at,
        updated_at=utc_now_iso(),
        last_used_at=existing.last_used_at,
        use_count=existing.use_count,
    )
    _atomic_write(_skill_path(user_id, skill_name), _skill_markdown(updated))
    return updated


def set_skill_enabled(user_id: str | None, name: str, enabled: bool) -> Skill:
    skill_name = validate_skill_name(name)
    existing = get_skill(user_id, skill_name)
    if existing is None:
        raise SkillError(f"Skill '{skill_name}' does not exist.")
    updated = Skill(
        name=existing.name,
        description=existing.description,
        content=existing.content,
        enabled=enabled,
        created_by=existing.created_by,
        created_at=existing.created_at,
        updated_at=utc_now_iso(),
        last_used_at=existing.last_used_at,
        use_count=existing.use_count,
    )
    _atomic_write(_skill_path(user_id, skill_name), _skill_markdown(updated))
    return updated


def record_skill_used(user_id: str | None, name: str) -> Skill | None:
    existing = get_skill(user_id, name)
    if existing is None:
        return None
    updated = Skill(
        name=existing.name,
        description=existing.description,
        content=existing.content,
        enabled=existing.enabled,
        created_by=existing.created_by,
        created_at=existing.created_at,
        updated_at=existing.updated_at,
        last_used_at=utc_now_iso(),
        use_count=existing.use_count + 1,
    )
    _atomic_write(_skill_path(user_id, existing.name), _skill_markdown(updated))
    return updated


def enabled_skill_summaries(user_id: str | None) -> list[dict[str, Any]]:
    return [skill.summary() for skill in list_skills(user_id, enabled_only=True)]


def format_skill_index(user_id: str | None) -> str:
    summaries = enabled_skill_summaries(user_id)
    if not summaries:
        return "No enabled skills are currently available."
    lines = []
    for item in summaries:
        lines.append(f"- {item['name']}: {item['description']}")
    return "\n".join(lines)
