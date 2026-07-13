"""Private, crash-aware storage for the canonical THS housefile.

The materialization boundary is the only current writer.  This module keeps the
filesystem mechanics separate so revision policy remains pure and testable.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from threading import get_ident


THS_SCHEMA_RESOURCE = files("threshold.housefile").joinpath("ths-0.1.schema.json")
MAX_HOUSEFILE_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 20_000


class HousefileStoreError(RuntimeError):
    """Sanitized storage failure; messages never contain paths or document data."""

    def __init__(self, failure: str) -> None:
        super().__init__(failure)
        self.failure = failure


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite number")


def _walk_json(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("document bounds")
        if isinstance(current, Mapping):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise ValueError("non-string key")
                stack.append((child, depth + 1))
        elif isinstance(current, (list, tuple)):
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("non-finite number")
        elif current is not None and not isinstance(current, (str, int, float, bool)):
            raise ValueError("unsupported JSON value")


def parse_json_bytes(data: bytes) -> dict[str, object]:
    """Parse bounded strict JSON and reject duplicate keys and non-finite values."""

    if not isinstance(data, bytes) or not data or len(data) > MAX_HOUSEFILE_BYTES:
        raise HousefileStoreError("invalid_housefile_json")
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        _walk_json(value)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise HousefileStoreError("invalid_housefile_json") from exc
    if not isinstance(value, dict):
        raise HousefileStoreError("invalid_housefile_json")
    return value


def canonical_json(value: object) -> bytes:
    """Return the repository's deterministic JSON encoding after strict checks."""

    try:
        _walk_json(value)
        encoded = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as exc:
        raise HousefileStoreError("invalid_housefile_json") from exc
    if len(encoded) > MAX_HOUSEFILE_BYTES:
        raise HousefileStoreError("invalid_housefile_json")
    return encoded


def validate_ths_document(document: Mapping[str, object]) -> None:
    """Validate against the bundled Draft 2020-12 schema, failing closed.

    ``jsonschema`` is a runtime dependency.  Materialization still fails closed if
    the dependency or bundled schema is unavailable at the point of use.
    """

    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency-failure contract
        raise HousefileStoreError("schema_validator_unavailable") from exc

    try:
        schema = parse_json_bytes(THS_SCHEMA_RESOURCE.read_bytes())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        if next(validator.iter_errors(document), None) is not None:
            raise HousefileStoreError("invalid_housefile_schema")
    except HousefileStoreError:
        raise
    except Exception as exc:
        raise HousefileStoreError("schema_validation_failed") from exc


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _reject_symlink_components(path: Path) -> None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    try:
        for component in absolute.parts[1:]:
            current /= component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise HousefileStoreError("unsafe_housefile_path")
    except HousefileStoreError:
        raise
    except OSError as exc:
        raise HousefileStoreError("housefile_directory_unavailable") from exc


def _ensure_private_directory(path: Path) -> None:
    _reject_symlink_components(path)
    try:
        st = path.lstat()
    except OSError as exc:
        raise HousefileStoreError("housefile_directory_unavailable") from exc
    if (
        not stat.S_ISDIR(st.st_mode)
        or _mode(st) != 0o700
        or st.st_uid != os.geteuid()
    ):
        raise HousefileStoreError("unsafe_housefile_directory")


def _validate_regular(st: os.stat_result, *, failure: str) -> None:
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_nlink != 1
        or _mode(st) != 0o600
        or st.st_uid != os.geteuid()
    ):
        raise HousefileStoreError(failure)


