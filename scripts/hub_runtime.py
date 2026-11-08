"""MKT Max 1 immutable local project runtime. Python 3.10+, stdlib only.

The runtime validates structure, paths, bytes and declared dependencies. It does
not certify research reading, semantic quality, real approval or execution.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation
import uuid
from typing import Any


SCHEMA_VERSION = 1
FINGERPRINT_VERSION = 2
WORKFLOW_VERSION = 2
HUMAN_GATES = {"brief", "research", "direction", "writing", "chapter_review", "delivery"}
PAUSE_NODES = HUMAN_GATES | {"change", "context_save"}
MATERIAL_CATEGORIES = {"original", "research", "creative", "pending", "next"}
APPLICABILITY = {"now", "later", "not_needed", "unknown"}
CONTENT_STATUS = {"outline", "draft", "reviewable", "needs_review", "blocked", "archived"}
COLLECTIONS = {
    "source": "sources", "fact": "facts", "decision": "decisions",
    "question": "questions", "module": "modules", "artifact": "artifacts",
    "resource": "resources", "cost": "costs", "event": "events", "review": "reviews",
    "unit": "content_units", "session": "sessions",
}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_loads(raw: str | bytes) -> Any:
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON constant is forbidden: {value}")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key: {key}")
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_pairs)


def _response(status: str = "success", project_id: str | None = None,
              current_revision: str | None = None, operation_id: str | None = None,
              **extra: Any) -> dict:
    result = {"status": status, "project_id": project_id,
              "current_revision": current_revision, "operation_id": operation_id,
              "artifact_paths": [], "context_path": None, "warnings": [],
              "next_actions": [], "error": None}
    result.update(extra)
    return result


class HubError(Exception):
    def __init__(self, message: str, exit_code: int = 2, **details: Any):
        super().__init__(message)
        self.exit_code = exit_code
        self.response = _response("blocked" if exit_code == 7 else "error", error={"code": exit_code, "message": message}, **details)


def _require(obj: dict, fields: list[str]) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise HubError("Missing required fields: " + ", ".join(missing))


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HubError(f"{label} must be nonempty text")
    return value


def _nonempty(value: Any, label: str) -> Any:
    if not isinstance(value, (str, list)) or not value or (isinstance(value, str) and not value.strip()):
        raise HubError(f"{label} must be nonempty text or a nonempty list")
    return value


def _list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise HubError(f"{label} must be a list")
    return value


def _id(value: Any, label: str = "ID") -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value) or value.upper() in WINDOWS_RESERVED:
        raise HubError(f"Unsafe {label}: {value!r}", 4)
    return value


def _generated(prefix: str, ident: str) -> str:
    result = prefix + ident
    if len(result) > 80:
        result = result[:59] + "-" + _hash(result.encode("ascii"))[:20]
    return _id(result, "generated artifact ID")


def _ref(value: Any) -> str:
    if not isinstance(value, str) or value.count(":") != 1:
        raise HubError(f"Invalid typed reference: {value!r}")
    kind, ident = value.split(":", 1)
    if kind in ("contract", "handoff"):
        if ident != "current":
            raise HubError(f"Invalid singleton reference: {value}")
    elif kind not in COLLECTIONS:
        raise HubError(f"Unknown reference type: {kind}")
    else:
        _id(ident, "reference ID")
    return value


def _refs(values: Any, label: str) -> list[str]:
    return list(dict.fromkeys(_ref(v) for v in _list(values, label)))


def _roles(value: Any) -> list[str]:
    roles = _list(value, "allowed_roles")
    if not roles:
        raise HubError("allowed_roles must name at least one role; omit for unrestricted")
    for role in roles:
        _text(role, "allowed role")
        if len(role) > 64:
            raise HubError("Allowed role name too long")
    return list(dict.fromkeys(roles))


def _enum(value: Any, options: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise HubError(f"Invalid {label}; expected one of {sorted(options)}")
    return value


def _preview(value: Any, depth: int = 0) -> tuple[Any, bool]:
    """Bound arbitrary caller-supplied fields; full data stays in originals/index."""
    if isinstance(value, str):
        return (value[:600] + " [truncated; read full original]", True) if len(value) > 600 else (value, False)
    if depth >= 5 and isinstance(value, (dict, list)):
        return "[truncated nested structure; read full original]", True
    if isinstance(value, list):
        output, truncated = [], len(value) > 10
        for item in value[:10]:
            converted, shortened = _preview(item, depth + 1)
            output.append(converted)
            truncated |= shortened
        if len(value) > 10:
            output.append(f"[truncated {len(value) - 10} additional entries]")
        return output, truncated
    if isinstance(value, dict):
        output, truncated = {}, len(value) > 20
        for key, item in list(value.items())[:20]:
            converted, shortened = _preview(item, depth + 1)
            output[str(key)[:120]] = converted
            truncated |= shortened
        if len(value) > 20:
            output["truncated_additional_fields"] = len(value) - 20
        return output, truncated
    return value, False


class HubRuntime:
    def __init__(self, workspace_root: Path | str):
        raw = Path(workspace_root).expanduser()
        if not raw.is_absolute():
            raise HubError("workspace_root must be absolute", 4)
        self._reject_traversal(raw)
        self._reject_links(raw)
        self.workspace_root = raw.resolve()
        self.projects_root = self.workspace_root / "projects"
        self._ensure_dir(self.projects_root)

    @staticmethod
    def _reject_traversal(path: Path) -> None:
        # Treat backslashes as separators even on a portable POSIX host.
        if ".." in re.split(r"[\\/]", str(path)):
            raise HubError("Path traversal is forbidden", 4)

    @staticmethod
    def _reject_links(path: Path) -> None:
        for part in (path, *path.parents):
            if not part.exists() and not part.is_symlink():
                continue
            try:
                info = part.lstat()
                reparse = bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))
                junction = getattr(part, "is_junction", lambda: False)()
                if part.is_symlink() or junction or reparse:
                    raise HubError(f"Symbolic link/junction/reparse path is forbidden: {part}", 4)
            except OSError as exc:
                raise HubError(f"Cannot inspect path: {part}: {exc}", 4) from exc

    def _write_path(self, path: Path | str) -> Path:
        candidate = Path(path)
        self._reject_traversal(candidate)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        self._reject_links(candidate)
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise HubError(f"Write path outside workspace: {candidate}", 4) from exc
        for part in relative.parts:
            if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in WINDOWS_RESERVED or any(c in part for c in '<>:"|?*'):
                raise HubError(f"Unsafe path component: {part}", 4)
        return resolved

    def _ensure_dir(self, path: Path) -> None:
        path = self._write_path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HubError(f"Cannot create directory: {path}: {exc}", 6) from exc

    def _write_bytes(self, path: Path, data: bytes, atomic: bool = False) -> None:
        path = self._write_path(path)
        self._ensure_dir(path.parent)
        temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex) if atomic else path
        temp = self._write_path(temp)
        try:
            with temp.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if atomic:
                os.replace(temp, path)
        except OSError as exc:
            raise HubError(f"Cannot save {path}: {exc}", 6) from exc

    def _write_json(self, path: Path, obj: Any, atomic: bool = False) -> None:
        self._write_bytes(path, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n", atomic)

    def _read_json(self, path: Path) -> dict:
        self._write_path(path)  # all authoritative inputs must be inside workspace
        try:
            obj = _json_loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise HubError(f"Missing or invalid JSON: {path}: {exc}", 4) from exc
        if not isinstance(obj, dict):
            raise HubError(f"JSON object required: {path}", 4)
        return obj

    def _view_warnings(self, project: Path, revision: str) -> list[str]:
        try:
            root_view = self._write_path(project / "项目中枢.md").read_bytes()
            authoritative_view = self._write_path(project / "revisions" / revision / "项目中枢.md").read_bytes()
            if root_view == authoritative_view:
                return []
        except (HubError, OSError):
            pass
        return ["Committed authority is valid; root view is missing/stale. Read the current snapshot or run repair.py; do not replay the operation"]

    def _input(self, value: Any, text: bool = False) -> dict:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise HubError("file must be a nonempty path", 4)
        path = Path(value).expanduser()
        self._reject_traversal(path)
        if not path.is_absolute():
            path = self.workspace_root / path
        self._reject_links(path)
        path = path.resolve()
        try:
            if not path.is_file():
                raise HubError(f"Input file missing: {path}", 4)
            data = path.read_bytes()
        except OSError as exc:
            raise HubError(f"Cannot read input: {path}: {exc}", 4) from exc
        if not data:
            raise HubError(f"Empty input artifact: {path}", 7)
        result = {"path": str(path), "name": path.name, "data": data, "sha256": _hash(data), "size": len(data)}
        if text:
            try:
                body = data.decode("utf-8-sig")
            except UnicodeError as exc:
                raise HubError(f"Body must be UTF-8 text: {path}", 2) from exc
            content = [line.strip() for line in body.splitlines() if line.strip()]
            # This rejects mechanical empty headings and obvious placeholders,
            # never claims that substantive-looking text is semantically complete.
            meaningful = [line for line in content if not re.match(r"^(#{1,6}\s|[-*+]\s*$|\d+[.)]\s*$|```|\[TOC\]$|目录$|待填写$|TODO$|TBD$)", line, re.I)]
            if not meaningful:
                raise HubError("Artifact contains only headings/empty placeholders", 7)
            result["text"] = body
        return result

    def _project(self, value: str | Path) -> Path:
        raw = Path(value)
        self._reject_traversal(raw)
        if raw.is_absolute() or len(raw.parts) > 1:
            path = self._write_path(raw)
        else:
            path = self._write_path(self.projects_root / _id(str(value), "project ID"))
        if path.parent != self.projects_root:
            raise HubError("Project path must be a direct child of workspace projects/", 4)
        _id(path.name, "project ID")
        if not path.is_dir():
            raise HubError(f"Project does not exist: {path}", 4, project_id=path.name)
        return path

    def _lock(self, project: Path, operation_id: str):
        runtime = self
        class Lock:
            def __enter__(self):
                self.path = runtime._write_path(project / ".write.lock")
                self.token = uuid.uuid4().hex
                record = {"pid": os.getpid(), "host": socket.gethostname(), "operation_id": operation_id,
                          "created_at": _now(), "token": self.token}
                try:
                    self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError as exc:
                    try:
                        existing = runtime._read_json(self.path)
                    except HubError:
                        existing = {"diagnosis": "Unreadable lock; inspect manually"}
                    existing["process_status"] = runtime._lock_process_status(existing)
                    existing["recovery"] = "manual inspection required; never automatically unlocked"
                    raise HubError("Project write lock occupied; no automatic unlock", 5,
                                   project_id=project.name, operation_id=operation_id, lock=existing,
                                   next_actions=["Inspect lock owner, HEAD and work/ before manual lock recovery"]) from exc
                except OSError as exc:
                    raise HubError(f"Cannot acquire project lock: {exc}", 6, project_id=project.name) from exc
                try:
                    os.write(self.fd, _canonical(record))
                    os.fsync(self.fd)
                finally:
                    os.close(self.fd)
                return self

            def __exit__(self, typ, value, traceback):
                try:
                    record = runtime._read_json(self.path)
                    if record.get("token") == self.token:
                        self.path.unlink()
                except (HubError, OSError):
                    pass
                return False
        return Lock()

    def _lock_process_status(self, record: dict) -> str:
        pid = record.get("pid")
        if record.get("host") != socket.gethostname() or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return "unknown"
        if pid == os.getpid():
            return "active"
        if os.name == "nt":
            # Read-only process query; never signal or terminate the lock owner.
            try:
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.GetExitCodeProcess.restype = wintypes.BOOL
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x1000, False, pid)
                if not handle:
                    return "not_running" if ctypes.get_last_error() == 87 else "unknown"
                try:
                    code = wintypes.DWORD()
                    if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                        return "unknown"
                    return "active" if code.value == 259 else "not_running"
                finally:
                    kernel.CloseHandle(handle)
            except (OSError, AttributeError):
                return "unknown"
        try:
            os.kill(pid, 0)
            return "active"
        except ProcessLookupError:
            return "not_running"
        except (PermissionError, OSError):
            return "unknown"

    def _state_template(self, project_id: str, name: str, revision: str, init_hash: str) -> dict:
        state = {"schema_version": SCHEMA_VERSION, "project_id": project_id, "name": name,
                 "revision": revision, "generation": 1, "phase": "research", "brief": None,
                 "workflow_mode": "collaborative", "workflow_version": WORKFLOW_VERSION,
                 "discussion_round": "round-" + uuid.uuid4().hex[:12],
                 "contract": None, "handoff": None,
                 "dependencies": {}, "last_change": None,
                 "initialized_at": _now(), "initialization_hash": init_hash,
                 "content_units": {}, "sessions": {}}
        state.update({name: {} for name in COLLECTIONS.values()})
        return state

    def _new_revision(self, generation: int) -> str:
        return f"r{generation:06d}-{uuid.uuid4().hex[:8]}"

    def _artifact(self, stage: Path, state: dict, artifact_id: str, kind: str,
                  owner: str, relative: str, item: dict, content_status: str = "draft",
                  **extra: Any) -> str:
        _id(artifact_id, "artifact ID")
        prior = state["artifacts"].get(artifact_id)
        if prior and prior.get("owner") != owner:
            raise HubError("Artifact ID already belongs to another object")
        path = self._write_path(stage / relative)
        self._write_bytes(path, item["data"])
        obj = {"artifact_id": artifact_id, "kind": kind, "owner": owner,
               "path": relative, "storage": "snapshot", "sha256": item["sha256"],
               "size": item["size"], "content_status": content_status,
               "stale": False, "stale_reasons": [], "created_revision": state["revision"]}
        obj.update(extra)
        if prior and "allowed_roles" in prior and "allowed_roles" not in obj:
            obj["allowed_roles"] = prior["allowed_roles"]
        state["artifacts"][artifact_id] = obj
        return artifact_id

    def _asset(self, project: Path, item: dict) -> str:
        relative = f"assets/{item['sha256']}/original"
        path = self._write_path(project / relative)
        if path.exists():
            if not path.is_file() or _hash(path.read_bytes()) != item["sha256"]:
                raise HubError(f"Existing deduplicated asset damaged: {path}", 4)
        else:
            self._write_bytes(path, item["data"], atomic=True)
        return relative

    def _object(self, state: dict, ref: str) -> dict:
        kind, ident = _ref(ref).split(":", 1)
        obj = state.get(kind) if kind in ("contract", "handoff") else state[COLLECTIONS[kind]].get(ident)
        if not isinstance(obj, dict):
            raise HubError(f"Reference does not exist in this project: {ref}")
        return obj

    def _objects(self, state: dict) -> dict[str, dict]:
        result = {f"{kind}:{ident}": obj for kind, collection in COLLECTIONS.items()
                  for ident, obj in state[collection].items()}
        for kind in ("contract", "handoff"):
            if state.get(kind):
                result[f"{kind}:current"] = state[kind]
        return result

    def _fingerprints(self, state: dict, version: int = FINGERPRINT_VERSION) -> dict[str, str]:
        if type(version) is not int or version not in (1, FINGERPRINT_VERSION):
            raise HubError("Unsupported object fingerprint version", 4)
        result = {}
        for ref, obj in self._objects(state).items():
            if ref.startswith("artifact:") or (version == 1 and ref.startswith("source:")):
                result[ref] = obj["sha256"]
            elif ref.startswith("source:"):
                # Bind the actual bytes and the submitter's evidence declarations.
                # Local storage locations and derived freshness are not evidence.
                excluded = {"stale", "stale_reasons", "artifact_id", "original_path", "updated_revision"}
                declaration = {k: v for k, v in obj.items() if k not in excluded}
                result[ref] = _hash(_canonical({"fingerprint_version": version, "source": declaration}))
            else:
                clean = {k: v for k, v in obj.items() if k not in ("stale", "stale_reasons", "review_status", "validation_status")}
                result[ref] = _hash(_canonical(clean))
        return result

    def _build_dependencies(self, state: dict) -> dict[str, list[str]]:
        graph = {}
        objects = self._objects(state)
        for ref, obj in objects.items():
            deps = list(obj.get("depends_on", []))
            for field, kind in (("source_ids", "source"), ("decision_ids", "decision"), ("fact_ids", "fact")):
                deps.extend(f"{kind}:{ident}" for ident in obj.get(field, []))
            if ref.startswith("artifact:"):
                owner = obj.get("owner")
                if owner and owner in objects:
                    deps.append(owner)
            if ref.startswith("review:"):
                deps.extend(obj.get("targets", []))
                deps.extend(obj.get("input_fingerprints", {}))
                deps.extend("artifact:" + ident for ident in obj.get("evidence", []))
            if ref.startswith("cost:") and obj.get("value", {}).get("shared_or_incremental") == "allocation":
                deps.append("cost:" + _id(obj["value"].get("master_cost_id"), "master cost ID"))
            if ref.startswith("unit:"):
                value = obj.get("value", obj)
                deps.extend(["module:" + value["module_id"], "artifact:" + value["artifact_id"]])
            if ref.startswith("session:"):
                value = obj["value"]
                for field, kind in (("unit_ids", "unit"), ("resource_ids", "resource"), ("cost_ids", "cost")):
                    deps.extend(f"{kind}:{ident}" for ident in value[field])
            if ref == "handoff:current":
                deps.extend(f"artifact:{ident}" for ident in obj.get("artifact_ids", []))
                deps.extend(f"module:{ident}" for ident in obj.get("module_ids", []))
            graph[ref] = list(dict.fromkeys(_ref(item) for item in deps))
        return graph

    def _validate_state(self, state: dict, project_id: str, revision: str) -> None:
        if state.get("schema_version") != SCHEMA_VERSION or state.get("project_id") != project_id or state.get("revision") != revision:
            raise HubError("Project/schema/revision identity mismatch", 4, project_id=project_id, current_revision=revision)
        if state.get("phase") not in ("research", "production"):
            raise HubError("Invalid project phase")
        if "workflow_version" in state:
            if type(state["workflow_version"]) is not int or state["workflow_version"] != WORKFLOW_VERSION or state.get("workflow_mode") != "collaborative":
                raise HubError("Unsupported human workflow version", 4)
            _id(state.get("discussion_round"), "discussion round")
        # Early development schema-1 snapshots had these optional empty object
        # collections. Defaults are in memory only; immutable bytes stay intact.
        state.setdefault("content_units", {})
        state.setdefault("sessions", {})
        if not isinstance(state.get("generation"), int) or isinstance(state["generation"], bool) or state["generation"] < 1:
            raise HubError("Invalid revision generation")
        for collection in COLLECTIONS.values():
            if not isinstance(state.get(collection), dict):
                raise HubError(f"Invalid collection: {collection}")
            for ident, obj in state[collection].items():
                _id(ident)
                if not isinstance(obj, dict):
                    raise HubError(f"Invalid object {collection}:{ident}")
                if "allowed_roles" in obj:
                    _roles(obj["allowed_roles"])
                for affected_ref in obj.get("impact", []):
                    self._object(state, affected_ref)
        for source in state["sources"].values():
            for source_id in source.get("same_origin_ids", []):
                # Same origin is a provenance relation, not a prerequisite DAG.
                self._object(state, "source:" + _id(source_id))
        for ident, module in state["modules"].items():
            _require(module, ["module_id", "applicability", "purpose", "author_role", "recipient_role", "delivery_depth", "depends_on", "source_ids", "decision_ids", "artifact_ids", "content_status", "unresolved", "acceptance"])
            if module["module_id"] != ident or module["applicability"] not in APPLICABILITY or module["content_status"] not in CONTENT_STATUS:
                raise HubError(f"Invalid independent module state: {ident}")
            for artifact_id in module["artifact_ids"]:
                self._object(state, f"artifact:{artifact_id}")
            self._unresolved(module["unresolved"])
            for item in module["unresolved"]:
                for affected_ref in item["impact"]:
                    self._object(state, affected_ref)
        if state.get("handoff"):
            self._unresolved(state["handoff"]["unresolved"])
            for item in state["handoff"]["unresolved"]:
                for affected_ref in item["impact"]:
                    self._object(state, affected_ref)
        for ident, unit in state["content_units"].items():
            value = unit.get("value", unit)
            _require(value, ["title", "module_id", "artifact_id"])
            _text(value["title"], "unit title")
            self._object(state, "module:" + value["module_id"])
            artifact = self._object(state, "artifact:" + value["artifact_id"])
            if artifact.get("owner") != "module:" + value["module_id"]:
                raise HubError("Content unit artifact must belong to its actual module")
        graph = self._build_dependencies(state)
        for target, upstreams in graph.items():
            for upstream in upstreams:
                if upstream not in graph:
                    raise HubError(f"Unresolved dependency {target} -> {upstream}")
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting:
                raise HubError(f"Dependency cycle at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dep in graph[node]:
                visit(dep)
            visiting.remove(node)
            visited.add(node)
        for node in graph:
            visit(node)
        state["dependencies"] = graph

    def _propagate(self, state: dict, changed: set[str], reason: str,
                   include_roots: bool = False) -> list[str]:
        graph = self._build_dependencies(state)
        reverse = {ref: set() for ref in graph}
        for target, dependencies in graph.items():
            for dep in dependencies:
                reverse.setdefault(dep, set()).add(target)
        affected, todo = set(changed if include_roots else ()), list(changed)
        expanded = set()
        while todo:
            ref = todo.pop()
            if ref in expanded:
                continue
            expanded.add(ref)
            for child in reverse.get(ref, ()):
                if child in changed and not include_roots:
                    todo.append(child)
                    continue
                if child not in affected:
                    affected.add(child)
                    todo.append(child)
        objects = self._objects(state)
        for ref in affected:
            if ref not in objects:
                continue
            obj = objects[ref]
            obj["stale"] = True
            obj["stale_reasons"] = list(dict.fromkeys(obj.get("stale_reasons", []) + [reason]))
            if ref.startswith(("module:", "artifact:")) and obj.get("content_status") != "outline":
                obj["content_status"] = "needs_review"
            if ref.startswith("review:"):
                obj["validation_status"] = "stale"
        return sorted(affected)

    def _closure(self, state: dict, roots: list[str]) -> list[str]:
        graph = state["dependencies"]
        found, todo = set(), list(roots)
        while todo:
            ref = todo.pop()
            if ref in found:
                continue
            self._object(state, ref)
            found.add(ref)
            todo.extend(graph.get(ref, []))
        return sorted(found)

    def _blocking(self, state: dict, module_id: str) -> list[dict]:
        roots = {f"module:{module_id}"} | set(self._closure(state, [f"module:{module_id}"]))
        questions = list(state["questions"].values()) + state["modules"][module_id].get("unresolved", [])
        if state.get("handoff"):
            questions += state["handoff"].get("unresolved", [])
        result = []
        for question in questions:
            if isinstance(question, dict) and question.get("blocking") and question.get("status") != "resolved":
                impact = question.get("impact", [])
                if not impact or roots.intersection(impact):
                    result.append(question)
        return result

    def _validate_payload(self, kind: str, payload: Any) -> dict:
        if not isinstance(kind, str) or kind not in {"source", "contract", "handoff", "module", "change", "review", "reopen", "pause"}:
            raise HubError(f"Unknown submit kind: {kind}")
        if not isinstance(payload, dict):
            raise HubError("Payload must be a JSON object")
        try:
            data = _json_loads(_canonical(payload))
        except (ValueError, TypeError) as exc:
            raise HubError(f"Payload must contain finite JSON values: {exc}") from exc
        _require(data, ["file"])
        required = {
            "pause": ["node", "authorized_scope", "refs"],
            "reopen": ["reason", "source_ids", "retained_refs"],
            "source": ["source_id", "title", "producer", "locator", "published_at", "occurred_at", "accessed_at", "version", "access_status", "read_scope", "supports", "limitations"],
            "contract": ["requirements", "author_role", "recipient_role", "document_use", "modules"],
            "handoff": ["policy", "decision_ids", "source_ids", "inventory_source_ids", "sufficiency", "unresolved"],
            "module": ["module_id", "source_ids", "decision_ids", "changes", "impact", "content_status", "acceptance_evidence"],
            "change": ["entity", "id", "old_value", "new_value", "reason", "source_ids", "decision_ids", "impact"],
            "review": ["review_id", "targets", "input_fingerprints", "reviewer", "method", "result", "evidence"],
        }
        _require(data, required[kind])
        for field in ("source_ids", "decision_ids", "fact_ids", "inventory_source_ids", "artifact_ids", "module_ids", "same_origin_ids", "evidence"):
            if field in data:
                _list(data[field], field)
                for ident in data[field]:
                    _id(ident, field)
        for field in ("depends_on", "impact", "targets", "remove_dependencies", "retained_refs", "refs"):
            if field in data:
                data[field] = _refs(data[field], field)
        if "allowed_roles" in data:
            data["allowed_roles"] = _roles(data["allowed_roles"])
        return data

    def _inputs(self, kind: str, payload: dict) -> list[dict]:
        inputs = [self._input(payload["file"], text=kind != "source")]
        if kind == "module":
            for artifact in _list(payload.get("handoff_artifacts", []), "handoff_artifacts"):
                if not isinstance(artifact, dict):
                    raise HubError("handoff_artifacts entries must be objects")
                _require(artifact, ["artifact_id", "file", "recipient_role", "purpose", "content_status"])
                _id(artifact["artifact_id"])
                _text(artifact["recipient_role"], "recipient_role")
                _text(artifact["purpose"], "purpose")
                _enum(artifact["content_status"], CONTENT_STATUS, "handoff artifact maturity")
                if "allowed_roles" in artifact:
                    artifact["allowed_roles"] = _roles(artifact["allowed_roles"])
                inputs.append(self._input(artifact["file"], text=True))
        if kind == "pause":
            _enum(payload["node"], PAUSE_NODES, "pause node")
            for material in _list(payload.get("materials", []), "materials"):
                if not isinstance(material, dict):
                    raise HubError("Materials must be classified objects")
                for file in _list(material.get("files", []), "material files"):
                    inputs.append(self._input(file))
            for extra in _list(payload.get("extra_files", []), "extra_files"):
                if not isinstance(extra, dict):
                    raise HubError("Extra files need category/title/file")
                _require(extra, ["category", "title", "file"])
                _enum(extra["category"], MATERIAL_CATEGORIES, "extra file category")
                _text(extra["title"], "extra file title")
                inputs.append(self._input(extra["file"]))
        return inputs

    def _candidate(self, project: Path, operation_id: str, request_hash: str,
                   request: dict, inputs: list[dict]) -> Path:
        path = project / "candidates" / f"{operation_id}-{request_hash[:16]}"
        self._ensure_dir(path)
        saved_inputs = []
        for index, item in enumerate(inputs):
            relative = f"input-{index:03d}.bin"
            self._write_bytes(path / relative, item["data"], atomic=True)
            saved_inputs.append({k: v for k, v in item.items() if k not in ("data", "text")} | {"candidate_file": relative})
        self._write_json(path / "request.json", {"request": request, "request_hash": request_hash,
                                                  "inputs": saved_inputs}, atomic=True)
        return path

    def _make_stage(self, project: Path, revision: str, parent: str | None) -> Path:
        stage = project / "work" / f"stage-{revision}"
        self._ensure_dir(stage)
        if parent:
            origin = project / "revisions" / parent
            for path in origin.rglob("*"):
                self._write_path(path)
                if path.is_file() and path.name not in {"manifest.json", "state.json", "operation.json", "fingerprints.json", "项目中枢.md"}:
                    self._write_bytes(stage / path.relative_to(origin), path.read_bytes())
        return stage

    def _artifact_path(self, project: Path, revision: str, artifact: dict) -> Path:
        if artifact["storage"] == "asset":
            return self._write_path(project / artifact["path"])
        return self._write_path(project / "revisions" / revision / artifact["path"])

    def _markdown_link(self, label: str, path: Path) -> str:
        return f"[{label}](<{path.as_posix()}>)"

    def _render_snapshot(self, stage: Path, final_path: Path, state: dict) -> None:
        lines = [f"# {state['name']} · 当前项目短视图", "", f"项目：{state['project_id']}；版本：{state['revision']}；阶段：{state['phase']}", "",
                 "本视图为可重建入口。真实决定、证据、正文和执行状态分别维护；脚本不认证语义。", ""]
        if state.get("handoff"):
            h = state["handoff"]
            lines.append(f"交接充分性：{h['sufficiency']}；待复核：{h.get('stale', False)}")
            lines.append(f"方针预览：{h['policy'][:600]}" + ("（预览截断，按原文回读）" if len(h["policy"]) > 600 else ""))
        else:
            lines.append("尚无正式阶段交接；继续研究及契约。")
        if state.get("workflow_mode") == "collaborative":
            lines += ["", self._next_discussion(state)]
        lines += ["", "## 当前模块（最多20项）", ""]
        for module in list(state["modules"].values())[:20]:
            lines.append(f"- {module['module_id']}：{module['applicability']} / {module['content_status']}；待复核={module.get('stale', False)}")
            for artifact_id in module["artifact_ids"][:3]:
                artifact = state["artifacts"][artifact_id]
                if artifact["storage"] == "snapshot":
                    # Read staging bytes; published destination does not yet exist.
                    raw = self._write_path(stage / artifact["path"]).read_bytes()
                    if _hash(raw) != artifact["sha256"]:
                        raise HubError("Staging artifact fingerprint mismatch", 4)
                    destination = final_path / artifact["path"]
                else:
                    destination = final_path.parent.parent / artifact["path"]
                lines.append("  - " + self._markdown_link(artifact_id, destination))
        if len(state["modules"]) > 20:
            lines.append("其余模块见分页目录；本视图未列出不等于不适用。")
        lines += ["", "## 原件与目录入口", "", self._markdown_link("权威state", final_path / "state.json"),
                  self._markdown_link("当前指纹", final_path / "fingerprints.json"),
                  "完整资料目录由 resume/repair 生成，默认只列当前页；目录识别与原文读取分别记录。", "",
                  "上下文遥测：unknown。真实核验、外部资源落实及活动结果由实际证据判断。"]
        self._write_bytes(stage / "项目中枢.md", ("\n".join(lines) + "\n").encode("utf-8"))

    def _manifest(self, project: Path, stage: Path, state: dict, parent: dict | None) -> dict:
        files = {}
        for path in sorted(stage.rglob("*")):
            self._write_path(path)
            if path.is_file() and path.name != "manifest.json":
                data = path.read_bytes()
                files[path.relative_to(stage).as_posix()] = {"sha256": _hash(data), "size": len(data)}
        assets = {a["path"]: {"sha256": a["sha256"], "size": a["size"]}
                  for a in state["artifacts"].values() if a["storage"] == "asset"}
        return {"schema_version": SCHEMA_VERSION, "project_id": state["project_id"], "revision": state["revision"],
                "parent_revision": parent["revision"] if parent else None,
                "parent_manifest_sha256": parent["manifest_sha256"] if parent else None,
                "files": files, "assets": assets}

    def _publish_head(self, project_path: Path, head_dict: dict) -> None:
        self._write_json(project_path / "HEAD.json", head_dict, atomic=True)

    def _finish(self, project: Path, stage: Path, state: dict, operation: dict,
                parent: dict | None, chain: list[dict]) -> dict:
        state["fingerprint_version"] = FINGERPRINT_VERSION
        revision = state["revision"]
        final_path = project / "revisions" / revision
        self._validate_state(state, project.name, revision)
        for ident, source in state["sources"].items():
            self._write_json(stage / "research" / "sources" / f"{ident}.json", source)
        self._write_json(stage / "state.json", state)
        self._write_json(stage / "operation.json", operation)
        self._write_json(stage / "fingerprints.json", self._fingerprints(state))
        self._render_snapshot(stage, final_path, state)
        manifest = self._manifest(project, stage, state, parent)
        self._write_json(stage / "manifest.json", manifest)
        manifest_hash = _hash((stage / "manifest.json").read_bytes())
        head = {"schema_version": SCHEMA_VERSION, "project_id": project.name, "revision": revision,
                "manifest_sha256": manifest_hash, "published_at": _now()}
        self._validate_revision(project, stage, revision, manifest_hash)
        try:
            self._write_path(final_path)
            if final_path.exists():
                raise HubError("Revision collision", 6)
            os.replace(stage, final_path)
            self._publish_head(project, head)
        except HubError:
            raise
        except OSError as exc:
            raise HubError(f"Publication failed; old HEAD remains authoritative: {exc}", 6,
                           project_id=project.name, current_revision=parent["revision"] if parent else None,
                           operation_id=operation["operation_id"], orphan_revision=revision) from exc
        warnings = []
        entry = {"revision": revision, "manifest_sha256": manifest_hash, "manifest": manifest,
                 "state": state, "operation": operation}
        try:
            self._refresh_views(project, state, [entry] + chain)
        except Exception as exc:
            warnings.append(f"Committed {revision}; derived views need repair: {type(exc).__name__}: {exc}")
        return _response(project_id=project.name, current_revision=revision, operation_id=operation["operation_id"],
                         artifact_paths=[str(self._artifact_path(project, revision, a)) for a in state["artifacts"].values()
                                         if a.get("created_revision") == revision],
                         context_path=str(project / "项目中枢.md"), warnings=warnings,
                         discussion_round=state.get("discussion_round"), workflow_version=state.get("workflow_version"),
                         next_actions=["Run repair.py to rebuild derived views"] if warnings else
                         ([self._next_discussion(state)] if state.get("workflow_mode") == "collaborative" else ["Resume current task and read required originals"]),
                         affected=operation.get("affected", []), project_path=str(project))

    def _validate_revision(self, project: Path, directory: Path, revision: str, expected_hash: str) -> dict:
        manifest_path = self._write_path(directory / "manifest.json")
        try:
            raw = manifest_path.read_bytes()
        except OSError as exc:
            raise HubError(f"Missing manifest: {manifest_path}", 4) from exc
        if _hash(raw) != expected_hash:
            raise HubError(f"Manifest fingerprint mismatch: {revision}", 4)
        manifest = self._read_json(manifest_path)
        if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("project_id") != project.name or manifest.get("revision") != revision:
            raise HubError("Manifest identity mismatch", 4)
        if not isinstance(manifest.get("files"), dict) or not isinstance(manifest.get("assets"), dict):
            raise HubError("Invalid manifest entries", 4)
        required = {"state.json", "operation.json", "fingerprints.json", "项目中枢.md"}
        if not required.issubset(manifest["files"]):
            raise HubError("Manifest omits critical snapshot files", 4)
        actual = set()
        for path in directory.rglob("*"):
            self._write_path(path)
            if path.is_file() and path.name != "manifest.json":
                actual.add(path.relative_to(directory).as_posix())
        if actual != set(manifest["files"]):
            raise HubError("Snapshot inventory differs from manifest", 4)
        for area, entries, root in (("file", manifest["files"], directory), ("asset", manifest["assets"], project)):
            for relative, metadata in entries.items():
                if not isinstance(relative, str) or Path(relative).is_absolute():
                    raise HubError("Manifest path must be relative", 4)
                if area == "asset" and not relative.startswith("assets/"):
                    raise HubError("Invalid manifest asset path", 4)
                path = self._write_path(root / relative)
                try:
                    path.relative_to(root)
                    data = path.read_bytes()
                except (ValueError, OSError) as exc:
                    raise HubError(f"Snapshot/asset missing or outside project: {relative}", 4) from exc
                if not isinstance(metadata, dict) or len(data) != metadata.get("size") or _hash(data) != metadata.get("sha256"):
                    raise HubError(f"Snapshot/asset fingerprint mismatch: {revision}/{relative}", 4)
        state = self._read_json(directory / "state.json")
        try:
            self._validate_state(state, project.name, revision)
        except HubError as exc:
            raise HubError(f"Invalid authoritative state: {exc}", 4) from exc
        for artifact in state["artifacts"].values():
            expected = manifest["assets"] if artifact.get("storage") == "asset" else manifest["files"]
            metadata = expected.get(artifact.get("path"))
            if not metadata or metadata.get("sha256") != artifact.get("sha256") or metadata.get("size") != artifact.get("size"):
                raise HubError("Artifact metadata disagrees with manifest", 4)
        saved_fingerprints = self._read_json(directory / "fingerprints.json")
        if saved_fingerprints != self._fingerprints(state, version=state.get("fingerprint_version", 1)):
            raise HubError("Object fingerprints disagree with state", 4)
        operation = self._read_json(directory / "operation.json")
        if operation.get("revision") != revision or operation.get("project_id") != project.name:
            raise HubError("Operation identity mismatch", 4)
        _id(operation.get("operation_id"), "operation ID")
        if operation.get("parent_revision") != manifest.get("parent_revision"):
            raise HubError("Operation/manifest parent mismatch", 4)
        if state.get("parent_revision") != manifest.get("parent_revision"):
            raise HubError("State/manifest parent mismatch", 4)
        request_hash = operation.get("request_hash")
        if not isinstance(request_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", request_hash):
            raise HubError("Invalid operation request fingerprint", 4)
        if "request" in operation and _hash(_canonical(operation["request"])) != request_hash:
            raise HubError("Operation request differs from recorded fingerprint", 4)
        return {"revision": revision, "manifest_sha256": expected_hash, "manifest": manifest,
                "state": state, "operation": operation}

    def _chain(self, project: Path) -> tuple[dict, list[dict]]:
        head = self._read_json(project / "HEAD.json")
        if head.get("schema_version") != SCHEMA_VERSION or head.get("project_id") != project.name:
            raise HubError("HEAD project/schema identity mismatch", 4, project_id=project.name)
        revision, fingerprint = head.get("revision"), head.get("manifest_sha256")
        chain, seen, operations = [], set(), set()
        while revision is not None:
            _id(revision, "revision")
            if revision in seen:
                raise HubError("Corrupted/cyclic committed ancestry", 4)
            seen.add(revision)
            entry = self._validate_revision(project, project / "revisions" / revision, revision, fingerprint)
            operation_id = entry["operation"]["operation_id"]
            if operation_id in operations:
                raise HubError("Duplicate operation ID in committed ancestry", 4)
            operations.add(operation_id)
            chain.append(entry)
            revision = entry["manifest"]["parent_revision"]
            fingerprint = entry["manifest"]["parent_manifest_sha256"]
            if (revision is None) != (fingerprint is None):
                raise HubError("Incomplete ancestry fingerprint", 4)
        if not chain:
            raise HubError("Empty committed ancestry", 4)
        for child, parent in zip(chain, chain[1:]):
            if child["state"]["generation"] != parent["state"]["generation"] + 1:
                raise HubError("Committed generation chain is inconsistent", 4)
        if chain[-1]["state"]["generation"] != 1:
            raise HubError("Committed ancestry does not reach its initialization", 4)
        return head, chain

    def _catalog(self, project: Path, state: dict) -> list[dict]:
        rows = []
        fingerprints = self._fingerprints(state)
        for ref, obj in sorted(self._objects(state).items()):
            kind, ident = ref.split(":", 1)
            row = {"ref": ref, "kind": kind, "id": ident, "revision": state["revision"],
                   "stale": obj.get("stale", False), "content_status": obj.get("content_status"),
                   "applicability": obj.get("applicability"), "fingerprint": fingerprints[ref]}
            if kind == "artifact":
                row["path"] = str(self._artifact_path(project, state["revision"], obj))
            elif kind == "source":
                row["source_id"] = ident
                row["path"] = str(self._artifact_path(project, state["revision"], state["artifacts"][obj["artifact_id"]]))
                row["locator"] = obj["locator"]
                row["read_scope"] = obj["read_scope"]
                row["access_status"] = obj["access_status"]
                row["file_sha256"] = obj["sha256"]
            else:
                artifact_ids = obj.get("artifact_ids", [])
                if obj.get("artifact_id"):
                    artifact_ids = [obj["artifact_id"]] + artifact_ids
                row["artifact_paths"] = [str(self._artifact_path(project, state["revision"], state["artifacts"][a])) for a in artifact_ids]
                row["state_path"] = str(project / "revisions" / state["revision"] / "state.json")
                row["state_locator"] = f"/{COLLECTIONS.get(kind, kind)}/{ident}" if kind in COLLECTIONS else f"/{kind}"
            if kind == "review":
                input_version = obj.get("input_fingerprint_version", 1)
                has_sources = any(ref.startswith("source:") for ref in obj.get("input_fingerprints", {}))
                row["input_fingerprint_version"] = input_version
                row["source_metadata_coverage"] = ("bound" if input_version == FINGERPRINT_VERSION else "not_bound") if has_sources else "not_applicable"
            rows.append(row)
        # Sources first supports deliberate directory walks. All other actual
        # objects remain in later pages rather than being silently omitted.
        return sorted(rows, key=lambda row: (0 if row["kind"] == "source" else 1, row["ref"]))

    def _visible_refs(self, state: dict, role: str) -> set[str]:
        objects = self._objects(state)
        if role == "master":
            return set(objects)
        graph = copy.deepcopy(state["dependencies"])
        # Full contract/handoff originals include their complete inventories.
        # Without a sanitized original, a mixed-scope file stays restricted.
        if state.get("contract"):
            graph["contract:current"] += [f"module:{ident}" for ident in state["contract"]["module_order"]]
        if state.get("handoff"):
            graph["handoff:current"] += [f"source:{ident}" for ident in state["handoff"]["inventory_source_ids"]]
        # A full writing commission names every chapter in its scope. Scope is
        # a disclosure relationship, not a content dependency (which would
        # create module/commission cycles). Mixed-scope originals stay private.
        invalid_scope = set()
        for ident, decision in state["decisions"].items():
            value = decision.get("value")
            if isinstance(value, dict) and value.get("gate") == "writing":
                try:
                    scopes = ["module:" + _id(module_id) for module_id in _list(value.get("modules"), "writing modules")]
                except HubError:
                    invalid_scope.add("decision:" + ident)
                else:
                    if not scopes:
                        invalid_scope.add("decision:" + ident)
                    graph["decision:" + ident] += scopes
        denied = invalid_scope
        for ref, obj in objects.items():
            own = obj.get("allowed_roles")
            if own is None and (ref.startswith("source:") or ref == "artifact:brief"):
                own = ["master"]
            if own is not None and role not in own:
                denied.add(ref)
            if ref.startswith("module:") and state.get("contract"):
                contract_roles = state["contract"].get("allowed_roles")
                spec_roles = obj.get("contract_spec", {}).get("allowed_roles")
                if (contract_roles is not None and role not in contract_roles) or (spec_roles is not None and role not in spec_roles):
                    denied.add(ref)
            if ref == "artifact:brief" and state.get("contract"):
                brief_roles = state["contract"].get("allowed_roles")
                if brief_roles is not None and role not in brief_roles:
                    denied.add(ref)
        # Scope relationships may contain legitimate loops. Propagating denial
        # to their fixed point is independent of object or dependency order.
        reverse = {ref: set() for ref in objects}
        for ref, dependencies in graph.items():
            for dependency in dependencies:
                if dependency not in objects:
                    denied.add(ref)
                else:
                    reverse[dependency].add(ref)
        pending = list(denied)
        while pending:
            for dependent in reverse[pending.pop()]:
                if dependent not in denied:
                    denied.add(dependent)
                    pending.append(dependent)
        return set(objects) - denied

    def _refresh_views(self, project_path: Path, state: dict, chain: list[dict]) -> None:
        revision_dir = project_path / "revisions" / state["revision"]
        self._write_bytes(project_path / "项目中枢.md", (revision_dir / "项目中枢.md").read_bytes(), atomic=True)
        self._write_json(project_path / "operations" / "index.json", {
            "project_id": project_path.name, "revision": state["revision"],
            "operations": {entry["operation"]["operation_id"]: {
                "revision": entry["revision"], "request_hash": entry["operation"]["request_hash"],
                "kind": entry["operation"]["kind"]} for entry in chain}}, atomic=True)
        self._write_json(project_path / "operations" / "catalog.json", {
            "project_id": project_path.name, "revision": state["revision"],
            "coverage": "inventory only; original reading not verified", "items": self._catalog(project_path, state)}, atomic=True)

    def _operation(self, state: dict, operation_id: str, kind: str, request_hash: str,
                   parent: str | None, affected: list[str] | None = None, **extra: Any) -> dict:
        return {"schema_version": SCHEMA_VERSION, "project_id": state["project_id"],
                "operation_id": operation_id, "kind": kind, "request_hash": request_hash,
                "revision": state["revision"], "parent_revision": parent, "created_at": _now(),
                "affected": affected or [], **extra}

    def init(self, name: str, project_id: str | None = None, brief: str | Path | None = None,
             brief_allowed_roles: list[str] | None = None) -> dict:
        _text(name, "name")
        if len(name) > 240:
            raise HubError("Project name too long")
        project_id = _id(project_id, "project ID") if project_id is not None else "project-" + uuid.uuid4().hex[:12]
        item = self._input(brief, text=True) if brief is not None else None
        if brief_allowed_roles is not None and item is None:
            raise HubError("brief_allowed_roles requires an actual brief input")
        brief_roles = _roles(brief_allowed_roles) if brief_allowed_roles is not None else ["master"]
        init_request = {"name": name, "project_id": project_id,
                        "brief_sha256": item["sha256"] if item else None}
        if brief_allowed_roles is not None:
            init_request["brief_allowed_roles"] = brief_roles
        init_hash = _hash(_canonical(init_request))
        project = self._write_path(self.projects_root / project_id)
        created = False
        try:
            project.mkdir()
            created = True
        except FileExistsError:
            if not project.is_dir():
                raise HubError("Project ID already exists as non-directory", 4, project_id=project_id)
        except OSError as exc:
            raise HubError(f"Cannot create project: {exc}", 6, project_id=project_id) from exc
        with self._lock(project, "init"):
            if not created:
                head, chain = self._chain(project)
                state = chain[0]["state"]
                if state["initialization_hash"] != init_hash:
                    raise HubError("Existing project identity/initial content conflicts; resume it instead", 3,
                                   project_id=project_id, current_revision=head["revision"])
                return _response("already_applied", project_id, head["revision"], "init",
                                 project_path=str(project), context_path=str(project / "项目中枢.md"),
                                 warnings=self._view_warnings(project, head["revision"]),
                                 next_actions=["Resume the existing project"])
            for folder in ("revisions", "assets", "candidates", "work", "operations", "deliverables"):
                self._ensure_dir(project / folder)
            revision = self._new_revision(1)
            state = self._state_template(project_id, name, revision, init_hash)
            stage = self._make_stage(project, revision, None)
            if item:
                self._artifact(stage, state, "brief", "brief", "project:brief", "research/brief.md", item,
                               allowed_roles=brief_roles)
                state["brief"] = {"artifact_id": "brief", "original_path": item["path"], "sha256": item["sha256"],
                                  "allowed_roles": brief_roles}
            operation = self._operation(state, "init", "init", init_hash, None)
            return self._finish(project, stage, state, operation, None, [])

    def _apply_source(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str) -> set[str]:
        ident = _id(payload["source_id"], "source ID")
        for field in ("title", "producer", "locator", "accessed_at", "version"):
            _text(payload[field], field)
        for field in ("published_at", "occurred_at"):
            if payload[field] is not None:
                _text(payload[field], field)
        _enum(payload["access_status"], {"full", "partial", "restricted", "unavailable"}, "source access_status")
        scope = payload["read_scope"]
        if not isinstance(scope, dict):
            raise HubError("read_scope must be an object")
        _require(scope, ["status", "ranges", "limitations"])
        _enum(scope["status"], {"unread", "partial", "full"}, "declared reading status")
        for field in ("ranges", "limitations"):
            _list(scope[field], f"read_scope.{field}")
            for item in scope[field]:
                _text(item, "read_scope." + field + " entry")
        if scope["status"] in {"partial", "full"} and not scope["ranges"]:
            raise HubError("Actual reading scope requires exact ranges")
        if scope["status"] == "unread" and scope["ranges"]:
            raise HubError("Unread source cannot declare read ranges")
        for field in ("supports", "limitations"):
            _list(payload[field], field)
            for item in payload[field]:
                _text(item, field + " entry")
        if "dynamic" in payload and not isinstance(payload["dynamic"], bool):
            raise HubError("dynamic must be boolean")
        artifact_id = _generated("source-", ident)
        prior_source = state["sources"].get(ident)
        prior = state["artifacts"].get(artifact_id)
        if prior and prior.get("owner") != f"source:{ident}":
            raise HubError("Generated source artifact collides with another object")
        relative = self._asset(project, inputs[0])
        state["artifacts"][artifact_id] = {"artifact_id": artifact_id, "kind": "source_original", "owner": f"source:{ident}",
            "storage": "asset", "path": relative, "sha256": inputs[0]["sha256"], "size": inputs[0]["size"],
            "original_name": inputs[0]["name"], "content_status": "draft", "stale": False, "stale_reasons": [],
            "created_revision": state["revision"]}
        state["sources"][ident] = {k: v for k, v in payload.items() if k not in {"file", "project_id"}}
        if prior_source and "allowed_roles" in prior_source and "allowed_roles" not in state["sources"][ident]:
            state["sources"][ident]["allowed_roles"] = prior_source["allowed_roles"]
        state["sources"][ident].setdefault("allowed_roles", ["master"])
        state["sources"][ident].update({"artifact_id": artifact_id, "sha256": inputs[0]["sha256"],
                                      "original_path": inputs[0]["path"], "stale": False, "stale_reasons": [],
                                      "updated_revision": state["revision"]})
        self._write_json(stage / "research" / "sources" / f"{ident}.json", state["sources"][ident])
        return {f"source:{ident}", f"artifact:{artifact_id}"}

    def reopen(self, project: str | Path, base: str, operation_id: str, file: str | Path,
               source_ids: list[str], reason: str, retained_refs: list[str] | None = None) -> dict:
        return self.submit(project, base, operation_id, "reopen", {
            "file": str(file), "source_ids": source_ids, "reason": reason,
            "retained_refs": [] if retained_refs is None else retained_refs})

    def pause(self, project: str | Path, base: str, operation_id: str, payload: dict) -> dict:
        return self.submit(project, base, operation_id, "pause", payload)

    def _checkpoint_record(self, snapshot: Path, state: dict, checkpoint_id: str | None) -> dict | None:
        artifact = state["artifacts"].get(checkpoint_id)
        if not artifact or artifact.get("kind") != "human_checkpoint" or artifact.get("storage") != "snapshot":
            return None
        raw = (snapshot / artifact["path"]).read_bytes()
        if _hash(raw) != artifact["sha256"]:
            raise HubError("Published checkpoint bytes do not match their record", 4)
        return _json_loads(raw)

    def _checkpoint_current(self, state: dict, record: dict, fingerprints: dict) -> bool:
        artifact = state["artifacts"].get(record.get("checkpoint_id"), {})
        return (artifact.get("kind") == "human_checkpoint"
            and record.get("saved_revision") == artifact.get("created_revision")
            and record.get("discussion_round") == state.get("discussion_round")
            and not artifact.get("stale")
            and all(fingerprints.get(ref) == value for ref, value in record.get("input_fingerprints", {}).items()))

    def _apply_pause(self, project: Path, stage: Path, state: dict, payload: dict,
                     inputs: list[dict], operation_id: str) -> set[str]:
        node = _enum(payload["node"], PAUSE_NODES, "pause node")
        _text(payload["authorized_scope"], "authorized_scope")
        reuse = payload.get("reuse_materials", False)
        if not isinstance(reuse, bool) or (reuse and node != "context_save"):
            raise HubError("reuse_materials is only available for context_save")
        prior = state.get("pause_checkpoint") or {}
        awaiting = (self._checkpoint_record(stage, state, state.get("pending_checkpoint_id"))
                    if node == "context_save" else None)
        pending_default = (awaiting or prior).get("pending_questions", []) if state.get("pending_checkpoint_id") else []
        pending = payload.get("pending_questions", pending_default if reuse else None)
        pending = _list(pending, "pending_questions")
        for question in pending:
            _text(question, "pending question")
        if node != "context_save" and not pending:
            raise HubError("人审节点须保存实际待答复问题。", 7)
        next_default = (awaiting or prior).get("next_action") if state.get("pending_checkpoint_id") else self._next_discussion(state)
        next_action = payload.get("next_action", next_default if reuse else None)
        _text(next_action, "next_action")
        if len(next_action) > 2000:
            raise HubError("next_action exceeds the resume task limit of 2000 characters")
        roles = _roles(payload.get("allowed_roles", ["master"]))
        materials = {}
        if reuse:
            for previous in prior.get("materials", []):
                refs = list(dict.fromkeys(previous.get("refs", []) + ["artifact:" + ident for ident in previous.get("artifact_ids", [])]))
                materials[previous["category"]] = {"category": previous["category"], "title": previous["title"],
                    "status": "referenced" if refs else "none", "refs": refs, "files": [],
                    "note": "复用上次已经保存的分类原件。" if refs else previous.get("note", "本类尚无新增材料。")}
            for category in MATERIAL_CATEGORIES:
                materials.setdefault(category, {"category": category, "title": category, "status": "none",
                    "refs": [], "files": [], "note": "尚无前序分类记录；已有项目资料仍由原索引保存。"})
        supplied = _list(payload.get("materials", []), "materials")
        seen = set()
        incoming = []
        for raw in supplied:
            _require(raw, ["category", "title", "status", "refs", "files"])
            category = _enum(raw["category"], MATERIAL_CATEGORIES, "material category")
            if category in seen:
                raise HubError("Each material category must occur once")
            seen.add(category)
            _text(raw["title"], "material title")
            _enum(raw["status"], {"new", "referenced", "none"}, "material status")
            refs = _refs(raw["refs"], "material refs")
            files = _list(raw["files"], "material files")
            if raw["status"] == "none":
                _text(raw.get("note"), "reason for no new material")
                if refs or files:
                    raise HubError("A none category cannot claim supplied files or refs")
            elif raw["status"] == "referenced" and not refs:
                raise HubError("Referenced materials require existing refs")
            elif raw["status"] == "new" and not refs and not files:
                raise HubError("New materials require actual files or existing refs")
            item = copy.deepcopy(raw)
            if reuse:
                item["refs"] = list(dict.fromkeys(materials[category]["refs"] + refs))
            materials[category] = item
            incoming.extend((category, raw["title"]) for file in files)
        if set(materials) != MATERIAL_CATEGORIES:
            raise HubError("节点收尾须逐项说明 original/research/creative/pending/next 五类材料。", 7)
        for extra in payload.get("extra_files", []):
            incoming.append((extra["category"], extra["title"]))
        if len(incoming) != len(inputs) - 1:
            raise HubError("Saved material inputs do not match their classification", 4)
        refs = list(payload["refs"])
        if reuse:
            # The displayed note and top-level inputs are independent of the five
            # classifications. Reusing only classifications loses the actual
            # pending proposal when those categories legitimately have no files.
            refs.extend(prior.get("refs", []))
            if prior.get("note_artifact_id"):
                refs.append("artifact:" + prior["note_artifact_id"])
        if awaiting:
            # Preserve the original human checkpoint, rather than blessing its
            # old display with fingerprints recalculated at autosave time.
            refs.extend(awaiting.get("refs", []))
            refs.append("artifact:" + awaiting["checkpoint_id"])
            refs.append("artifact:" + awaiting["note_artifact_id"])
        for material in materials.values():
            refs.extend(material["refs"])
        refs = list(dict.fromkeys(refs))
        for ref in refs:
            self._object(state, ref)
        closure = self._closure(state, refs) if refs else []
        fingerprints = self._fingerprints(state)
        inputs_bound = {ref: fingerprints[ref] for ref in closure}
        checkpoint_id = _generated("pause-", operation_id)
        note_id = _generated("pause-note-", operation_id)
        changed = {"artifact:" + note_id, "artifact:" + checkpoint_id}
        self._artifact(stage, state, note_id, "checkpoint_note", "", f"checkpoints/{operation_id}/note.md",
                       inputs[0], allowed_roles=roles, depends_on=refs)
        captured_files = []
        for index, ((category, title), item) in enumerate(zip(incoming, inputs[1:])):
            suffix = Path(item["name"]).suffix
            if not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
                suffix = ".bin"
            artifact_id = _generated("pause-file-", operation_id + "-" + str(index))
            self._artifact(stage, state, artifact_id, "checkpoint_material", "",
                           f"checkpoints/{operation_id}/files/{index:03d}{suffix}", item,
                           allowed_roles=roles, category=category, title=title, original_name=item["name"],
                           depends_on=materials[category]["refs"])
            materials[category].setdefault("artifact_ids", []).append(artifact_id)
            materials[category]["status"] = "new"
            captured_files.append({"original_path": item["path"], "sha256": item["sha256"],
                                   "size": item["size"], "category": category, "artifact_id": artifact_id})
            changed.add("artifact:" + artifact_id)
        for material in materials.values():
            material.pop("files", None)
            material.setdefault("artifact_ids", [])
            if material["status"] == "none" and material["refs"]:
                material["status"] = "referenced"
        metadata = payload.get("metadata", {})
        telemetry = payload.get("telemetry", {"status": "unknown"})
        if not isinstance(metadata, dict) or not isinstance(telemetry, dict):
            raise HubError("metadata and telemetry must be JSON objects")
        record = {"checkpoint_version": 1, "checkpoint_id": checkpoint_id, "operation_id": operation_id,
            "saved_revision": state["revision"], "discussion_round": state.get("discussion_round"),
            "node": node, "pending_questions": pending, "next_action": next_action,
            "authorized_scope": payload["authorized_scope"], "refs": refs,
            "input_fingerprints": inputs_bound, "materials": [materials[key] for key in sorted(materials)],
            "captured_files": captured_files,
            "note_artifact_id": note_id, "metadata": metadata, "telemetry": telemetry,
            "awaiting_checkpoint_id": checkpoint_id if node != "context_save" else state.get("pending_checkpoint_id"),
            "saved_at": _now()}
        body = _canonical(record)
        file_refs = ["artifact:" + ident for material in materials.values() for ident in material["artifact_ids"]]
        self._artifact(stage, state, checkpoint_id, "human_checkpoint", "", f"checkpoints/{operation_id}/checkpoint.json",
                       {"data": body, "sha256": _hash(body), "size": len(body)}, allowed_roles=roles,
                       depends_on=list(dict.fromkeys(refs + file_refs + ["artifact:" + note_id])),
                       checkpoint_node=node, discussion_round=state.get("discussion_round"))
        state["pause_checkpoint"] = record
        if node != "context_save":
            state["pending_checkpoint_id"] = checkpoint_id
        return changed

    def _apply_reopen(self, project: Path, stage: Path, state: dict, payload: dict,
                      inputs: list[dict], operation_id: str) -> set[str]:
        _text(payload["reason"], "reopen reason")
        if not payload["source_ids"]:
            raise HubError("重开须引用主创本次实际原话，先保存重开委托来源。", 7)
        for source_id in payload["source_ids"]:
            self._object(state, "source:" + source_id)
        for ref in payload["retained_refs"]:
            self._object(state, ref)
        previous_round = state.get("discussion_round")
        state.update(workflow_mode="collaborative", workflow_version=WORKFLOW_VERSION,
                     discussion_round="round-" + uuid.uuid4().hex[:12], phase="research",
                     round_started_revision=state["revision"], previous_discussion_round=previous_round,
                     retained_refs=list(payload["retained_refs"]), pending_checkpoint_id=None)
        if state.get("contract"):
            state["contract"]["stale"] = True
            state["contract"]["stale_reasons"] = ["本轮重开后须核对委托与继承范围"]
        if state.get("handoff"):
            state["handoff"]["stale"] = True
            state["handoff"]["stale_reasons"] = ["旧交接保留为历史，本轮须重新委托接笔"]
        old_gates = set()
        for decision_id, decision in state["decisions"].items():
            value = decision.get("value")
            if isinstance(value, dict) and value.get("gate") in HUMAN_GATES:
                old_gates.add(decision_id)
                decision["stale"] = True
                decision["stale_reasons"] = ["旧轮人工答复保留为历史，本轮须核对其适用范围"]
        for ident, module in state["modules"].items():
            for declaration in (module, module.get("contract_spec", {})):
                declaration["decision_ids"] = [item for item in declaration.get("decision_ids", []) if item not in old_gates]
                declaration["depends_on"] = [ref for ref in declaration.get("depends_on", [])
                                             if not (ref.startswith("decision:") and ref.split(":", 1)[1] in old_gates)]
            if "module:" + ident not in payload["retained_refs"]:
                module["stale"] = True
                module["stale_reasons"] = ["本轮重开后须核对原稿与继承范围"]
                if module.get("body_artifact_id"):
                    module["content_status"] = "needs_review"
        artifact_id = _generated("reopen-", operation_id)
        self._artifact(stage, state, artifact_id, "discussion_reopen", "", f"changes/reopen-{operation_id}.md",
                       inputs[0], allowed_roles=["master"],
                       depends_on=["source:" + source_id for source_id in payload["source_ids"]])
        return {"artifact:" + artifact_id}

    def _apply_contract(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str) -> set[str]:
        for field in ("author_role", "recipient_role", "document_use"):
            _text(payload[field], field)
        _nonempty(payload["requirements"], "requirements")
        old_contract = state.get("contract")
        old_modules = state["modules"]
        updated, changed = {}, set()
        specs = _list(payload["modules"], "modules")
        for spec in specs:
            if not isinstance(spec, dict):
                raise HubError("Module contract entries must be objects")
            _require(spec, ["module_id", "applicability", "purpose", "author_role", "recipient_role", "delivery_depth", "depends_on", "source_ids", "decision_ids", "acceptance", "unresolved"])
            ident = _id(spec["module_id"], "module ID")
            if ident in updated:
                raise HubError(f"Duplicate module contract: {ident}")
            _enum(spec["applicability"], APPLICABILITY, "applicability")
            if "audience" in spec:
                _enum(spec["audience"], {"client", "internal"}, "module audience")
            for field in ("purpose", "author_role", "recipient_role", "delivery_depth"):
                _text(spec[field], field)
            _nonempty(spec["acceptance"], "acceptance")
            self._unresolved(spec["unresolved"])
            spec = copy.deepcopy(spec)
            spec["depends_on"] = _refs(spec["depends_on"], "depends_on")
            for field in ("source_ids", "decision_ids", "fact_ids"):
                for value in _list(spec.get(field, []), field):
                    _id(value, field)
            _enum(spec.get("content_status", "outline"), CONTENT_STATUS, "content_status")
            prior = old_modules.get(ident)
            module = dict(spec)
            module.update({"artifact_ids": prior["artifact_ids"] if prior else [],
                           "content_status": prior["content_status"] if prior else "outline",
                           "stale": prior.get("stale", False) if prior else False,
                           "stale_reasons": prior.get("stale_reasons", []) if prior else [],
                           "contract_spec": dict(spec)})
            if prior:
                if "allowed_roles" in prior and "allowed_roles" not in module:
                    module["allowed_roles"] = prior["allowed_roles"]
                for key in ("body_artifact_id", "acceptance_evidence", "changes", "impact", "updated_revision", "units", "unit_ids"):
                    if key in prior:
                        module[key] = prior[key]
                for field in ("source_ids", "decision_ids", "fact_ids", "depends_on"):
                    module[field] = list(dict.fromkeys(module.get(field, []) + prior.get(field, [])))
                if prior.get("contract_spec") == spec:
                    module["unresolved"] = prior.get("unresolved", [])
                if prior.get("contract_spec") != spec:
                    changed.add(f"module:{ident}")
            updated[ident] = module
        omitted = set(old_modules) - set(updated)
        if omitted:
            raise HubError("Existing modules must remain explicit (use not_needed); omission is not deletion: " + ", ".join(sorted(omitted)))
        state["modules"] = updated
        self._artifact(stage, state, "contract-current", "contract", "contract:current", "research/contract.md", inputs[0])
        new_contract = {k: v for k, v in payload.items() if k not in {"file", "modules", "project_id"}}
        new_contract.update({"module_order": [spec["module_id"] for spec in specs], "artifact_id": "contract-current",
                             "stale": False, "stale_reasons": []})
        if old_contract and "allowed_roles" in old_contract and "allowed_roles" not in new_contract:
            new_contract["allowed_roles"] = old_contract["allowed_roles"]
        state["contract"] = new_contract
        if old_contract and any(old_contract.get(k) != new_contract.get(k) for k in ("requirements", "author_role", "recipient_role", "document_use")):
            changed.update(f"module:{ident}" for ident in updated)
        return changed | {"contract:current", "artifact:contract-current"}

    def _unresolved(self, values: Any) -> list:
        result = _list(values, "unresolved")
        for item in result:
            if not isinstance(item, dict):
                raise HubError("Unresolved questions require structured impact/owner/action")
            _require(item, ["question", "impact", "blocking", "owner_role", "next_action", "finalization_boundary"])
            for field in ("question", "owner_role", "next_action", "finalization_boundary"):
                _text(item[field], field)
            item["impact"] = _refs(item["impact"], "unresolved impact")
            if not isinstance(item["blocking"], bool):
                raise HubError("blocking must be boolean")
        return result

    @staticmethod
    def _require_human_workflow(state: dict) -> None:
        if state.get("workflow_mode") != "collaborative" or state.get("workflow_version") != WORKFLOW_VERSION:
            raise HubError("旧项目须先用 reopen 建立本轮协作委托；旧生产状态不能放行新的章节或客户交付。", 7)

    @staticmethod
    def _confirmed_gate(state: dict, ids: list[str], gate: str, field: str, expected: str) -> str:
        matches = []
        for ident in ids:
            decision = state["decisions"].get(ident) or {}
            value = decision.get("value")
            if (decision.get("status") == "confirmed" and not decision.get("stale") and isinstance(value, dict)
                    and value.get("gate") == gate and value.get(field) == expected
                    and (state.get("workflow_version") != WORKFLOW_VERSION
                         or value.get("round_id") == state.get("discussion_round"))):
                matches.append(ident)
        if len(matches) != 1:
            raise HubError(f"请引用与当前内容一致的一条有效人工决定（gate={gate}）。", 7)
        return matches[0]

    def _brief_gate(self, state: dict, ids: list[str]) -> str:
        contract = state.get("contract") or {}
        scope = contract.get("brief_scope")
        if not isinstance(scope, str) or not scope.strip() or contract.get("stale"):
            raise HubError("请在当前契约 brief_scope 中记录对象、首要目标、主路径和本轮用途。", 7)
        return self._confirmed_gate(state, ids, "brief", "scope", scope)

    def _direction_gates(self, state: dict, handoff: dict | None) -> tuple[str, str]:
        self._require_human_workflow(state)
        if not handoff or handoff.get("stale") or handoff["sufficiency"] == "blocked":
            raise HubError("需要当前有效且具备生产条件的方针交接；请先审阅研究材料和方向选择。", 7)
        brief = self._brief_gate(state, handoff["decision_ids"])
        direction = self._confirmed_gate(state, handoff["decision_ids"], "direction", "policy", handoff["policy"])
        if brief not in state["decisions"][direction]["decision_ids"]:
            raise HubError("方针决定须引用同一份已确认的委托。", 7)
        self._research_gate(state, state["decisions"][direction]["decision_ids"])
        return brief, direction

    def _research_gate(self, state: dict, ids: list[str]) -> str:
        matches = []
        for ident in ids:
            decision = state["decisions"].get(ident) or {}
            value = decision.get("value")
            if (isinstance(value, dict) and value.get("gate") == "research"
                    and decision.get("status") == "confirmed" and not decision.get("stale")
                    and value.get("round_id") == state.get("discussion_round")):
                matches.append(ident)
        if len(matches) != 1:
            raise HubError("先向主创回交研究发现，并记录本轮采用、继续查或调整重点的明确答复。", 7)
        value = state["decisions"][matches[0]]["value"]
        return self._confirmed_gate(state, ids, "research", "selection", value.get("selection"))

    def _writing_gate(self, state: dict, ids: list[str], module_id: str | None = None) -> str:
        self._require_human_workflow(state)
        brief, direction = self._direction_gates(state, state.get("handoff"))
        matches = []
        for ident in ids:
            decision = state["decisions"].get(ident) or {}
            value = decision.get("value")
            if (decision.get("status") != "confirmed" or decision.get("stale")
                    or not isinstance(value, dict) or value.get("gate") != "writing"
                    or value.get("round_id") != state["discussion_round"]):
                continue
            if module_id is not None and module_id not in value.get("modules", []):
                continue
            if any(item not in state["modules"] for item in value.get("modules", [])):
                continue
            if {brief, direction}.issubset(decision.get("decision_ids", [])):
                matches.append(ident)
        if not matches or (module_id is not None and len(matches) != 1):
            raise HubError("选中创意后仍须明确接笔委托，请引用本轮有效的章节范围、读者用途和审阅节奏。", 7)
        return matches[0]

    def _chapter_permission(self, state: dict, ids: list[str], module_id: str) -> list[str]:
        writing = self._writing_gate(state, ids, module_id)
        value = state["decisions"][writing]["value"]
        permission = [writing]
        if value["mode"] == "chapter":
            position = value["modules"].index(module_id)
            for previous_id in value["modules"][:position]:
                previous = state["modules"][previous_id]
                body_id = previous.get("body_artifact_id")
                body = state["artifacts"].get(body_id, {})
                if not body_id or previous.get("stale"):
                    raise HubError(f"先交 {previous_id} 的当前正文给人审阅，再继续下一章。", 7)
                reviews = []
                for ident, decision in state["decisions"].items():
                    reviewed = decision.get("value")
                    if (decision.get("status") == "confirmed" and not decision.get("stale")
                            and isinstance(reviewed, dict) and reviewed.get("gate") == "chapter_review"
                            and reviewed.get("round_id") == state["discussion_round"]
                            and reviewed.get("module_id") == previous_id
                            and reviewed.get("body_sha256") == body.get("sha256")
                            and writing in decision.get("decision_ids", [])):
                        reviews.append((decision["updated_revision"], ident, reviewed["outcome"]))
                latest = max(reviews) if reviews else None
                if latest is None or latest[2] != "continue":
                    raise HubError(f"{previous_id} 已交稿，须取得对应版本的章节反馈后再写下一章。", 7)
                permission.append(latest[1])
        return permission

    def _verify_chapter_review(self, state: dict, payload: dict, chain: list[dict]) -> str:
        value = payload["new_value"]
        _require(value, ["module_id", "review_revision", "body_sha256", "outcome"])
        module_id = _id(value["module_id"], "reviewed module")
        _enum(value["outcome"], {"continue", "revise"}, "chapter review outcome")
        writing = self._writing_gate(state, payload["decision_ids"], module_id)
        ancestor = next((item for item in chain if item["revision"] == value["review_revision"]), None)
        if ancestor is None or ancestor["state"].get("discussion_round") != state["discussion_round"]:
            raise HubError("章节反馈须指向本轮实际展示的已提交版本。", 7)
        shown = ancestor["state"]["modules"].get(module_id, {})
        shown_body = ancestor["state"]["artifacts"].get(shown.get("body_artifact_id"), {})
        current = state["modules"].get(module_id, {})
        current_body = state["artifacts"].get(current.get("body_artifact_id"), {})
        if (not shown_body or shown_body.get("sha256") != value["body_sha256"]
                or current_body.get("sha256") != value["body_sha256"] or current.get("stale")):
            raise HubError("章审须绑定所读正文的 SHA256，并核对当前正文和条件；请先交修订稿。", 7)
        payload["depends_on"] = list(dict.fromkeys(payload.get("depends_on", []) + ["module:" + module_id]))
        return writing

    def _require_checkpoint(self, stage: Path, state: dict, payload: dict, node: str) -> None:
        checkpoint_id = payload.get("checkpoint_id")
        artifact = state["artifacts"].get(checkpoint_id) if isinstance(checkpoint_id, str) else None
        if not artifact or artifact.get("kind") != "human_checkpoint":
            raise HubError("先用 pause 保存本节点实际展示材料和待确认事项，再登记人的答复。", 7)
        if artifact.get("storage") != "snapshot" or artifact.get("stale"):
            raise HubError("节点沉淀已失效，请回交当前材料并重新保存节点。", 7)
        path = self._write_path(stage / artifact["path"])
        raw = path.read_bytes()
        if _hash(raw) != artifact["sha256"]:
            raise HubError("Published checkpoint bytes do not match their record", 4)
        checkpoint = _json_loads(raw)
        if (checkpoint.get("checkpoint_id") != checkpoint_id or checkpoint.get("node") != node
                or checkpoint.get("discussion_round") != state.get("discussion_round")
                or checkpoint.get("saved_revision") != artifact.get("created_revision")):
            raise HubError("人工答复须引用同轮、同节点已发布的展示材料。", 7)
        current = self._fingerprints(state)
        if any(current.get(ref) != fingerprint for ref, fingerprint in checkpoint["input_fingerprints"].items()):
            raise HubError("节点展示材料已经变化，请先交当前版本，再保存并核对实际答复。", 7)
        value = payload["new_value"]
        required = set()
        if node == "brief":
            required.add("contract:current")
        if isinstance(value, dict):
            if node == "research":
                required.update(value.get("material_refs", []))
            elif node == "writing":
                required.add("handoff:current")
                required.update("module:" + ident for ident in value.get("modules", []))
            elif node == "chapter_review":
                required.add("module:" + value["module_id"])
            elif node == "delivery":
                required.update("module:" + ident for ident in value.get("accepted_modules", []))
                required.update("module:" + section["module_id"] for section in value.get("accepted_sections", []))
        if not required.issubset(checkpoint["input_fingerprints"]):
            raise HubError("节点沉淀没有覆盖本次答复采用的实际材料和章节范围。", 7)
        if state.get("pending_checkpoint_id") == checkpoint_id:
            state["pending_checkpoint_id"] = None

    def _refresh_phase(self, state: dict) -> None:
        if state.get("workflow_version") == WORKFLOW_VERSION:
            try:
                self._writing_gate(state, list(state["decisions"]))
            except HubError:
                state["phase"] = "research"
            else:
                state["phase"] = "production"

    def _next_discussion(self, state: dict) -> str:
        if state.get("workflow_version") != WORKFLOW_VERSION:
            return "先回交旧案的资料与决定继承范围，用 reopen 建立本轮协作，再确认本轮委托。"
        if state["phase"] == "production":
            commissions = sorted(state["decisions"].items(), key=lambda item: item[1].get("updated_revision", ""), reverse=True)
            for writing_id, commission in commissions:
                value = commission.get("value")
                if not isinstance(value, dict) or value.get("gate") != "writing":
                    continue
                try:
                    self._writing_gate(state, [writing_id])
                except HubError:
                    continue
                for module_id in value["modules"]:
                    module = state["modules"][module_id]
                    body = state["artifacts"].get(module.get("body_artifact_id"), {})
                    if not body or module.get("stale"):
                        return f"按本轮委托写或修订 {module_id} 的实际正文；交稿后按约定逐章或整组回交。"
                    if value["mode"] == "chapter":
                        feedback = [record for record in state["decisions"].values()
                                    if record.get("status") == "confirmed" and not record.get("stale")
                                    and isinstance(record.get("value"), dict) and record["value"].get("gate") == "chapter_review"
                                    and record["value"].get("round_id") == state["discussion_round"]
                                    and record["value"].get("module_id") == module_id
                                    and record["value"].get("body_sha256") == body.get("sha256")
                                    and writing_id in record.get("decision_ids", [])]
                        latest = max(feedback, key=lambda item: item["updated_revision"]) if feedback else None
                        if latest is None:
                            return f"交出 {module_id} 的当前实际正文，等待主创反馈后再推进下一章；可核已委托的共用材料。"
                        if latest["value"]["outcome"] == "revise":
                            return f"按已收到的具体反馈修改 {module_id}，再回交本章；下一章仍等待本章续写决定。"
                return "本次委托的章节已写齐，回读实际审阅和采纳记录；尚未审阅的正文回交接收者，已采纳部分按约定接续。"
            return "按本轮接笔范围写当前章并交实际正文；逐章模式等待该章反馈，明确批量授权才连写该组。"
        try:
            self._brief_gate(state, list(state["decisions"]))
        except HubError:
            return "先给委托人看委托与分流简报，核对眼前的决定、目标、本轮用途及范围，沿用已明确的事项。"
        try:
            self._research_gate(state, list(state["decisions"]))
        except HubError:
            return "回交研究发现、原件细节和反例，问主创采用、继续查或改变哪一重点，等本轮答复。"
        directions = [decision for decision in state["decisions"].values()
                      if decision.get("status") == "confirmed" and not decision.get("stale")
                      and isinstance(decision.get("value"), dict) and decision["value"].get("gate") == "direction"
                      and decision["value"].get("round_id") == state["discussion_round"]]
        if not directions:
            return "把创意原型、差异和代价交主创取舍；保存选中、保留和暂缓的原话，尚未选择时继续共同研究。"
        try:
            self._direction_gates(state, state.get("handoff"))
        except HubError:
            return "按已选方向整理原稿、依据、编辑范围与章节安排，保存本轮交接；已有明确取舍直接沿用。"
        return "回交主创底稿和章节安排，请明确接笔章节、读者用途与逐章或批量审阅范围，再进入第二阶段。"

    def _apply_handoff(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str) -> set[str]:
        if not state.get("contract"):
            raise HubError("Handoff needs current demand contract", 7)
        _text(payload["policy"], "policy")
        _enum(payload["sufficiency"], {"ready", "conditional", "blocked"}, "research sufficiency")
        unresolved = self._unresolved(payload["unresolved"])
        if payload["sufficiency"] != "ready" and not unresolved:
            raise HubError("Conditional/blocked handoff must declare unresolved impact", 7)
        if set(payload["inventory_source_ids"]) != set(state["sources"]):
            raise HubError("Handoff inventory must identify all current sources; this does not certify reading", 7)
        self._direction_gates(state, payload)
        prior_handoff = state.get("handoff")
        self._artifact(stage, state, "handoff-current", "handoff", "handoff:current", "research/handoff.md", inputs[0])
        state["handoff"] = {k: v for k, v in payload.items() if k not in {"file", "project_id"}}
        if prior_handoff and "allowed_roles" in prior_handoff and "allowed_roles" not in state["handoff"]:
            state["handoff"]["allowed_roles"] = prior_handoff["allowed_roles"]
        state["handoff"].update({"artifact_id": "handoff-current", "stale": False, "stale_reasons": [], "updated_revision": state["revision"]})
        return {"handoff:current", "artifact:handoff-current"}

    def _apply_module(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str) -> set[str]:
        ident = _id(payload["module_id"], "module ID")
        if ident not in state["modules"]:
            raise HubError("Module must derive from current contract", 7)
        module = state["modules"][ident]
        if module["applicability"] not in {"now", "later"}:
            raise HubError("Module applicability does not authorize body production", 7)
        if not state.get("handoff"):
            raise HubError("Module production needs actual phase-one handoff", 7)
        gates = list(self._direction_gates(state, state["handoff"]))
        gates += self._chapter_permission(state, payload["decision_ids"], ident)
        if any("decision:" + gate in payload.get("remove_dependencies", []) for gate in gates):
            raise HubError("正式正文必须保留本轮人工决定和接笔委托。", 7)
        ordinary_decisions = [item for item in module["decision_ids"]
                              if not (isinstance(state["decisions"].get(item, {}).get("value"), dict)
                                      and state["decisions"][item]["value"].get("gate") in HUMAN_GATES)]
        module["decision_ids"] = list(dict.fromkeys(ordinary_decisions + gates))
        _enum(payload["content_status"], CONTENT_STATUS, "body maturity")
        if payload["content_status"] in {"outline", "archived"}:
            raise HubError("Body submission requires draft/reviewable/needs_review/blocked maturity")
        _nonempty(payload["changes"], "changes")
        _nonempty(payload["acceptance_evidence"], "acceptance_evidence")
        removals = set(payload.get("remove_dependencies", []))
        if removals:
            contract_spec = module["contract_spec"]
            contract_required = set(contract_spec.get("depends_on", []))
            for field, ref_kind in (("source_ids", "source"), ("decision_ids", "decision"), ("fact_ids", "fact")):
                contract_required.update(ref_kind + ":" + value for value in contract_spec.get(field, []))
                added = {ref_kind + ":" + value for value in payload.get(field, [])}
                if removals.intersection(added):
                    raise HubError("Candidate cannot both adopt and remove the same dependency")
                module[field] = [value for value in module.get(field, []) if ref_kind + ":" + value not in removals]
            if removals.intersection(contract_required) or removals.intersection(payload.get("depends_on", [])):
                raise HubError("Current contractual or newly adopted dependency cannot be removed")
            module["depends_on"] = [ref for ref in module.get("depends_on", []) if ref not in removals]
        for field in ("source_ids", "decision_ids", "fact_ids", "depends_on"):
            if field in payload:
                module[field] = list(dict.fromkeys(module.get(field, []) + payload[field]))
        self._validate_state(state, project.name, state["revision"])
        if payload["content_status"] == "reviewable":
            blocking = self._blocking(state, ident)
            stale = [ref for ref in self._closure(state, [f"module:{ident}"]) if ref != f"module:{ident}" and self._object(state, ref).get("stale")]
            if blocking or stale:
                raise HubError("Reviewable maturity blocked by affected unresolved/stale inputs", 7, blockers=blocking, stale_inputs=stale)
        artifact_id = _generated("module-", ident)
        self._artifact(stage, state, artifact_id, "module_body", f"module:{ident}", f"modules/{ident}/body.md", inputs[0], payload["content_status"])
        artifact_ids = [artifact_id]
        supplied_artifacts = [extra["artifact_id"] for extra in payload.get("handoff_artifacts", [])]
        if len(set(supplied_artifacts)) != len(supplied_artifacts) or artifact_id in supplied_artifacts:
            raise HubError("Duplicate handoff/body artifact ID in candidate")
        for extra, item in zip(payload.get("handoff_artifacts", []), inputs[1:]):
            extra_id = extra["artifact_id"]
            prior = state["artifacts"].get(extra_id)
            if prior and prior.get("owner") != f"module:{ident}":
                raise HubError("Handoff artifact ID belongs to another object")
            self._artifact(stage, state, extra_id, "handoff_workpiece", f"module:{ident}",
                           f"modules/{ident}/handoff/{extra_id}.md", item, extra["content_status"],
                           recipient_role=extra["recipient_role"], purpose=extra["purpose"],
                           **({"allowed_roles": extra["allowed_roles"]} if "allowed_roles" in extra else {}))
            artifact_ids.append(extra_id)
        supplied_units = set()
        for unit in _list(payload.get("units", []), "units"):
            if not isinstance(unit, dict):
                raise HubError("Content unit must be an object")
            _require(unit, ["unit_id", "title", "artifact_id"])
            unit_id = _id(unit["unit_id"])
            if unit_id in supplied_units or (unit_id in state["content_units"] and state["content_units"][unit_id]["module_id"] != ident):
                raise HubError("Duplicate or cross-module content unit ID")
            supplied_units.add(unit_id)
            _text(unit["title"], "unit title")
            if unit["artifact_id"] not in artifact_ids:
                raise HubError("Content unit must reference this module's real artifact")
            state["content_units"][unit_id] = {**unit, "module_id": ident,
                "value": {"title": unit["title"], "module_id": ident, "artifact_id": unit["artifact_id"]},
                "status": "draft", "stale": False, "stale_reasons": [], "updated_revision": state["revision"]}
        if "unresolved" in payload:
            module["unresolved"] = self._unresolved(payload["unresolved"])
        if "allowed_roles" in payload:
            module["allowed_roles"] = payload["allowed_roles"]
        module.update({"artifact_ids": artifact_ids, "body_artifact_id": artifact_id,
                       "content_status": payload["content_status"], "acceptance_evidence": payload["acceptance_evidence"],
                       "changes": payload["changes"], "impact": payload["impact"], "stale": False,
                       "stale_reasons": [], "updated_revision": state["revision"]})
        if "units" in payload:
            module["units"] = copy.deepcopy(payload["units"])
            module["unit_ids"] = [unit["unit_id"] for unit in payload["units"]]
        return {f"module:{ident}"} | {f"artifact:{a}" for a in artifact_ids}

    def _validate_cost(self, state: dict, value: Any, payload: dict) -> dict:
        if not isinstance(value, dict):
            raise HubError("Cost value must preserve explicit quantity/unit/unit_price/amount/currency/tax/source/status/basis")
        _require(value, ["quantity", "unit", "unit_price", "amount", "currency", "tax_basis", "source", "status", "shared_or_incremental"])
        def number(field):
            raw = value[field]
            if raw is None:
                return None
            if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
                raise HubError(f"Cost {field} must be a finite number or null (unknown)")
            try:
                parsed = Decimal(str(raw))
            except InvalidOperation as exc:
                raise HubError(f"Invalid cost numeric field: {field}") from exc
            if not parsed.is_finite() or parsed < 0:
                raise HubError(f"Cost {field} must be finite and nonnegative")
            return parsed
        quantity, price, amount = (number(field) for field in ("quantity", "unit_price", "amount"))
        try:
            if quantity is not None and price is not None and amount is not None and abs(quantity * price - amount) > Decimal("0.01"):
                raise HubError("Cost quantity × unit_price differs from amount (tolerance 0.01)")
        except DecimalException as exc:
            raise HubError("Cost numbers exceed supported decimal arithmetic") from exc
        for field in ("unit", "currency", "tax_basis"):
            if value[field] is not None:
                _text(value[field], "cost." + field)
        _text(value["status"], "cost.status")
        sources = value["source"]
        sources = [sources] if isinstance(sources, str) else _list(sources, "cost.source")
        if not sources:
            raise HubError("Cost must declare actual estimate/quote/source IDs")
        for source in sources:
            _id(source, "cost source ID")
            self._object(state, "source:" + source)
            if source not in payload["source_ids"]:
                raise HubError("Cost source must also be registered in source_ids")
        basis = value["shared_or_incremental"]
        _enum(basis, {"shared", "incremental", "allocation", "unknown"}, "cost basis")
        if basis == "allocation":
            master_id = _id(value.get("master_cost_id"), "master cost ID")
            if master_id == payload["id"]:
                raise HubError("Cost allocation cannot reference itself")
            master_record = self._object(state, "cost:" + master_id)
            if master_record.get("stale"):
                raise HubError("Allocation requires a current master cost; reconcile the master first", 7)
            master = master_record["value"]
            if master.get("shared_or_incremental") != "shared":
                raise HubError("Allocation must refer to one existing shared master cost")
            if value["currency"] != master["currency"] or value["tax_basis"] != master["tax_basis"]:
                raise HubError("Allocation currency/tax basis differs from master cost")
            if amount is not None and master["amount"] is not None and amount > Decimal(str(master["amount"])):
                raise HubError("Allocated amount exceeds master cost")
            existing_amounts = [record["value"]["amount"] for ident, record in state["costs"].items()
                if ident != payload["id"] and record["value"].get("shared_or_incremental") == "allocation"
                and record["value"].get("master_cost_id") == master_id and not record.get("stale")]
            if master["amount"] is not None:
                try:
                    known_total = sum((Decimal(str(existing)) for existing in existing_amounts if existing is not None), amount if amount is not None else Decimal(0))
                    if known_total > Decimal(str(master["amount"])):
                        raise HubError("Combined allocations exceed one shared master expense")
                except DecimalException as exc:
                    raise HubError("Allocation amounts exceed supported decimal arithmetic") from exc
        return value

    def cost_audit(self, project: str | Path) -> dict:
        project_path = self._project(project)
        head, chain = self._chain(project_path)
        state = chain[0]["state"]
        totals, unknown, allocations, known_allocated = {}, [], [], {}
        for record in state["costs"].values():
            value = record["value"]
            if value["shared_or_incremental"] == "allocation" and not record.get("stale") and value["amount"] is not None:
                master_id = value["master_cost_id"]
                known_allocated[master_id] = known_allocated.get(master_id, Decimal(0)) + Decimal(str(value["amount"]))
        for ident, record in state["costs"].items():
            value = record["value"]
            if value["shared_or_incremental"] == "allocation":
                master_record = state["costs"].get(value["master_cost_id"])
                master = master_record.get("value", {}) if master_record else {}
                issues = []
                stale = bool(record.get("stale") or (master_record and master_record.get("stale")))
                if record.get("stale"):
                    issues.append("allocation_stale")
                if master_record and master_record.get("stale"):
                    issues.append("master_stale")
                if not master_record:
                    issues.append("master_missing")
                elif master.get("shared_or_incremental") != "shared":
                    issues.append("master_not_shared")
                for field in ("currency", "tax_basis"):
                    if master_record and value[field] != master.get(field):
                        issues.append(field + "_mismatch")
                    if value[field] is None or master.get(field) is None:
                        issues.append(field + "_unknown")
                if value["amount"] is None:
                    issues.append("amount_unknown")
                if master.get("amount") is None:
                    issues.append("master_amount_unknown")
                elif known_allocated.get(value["master_cost_id"], Decimal(0)) > Decimal(str(master["amount"])):
                    issues.append("known_allocations_exceed_master")
                invalid = any(issue in {"master_missing", "master_not_shared", "currency_mismatch", "tax_basis_mismatch", "known_allocations_exceed_master"} for issue in issues)
                status = "stale" if stale else "invalid" if invalid else "unknown" if issues else "current"
                if status != "current":
                    unknown.append(ident)
                allocations.append({"cost_id": ident, "master_cost_id": value["master_cost_id"],
                    "amount": value["amount"], "added_to_total": False, "stale": stale,
                    "validation_status": status, "issues": issues})
                continue
            if value["amount"] is None or value["currency"] is None or value["tax_basis"] is None or value["shared_or_incremental"] == "unknown" or record.get("stale"):
                unknown.append(ident)
                continue
            key = (value["currency"], value["tax_basis"])
            totals[key] = totals.get(key, Decimal(0)) + Decimal(str(value["amount"]))
        return _response(project_id=project_path.name, current_revision=head["revision"],
            totals=[{"currency": currency, "tax_basis": tax, "amount": str(amount)} for (currency, tax), amount in sorted(totals.items())],
            unknown_cost_ids=unknown, allocations=allocations,
            warnings=["Different currencies/tax bases kept separate; null remains unknown; allocations do not add master expense; stale allocations await reconciliation; sources are submitter declarations"])

    def _apply_change(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str,
                      chain: list[dict]) -> set[str]:
        replaced_reviews = set()
        kind = payload["entity"]
        _enum(kind, {"fact", "decision", "resource", "cost", "question", "event", "unit", "session"}, "change entity")
        ident = _id(payload["id"])
        _text(payload["reason"], "reason")
        if payload["new_value"] is None:
            raise HubError("new_value must be explicit non-null JSON value")
        previous = state[COLLECTIONS[kind]].get(ident)
        if payload["old_value"] != (previous.get("value") if previous else None):
            raise HubError("old_value does not match current authoritative value", 3)
        if kind in {"fact", "decision"} and not payload["source_ids"] and not payload["decision_ids"]:
            raise HubError("Fact/decision requires explicit evidence or decision source")
        status_default = {"fact": "asserted", "decision": "proposed", "resource": "unknown", "cost": "estimate", "question": "open", "event": "recorded", "unit": "draft", "session": "planned"}
        status_value = payload.get("status", status_default[kind])
        _text(status_value, "status")
        if kind == "fact" and status_value not in {"asserted", "verified", "unknown", "needs_review"}:
            raise HubError("Invalid fact evidence state")
        if kind == "decision" and status_value not in {"proposed", "confirmed", "rejected", "superseded", "needs_review"}:
            raise HubError("Invalid decision state")
        if kind == "decision" and status_value == "confirmed":
            confirmation = payload.get("confirmation")
            if not isinstance(confirmation, dict):
                raise HubError("Confirmed decision needs actual actor/time/evidence record")
            _require(confirmation, ["actor", "at", "evidence"])
            for field in ("actor", "at", "evidence"):
                _text(confirmation[field], "confirmation." + field)
            value = payload["new_value"]
            if isinstance(value, dict) and value.get("gate") in HUMAN_GATES:
                gate = value.get("gate")
                self._require_human_workflow(state)
                if value.get("round_id") != state["discussion_round"]:
                    raise HubError("人工答复须绑定当前 discussion_round；旧轮批准不能放行本轮工作。", 7)
                if not payload["source_ids"]:
                    raise HubError("已确认的审核决定须用 source_ids 引用本次实际回复或委托原话。", 7)
                if gate in ("brief", "research", "direction"):
                    _text(value.get({"brief": "scope", "research": "selection", "direction": "policy"}[gate]), gate)
                    if gate == "brief":
                        contract = state.get("contract") or {}
                        if contract.get("stale") or contract.get("brief_scope") != value["scope"]:
                            raise HubError("先保存并核对当前委托简报，A 的 scope 要与有效契约 brief_scope 一致。", 7)
                    for other_id, other in state["decisions"].items():
                        other_value = other.get("value")
                        if (other_id != ident and other["status"] == "confirmed" and not other.get("stale")
                                and isinstance(other_value, dict) and other_value.get("gate") == gate
                                and other_value.get("round_id") == state["discussion_round"]):
                            raise HubError(f"已有有效 {gate} 决定。请更新原决定，或先记录作废再换用新决定。", 7)
                    if gate in ("research", "direction"):
                        self._brief_gate(state, payload["decision_ids"])
                    if gate == "research":
                        materials = _refs(value.get("material_refs"), "research material_refs")
                        if not materials:
                            raise HubError("研究回交须指向实际给主创看的原件、发现稿或原型。", 7)
                        for ref in materials:
                            self._object(state, ref)
                        payload["depends_on"] = list(dict.fromkeys(payload.get("depends_on", []) + materials))
                    if gate == "direction":
                        self._research_gate(state, payload["decision_ids"])
                if gate == "writing":
                    brief, direction = self._direction_gates(state, state.get("handoff"))
                    if not {brief, direction}.issubset(payload["decision_ids"]):
                        raise HubError("接笔委托须引用本轮委托和选定方向。", 7)
                    modules = _list(value.get("modules"), "writing modules")
                    for module_id in modules:
                        self._object(state, "module:" + _id(module_id))
                    if not modules or len(set(modules)) != len(modules):
                        raise HubError("接笔范围须为非空且不重复的有序章节列表。", 7)
                    _enum(value.get("mode"), {"chapter", "batch"}, "writing mode")
                    _text(value.get("document_use"), "writing document_use")
                if gate == "chapter_review":
                    writing = self._verify_chapter_review(state, payload, chain)
                    for other_id, other in state["decisions"].items():
                        other_value = other.get("value")
                        if (other_id != ident and other.get("status") == "confirmed"
                                and isinstance(other_value, dict) and other_value.get("gate") == "chapter_review"
                                and other_value.get("round_id") == state["discussion_round"]
                                and other_value.get("module_id") == value["module_id"]
                                and writing in other.get("decision_ids", [])):
                            other["status"] = "superseded"
                            replaced_reviews.add("decision:" + other_id)
                if gate == "delivery":
                    self._verify_delivery_decision(project, state, payload, chain)
            node = value.get("gate") if isinstance(value, dict) else None
            self._require_checkpoint(stage, state, payload, node if node in HUMAN_GATES else "change")
        if "dynamic" in payload and not isinstance(payload["dynamic"], bool):
            raise HubError("dynamic must be boolean")
        if kind == "cost":
            self._validate_cost(state, payload["new_value"], payload)
            status_value = payload.get("status", payload["new_value"]["status"])
        if kind == "unit":
            value = payload["new_value"]
            if not isinstance(value, dict):
                raise HubError("Unit value must identify actual title/module/artifact")
            _require(value, ["title", "module_id", "artifact_id"])
            _text(value["title"], "unit title")
            self._object(state, "module:" + _id(value["module_id"]))
            artifact = self._object(state, "artifact:" + _id(value["artifact_id"]))
            if artifact.get("owner") != "module:" + value["module_id"]:
                raise HubError("Unit artifact belongs to a different module")
        if kind == "session":
            value = payload["new_value"]
            if not isinstance(value, dict):
                raise HubError("Session value must preserve unit/date/time/resource/cost relationships")
            _require(value, ["title", "unit_ids", "date", "time", "resource_ids", "cost_ids"])
            _text(value["title"], "session title")
            for field in ("date", "time"):
                if value[field] is not None:
                    _text(value[field], "session." + field)
            for field, entity in (("unit_ids", "unit"), ("resource_ids", "resource"), ("cost_ids", "cost")):
                for ref_id in _list(value[field], "session." + field):
                    self._object(state, entity + ":" + _id(ref_id))
        artifact_id = _generated("change-", operation_id)
        self._artifact(stage, state, artifact_id, "change_record", f"{kind}:{ident}", f"changes/{operation_id}.md", inputs[0])
        obj = {k: v for k, v in payload.items() if k not in {"file", "project_id", "old_value", "new_value", "entity", "id"}}
        if previous and "allowed_roles" in previous and "allowed_roles" not in obj:
            obj["allowed_roles"] = previous["allowed_roles"]
        obj.update({"id": ident, "value": payload["new_value"], "status": status_value,
                    "artifact_id": artifact_id, "updated_revision": state["revision"], "stale": False, "stale_reasons": []})
        if kind == "question" and isinstance(payload["new_value"], dict):
            obj.update(self._unresolved([payload["new_value"]])[0])
        if kind == "event":
            # Append-only history is retained even when the event's current detail
            # is corrected; rollback never erases real-world occurrences.
            obj["history"] = (previous.get("history", []) if previous else []) + [{"value": payload["new_value"], "status": status_value, "at": _now(), "revision": state["revision"], "artifact_id": artifact_id}]
        state[COLLECTIONS[kind]][ident] = obj
        return {f"{kind}:{ident}", f"artifact:{artifact_id}"} | replaced_reviews

    def _apply_review(self, project: Path, stage: Path, state: dict, payload: dict, inputs: list[dict], operation_id: str) -> set[str]:
        ident = _id(payload["review_id"])
        for field in ("reviewer", "method"):
            _text(payload[field], field)
        _enum(payload["result"], {"pass", "fail", "unknown"}, "review result")
        if not payload["targets"]:
            raise HubError("Review requires actual targets")
        fingerprints = payload["input_fingerprints"]
        if not isinstance(fingerprints, dict):
            raise HubError("input_fingerprints must be a typed-ref hash mapping")
        closure = set(self._closure(state, payload["targets"] + ["artifact:" + ident for ident in payload["evidence"]]))
        if not closure.issubset(fingerprints):
            raise HubError("Review fingerprints omit target or required dependency")
        current = self._fingerprints(state)
        for ref, value in fingerprints.items():
            _ref(ref)
            if value != current.get(ref):
                raise HubError(f"Review input fingerprint is stale/unknown: {ref}", 3)
        for artifact_id in payload["evidence"]:
            self._object(state, f"artifact:{artifact_id}")
        artifact_id = _generated("review-", ident)
        self._artifact(stage, state, artifact_id, "review_record", f"review:{ident}", f"reviews/{ident}.md", inputs[0])
        prior_review = state["reviews"].get(ident)
        state["reviews"][ident] = {k: v for k, v in payload.items() if k not in {"file", "project_id"}}
        if prior_review and "allowed_roles" in prior_review and "allowed_roles" not in state["reviews"][ident]:
            state["reviews"][ident]["allowed_roles"] = prior_review["allowed_roles"]
        state["reviews"][ident].update({"artifact_id": artifact_id, "input_revision": state.get("parent_revision"),
                                      "input_fingerprint_version": FINGERPRINT_VERSION,
                                      "validation_status": "current", "stale": False, "stale_reasons": [],
                                      "updated_revision": state["revision"]})
        return {f"review:{ident}", f"artifact:{artifact_id}"}

    def submit(self, project: str | Path, base: str, operation_id: str, kind: str, payload: dict) -> dict:
        result = self._submit(project, base, operation_id, kind, payload)
        if kind != "pause":
            return result
        return self._complete_pause(project, operation_id, result)

    def _complete_pause(self, project: str | Path, operation_id: str, result: dict) -> dict:
        project_path = self._project(project)
        saved_revision = result.get("applied_revision", result["current_revision"])
        checkpoint_id = _generated("pause-", operation_id)
        checkpoint_path = self._write_path(project_path / "revisions" / saved_revision / "checkpoints" / operation_id / "checkpoint.json")
        result.update(committed=True, saved_revision=saved_revision, saved_checkpoint_id=checkpoint_id,
                      saved_checkpoint_path=str(checkpoint_path), recovery_ready=False,
                      recovery_context_path=None, recovery_context_json_path=None)
        try:
            record = self._read_json(checkpoint_path)
            if record.get("checkpoint_id") != checkpoint_id or record.get("saved_revision") != saved_revision:
                raise HubError("Published checkpoint identity mismatch", 4)
            result["captured_files"] = record.get("captured_files", [])
            recovery = self.resume(project, required_refs=["artifact:" + checkpoint_id])
            context = self._read_json(Path(recovery["context_json_path"]))
            if (recovery["status"] != "success" or context["revision"] != recovery["current_revision"]
                    or not Path(recovery["context_path"]).is_file()):
                raise HubError("Recovery packet could not be verified", 6)
            result.update(current_revision=recovery["current_revision"], recovery_ready=True,
                          recovery_context_path=recovery["context_path"],
                          recovery_context_json_path=recovery["context_json_path"],
                          context_path=recovery["context_path"], checkpoint_path=recovery["context_json_path"],
                          next_actions=recovery["next_actions"])
        except Exception as exc:
            result["warnings"].append(f"Checkpoint committed; recovery entry needs repair: {type(exc).__name__}: {exc}")
            result["next_actions"] = ["原件和节点修订已发布；修复接续入口并核验后再报告可靠停妥，不重复保存事务。"]
        return result

    def _submit(self, project: str | Path, base: str, operation_id: str, kind: str, payload: dict) -> dict:
        project_path = self._project(project)
        _id(base, "base revision")
        _id(operation_id, "operation ID")
        payload = self._validate_payload(kind, payload)
        if "project_id" in payload and payload["project_id"] != project_path.name:
            raise HubError("Payload belongs to a different project", 4, project_id=project_path.name)
        inputs = self._inputs(kind, payload)
        request = {"project_id": project_path.name, "base": base, "operation_id": operation_id,
                   "kind": kind, "payload": copy.deepcopy(payload), "input_fingerprints": [item["sha256"] for item in inputs]}
        request_hash = _hash(_canonical(request))
        with self._lock(project_path, operation_id):
            candidate = self._candidate(project_path, operation_id, request_hash, request, inputs)
            head, chain = self._chain(project_path)
            for entry in chain:
                if entry["operation"]["operation_id"] == operation_id:
                    if entry["operation"]["request_hash"] != request_hash:
                        raise HubError("Operation ID already committed with a different request", 3,
                                       project_id=project_path.name, current_revision=head["revision"], operation_id=operation_id,
                                       candidate_path=str(candidate), next_actions=["Read current revision, compare candidate, revise and use a new operation ID"])
                    return _response("already_applied", project_path.name, head["revision"], operation_id,
                                     applied_revision=entry["revision"], context_path=str(project_path / "项目中枢.md"),
                                     artifact_paths=[str(self._artifact_path(project_path, entry["revision"], a)) for a in entry["state"]["artifacts"].values() if a.get("created_revision") == entry["revision"]],
                                     warnings=self._view_warnings(project_path, head["revision"]),
                                     candidate_path=str(candidate))
            if base != head["revision"]:
                raise HubError("Base revision conflict; candidate retained", 3,
                               project_id=project_path.name, current_revision=head["revision"], operation_id=operation_id,
                               candidate_path=str(candidate), next_actions=["Read latest originals and compare candidate; revise content before a new operation"])
            state = copy.deepcopy(chain[0]["state"])
            state["generation"] += 1
            state["revision"] = self._new_revision(state["generation"])
            state["parent_revision"] = base
            stage = self._make_stage(project_path, state["revision"], base)
            try:
                handler = getattr(self, "_apply_" + kind)
                args = (project_path, stage, state, payload, inputs, operation_id)
                changed = handler(*args, chain) if kind == "change" else handler(*args)
                self._validate_state(state, project_path.name, state["revision"])
                affected = self._propagate(state, changed, f"{kind} operation {operation_id} changed registered inputs")
                explicit_impact = set(payload.get("impact", [])) - changed
                if explicit_impact:
                    affected = sorted(set(affected) | set(self._propagate(state, explicit_impact,
                        f"Explicit impact of {operation_id}; actual text requires recheck", include_roots=True)))
                if kind == "contract":
                    affected = sorted(set(affected) | set(self._propagate(state, {r for r in changed if r.startswith("module:")}, "Module contract changed", include_roots=True)))
                    prior_scope = (chain[0]["state"].get("contract") or {}).get("brief_scope")
                    if state.get("workflow_mode") == "collaborative" and prior_scope and prior_scope != state["contract"].get("brief_scope"):
                        prior_briefs = {f"decision:{ident}" for ident, decision in state["decisions"].items()
                                        if isinstance(decision.get("value"), dict) and decision["value"].get("gate") == "brief"
                                        and decision["value"].get("scope") == prior_scope}
                        affected = sorted(set(affected) | set(self._propagate(state, prior_briefs, "委托重点改变，须重新核对原选择", include_roots=True)))
                # New/replaced artifacts themselves are current bytes. Their
                # downstream owners have already been invalidated as appropriate.
                if kind == "module":
                    fresh_refs = changed
                elif kind in {"source", "change", "review", "handoff", "reopen", "pause"}:
                    fresh_refs = changed
                else:
                    fresh_refs = {"contract:current", "artifact:contract-current"}
                for ref in fresh_refs:
                    obj = self._object(state, ref)
                    obj["stale"] = False
                    obj["stale_reasons"] = []
                    if kind == "module" and ref.startswith(("module:", "artifact:")):
                        obj["content_status"] = payload["content_status"] if ref.startswith("module:") or obj.get("kind") == "module_body" else obj["content_status"]
                for impacted in payload.get("impact", []):
                    self._object(state, impacted)
                self._refresh_phase(state)
                delivery_changes = self._recheck_deliveries(chain[0]["state"], state)
                if delivery_changes:
                    affected = sorted(set(affected) | set(delivery_changes))
                    self._refresh_phase(state)
                state["last_change"] = {"operation_id": operation_id, "kind": kind, "changed": sorted(changed),
                                        "affected": affected, "reason": payload.get("reason", payload.get("changes")), "at": _now()}
                operation = self._operation(state, operation_id, kind, request_hash, base, affected,
                                            candidate_path=str(candidate), request=request)
                result = self._finish(project_path, stage, state, operation, chain[0], chain)
                result["candidate_path"] = str(candidate)
                return result
            except HubError as exc:
                exc.response.update(project_id=project_path.name, current_revision=head["revision"],
                                    operation_id=operation_id, candidate_path=str(candidate), stage_path=str(stage))
                raise
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise HubError(f"Storage/staging failed; old authority retained: {exc}", 6,
                               project_id=project_path.name, current_revision=head["revision"], operation_id=operation_id,
                               candidate_path=str(candidate), stage_path=str(stage)) from exc

    def resume(self, project: str | Path, module_id: str | None = None, task: str | None = None,
               page: int = 1, page_size: int = 40, role: str = "master",
               required_refs: list[str] | None = None) -> dict:
        project_path = self._project(project)
        requested_refs = _refs(required_refs if required_refs is not None else [], "required_refs")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1 or not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise HubError("page must be >=1; page_size must be 1..100")
        _text(role, "role")
        if len(role) > 240 or (task is not None and (not isinstance(task, str) or len(task) > 2000)):
            raise HubError("role/task too large or invalid")
        # Packet generation writes derived files, so shares the project lock.
        with self._lock(project_path, "resume"):
            head, chain = self._chain(project_path)
            state = chain[0]["state"]
            visible = self._visible_refs(state, role)
            saved_checkpoint = state.get("pause_checkpoint") or {}
            checkpoint_ref = "artifact:" + saved_checkpoint.get("checkpoint_id", "")
            checkpoint_visible = bool(saved_checkpoint) and checkpoint_ref in visible
            checkpoint_current = False
            pending_review = None
            if checkpoint_visible:
                current_fingerprints = self._fingerprints(state)
                checkpoint_current = self._checkpoint_current(state, saved_checkpoint, current_fingerprints)
                pending_id = state.get("pending_checkpoint_id")
                if (pending_id and saved_checkpoint.get("awaiting_checkpoint_id") == pending_id
                        and "artifact:" + pending_id in visible):
                    awaiting = self._checkpoint_record(project_path / "revisions" / state["revision"], state, pending_id)
                    if awaiting:
                        awaiting_current = (awaiting.get("node") != "context_save"
                            and self._checkpoint_current(state, awaiting, current_fingerprints))
                        pending_review = {key: awaiting[key] for key in ("checkpoint_id", "saved_revision", "node",
                            "authorized_scope", "pending_questions", "next_action", "note_artifact_id")}
                        pending_review["current"] = awaiting_current
                        checkpoint_current = checkpoint_current and awaiting_current
            if module_id is not None:
                _id(module_id, "module ID")
                if module_id not in state["modules"]:
                    raise HubError("Module absent from current demand contract", 7)
                roots = [f"module:{module_id}"]
            else:
                roots = ["handoff:current"] if state.get("handoff") else []
            if checkpoint_visible and (module_id is None or "module:" + module_id in saved_checkpoint["input_fingerprints"]):
                roots.append(checkpoint_ref)
            for ref in requested_refs:
                self._object(state, ref)
            roots = list(dict.fromkeys(roots + requested_refs))
            required = self._closure(state, roots) if roots else []
            context_refs = []
            if state.get("brief"):
                context_refs.append("artifact:" + state["brief"]["artifact_id"])
            for singleton in ("contract", "handoff"):
                if state.get(singleton):
                    context_refs.append(f"{singleton}:current")
            if module_id is None:
                required.extend(context_refs)

            def with_artifacts(refs):
                expanded = list(refs)
                for ref in refs:
                    obj = self._object(state, ref)
                    expanded.extend(f"artifact:{a}" for a in obj.get("artifact_ids", []))
                    if obj.get("artifact_id"):
                        expanded.append("artifact:" + obj["artifact_id"])
                return list(dict.fromkeys(expanded))

            # Declared module inputs and explicit required refs are hard inputs.
            # Unrelated project originals are optional navigation for a selected
            # module: a private sibling's full contract must not block public work.
            required = with_artifacts(required)
            restricted_count = len([ref for ref in required if ref not in visible])
            required = [ref for ref in required if ref in visible]
            if module_id is not None:
                optional = with_artifacts([ref for ref in context_refs if ref in visible])
                required = list(dict.fromkeys(required + [ref for ref in optional if ref in visible]))
            catalog = [row for row in self._catalog(project_path, state) if row["ref"] in visible]
            role_key = _hash(role.encode("utf-8"))[:12]
            catalog_path = project_path / "operations" / ("catalog.json" if role == "master" else f"catalog-role-{role_key}.json")
            snapshot_fingerprints = role == "master" and state.get("fingerprint_version", 1) == FINGERPRINT_VERSION
            fingerprints_path = (project_path / "revisions" / state["revision"] / "fingerprints.json") if snapshot_fingerprints else project_path / "work" / "context" / state["revision"] / f"fingerprints-v2-role-{role_key}.json"
            if role != "master":
                for row in catalog:
                    # A global state path/index would expose restricted siblings.
                    row.pop("state_path", None)
                    row["state_entry_path"] = str(catalog_path)
                    if "artifact_paths" in row:
                        obj = self._object(state, row["ref"])
                        artifact_ids = ([obj["artifact_id"]] if obj.get("artifact_id") else []) + obj.get("artifact_ids", [])
                        row["artifact_paths"] = [str(self._artifact_path(project_path, state["revision"], state["artifacts"][ident])) for ident in artifact_ids if "artifact:" + ident in visible]
            by_ref = {row["ref"]: row for row in catalog}
            must_read = [by_ref[ref] for ref in required]
            decisions = [dict(row, value=state["decisions"][row["id"]]["value"],
                              status=state["decisions"][row["id"]]["status"],
                              confirmation=state["decisions"][row["id"]].get("confirmation"))
                         for row in catalog if row["kind"] == "decision"]
            def paged(items):
                start = (page - 1) * page_size
                return items[start:start + page_size], {"page": page, "page_size": page_size,
                    "total": len(items), "total_pages": max(1, (len(items) + page_size - 1) // page_size),
                    "listed_start": start + 1 if start < len(items) else None,
                    "listed_end": min(start + page_size, len(items)) if start < len(items) else None,
                    "has_more": start + page_size < len(items)}
            inv_page, inv_meta = paged(catalog)
            read_page, read_meta = paged(must_read)
            decision_page, decision_meta = paged(decisions)
            def preview_rows(items):
                output = []
                for row in items:
                    shortened, truncated = _preview(row)
                    shortened["truncated"] = truncated
                    shortened["full_entry_path"] = str(catalog_path)
                    output.append(shortened)
                return output
            inv_page, read_page, decision_page = (preview_rows(items) for items in (inv_page, read_page, decision_page))
            relevant_sources = [state["sources"][r.split(":", 1)[1]] for r in required if r.startswith("source:")]
            unresolved = []
            if module_id and f"module:{module_id}" in visible:
                unresolved += state["modules"][module_id].get("unresolved", [])
            if state.get("handoff") and "handoff:current" in visible:
                unresolved += state["handoff"].get("unresolved", [])
            unresolved += [obj for ident, obj in state["questions"].items() if f"question:{ident}" in visible]
            unresolved = [item for item in unresolved if isinstance(item, dict) and all(ref in visible for ref in item.get("impact", []))]
            blockers = [item for item in unresolved if item.get("blocking") and item.get("status") != "resolved"]
            blocker_page, blocker_meta = paged(blockers)
            unresolved_page, unresolved_meta = paged(unresolved)
            blocker_page, unresolved_page = (preview_rows(items) for items in (blocker_page, unresolved_page))
            current_module = state["modules"].get(module_id) if module_id else None
            if module_id and f"module:{module_id}" not in visible:
                current_module = None
            handoff = state.get("handoff") if "handoff:current" in visible else None
            policy_preview, policy_truncated = _preview(handoff["policy"]) if handoff else (None, False)
            legacy_reviews = [row for row in catalog if row.get("source_metadata_coverage") == "not_bound"]
            packet = {"schema_version": SCHEMA_VERSION, "fingerprint_version": FINGERPRINT_VERSION,
                "project_id": project_path.name,
                "revision": head["revision"], "phase": state["phase"], "workflow_mode": state.get("workflow_mode", "legacy"),
                "workflow_version": state.get("workflow_version"), "discussion_round": state.get("discussion_round"),
                "human_workflow_required": state.get("workflow_version") != WORKFLOW_VERSION,
                "module_id": module_id if current_module else None,
                "required_refs": [ref for ref in requested_refs if ref in visible],
                "task": task or (current_module["purpose"] if current_module else "Continue current research/production from project files"),
                "role": role, "context_telemetry": "unknown", "semantic_verification": "not performed",
                "inventory": inv_page, "must_read": read_page, "current_decisions": decision_page,
                "blockers": blocker_page, "unresolved": unresolved_page,
                "handoff": {"sufficiency": handoff["sufficiency"], "policy_preview": policy_preview,
                    "policy_truncated": policy_truncated, "stale": handoff.get("stale", False)} if handoff else None,
                "restricted_dependencies": {"count": restricted_count, "status": "blocked" if restricted_count else "clear",
                    "next_action": "Ask master for an authorized sanitized task input" if restricted_count else None},
                "pagination": {"inventory": inv_meta, "must_read": read_meta,
                    "current_decisions": decision_meta, "blockers": blocker_meta, "unresolved": unresolved_meta},
                "coverage": {"inventory": "this page lists entries only", "original_reading": "not verified; source declarations follow",
                    "reading_declarations": [{"source_id": s["source_id"], "read_scope": _preview(s["read_scope"])[0], "access_status": s["access_status"]} for s in relevant_sources[(page - 1) * page_size:page * page_size]],
                    "reading_declarations_total": len(relevant_sources)},
                "contract_path": str(self._artifact_path(project_path, state["revision"], state["artifacts"][state["contract"]["artifact_id"]])) if "contract:current" in visible and "artifact:" + state["contract"]["artifact_id"] in visible else None,
                "handoff_path": str(self._artifact_path(project_path, state["revision"], state["artifacts"][state["handoff"]["artifact_id"]])) if "handoff:current" in visible and "artifact:" + state["handoff"]["artifact_id"] in visible else None,
                "catalog_path": str(catalog_path),
                "legacy_source_metadata_reviews": {"count": len(legacy_reviews), "next_action": "Re-review source declarations using current v2 fingerprints" if legacy_reviews else None},
                "fingerprints_path": str(fingerprints_path),
                "fingerprints": {row["ref"]: row["fingerprint"] for row in read_page},
                "module": {key: current_module[key] for key in ("module_id", "applicability", "content_status", "stale") if key in current_module} if current_module else None,
                "next_actions": ["Read required original files and full exceptions; record actual reading separately", "Use current revision as base; preserve a candidate before writeback"]}
            packet["pause_checkpoint"] = None
            if checkpoint_visible:
                checkpoint_preview, truncated = _preview(saved_checkpoint)
                packet["pause_checkpoint"] = {"checkpoint_id": saved_checkpoint["checkpoint_id"],
                    "saved_revision": saved_checkpoint["saved_revision"], "node": saved_checkpoint["node"],
                    "current": checkpoint_current,
                    "awaiting_reply": bool(pending_review) and checkpoint_current,
                    "pending_review": pending_review,
                    "index_path": str(self._artifact_path(project_path, state["revision"], state["artifacts"][saved_checkpoint["checkpoint_id"]])),
                    "preview": checkpoint_preview, "truncated": truncated}
            if role == "master":
                packet["next_actions"].insert(0, self._next_discussion(state))
                if not task and not current_module:
                    packet["task"] = packet["next_actions"][0]
                if checkpoint_visible and checkpoint_current and packet["pause_checkpoint"]["awaiting_reply"]:
                    packet["next_actions"].insert(0, "先回读已保存节点的原稿、研究、创意取舍与待答复原话，等待实际回复后按范围接续。")
                    if not task and not current_module:
                        packet["task"] = saved_checkpoint["next_action"]
                elif pending_review and not checkpoint_current:
                    packet["next_actions"].insert(0, "原材料已变，先回读保留的原待审问题与展示正文，回交新版并重新保存节点，再核对人的实际答复。")
                    if not task and not current_module:
                        packet["task"] = packet["next_actions"][0]
            # Catalog is a complete persisted index; stdout remains paged.
            self._write_json(catalog_path, {"project_id": project_path.name,
                "revision": state["revision"], "fingerprint_version": FINGERPRINT_VERSION,
                "role": role, "coverage": "inventory only", "items": catalog}, atomic=True)
            if not snapshot_fingerprints:
                self._write_json(fingerprints_path, {ref: value for ref, value in self._fingerprints(state).items() if ref in visible}, atomic=True)
            key = _hash(_canonical({"revision": state["revision"], "module": module_id, "task": task,
                                    "page": page, "page_size": page_size, "role": role,
                                    "required_refs": requested_refs, "fingerprint_version": FINGERPRINT_VERSION}))[:16]
            packet_dir = project_path / "work" / "context" / state["revision"]
            json_path, md_path = packet_dir / f"{key}.json", packet_dir / f"{key}.md"
            self._write_json(json_path, packet, atomic=True)
            display_name = state["name"] if role == "master" else project_path.name
            lines = [f"# {display_name} · 接续任务包", "", f"项目={project_path.name}；版本={state['revision']}；阶段={state['phase']}",
                     f"任务：{packet['task'][:2000]}", f"角色：{role}", "", "适用与成熟度分别维护；批准/执行由真实记录判断。",
                     "目录本页已列出，原文实际阅读未由脚本验证。上下文遥测 unknown。", "",
                     self._markdown_link("完整目录（只证明清单）", Path(packet["catalog_path"])),
                     self._markdown_link("本包机器JSON及分页信息", json_path),
                     self._markdown_link("完整当前指纹", Path(packet["fingerprints_path"])), "", "## 必读原文/当前依赖", ""]
            if checkpoint_visible:
                lines += [self._markdown_link("节点沉淀分类索引及原稿入口", Path(packet["pause_checkpoint"]["index_path"])),
                          f"保存节点={saved_checkpoint['node']}；当前材料仍适用={checkpoint_current}；等待答复={packet['pause_checkpoint']['awaiting_reply']}", ""]
            for row in read_page:
                paths = ([row["path"]] if row.get("path") else row.get("artifact_paths", []))
                links = "; ".join(self._markdown_link("原件/正文", Path(p)) for p in paths[:5])
                lines.append(f"- {row['ref']}；待复核={row['stale']}；{links or self._markdown_link('当前对象定位', Path(row.get('state_path', row['full_entry_path'])))}")
                if row.get("read_scope"):
                    lines.append(f"  - 提交者读取申报：{row['read_scope']['status']}；范围预览={str(row['read_scope']['ranges'])[:240]}；完整范围和限制见JSON/来源原件。")
            if read_meta["has_more"]:
                lines.append("必读列表还有后续页，不能仅凭本页声称依赖已覆盖。")
            if handoff:
                lines += ["", "方针预览：" + str(policy_preview)]
                if packet["handoff_path"]:
                    lines.append("完整交接：" + self._markdown_link("交接原文", Path(packet["handoff_path"])))
            if restricted_count:
                lines.append("当前角色的必要输入受限；请主控提供获授权的脱敏输入，当前任务阻断。")
            if legacy_reviews:
                lines.append("存在仅绑定来源文件字节的历史复核；来源声明元数据尚未被该复核绑定，请使用当前v2指纹重新复核。")
            lines += ["", "## 当前决定及阻断", ""]
            for row in decision_page:
                preview = str(row["value"])[:300]
                lines.append(f"- {row['ref']}：{row['status']}；{preview}（完整值见当前state）")
            for blocker in unresolved_page:
                lines.append(f"- {str(blocker.get('question', blocker))[:300]}；边界={str(blocker.get('finalization_boundary', ''))[:240]}")
            lines += ["", "下一步：实际回读必要原件及完整例外，核当前决定，保存实质单元，再按当前base回写。"]
            self._write_bytes(md_path, ("\n".join(lines) + "\n").encode("utf-8"), atomic=True)
            return _response("blocked" if restricted_count else "success", project_id=project_path.name, current_revision=state["revision"],
                context_path=str(md_path), context_json_path=str(json_path), checkpoint_path=str(json_path), catalog_path=packet["catalog_path"],
                packet=packet, next_actions=packet["next_actions"],
                error={"code": 7, "message": "Required task inputs restricted for this role; request sanitized authorized inputs"} if restricted_count else None,
                warnings=["Declared reading is unverified; follow later pages and original exceptions"])

    def rollback(self, project: str | Path, base: str, operation_id: str, to_revision: str, reason: str) -> dict:
        project_path = self._project(project)
        for value in (base, operation_id, to_revision):
            _id(value)
        _text(reason, "reason")
        request = {"project_id": project_path.name, "base": base, "operation_id": operation_id,
                   "kind": "rollback", "to_revision": to_revision, "reason": reason}
        request_hash = _hash(_canonical(request))
        with self._lock(project_path, operation_id):
            candidate = self._candidate(project_path, operation_id, request_hash, request, [])
            head, chain = self._chain(project_path)
            for entry in chain:
                if entry["operation"]["operation_id"] == operation_id:
                    if entry["operation"]["request_hash"] == request_hash:
                        return _response("already_applied", project_path.name, head["revision"], operation_id,
                                         applied_revision=entry["revision"], context_path=str(project_path / "项目中枢.md"),
                                         warnings=self._view_warnings(project_path, head["revision"]))
                    raise HubError("Operation ID conflicts with committed request", 3, project_id=project_path.name,
                                   current_revision=head["revision"], operation_id=operation_id, candidate_path=str(candidate))
            if base != head["revision"]:
                raise HubError("Rollback base conflict", 3, project_id=project_path.name,
                               current_revision=head["revision"], operation_id=operation_id, candidate_path=str(candidate))
            target = next((entry for entry in chain if entry["revision"] == to_revision), None)
            if target is None:
                raise HubError("Rollback target must be a validated committed ancestor", 4)
            current = chain[0]["state"]
            state = copy.deepcopy(target["state"])
            if current.get("workflow_version") == WORKFLOW_VERSION:
                for field in ("workflow_mode", "workflow_version", "discussion_round", "round_started_revision",
                              "previous_discussion_round", "retained_refs"):
                    if field in current:
                        state[field] = copy.deepcopy(current[field])
            state["generation"] = current["generation"] + 1
            state["revision"] = self._new_revision(state["generation"])
            state["parent_revision"] = base
            stage = self._make_stage(project_path, state["revision"], to_revision)
            differences, changed = [], set()
            # Current real conditions and real decisions cannot be erased by
            # restoring historic prose. Their supporting sources/artifacts follow.
            preserve = set()
            for kind in ("fact", "decision", "event", "resource", "cost"):
                for ident, obj in current[COLLECTIONS[kind]].items():
                    if kind in {"resource", "cost"} and obj.get("status") not in {"confirmed", "reserved", "contracted", "paid", "actual", "occurred", "published", "delivered", "locked"}:
                        continue
                    old = state[COLLECTIONS[kind]].get(ident)
                    if old != obj:
                        differences.append({"ref": f"{kind}:{ident}", "restored_value": old.get("value") if old else None,
                                            "current_value": obj.get("value"), "handling": "current real condition/decision/event retained"})
                        changed.add(f"{kind}:{ident}")
                    preserve.update(self._closure(current, [f"{kind}:{ident}"]))
                    preserve.add(f"{kind}:{ident}")
                    if kind == "event":
                        for historical_event in obj.get("history", []):
                            preserve.update(self._closure(current, ["artifact:" + historical_event["artifact_id"]]))
            # The closure contains declared original dependencies. Keep these
            # current records and bytes; do not replace restored module bodies.
            for ref in sorted(preserve):
                kind, ident = ref.split(":", 1)
                if kind in {"module", "contract", "handoff", "review"}:
                    continue
                obj = copy.deepcopy(self._object(current, ref))
                state[COLLECTIONS[kind]][ident] = obj
                if kind == "artifact" and obj["storage"] == "snapshot":
                    original = self._artifact_path(project_path, base, obj)
                    self._write_bytes(stage / obj["path"], original.read_bytes())
                if obj.get("artifact_id"):
                    artifact = copy.deepcopy(current["artifacts"][obj["artifact_id"]])
                    state["artifacts"][obj["artifact_id"]] = artifact
                    if artifact["storage"] == "snapshot":
                        self._write_bytes(stage / artifact["path"], self._artifact_path(project_path, base, artifact).read_bytes())
            dynamic_refs = {ref for ref, obj in self._objects(state).items() if obj.get("dynamic")}
            condition_differences = {f"{kind}:{ident}" for kind in ("resource", "cost", "session")
                for ident, obj in state[COLLECTIONS[kind]].items() if obj != current[COLLECTIONS[kind]].get(ident)}
            for ref in condition_differences:
                differences.append({"ref": ref, "handling": "restored condition differs from current; recheck required"})
            for ref in dynamic_refs:
                differences.append({"ref": ref, "handling": "dynamic condition needs current recheck", "recheck_trigger": self._object(state, ref).get("recheck_trigger")})
            # All restored body versions differing from current must be assessed
            # against current decisions; old approval/old review is not replayed.
            restored_changed = {f"module:{ident}" for ident, obj in state["modules"].items()
                                if obj != current["modules"].get(ident)}
            restored_reviews = {f"review:{ident}" for ident in state["reviews"]}
            delivery_records = [obj for obj in state["decisions"].values()
                                if state.get("workflow_mode") == "collaborative" and obj["status"] == "confirmed"
                                and isinstance(obj.get("value"), dict) and obj["value"].get("gate") == "delivery"]
            chapter_records = [obj for obj in state["decisions"].values()
                               if isinstance(obj.get("value"), dict) and obj["value"].get("gate") == "chapter_review"]
            for obj in delivery_records + chapter_records:
                # An adopted historical passage remains recorded even when
                # rolling back to a version before its module existed.
                obj["depends_on"] = [ref for ref in obj.get("depends_on", [])
                                     if not ref.startswith("module:") or ref.split(":", 1)[1] in state["modules"]]
                if obj["value"].get("gate") == "chapter_review" and obj["value"]["module_id"] not in state["modules"]:
                    obj["stale"] = True
                    obj["stale_reasons"] = ["回滚后的版本没有原审阅章节，反馈保留为历史"]
            self._validate_state(state, project_path.name, state["revision"])
            affected = self._propagate(state, changed | dynamic_refs | condition_differences | restored_changed | restored_reviews,
                                       "Rollback restored historic content; reconcile current conditions and decisions", include_roots=True)
            for ref in changed:
                if ref.startswith(("decision:", "event:")):
                    # Retained true records stay current. Their old-dependent
                    # prose/reviews have already been marked for recheck.
                    obj = self._object(state, ref)
                    obj["stale"] = current[COLLECTIONS[ref.split(":", 1)[0]]][ref.split(":", 1)[1]].get("stale", False)
            self._refresh_phase(state)
            for obj in delivery_records:
                modules = obj["value"].get("accepted_modules", [])
                modules = modules + [section["module_id"] for section in obj["value"].get("accepted_sections", [])]
                if state["phase"] != "production" or any(state["modules"].get(ident, {}).get("stale", True) for ident in modules):
                    obj["stale"] = True
                    obj["stale_reasons"] = list(dict.fromkeys(obj.get("stale_reasons", []) + ["回滚后的正文和条件须重新核对"]))
            affected = sorted(set(affected) | set(self._recheck_deliveries(current, state)))
            report = {"from_revision": base, "restored_revision": to_revision, "new_revision": state["revision"],
                      "reason": reason, "differences": differences, "affected": affected,
                      "external_effects": "Messages, contracts, purchases, publication and actual decisions are not undone",
                      "approval": "Restored past approval is not a new current approval"}
            body = ("# 回滚与当前条件对照\n\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._artifact(stage, state, _generated("rollback-", operation_id), "rollback_report", "", f"changes/rollback-{operation_id}.md",
                           {"data": body, "sha256": _hash(body), "size": len(body)}, "needs_review")
            state["last_change"] = {"operation_id": operation_id, "kind": "rollback", "from": base,
                                    "restored": to_revision, "reason": reason, "affected": affected, "at": _now()}
            operation = self._operation(state, operation_id, "rollback", request_hash, base, affected,
                                        restored_revision=to_revision, rollback_report=report, request=request)
            result = self._finish(project_path, stage, state, operation, chain[0], chain)
            result["rollback_report"] = report
            result["candidate_path"] = str(candidate)
            result["warnings"].append("Restored historic content requires current-condition review; external events are retained")
            return result

    def repair(self, project: str | Path) -> dict:
        project_path = self._project(project)
        with self._lock(project_path, "repair"):
            head, chain = self._chain(project_path)
            self._refresh_views(project_path, chain[0]["state"], chain)
            committed = {entry["revision"] for entry in chain}
            orphan_revisions = [p.name for p in (project_path / "revisions").iterdir() if p.is_dir() and p.name not in committed]
            stages = [p.name for p in (project_path / "work").glob("stage-*")]
            return _response(project_id=project_path.name, current_revision=head["revision"],
                context_path=str(project_path / "项目中枢.md"), catalog_path=str(project_path / "operations" / "catalog.json"),
                diagnostics={"orphan_revisions": orphan_revisions, "stages": stages, "history": "validated; no automatic deletion"},
                next_actions=["Resume current work; inspect preserved stages/orphans separately if present"])

    @staticmethod
    def _client_body(name: str, purpose: str, body: str) -> str:
        stripped = body.strip("\r\n")
        first, newline, rest = stripped.partition("\n")
        if first.startswith("# "):
            title = re.sub(r"\s+#+$", "", first[2:]).strip()
            if title == name:
                return rest.lstrip("\n")
            return "## " + title + newline + rest
        if re.match(r"^#{2,6}\s", first):
            return stripped
        return f"## {purpose}\n\n{stripped}"

    def _render_assembly(self, project: Path, state: dict, revision: str, modules: list[str] | None,
                         view: str) -> tuple[Path, str, list[str], dict]:
        output_dir = project / "deliverables" / revision
        has_body = any(module.get("body_artifact_id") and module["applicability"] == "now" for module in state["modules"].values())
        if view == "editor" and modules is None and (state["phase"] == "research" or not has_body):
            handoff = state.get("handoff") if state["phase"] == "production" else None
            if state.get("workflow_version") == WORKFLOW_VERSION and state.get("handoff"):
                try:
                    self._direction_gates(state, state["handoff"])
                except HubError:
                    handoff = None
                else:
                    handoff = state["handoff"]
            research = handoff or state.get("contract") or state.get("brief")
            if not research:
                raise HubError("尚无已保存的讨论正文，请先写入委托、分流或原型比较稿。", 7)
            ident = research["artifact_id"]
            artifact = state["artifacts"][ident]
            body = self._artifact_path(project, revision, artifact).read_text(encoding="utf-8-sig")
            label = "方针交接稿 · 供编辑审阅" if handoff else "策划讨论稿 · 等待核对委托或方针"
            return (self._write_path(output_dir / "editor-review.md"),
                    f"# {state['name']}\n\n{label}\n\n{body}\n",
                    [], {ident: artifact["sha256"]})
        if not state.get("contract"):
            raise HubError("Assembly requires current contract", 7)
        if view == "client" and "client" not in state["contract"].get("allowed_roles", ["client"]):
            raise HubError("当前契约仅供指定内部角色使用；请核对整份契约的客户阅读范围。", 7)
        if view == "client":
            self._direction_gates(state, state.get("handoff"))
        if modules is None:
            selected = [ident for ident in state["contract"]["module_order"]
                        if state["modules"][ident]["applicability"] == "now"
                        and (view != "editor" or state["modules"][ident].get("body_artifact_id"))
                        and (view != "client" or state["modules"][ident].get("audience") == "client")]
        else:
            selected = list(dict.fromkeys(_id(item) for item in _list(modules, "modules")))
        if not selected:
            raise HubError("没有符合当前阅读用途的模块；请核对契约、读者和正文。", 7)
        contents, used = [], {}
        for ident in selected:
            if ident not in state["modules"]:
                raise HubError("Assembly module does not belong to this contract", 2)
            module = state["modules"][ident]
            if view == "client":
                self._writing_gate(state, module.get("decision_ids", []), ident)
            if view == "client" and (module.get("audience") != "client" or module["applicability"] != "now" or module["content_status"] != "reviewable"):
                raise HubError(f"客户审阅稿只接受契约标为 client、当前需要且可评审的正文：{ident}", 7)
            blockers = self._blocking(state, ident)
            unready = module.get("stale") or module["content_status"] in {"outline", "blocked", "needs_review", "archived"} or blockers
            if not module.get("body_artifact_id") or (view != "editor" and unready):
                raise HubError(f"Assembly blocked by missing/stale/blocked body: {ident}", 7)
            body_id = module["body_artifact_id"]
            if view == "client":
                for declaration in (module["contract_spec"], module, state["artifacts"][body_id]):
                    if "allowed_roles" in declaration and "client" not in declaration["allowed_roles"]:
                        raise HubError(f"正文的读取范围未包含 client；请另行编辑获准交客户的正文：{ident}", 7)
            for artifact_id in ([body_id] if view == "client" else module["artifact_ids"]):
                artifact = state["artifacts"][artifact_id]
                if view != "editor" and artifact.get("stale"):
                    raise HubError(f"Assembly artifact stale: {artifact_id}", 7)
                body = self._artifact_path(project, revision, artifact).read_text(encoding="utf-8-sig")
                if view == "client":
                    contents.append(self._client_body(state["name"], module["purpose"], body))
                else:
                    title = module["purpose"]
                    if artifact_id != body_id:
                        title += f" · {artifact.get('purpose', artifact_id)}"
                    if view == "editor":
                        status = "待复核" if unready or artifact.get("stale") else ("可评审" if artifact["content_status"] == "reviewable" else "草案")
                        title += f"（{status}）"
                        if blockers and artifact_id == body_id:
                            body = "待核对：" + "；".join(str(item.get("question", "待确认条件")) for item in blockers) + "\n\n" + body
                    contents.append(f"## {title}\n\n{body}")
                used[artifact_id] = artifact["sha256"]
        stem = {"legacy": "complete-plan", "client": "client-review", "editor": "editor-review"}[view]
        if modules is not None:
            suffix = "selection-" + _hash(_canonical(selected))[:12]
            stem = suffix if view == "legacy" else f"{stem}-{suffix}"
        label = {"legacy": f"版本：{revision}。正文状态与真实资源/审批/执行分别判断。",
                 "editor": "内部编辑工作稿（含接手工作件）", "client": "客户审阅稿"}[view]
        output = self._write_path(output_dir / f"{stem}.md")
        return output, f"# {state['name']}\n\n{label}\n\n" + "\n\n".join(contents) + "\n", selected, used

    @staticmethod
    def _assembly_manifest(project: Path, revision: str, modules: list[str], used: dict, text: str, view: str) -> dict:
        manifest = {"project_id": project.name, "revision": revision, "modules": modules, "input_fingerprints": used,
                    "sha256": _hash(text.encode("utf-8")), "semantic_verification": "not performed"}
        if view != "legacy":
            manifest.update(view=view, status="awaiting_review")
        return manifest

    def _delivery_scope(self, state: dict, selected: list[str]) -> dict:
        roots = [f"module:{ident}" for ident in selected]
        closure = set(self._closure(state, roots))
        fingerprints = self._fingerprints(state)
        modules = {}
        for ident in selected:
            module = state["modules"][ident]
            body = state["artifacts"][module["body_artifact_id"]]
            modules[ident] = {"body_sha256": body["sha256"], "spec": module["contract_spec"],
                              "unresolved": module["unresolved"], "audience": module.get("audience")}
        handoff = state["handoff"]
        handoff_conditions = [item for item in handoff["unresolved"] if not item.get("impact") or closure.intersection(item["impact"])]
        open_questions = [item for item in state["questions"].values() if not item.get("impact") or closure.intersection(item["impact"])]
        return {"modules": modules, "document_use": state["contract"]["document_use"], "policy": handoff["policy"],
                "client_access": "client" in state["contract"].get("allowed_roles", ["client"]),
                "sufficiency": handoff["sufficiency"] if handoff_conditions else "ready",
                "conditions": handoff_conditions + open_questions,
                "dependencies": {ref: fingerprints[ref] for ref in closure.difference(roots)}}

    def _recheck_deliveries(self, previous: dict, state: dict) -> list[str]:
        if state.get("workflow_mode") != "collaborative":
            return []
        changed = set()
        for ident, record in state["decisions"].items():
            value = record.get("value")
            if record["status"] != "confirmed" or record.get("stale") or not isinstance(value, dict) or value.get("gate") != "delivery":
                continue
            prior = previous["decisions"].get(ident)
            if not prior or prior["status"] != "confirmed" or prior.get("stale") or prior["value"] != value:
                continue
            selected = list(dict.fromkeys(value["accepted_modules"] + [part["module_id"] for part in value.get("accepted_sections", [])]))
            if state["phase"] != "production" or self._delivery_scope(previous, selected) != self._delivery_scope(state, selected):
                changed.add(f"decision:{ident}")
        return self._propagate(state, changed, "已采纳内容的成立条件或阅读范围改变，请复核", include_roots=True) if changed else []

    def _verify_delivery_decision(self, project: Path, state: dict, payload: dict, chain: list[dict]) -> None:
        value = payload["new_value"]
        _require(value, ["review_revision", "review_sha256"])
        revision = value["review_revision"]
        reviewed = next((entry["state"] for entry in chain if entry["revision"] == revision), None)
        if reviewed is None:
            raise HubError("审阅版本须为本项目已提交版本，请回读实际发给人的客户稿。", 7)
        output, body, shown, used = self._render_assembly(project, reviewed, revision, value.get("modules"), "client")
        expected = body.encode("utf-8")
        if not output.is_file() or output.read_bytes() != expected or value["review_sha256"] != _hash(expected):
            raise HubError("客户审阅稿未导出或指纹不符，请核对交给人审阅的实际文件。", 7)
        receipt = self._write_path(output.with_suffix(".manifest.json"))
        manifest = self._assembly_manifest(project, revision, shown, used, body, "client")
        if not receipt.is_file() or self._read_json(receipt) != manifest:
            raise HubError("缺少完整的审阅稿清单，或版本、范围、输入、文件指纹与权威稿不符。", 7)
        sections = _list(value.get("accepted_sections", []), "accepted_sections")
        whole = _list(value.get("accepted_modules", [] if sections else shown), "accepted_modules")
        if any(_id(ident) not in shown for ident in whole) or len(set(whole)) != len(whole):
            raise HubError("采纳的章节必须来自实际展示稿，每章只列一次。", 7)
        selected = list(whole)
        passages = set()
        for section in sections:
            if not isinstance(section, dict):
                raise HubError("accepted_sections entries require module_id and quote")
            _require(section, ["module_id", "quote"])
            ident = _id(section["module_id"])
            quote = _text(section["quote"], "quote")
            if ident not in shown or ident in whole or (ident, quote) in passages:
                raise HubError("请从展示稿指定模块摘录本次采纳的唯一片段，避免重复记录。", 7)
            artifact = reviewed["artifacts"][reviewed["modules"][ident]["body_artifact_id"]]
            raw = self._artifact_path(project, revision, artifact).read_text(encoding="utf-8-sig")
            shown_body = self._client_body(reviewed["name"], reviewed["modules"][ident]["purpose"], raw)
            first = shown_body.find(quote)
            if first < 0 or first != shown_body.rfind(quote):
                raise HubError("摘录未唯一对应审阅原文，请补充相邻原句。", 7)
            passages.add((ident, quote))
            if ident not in selected:
                selected.append(ident)
        if not selected:
            raise HubError("请明确采纳实际展示的哪些章节或原文片段。", 7)
        self._render_assembly(project, state, state["parent_revision"], selected, "client")
        if self._delivery_scope(reviewed, selected) != self._delivery_scope(state, selected):
            raise HubError("被采纳正文或已登记成立条件已变化；请保留原意见并把变更交人复核。", 7)
        value["accepted_modules"] = whole
        deps = payload.get("depends_on", []) + [f"module:{ident}" for ident in selected]
        payload["depends_on"] = list(dict.fromkeys(deps))

    def assemble(self, project: str | Path, modules: list[str] | None = None, view: str | None = None) -> dict:
        if view is not None:
            _enum(view, {"editor", "client"}, "reading view")
        project_path = self._project(project)
        with self._lock(project_path, "assemble"):
            head, chain = self._chain(project_path)
            state = chain[0]["state"]
            view = view or ("editor" if state.get("workflow_mode") == "collaborative" else "legacy")
            output, text, selected, used = self._render_assembly(project_path, state, head["revision"], modules, view)
            self._write_bytes(output, text.encode("utf-8"), atomic=True)
            manifest = self._assembly_manifest(project_path, head["revision"], selected, used, text, view)
            self._write_json(output.with_suffix(".manifest.json"), manifest, atomic=True)
            return _response(project_id=project_path.name, current_revision=head["revision"],
                artifact_paths=[str(output)], context_path=str(project_path / "项目中枢.md"),
                warnings=["Markdown assembled from actual files; semantic, native-format and real-world acceptance are separate"])


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.json"
    try:
        value = _json_loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise HubError(f"Cannot read config: {config_path}: {exc}", 4) from exc
    if not isinstance(value, dict) or not isinstance(value.get("workspace_root"), str):
        raise HubError("Config requires workspace_root string", 2)
    return value


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise HubError(message, 2)


def cli_main(entry: str, argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    try:
        # Resolve --config regardless of position without shell interpolation.
        config = None
        cleaned = []
        index = 0
        while index < len(args_list):
            arg = args_list[index]
            if arg == "--config":
                if index + 1 == len(args_list):
                    raise HubError("--config requires a path")
                config = args_list[index + 1]
                index += 2
            elif arg.startswith("--config="):
                config = arg.split("=", 1)[1]
                index += 1
            else:
                cleaned.append(arg)
                index += 1
        parser = JsonArgumentParser(description="MKT Max 1 local runtime; JSON stdout")
        if entry == "start":
            commands = parser.add_subparsers(dest="command", required=True)
            init = commands.add_parser("init")
            init.add_argument("--name", required=True)
            init.add_argument("--id", dest="project_id")
            init.add_argument("--brief")
            init.add_argument("--brief-allowed-roles", nargs="+")
            resume = commands.add_parser("resume")
            resume.add_argument("--project", required=True)
            resume.add_argument("--module", dest="module_id")
            resume.add_argument("--task")
            resume.add_argument("--page", type=int, default=1)
            resume.add_argument("--page-size", type=int, default=40)
            resume.add_argument("--role", default="master")
            resume.add_argument("--required-ref", dest="required_refs", action="append")
            reopen = commands.add_parser("reopen")
            reopen.add_argument("--project", required=True)
            reopen.add_argument("--base", required=True)
            reopen.add_argument("--operation-id", required=True)
            reopen.add_argument("--file", required=True)
            reopen.add_argument("--source-id", dest="source_ids", action="append", required=True)
            reopen.add_argument("--reason", required=True)
            reopen.add_argument("--retain-ref", dest="retained_refs", action="append")
            pause = commands.add_parser("pause")
            pause.add_argument("--project", required=True)
            pause.add_argument("--base", required=True)
            pause.add_argument("--operation-id", required=True)
            pause.add_argument("--payload", required=True)
        elif entry == "writeback":
            parser.add_argument("kind", choices=["source", "contract", "handoff", "module", "change", "review", "reopen", "pause"])
            parser.add_argument("--project", required=True)
            parser.add_argument("--base", required=True)
            parser.add_argument("--operation-id", required=True)
            parser.add_argument("--payload", required=True)
        elif entry == "rollback":
            parser.add_argument("--project", required=True)
            parser.add_argument("--base", required=True)
            parser.add_argument("--operation-id", required=True)
            parser.add_argument("--to", dest="to_revision", required=True)
            parser.add_argument("--reason", required=True)
        elif entry in {"repair", "assemble", "cost_audit"}:
            parser.add_argument("--project", required=True)
            if entry == "assemble":
                parser.add_argument("--modules", nargs="+")
                parser.add_argument("--view", choices=["editor", "client"])
        else:
            raise HubError("Unknown CLI entry")
        arguments = vars(parser.parse_args(cleaned))
        runtime = HubRuntime(load_config(config)["workspace_root"])
        command = arguments.pop("command") if entry == "start" else None
        if entry == "writeback" or (entry == "start" and command == "pause"):
            payload_path = Path(arguments.pop("payload"))
            HubRuntime._reject_traversal(payload_path)
            HubRuntime._reject_links(payload_path)
            try:
                payload = _json_loads(payload_path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise HubError(f"Cannot read JSON payload: {exc}", 2) from exc
            response = runtime.pause(payload=payload, **arguments) if entry == "start" else runtime.submit(payload=payload, **arguments)
        elif entry == "start":
            response = getattr(runtime, command)(**arguments)
        else:
            response = getattr(runtime, entry)(**arguments)
        if entry == "start" and command == "resume":
            # The complete packet is already persisted. Avoid dumping repeated
            # paths/metadata into an agent's stdout context by default.
            packet = response.pop("packet", None)
            if packet:
                response["pagination"] = packet["pagination"]
                response["packet_summary"] = {"phase": packet["phase"], "module_id": packet["module_id"],
                    "workflow_mode": packet["workflow_mode"],
                    "workflow_version": packet["workflow_version"], "discussion_round": packet["discussion_round"],
                    "human_workflow_required": packet["human_workflow_required"],
                    "role": packet["role"], "restricted_dependencies": packet["restricted_dependencies"],
                    "fingerprint_version": packet["fingerprint_version"], "required_refs": packet["required_refs"],
                    "semantic_verification": "not performed", "context_telemetry": "unknown"}
                response["pause_checkpoint"] = packet["pause_checkpoint"]
                response["next_actions"] = ["Read persisted context Markdown/JSON; page or narrow the task if the pack is too large"] + response["next_actions"]
        code = 7 if response["status"] == "blocked" else 0
    except HubError as exc:
        response, code = exc.response, exc.exit_code
    except (OSError, ValueError, TypeError) as exc:
        response, code = _response("error", error={"code": 6, "message": str(exc)}), 6
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(cli_main("start"))
