"""Optional local Codex context telemetry and pre-compaction save adapter.

No hook is installed or trusted by this script. Bind each session explicitly;
neither cwd nor a chat title selects a project. Rollout JSONL is an unstable,
best-effort telemetry source, never an exact live context meter. Only files
explicitly listed in a binding can be rescued; unsaved model text cannot.

Examples (all paths must be absolute):
  context_guard.py --bindings FILE bind --session-id ID --transcript FILE \
      --project DIRECTORY --scope research --file DRAFT --task TEXT
  context_guard.py --bindings FILE snapshot --session-id ID
  context_guard.py --bindings FILE --hook    # native hook JSON on stdin

Native hooks require the host's actual review/trust flow. Current-chat hot
reload has not been verified. The adapter never blocks host compaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from datetime import datetime, timezone
from typing import Any
from contextlib import contextmanager

sys.dont_write_bytecode = True
from hub_runtime import HubError, HubRuntime, load_config


SCHEMA_VERSION = 1
MAX_BINDINGS_BYTES = 2 * 1024 * 1024
MAX_HOOK_BYTES = 1024 * 1024
UNSAVED_LIMITATION = "Only declared existing files are saved; text not written to a file cannot be recovered."
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CATEGORIES = {"original", "research", "creative", "pending", "next"}


class GuardError(ValueError):
    """A safe-to-display operational error, never a transcript excerpt."""


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise GuardError("Missing event timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GuardError("Invalid event timestamp") from exc
    if result.tzinfo is None:
        raise GuardError("Event timestamp must include timezone")
    return result.astimezone(timezone.utc)


def _json(raw: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise GuardError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise GuardError("Non-finite JSON number")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=constant)


def _session(value: str) -> str:
    if not isinstance(value, str) or not SESSION_PATTERN.fullmatch(value):
        raise GuardError("Invalid session id")
    return value


def _absolute(value: str | Path, *, must_exist: bool = True) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise GuardError("An explicit absolute path without traversal is required")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (part.is_symlink() or bool(getattr(info, "st_file_attributes", 0)
                                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))):
            raise GuardError("Symlink, junction or reparse path is not allowed")
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError as exc:
        raise GuardError("Required path is unavailable") from exc
    return resolved


def _same_path(first: str | Path, second: str | Path) -> bool:
    return os.path.normcase(str(_absolute(first))) == os.path.normcase(str(_absolute(second)))


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise GuardError("Unknown single-request usage format")
    result = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise GuardError("Invalid single-request token count")
        result[key] = number
    if result["input_tokens"] + result["output_tokens"] != result["total_tokens"]:
        raise GuardError("Inconsistent single-request token counts")
    for key in ("cached_input_tokens", "reasoning_output_tokens"):
        number = value.get(key)
        if number is not None:
            if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                raise GuardError("Invalid token detail count")
            result[key] = number
    return result


def _records(path: Path):
    """Yield metadata only to the caller; never include source lines in errors."""
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.endswith("\n"):
                # The writer can be in the middle of appending a record.
                try:
                    value = _json(line)
                except (ValueError, TypeError):
                    yield line_number, None
                    continue
            else:
                try:
                    value = _json(line)
                except (ValueError, TypeError) as exc:
                    raise GuardError("Malformed complete transcript record") from exc
            if not isinstance(value, dict):
                raise GuardError("Unknown transcript record format")
            yield line_number, value


def _verify_identity(path: Path, session_id: str) -> None:
    # The first record is intentionally inspected without loading any messages.
    first = next(_records(path), (None, None))[1]
    if (not first or first.get("type") != "session_meta"
            or not isinstance(first.get("payload"), dict)
            or first["payload"].get("id") != session_id):
        raise GuardError("Transcript session identity does not match binding")


def snapshot(session_id: str, transcript: str | Path, *, max_age_seconds: float = 120,
             warning_ratio: float = 0.80, critical_ratio: float = 0.90,
             now: datetime | None = None) -> dict:
    """Read only the explicitly specified session; return no chat content."""
    _session(session_id)
    if (not math.isfinite(max_age_seconds) or max_age_seconds <= 0
            or not 0 < warning_ratio < critical_ratio <= 1):
        raise GuardError("Invalid freshness or signal thresholds")
    clock = now or _utc()
    if clock.tzinfo is None:
        raise GuardError("Observation time must include timezone")
    result = {"schema_version": SCHEMA_VERSION, "session_id": session_id,
              "observed_at": clock.isoformat(), "status": "unknown", "signal": "unknown",
              "measurement_kind": "last_request_snapshot_not_live_context",
              "reason": None, "warnings": ["Transcript format is not a stable host API.",
                 "Cumulative usage, cached tokens and file mtime are not current context occupancy."],
              "unsaved_text_limit": UNSAVED_LIMITATION}
    try:
        path = _absolute(transcript)
        if not path.is_file():
            raise GuardError("Transcript is not a regular file")
        _verify_identity(path, session_id)
        result["identity_verified"] = True
        result["transcript_path"] = str(path)
        identity = False
        last = None
        latest_usage_record = None
        compaction_line = 0
        compaction_at = None
        incomplete_tail = False
        for line_number, record in _records(path):
            if record is None:
                incomplete_tail = True
                continue
            kind = record.get("type")
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                raise GuardError("Unknown transcript payload format")
            if kind == "session_meta":
                if payload.get("id") != session_id:
                    result["identity_verified"] = False
                    raise GuardError("Transcript session identity does not match binding")
                identity = True
            elif kind == "compacted":
                compaction_at = _time(record.get("timestamp")).isoformat()
                compaction_line = line_number
            elif kind == "token_usage_record":
                if (payload.get("thread_id") != session_id
                        or payload.get("session_id") != session_id):
                    result["identity_verified"] = False
                    raise GuardError("Usage record identity does not match binding")
                latest_usage_record = {"line": line_number, "usage": payload.get("usage")}
            elif kind == "event_msg" and payload.get("type") == "token_count":
                # Older post-compaction estimates can have total_tokens but
                # zero input/output. Validate only the latest candidate, never
                # mislabel those estimates as a single-request measurement.
                last = {"line": line_number, "info": payload.get("info"),
                        "timestamp": record.get("timestamp")}
        if not identity:
            raise GuardError("No matching session_meta identity record")
        result["identity_verified"] = True
        result["last_compaction_at"] = compaction_at
        result["last_compaction_line"] = compaction_line or None
        result["incomplete_tail"] = incomplete_tail
        if not last:
            raise GuardError("No usable last-request token_count snapshot")
        if last["line"] <= compaction_line:
            raise GuardError("Compacted after last usage; waiting for a post-compaction snapshot")
        info = last.pop("info")
        if not isinstance(info, dict):
            raise GuardError("Unknown token_count info format")
        window = info.get("model_context_window")
        if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
            raise GuardError("Unknown or invalid model context window")
        last.update(usage=_usage(info.get("last_token_usage")), window=window,
                    timestamp=_time(last["timestamp"]))
        # A newer request may have usage but no matching window snapshot yet.
        if latest_usage_record and latest_usage_record["line"] > last["line"]:
            raise GuardError("Latest request has no corresponding context-window snapshot yet")
        if (latest_usage_record and latest_usage_record["line"] > compaction_line
                and _usage(latest_usage_record["usage"]) != last["usage"]):
            raise GuardError("Last usage records disagree")
        age = (clock.astimezone(timezone.utc) - last["timestamp"]).total_seconds()
        if age < -5:
            raise GuardError("Usage timestamp is in the future")
        ratio = last["usage"]["total_tokens"] / last["window"]
        result.update({"snapshot_at": last["timestamp"].isoformat(), "snapshot_line": last["line"],
                       "age_seconds": round(max(0, age), 3), "single_request_usage": last["usage"],
                       "model_context_window": last["window"],
                       "last_request_total_to_window_ratio": ratio,
                       "thresholds": {"warning": warning_ratio, "critical": critical_ratio},
                       "usage_identity_bound": bool(latest_usage_record)})
        if age > max_age_seconds or incomplete_tail:
            result.update(status="stale", reason="snapshot_expired" if age > max_age_seconds else "transcript_append_in_progress")
        else:
            result.update(status="fresh", reason="last_request_snapshot_available",
                          signal="critical" if ratio >= critical_ratio else "warning" if ratio >= warning_ratio else "normal")
    except (GuardError, OSError, UnicodeError) as exc:
        result["reason"] = str(exc) if isinstance(exc, GuardError) else "Transcript cannot be read"
        result["status"], result["signal"] = "unknown", "unknown"
    return result


def _registry_path(runtime: HubRuntime, path: str | Path) -> Path:
    return runtime._write_path(_absolute(path, must_exist=False))


@contextmanager
def _exclusive_file(runtime: HubRuntime, path: Path):
    path = runtime._write_path(path)
    runtime._ensure_dir(path.parent)
    warnings = []
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise GuardError("Context guard is busy or has an interrupted lock; inspect before retrying") from exc
    try:
        with stream:
            stream.write(json.dumps({"pid": os.getpid(), "created_at": _utc().isoformat()}))
        yield warnings
    finally:
        try:
            path.unlink()
        except OSError:
            warnings.append("Guard lock cleanup failed; inspect the interrupted lock before retrying.")


def _read_bindings(runtime: HubRuntime, path: str | Path, *, missing_ok: bool = False) -> dict:
    resolved = _registry_path(runtime, path)
    if missing_ok and not resolved.exists():
        return {"schema_version": SCHEMA_VERSION, "bindings": {}}
    if not resolved.is_file() or resolved.stat().st_size > MAX_BINDINGS_BYTES:
        raise GuardError("Bindings registry is unavailable or too large")
    try:
        value = _json(resolved.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise GuardError("Bindings registry has invalid JSON") from exc
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION
            or not isinstance(value.get("bindings"), dict)):
        raise GuardError("Unknown bindings registry format")
    return value


def bind(runtime: HubRuntime, registry: str | Path, *, session_id: str,
         transcript: str | Path, project: str | Path, scope: str,
         files: list[str] | None = None, task: str | None = None,
         materials: list[str] | None = None) -> dict:
    """Explicit user/agent action; never called implicitly by a hook."""
    _session(session_id)
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 2000:
        raise GuardError("Explicit save scope is required")
    transcript_path = _absolute(transcript)
    _verify_identity(transcript_path, session_id)
    project_path = runtime._project(_absolute(project))
    runtime._chain(project_path)  # Verify this really is a runtime project.
    declarations = [("pending", value, "Explicitly declared working file awaiting classification")
                    for value in files or []]
    for material in materials or []:
        category, separator, file = material.partition("=")
        if not separator or category not in CATEGORIES or not file:
            raise GuardError("--material must be CATEGORY=ABSOLUTE_PATH with an explicit valid category")
        declarations.append((category, file, "Explicitly classified file: " + category))
    extra_files = []
    declared_paths = set()
    for category, value, title in declarations:
        file_path = runtime._write_path(_absolute(value))
        if not file_path.is_file():
            raise GuardError("Declared draft is not a regular existing file")
        if str(file_path) in declared_paths:
            raise GuardError("Declare each file only once with one classification")
        declared_paths.add(str(file_path))
        extra_files.append({"category": category, "file": str(file_path), "title": title})
    value = {"session_id": session_id, "transcript_path": str(transcript_path),
             "workspace_root": str(runtime.workspace_root), "project_path": str(project_path),
             "scope": scope.strip(), "extra_files": extra_files,
             "task": task, "bound_at": _utc().isoformat(),
             "unsaved_text_limit": UNSAVED_LIMITATION}
    registry_path = _registry_path(runtime, registry)
    with _exclusive_file(runtime, registry_path.with_suffix(registry_path.suffix + ".lock")) as warnings:
        data = _read_bindings(runtime, registry_path, missing_ok=True)
        data["bindings"][session_id] = value
        runtime._write_json(registry_path, data, atomic=True)
    return {"status": "bound", "bindings_path": str(registry_path), "binding": value,
            "hook_registered": False, "hook_trusted": False,
            "current_chat_hot_reload": "not_verified", "warnings": warnings}


def _binding(runtime: HubRuntime, registry: str | Path, session_id: str) -> dict | None:
    value = _read_bindings(runtime, registry, missing_ok=True)["bindings"].get(_session(session_id))
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("session_id") != session_id:
        raise GuardError("Invalid session binding")
    if not _same_path(value.get("workspace_root", ""), runtime.workspace_root):
        raise GuardError("Binding workspace differs from configured runtime workspace")
    project = runtime._project(_absolute(value.get("project_path", "")))
    if not isinstance(value.get("scope"), str) or not value["scope"].strip():
        raise GuardError("Binding has no explicit save scope")
    if not isinstance(value.get("extra_files"), list):
        raise GuardError("Binding has no declared file list")
    value["project_path"] = str(project)
    value["transcript_path"] = str(_absolute(value.get("transcript_path", "")))
    for material in value["extra_files"]:
        if (not isinstance(material, dict) or material.get("category") not in CATEGORIES
                or not isinstance(material.get("title"), str) or not material["title"].strip()):
            raise GuardError("Binding contains an invalid classified file")
        runtime._write_path(_absolute(material.get("file", ""), must_exist=False))
    return value


def bound_snapshot(runtime: HubRuntime, registry: str | Path, session_id: str, **options: Any) -> dict:
    value = _binding(runtime, registry, session_id)
    if value is None:
        return {"status": "unknown", "signal": "unknown", "session_id": session_id,
                "reason": "session_not_explicitly_bound"}
    result = snapshot(session_id, value["transcript_path"], **options)
    result.update(project_path=value["project_path"], scope=value["scope"])
    return result


def _fingerprint_files(runtime: HubRuntime, materials: list[dict]) -> tuple[list[dict], dict, list[str]]:
    existing, fingerprints, missing = [], {}, []
    for material in materials:
        path = runtime._write_path(_absolute(material["file"], must_exist=False))
        if not path.is_file():
            missing.append(str(path))
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        existing.append(material)
        fingerprints[str(path)] = digest.hexdigest()
    return existing, fingerprints, missing


def _save(runtime: HubRuntime, value: dict, event: dict, current: dict) -> dict:
    project = runtime._project(value["project_path"])
    session_key = hashlib.sha256(value["session_id"].encode("utf-8")).hexdigest()[:20]
    lock_path = project / "work" / "context-guard" / session_key / "save.lock"
    with _exclusive_file(runtime, lock_path) as warnings:
        result = _save_locked(runtime, value, event, current)
    if warnings:
        result.setdefault("warnings", []).extend(warnings)
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _binding_signature(value: dict) -> str:
    # Binding time is administrative; category/title/task changes are semantic.
    return _digest({key: value.get(key) for key in ("session_id", "transcript_path",
        "workspace_root", "project_path", "scope", "task", "extra_files")})


def _adapter_metadata(entry: dict) -> dict:
    operation = entry.get("operation", {})
    payload = operation.get("request", {}).get("payload", {})
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    if (operation.get("kind") == "pause" and payload.get("node") == "context_save"
            and isinstance(metadata, dict) and metadata.get("adapter") == "mkt_context_guard_v2"):
        return metadata
    return {}


def _project_observation(chain: list[dict]) -> dict:
    # Adapter-only snapshots must not make an exact event appear new after its
    # disposable receipt disappears. Real project operations remain anchors.
    anchor = next((entry["revision"] for entry in chain if not _adapter_metadata(entry)), chain[-1]["revision"])
    state = chain[0]["state"]
    checkpoint = state.get("pause_checkpoint") or {}
    return {"head": state["revision"], "state_anchor": anchor,
            "discussion_round": state.get("discussion_round"),
            "pending_checkpoint_id": state.get("pending_checkpoint_id"),
            "classification_sha256": _digest(checkpoint.get("materials", [])),
            "checkpoint_refs_sha256": _digest(checkpoint.get("refs", []))}


def _captured_hashes(runtime: HubRuntime, rows: list[dict], expected: dict) -> dict:
    captured = {}
    for row in rows:
        if (isinstance(row, dict) and isinstance(row.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            path = str(runtime._write_path(_absolute(row.get("original_path", ""), must_exist=False)))
            if path in expected:
                captured[path] = row["sha256"]
    return captured


def _recover_committed_event(runtime: HubRuntime, project: Path, head: dict, chain: list[dict],
                             event_key: str, binding_signature: str, fingerprints: dict) -> dict | None:
    for entry in chain:
        metadata = _adapter_metadata(entry)
        if (metadata.get("guard_event_key") != event_key
                or metadata.get("guard_binding_signature") != binding_signature):
            continue
        checkpoint = entry["state"].get("pause_checkpoint") or {}
        if (_captured_hashes(runtime, checkpoint.get("captured_files", []), fingerprints) != fingerprints
                or checkpoint.get("saved_revision") != entry["revision"]):
            continue
        # Rebuild only derived recovery entries from validated immutable history.
        # Replaying mutable source files would not prove the original request.
        return runtime._complete_pause(project, entry["operation"]["operation_id"], {
            "status": "already_applied", "project_id": project.name,
            "current_revision": head["revision"], "applied_revision": entry["revision"],
            "operation_id": entry["operation"]["operation_id"], "artifact_paths": [],
            "warnings": [], "next_actions": [], "error": None})
    return None


def _reconcile_pending(runtime: HubRuntime, state_path: Path, pending: dict,
                       observation: dict, signature: str, fingerprints: dict) -> dict:
    comparison = {"previous_base": pending.get("base"), "current_head": observation["head"],
        "current_project_state_verified": True,
        "declaration_comparison": {"previous_binding_signature": pending.get("binding_signature"),
            "current_binding_signature": signature, "previous_files": pending.get("file_fingerprints"),
            "current_files": fingerprints},
        "previous_project_observation": pending.get("project_observation"),
        "current_project_observation": observation,
        "previous_error": pending.get("last_error"),
        "policy": "Rebuild context_save from current verified project state and explicit binding; do not replay approvals or rewrite manuscripts."}
    archive = runtime._write_path(state_path.parent / "conflicts" /
        ("pending-" + _digest(pending)[:24] + ".json"))
    runtime._write_json(archive, {"pending_request": pending, "comparison": comparison}, atomic=True)
    comparison["preserved_pending_path"] = str(archive)
    return comparison


def _save_locked(runtime: HubRuntime, value: dict, event: dict, current: dict,
                 conflict_attempt: int = 0) -> dict:
    saver = getattr(runtime, "pause", None)
    if not callable(saver):
        return {"status": "error", "committed": False, "recovery_ready": False,
                "reason": "Runtime pause API is unavailable; no save was performed",
                "unsaved_text_limit": UNSAVED_LIMITATION}
    project = runtime._project(value["project_path"])
    head, chain = runtime._chain(project)
    observation = _project_observation(chain)
    signature = _binding_signature(value)
    existing, fingerprints, missing = _fingerprint_files(runtime, value["extra_files"])
    event_key = _digest({"event": event["hook_event_name"],
        "turn": event.get("turn_id"), "trigger": event.get("trigger"),
        "snapshot_line": current.get("snapshot_line"), "compaction_line": current.get("last_compaction_line"),
        "files": fingerprints, "missing_files": missing, "binding_signature": signature,
        "state_anchor": observation["state_anchor"]})
    session_key = hashlib.sha256(value["session_id"].encode("utf-8")).hexdigest()[:20]
    state_path = runtime._write_path(project / "work" / "context-guard" / session_key / "last-save.json")
    previous = None
    if state_path.is_file() and state_path.stat().st_size <= MAX_BINDINGS_BYTES:
        try:
            previous = _json(state_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            previous = None
    if (not missing and isinstance(previous, dict)
            and previous.get("covered_head_revision", previous.get("saved_revision")) == head["revision"]
            and previous.get("file_fingerprints") == fingerprints
            and previous.get("binding_signature") == signature and previous.get("recovery_ready") is True
            and (event["hook_event_name"] == "PostModelRequest" or previous.get("event_key") == event_key)):
        return {"status": "unchanged", "committed": False, "recovery_ready": True,
                "reason": "No new committed revision or declared file bytes since the last verified save",
                "previous_save": previous, "unsaved_text_limit": UNSAVED_LIMITATION}
    pending_path = state_path.with_name("pending-save.json")
    recovered = _recover_committed_event(runtime, project, head, chain, event_key, signature, fingerprints)
    if recovered is not None:
        return _record_save(runtime, state_path, pending_path, value, event_key, fingerprints, missing, recovered)
    reconciliation = None
    if pending_path.is_file() and pending_path.stat().st_size <= MAX_BINDINGS_BYTES:
        try:
            pending = _json(pending_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise GuardError("An interrupted guard request is unreadable; inspect before retrying")
        if not isinstance(pending, dict):
            raise GuardError("Unknown interrupted guard request format")
        if (pending.get("base") == head["revision"] and pending.get("event_key") == event_key
                and pending.get("binding_signature") == signature
                and pending.get("file_fingerprints") == fingerprints
                and pending.get("project_observation") == observation):
            try:
                saved = saver(str(project), pending["base"], pending["operation_id"], pending["payload"])
            except HubError as exc:
                pending["last_error"] = {"code": exc.exit_code, "response": exc.response}
                runtime._write_json(pending_path, pending, atomic=True)
                if exc.exit_code == 3 and conflict_attempt < 2:
                    return _save_locked(runtime, value, event, current, conflict_attempt + 1)
                raise
            return _record_save(runtime, state_path, pending_path, value, event_key, fingerprints, missing, saved)
        reconciliation = _reconcile_pending(runtime, state_path, pending, observation, signature, fingerprints)
    # Deterministic per observed event: loss of a derived receipt must never
    # cause a second publication of the very same hook event.
    operation_id = "context-guard-" + hashlib.sha256(
        (event_key + ":" + head["revision"]).encode("utf-8")).hexdigest()[:24]
    note_path = runtime._write_path(state_path.parent / (operation_id + ".md"))
    note = ("# Context save observation\n\n"
            "This is a storage observation, not a new human approval or author draft.\n\n"
            f"Session: {value['session_id']}\n\nEvent: {event['hook_event_name']}\n\n"
            f"Authorized scope: {value['scope']}\n\n"
            f"Telemetry status: {current['status']}; signal: {current['signal']}\n\n"
            f"Declared files currently available: {len(existing)}; unavailable: {len(missing)}\n\n"
            + UNSAVED_LIMITATION + "\n")
    runtime._write_bytes(note_path, note.encode("utf-8"), atomic=True)
    payload = {"file": str(note_path), "node": "context_save", "reuse_materials": True,
               "authorized_scope": value["scope"], "refs": [], "extra_files": existing,
               "metadata": {"session_id": value["session_id"], "reason": "native " + event["hook_event_name"],
                   "adapter": "mkt_context_guard_v2", "guard_event_key": event_key,
                   "guard_binding_signature": signature, "guard_project_observation": observation,
                   "turn_id": event.get("turn_id"), "trigger": event.get("trigger"),
                   "binding_task": value.get("task"), "missing_declared_files": missing,
                   "unsaved_text_limit": UNSAVED_LIMITATION}, "telemetry": current}
    if reconciliation is not None:
        payload["metadata"]["guard_reconciliation"] = reconciliation
    journal = {"base": head["revision"], "operation_id": operation_id,
        "payload": payload, "event_key": event_key, "scope": value["scope"],
        "binding_signature": signature, "project_observation": observation,
        "file_fingerprints": fingerprints}
    runtime._write_json(pending_path, journal, atomic=True)
    try:
        saved = saver(str(project), head["revision"], operation_id, payload)
    except HubError as exc:
        journal["last_error"] = {"code": exc.exit_code, "response": exc.response}
        runtime._write_json(pending_path, journal, atomic=True)
        if exc.exit_code == 3 and conflict_attempt < 2:
            return _save_locked(runtime, value, event, current, conflict_attempt + 1)
        raise
    return _record_save(runtime, state_path, pending_path, value, event_key, fingerprints, missing, saved)


def _record_save(runtime: HubRuntime, state_path: Path, pending_path: Path, value: dict,
                 event_key: str, fingerprints: dict, missing: list[str], saved: dict) -> dict:
    committed = saved.get("committed") is True
    recovery_ready = saved.get("recovery_ready") is True
    receipt_ready = False
    captured = _captured_hashes(runtime, saved.get("captured_files", []), fingerprints)
    baseline_verified = set(captured) == set(fingerprints)
    capture_changes = [path for path in fingerprints if captured.get(path) != fingerprints[path]]
    if committed:
        try:
            runtime._write_json(state_path, {"session_id": value["session_id"], "scope": value["scope"],
                "saved_revision": saved.get("saved_revision"),
                "covered_head_revision": saved.get("current_revision"),
                "binding_signature": _binding_signature(value),
                "file_fingerprints": captured if baseline_verified else None,
                "saved_checkpoint_path": saved.get("saved_checkpoint_path"),
                "recovery_context_path": saved.get("recovery_context_path"), "recovery_ready": recovery_ready,
                "event_key": event_key, "observed_at": _utc().isoformat(), "missing_declared_files": missing}, atomic=True)
            receipt_ready = True
            if recovery_ready:
                pending_path.unlink(missing_ok=True)
        except (HubError, OSError):
            # The immutable save remains committed. Keep the request journal
            # so the next hook retries the same operation, never a new one.
            receipt_ready = False
    result = {"status": "saved" if committed and recovery_ready and receipt_ready and not missing else "partial" if committed else "error",
              "committed": committed, "recovery_ready": recovery_ready, "save_result": saved,
              "guard_receipt_ready": receipt_ready, "missing_declared_files": missing,
              "unsaved_text_limit": UNSAVED_LIMITATION}
    if not baseline_verified:
        result.setdefault("warnings", []).append("Captured file hash receipts are unavailable; repeated-save suppression is disabled.")
    elif capture_changes:
        result.setdefault("warnings", []).append("Source files changed during capture; suppression uses the runtime's actual captured byte hashes.")
    if missing:
        result["reason"] = "Existing available files were captured, but some declared files were unavailable"
    elif committed and not recovery_ready:
        result["reason"] = "Revision committed but recovery bundle is incomplete; repair before claiming recoverability"
    elif committed and not receipt_ready:
        result["reason"] = "Revision committed but guard receipt is incomplete; the saved operation journal must be retried"
    elif not committed:
        result["reason"] = "Runtime did not confirm a committed context save"
    return result


def handle_hook(runtime: HubRuntime, registry: str | Path, event: dict,
                **snapshot_options: Any) -> dict:
    """Dispatch only mapped sessions. Never return a host blocking decision."""
    if not isinstance(event, dict):
        raise GuardError("Hook input must be a JSON object")
    event_name = event.get("hook_event_name")
    if event_name not in {"PreCompact", "PostModelRequest"}:
        return {"status": "ignored", "reason": "unsupported_event"}
    session_id = _session(event.get("session_id"))
    value = _binding(runtime, registry, session_id)
    if value is None:
        return {"status": "ignored", "reason": "session_not_explicitly_bound"}
    if event.get("agent_id") or event.get("agent_type"):
        return {"status": "ignored", "reason": "subagent_usage_not_root_session_usage"}
    if not event.get("transcript_path") or not _same_path(event["transcript_path"], value["transcript_path"]):
        raise GuardError("Hook transcript does not match the explicit binding")
    current = snapshot(session_id, value["transcript_path"], **snapshot_options)
    if not current.get("identity_verified"):
        raise GuardError("Cannot save from a hook with unverified transcript identity")
    if event_name == "PostModelRequest":
        if event.get("status") != "completed":
            return {"status": "ignored", "reason": "model_request_not_completed"}
        if current["status"] != "fresh" or current["signal"] not in {"warning", "critical"}:
            return {"status": "observed", "snapshot": current, "saved": False}
    if event_name == "PreCompact" and event.get("trigger") not in {"manual", "auto"}:
        raise GuardError("Unknown native compaction trigger")
    # The runtime owns file capture, node classification, version checks and
    # resume generation. Do not manufacture approval or mutate a HEAD here.
    return _save(runtime, value, event, current)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config")
    parser.add_argument("--bindings", required=True, help="Explicit registry path inside configured workspace")
    parser.add_argument("--hook", action="store_true", help="Receive a native hook JSON object on stdin")
    commands = parser.add_subparsers(dest="command")
    binding = commands.add_parser("bind")
    binding.add_argument("--session-id", required=True)
    binding.add_argument("--transcript", required=True)
    binding.add_argument("--project", required=True)
    binding.add_argument("--scope", required=True)
    binding.add_argument("--file", dest="files", action="append", default=[])
    binding.add_argument("--material", dest="materials", action="append", default=[],
                         help="Explicit classification: original|research|creative|pending|next=ABSOLUTE_PATH")
    binding.add_argument("--task")
    reading = commands.add_parser("snapshot")
    reading.add_argument("--session-id", required=True)
    reading.add_argument("--max-age-seconds", type=float, default=120)
    reading.add_argument("--warning-ratio", type=float, default=0.80)
    reading.add_argument("--critical-ratio", type=float, default=0.90)
    args = parser.parse_args(argv)
    try:
        runtime = HubRuntime(load_config(args.config)["workspace_root"])
        if args.hook:
            if args.command:
                raise GuardError("--hook cannot be combined with a subcommand")
            raw = sys.stdin.read(MAX_HOOK_BYTES + 1)
            if len(raw.encode("utf-8")) > MAX_HOOK_BYTES:
                raise GuardError("Hook input exceeds limit")
            result = handle_hook(runtime, args.bindings, _json(raw))
            if result.get("status") in {"error", "partial"}:
                print(json.dumps({"systemMessage": "MKT context guard: "
                    + result.get("reason", "Check the project save result.") + " " + UNSAVED_LIMITATION}), flush=True)
            elif result.get("warnings"):
                print(json.dumps({"systemMessage": "MKT context guard: " + " ".join(result["warnings"])}), flush=True)
            # Empty stdout/exit 0 lets native compaction continue. No trust,
            # hook registration, chat creation or model settings are changed.
            return 0
        if args.command == "bind":
            result = bind(runtime, args.bindings, session_id=args.session_id,
                          transcript=args.transcript, project=args.project, scope=args.scope,
                          files=args.files, materials=args.materials, task=args.task)
        elif args.command == "snapshot":
            result = bound_snapshot(runtime, args.bindings, args.session_id,
                                    max_age_seconds=args.max_age_seconds,
                                    warning_ratio=args.warning_ratio, critical_ratio=args.critical_ratio)
        else:
            raise GuardError("Choose bind, snapshot, or --hook")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (GuardError, HubError, OSError, ValueError, TypeError, KeyError) as exc:
        if args.hook:
            # A failed save must be visible without preventing host compaction.
            print(json.dumps({"systemMessage": "MKT context guard did not save: "
                + (str(exc) if isinstance(exc, (GuardError, HubError)) else "operational failure")
                + ". " + UNSAVED_LIMITATION}, ensure_ascii=False))
            return 0
        print(json.dumps({"status": "error", "saved": False,
                          "reason": str(exc) if isinstance(exc, (GuardError, HubError)) else "operational failure"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