def _read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(64 * 1024, MAX_HOUSEFILE_BYTES + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_HOUSEFILE_BYTES:
            raise HousefileStoreError("housefile_too_large")


def _open_existing_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise HousefileStoreError("housefile_unavailable") from exc
    try:
        _validate_regular(os.fstat(fd), failure="unsafe_housefile_file")
        return _read_fd(fd)
    finally:
        os.close(fd)


def _new_private_file(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise HousefileStoreError("housefile_stage_failed") from exc
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
        _validate_regular(os.fstat(fd), failure="unsafe_housefile_stage")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class HousefileStore:
    """Stable-lock store for one existing private canonical housefile."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(os.path.abspath(os.fspath(path)))
        self.lock_path = self.path.parent / f".{self.path.name}.lock"
        self._lock_owner: int | None = None

    @contextmanager
    def locked(self) -> Iterator["HousefileStore"]:
        if self._lock_owner is not None:
            raise HousefileStoreError("housefile_lock_already_held")
        _ensure_private_directory(self.path.parent)
        # The writer never creates a canonical housefile.  Validate the existing
        # target before creating even the stable lock file.
        _open_existing_bytes(self.path)
        base_flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        created = False
        marker_set = False
        try:
            try:
                fd = os.open(self.lock_path, base_flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(self.lock_path, base_flags)
        except OSError as exc:
            raise HousefileStoreError("housefile_lock_unavailable") from exc
        try:
            if created:
                os.fchmod(fd, 0o600)
            _validate_regular(os.fstat(fd), failure="unsafe_housefile_lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            _validate_regular(os.fstat(fd), failure="unsafe_housefile_lock")
            if self._lock_owner is not None:
                raise HousefileStoreError("housefile_lock_already_held")
            self._lock_owner = get_ident()
            marker_set = True
            yield self
        except OSError as exc:
            raise HousefileStoreError("housefile_lock_unavailable") from exc
        finally:
            if marker_set:
                self._lock_owner = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def read_bytes_locked(self) -> bytes:
        self._require_lock()
        return _open_existing_bytes(self.path)

    def read_document_locked(self) -> dict[str, object]:
        return parse_json_bytes(self.read_bytes_locked())

    def _replace_existing_locked(self, data: bytes) -> None:
        """Replace the target, restoring its exact old bytes on commit failure."""

        self._require_lock()
        if not isinstance(data, bytes) or not data or len(data) > MAX_HOUSEFILE_BYTES:
            raise HousefileStoreError("invalid_housefile_json")
        old = self.read_bytes_locked()
        directory = self.path.parent
        replacement: Path | None = None
        rollback: Path | None = None
        replaced = False
        try:
            new_fd, new_name = tempfile.mkstemp(prefix=f".{self.path.name}.new-", dir=directory)
            os.close(new_fd)
            replacement = Path(new_name)
            replacement.unlink()
            old_fd, old_name = tempfile.mkstemp(prefix=f".{self.path.name}.old-", dir=directory)
            os.close(old_fd)
            rollback = Path(old_name)
            rollback.unlink()
            _new_private_file(replacement, data)
            _new_private_file(rollback, old)
            os.replace(replacement, self.path)
            replaced = True
            _fsync_directory(directory)
            rollback.unlink()
            rollback = None
            _fsync_directory(directory)
            _validate_regular(self.path.stat(), failure="unsafe_housefile_file")
        except Exception as exc:
            if replaced:
                try:
                    if rollback is None or not rollback.exists():
                        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.restore-", dir=directory)
                        os.close(fd)
                        rollback = Path(name)
                        rollback.unlink()
                        _new_private_file(rollback, old)
                    os.replace(rollback, self.path)
                    rollback = None
                    try:
                        _fsync_directory(directory)
                    except OSError:
                        pass
                except Exception as restore_exc:
                    raise HousefileStoreError("housefile_rollback_failed") from restore_exc
            if isinstance(exc, HousefileStoreError):
                raise
            raise HousefileStoreError("housefile_commit_failed") from exc
        finally:
            for staged in (replacement, rollback):
                if staged is not None:
                    try:
                        staged.unlink(missing_ok=True)
                    except OSError:
                        pass

    def load(self) -> dict[str, object]:
        with self.locked():
            return self.read_document_locked()

    def _require_lock(self) -> None:
        if self._lock_owner != get_ident():
            raise HousefileStoreError("housefile_lock_required")


def load(path: str | os.PathLike[str]) -> dict[str, object]:
    """Compatibility wrapper around the hardened store."""

    return HousefileStore(path).load()


def save(path: str | os.PathLike[str], data: dict[str, object]) -> None:
    """Refuse legacy direct writes; THS-0023 is the sole canonical writer."""

    del path, data
    raise HousefileStoreError("direct_housefile_write_forbidden")
