"""Per-session ledger of failed tool attempts.

Two things in the loop needed a memory of failure that the message history does
not provide:

* Compaction folds the middle of the conversation into a summary. Whatever the
  summary omits is gone, and "the four things I already tried that don't work" is
  exactly what a readable summary tends to drop. A compacted agent then retries a
  command that failed four times.
* ``agent.core.doom_loop`` only catches *literal* repetition — same tool, same
  arguments, same result. It cannot see ``pip install flash-attn`` →
  ``pip install flash_attn`` → build from source: three different calls, one
  strategy, all doomed.

So the ledger lives on the Session rather than in ``context_manager.items``: it is
untouched by compaction, costs nothing per turn, and is read in the two places
that need it — the compaction summary and the end-of-turn completion gate.

A failure is considered resolved once the *same tool* later succeeds. Matching on
arguments instead would never resolve anything, because fixing the arguments is
the normal repair path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Enough to see the pattern, small enough to paste into a prompt.
MAX_RECORDS = 40
_MAX_ERROR_CHARS = 400
_MAX_ARGS_CHARS = 200


@dataclass
class AttemptRecord:
    """One failed tool call."""

    tool: str
    args: str
    error: str
    iteration: int
    resolved: bool = False

    def describe(self) -> str:
        args = f" {self.args}" if self.args else ""
        return f"- {self.tool}{args} → {self.error}"


@dataclass
class AttemptLog:
    records: list[AttemptRecord] = field(default_factory=list)

    def unresolved(self) -> list[AttemptRecord]:
        return [r for r in self.records if not r.resolved]


def _digest_args(args: Any) -> str:
    """Short, readable rendering of tool arguments."""
    if args is None:
        return ""
    if isinstance(args, str):
        text = args
    else:
        try:
            text = json.dumps(args, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(args)
    text = " ".join(text.split())
    if len(text) > _MAX_ARGS_CHARS:
        text = text[:_MAX_ARGS_CHARS] + "…"
    return text


def _digest_error(output: Any) -> str:
    text = " ".join(str(output or "").split())
    if len(text) > _MAX_ERROR_CHARS:
        text = text[:_MAX_ERROR_CHARS] + "…"
    return text or "(no output)"


def _log_for(session: Any) -> AttemptLog | None:
    if session is None:
        return None
    log = getattr(session, "attempt_log", None)
    if log is None:
        log = AttemptLog()
        try:
            session.attempt_log = log
        except AttributeError:
            return None
    return log


def record_failure(
    session: Any, tool: str, args: Any, output: Any, iteration: int = 0
) -> None:
    log = _log_for(session)
    if log is None or not tool:
        return
    log.records.append(
        AttemptRecord(
            tool=tool,
            args=_digest_args(args),
            error=_digest_error(output),
            iteration=iteration,
        )
    )
    if len(log.records) > MAX_RECORDS:
        # Drop resolved records first — they carry the least information.
        keep = [r for r in log.records if not r.resolved]
        dropped_resolved = log.records[: len(log.records) - len(keep)]
        log.records = (dropped_resolved + keep)[-MAX_RECORDS:]


def record_success(session: Any, tool: str) -> None:
    """Mark earlier failures of ``tool`` resolved — the agent recovered."""
    log = _log_for(session)
    if log is None or not tool:
        return
    for record in log.records:
        if record.tool == tool:
            record.resolved = True


def unresolved_failures(session: Any) -> list[AttemptRecord]:
    log = _log_for(session)
    return log.unresolved() if log is not None else []


def clear(session: Any) -> None:
    """Reset the ledger — used when a fresh conversation starts."""
    log = _log_for(session)
    if log is not None:
        log.records.clear()


def format_block(session: Any, *, header: str | None = None) -> str:
    """Render unresolved failures for injection into a prompt. '' when clean."""
    records = unresolved_failures(session)
    if not records:
        return ""
    lines = [header or "Approaches already tried in this session that FAILED:"]
    lines.extend(r.describe() for r in records)
    lines.append(
        "Do not repeat these as-is. Either change the approach materially or "
        "explain why the failure is acceptable."
    )
    return "\n".join(lines)
