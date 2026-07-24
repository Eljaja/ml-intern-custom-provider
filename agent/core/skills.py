"""Filesystem-backed procedural skills for local web sessions."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from agent.core.redact import scrub_string

logger = logging.getLogger(__name__)

# A skill is a procedure, not a knowledge base. Bodies are loaded whole by
# skill_view, and every enabled skill's description rides in the system prompt on
# every request, so both need a ceiling — the writer is an LLM with no notion of
# how much context it is spending.
MAX_SKILL_CONTENT_CHARS = 20_000
MAX_INDEXED_SKILLS = 40

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


def _reject_oversized(name: str, content: str) -> None:
    if len(content) > MAX_SKILL_CONTENT_CHARS:
        raise SkillError(
            f"Skill '{name}' body is {len(content)} characters; the limit is "
            f"{MAX_SKILL_CONTENT_CHARS}. Keep skills procedural — link to or "
            "re-derive bulk reference material instead of pasting it."
        )


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


_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[tuple[str, str], threading.Lock] = {}


@contextmanager
def _skill_lock(user_id: str | None, name: str) -> Iterator[None]:
    """Serialise read-modify-write on one skill file.

    ``_atomic_write`` keeps a reader from seeing a torn file, but it does not stop
    two concurrent updates from both reading the old state and the second write
    discarding the first — e.g. a ``skill_view`` bumping use_count while the API
    toggles ``enabled``.

    Process-local only. Sufficient for the single-uvicorn deployment in
    docker-compose.yaml; a multi-process setup would need an OS file lock, which
    is not portable to Windows via fcntl.
    """
    key = (safe_user_id(user_id), name)
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        yield


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
        except Exception as e:
            # A malformed skill used to vanish from the UI with no trace, which
            # is indistinguishable from "the agent never saved it".
            logger.warning("Skipping unreadable skill %s: %s", skill_file, e)
            continue
        if enabled_only and not skill.enabled:
            continue
        skills.append(skill)
    return skills


def delete_skill(user_id: str | None, name: str) -> bool:
    """Remove a skill and its directory. Returns False if it wasn't there.

    Skills are written automatically by the post-turn reflection, so without a
    delete there is no way to undo a bad one — only to disable it, leaving it on
    disk forever.
    """
    skill_name = validate_skill_name(name)
    with _skill_lock(user_id, skill_name):
        path = _skill_path(user_id, skill_name)
        if not path.exists():
            return False
        path.unlink()
        skill_dir = path.parent
        try:
            next(skill_dir.iterdir())
        except StopIteration:
            skill_dir.rmdir()
        except OSError:
            pass
        return True


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
    body = _redact_secrets(content or "")
    _reject_oversized(skill_name, body)
    summary = (description or "").strip() or "No description provided."

    with _skill_lock(user_id, skill_name):
        existing = get_skill(user_id, skill_name)
        now = utc_now_iso()

        if existing is None:
            skill = Skill(
                name=skill_name,
                description=summary,
                content=body,
                enabled=True if enabled is None else bool(enabled),
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
        else:
            skill = replace(
                existing,
                description=summary,
                content=body,
                enabled=existing.enabled if enabled is None else bool(enabled),
                updated_at=now,
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
    if not old_string:
        raise SkillError("old_string is required for patch.")

    with _skill_lock(user_id, skill_name):
        existing = get_skill(user_id, skill_name)
        if existing is None:
            raise SkillError(f"Skill '{skill_name}' does not exist.")
        if existing.content.count(old_string) != 1:
            raise SkillError("old_string must match exactly one location in the skill.")
        content = existing.content.replace(old_string, _redact_secrets(new_string), 1)
        _reject_oversized(skill_name, content)
        updated = replace(existing, content=content, updated_at=utc_now_iso())
        _atomic_write(_skill_path(user_id, skill_name), _skill_markdown(updated))
    return updated


def set_skill_enabled(user_id: str | None, name: str, enabled: bool) -> Skill:
    skill_name = validate_skill_name(name)
    with _skill_lock(user_id, skill_name):
        existing = get_skill(user_id, skill_name)
        if existing is None:
            raise SkillError(f"Skill '{skill_name}' does not exist.")
        updated = replace(existing, enabled=enabled, updated_at=utc_now_iso())
        _atomic_write(_skill_path(user_id, skill_name), _skill_markdown(updated))
    return updated


def record_skill_used(user_id: str | None, name: str) -> Skill | None:
    skill_name = validate_skill_name(name)
    with _skill_lock(user_id, skill_name):
        existing = get_skill(user_id, skill_name)
        if existing is None:
            return None
        updated = replace(
            existing,
            last_used_at=utc_now_iso(),
            use_count=existing.use_count + 1,
        )
        _atomic_write(_skill_path(user_id, existing.name), _skill_markdown(updated))
    return updated


def enabled_skill_summaries(user_id: str | None) -> list[dict[str, Any]]:
    return [skill.summary() for skill in list_skills(user_id, enabled_only=True)]


def format_skill_index(user_id: str | None) -> str:
    """Render the enabled-skill index that goes into the system prompt.

    Capped at :data:`MAX_INDEXED_SKILLS`, most recently used first. This text is
    part of every request for the whole session, and the reflection loop adds
    skills on its own, so an uncapped list is a prompt that silently grows
    without anyone deciding to grow it.
    """
    skills = list_skills(user_id, enabled_only=True)
    if not skills:
        return "No enabled skills are currently available."

    ordered = sorted(
        skills,
        key=lambda s: (s.last_used_at or "", s.use_count),
        reverse=True,
    )
    shown = ordered[:MAX_INDEXED_SKILLS]
    lines = [f"- {s.name}: {s.description}" for s in shown]
    hidden = len(ordered) - len(shown)
    if hidden:
        lines.append(
            f"- (+{hidden} more enabled skills not listed; call skills_list to "
            "see all of them)"
        )
    return "\n".join(lines)
