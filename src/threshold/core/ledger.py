"""THS-0016 — durable, append-only JSONL event ledger."""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import threading
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from threshold.core.types import EventType

try:  # Jetson/Linux provides process-safe advisory file locks.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX development fallback
    fcntl = None  # type: ignore[assignment]


log = logging.getLogger("threshold.ledger")

DEFAULT_READ_LIMIT = 100
MAX_READ_LIMIT = 1_000
MAX_ENTRY_BYTES = 256 * 1024
MAX_READ_BYTES = 4 * 1024 * 1024
ALLOWED_EVENT_TYPES = frozenset(event_type.value for event_type in EventType)
_MISSING = object()
_RFC3339_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


class JsonlLedger:
    """Small local ledger with transactional appends and bounded tail reads.

    Event payloads are reduced to the THS-0.1 ledger fields. This prevents an
    unrelated event field from accidentally persisting credentials or raw
    adapter payloads. The format is durable but not tamper-evident.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._thread_lock = threading.RLock()

    def append(self, entry: Mapping[str, object]) -> dict[str, object]:
        """Append one canonical event and fsync it before returning.

        If a write or fsync fails, the ledger is truncated back to the
        pre-append boundary while the exclusive lock is held. Direct callers
        receive the failure so a policy boundary can fail closed.
        """

        event_type = entry.get("type")
        normalized = self._normalize(event_type, entry, strict=False)
        encoded = (
            json.dumps(
                normalized,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        if len(encoded) > MAX_ENTRY_BYTES:
            raise ValueError("ledger entry exceeds the local size limit")

        with self._thread_lock:
            parent = self.path.parent
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if parent.is_symlink():
                raise OSError("ledger parent is not a direct directory")

            descriptor = os.open(self.path, self._write_flags(), 0o600)
            original_size: int | None = None
            try:
                self._verify_regular_private_file(descriptor)
                os.fchmod(descriptor, 0o600)
                self._file_lock(descriptor, exclusive=True)
                self._repair_incomplete_tail(descriptor)
                original_size = os.fstat(descriptor).st_size
                try:
                    self._write_all(descriptor, encoded)
                    os.fsync(descriptor)
                    self._fsync_parent(parent)
                except OSError:
                    self._rollback(descriptor, original_size)
                    raise
            finally:
                self._file_unlock(descriptor)
                os.close(descriptor)
        return normalized

    def record_event(
        self,
        event_type: str | Enum,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        """Normalize and durably append one EventBus event."""

        return self.append({**payload, "type": event_type})

    def handle_event(self, event_type: str, payload: dict[str, object]) -> None:
        """Wildcard EventBus handler that never lets ledger I/O crash the bus."""

        try:
            self.record_event(event_type, payload)
        except (OSError, TypeError, ValueError):
            # Do not include paths, payloads, or exception text in logs.
            log.error("ledger event append failed")

    def attach(self, bus: Any) -> "JsonlLedger":
        """Attach this ledger as the bus wildcard subscriber."""

        bus.on("*", self.handle_event)
        return self

    def read(
        self,
        limit: int = DEFAULT_READ_LIMIT,
        *,
        fail_on_unavailable: bool = False,
    ) -> list[dict[str, object]]:
        """Return valid entries from a bounded tail window, newest first.

        Missing files mean an empty ledger. Malformed rows are skipped without
        inventing fields. Other filesystem failures either return an empty list
        for best-effort diagnostics or raise a generic error for API callers.
        """

        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return []
        bounded_limit = min(limit, MAX_READ_LIMIT)
        entries: deque[dict[str, object]] = deque(maxlen=bounded_limit)

        with self._thread_lock:
            descriptor: int | None = None
            try:
                descriptor = os.open(self.path, self._read_flags())
                self._verify_regular_private_file(descriptor)
                self._file_lock(descriptor, exclusive=False)
                for raw_line in self._tail_lines(descriptor):
                    if not raw_line.strip() or len(raw_line) > MAX_ENTRY_BYTES:
                        continue
                    try:
                        parsed = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    try:
                        entries.append(
                            self._normalize(parsed.get("type"), parsed, strict=True)
                        )
                    except (TypeError, ValueError):
                        continue
            except FileNotFoundError:
                return []
            except OSError:
                log.warning("ledger read unavailable")
                if fail_on_unavailable:
                    raise OSError("ledger read unavailable") from None
                return []
            finally:
                if descriptor is not None:
                    self._file_unlock(descriptor)
                    os.close(descriptor)

        return list(reversed(entries))

    @staticmethod
    def _normalize(
        event_type: object,
        payload: Mapping[str, object],
        *,
        strict: bool,
    ) -> dict[str, object]:
        if isinstance(event_type, Enum):
            event_type = event_type.value
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("ledger event type is required")
        event_name = event_type.strip()
        if event_name not in ALLOWED_EVENT_TYPES:
            raise ValueError("ledger event type is not recognized")

        timestamp = payload.get("ts", _MISSING)
        if timestamp is _MISSING and not strict:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError("ledger timestamp is required")
        JsonlLedger._validate_timestamp(timestamp)

        agent = payload.get("agent", _MISSING)
        if agent is _MISSING and not strict:
            agent = "system"
        if not isinstance(agent, str) or not agent:
            raise ValueError("ledger agent is required")

        detail = payload.get("detail", _MISSING)
        if detail is _MISSING and not strict:
            detail = ""
        if not isinstance(detail, str):
            raise ValueError("ledger detail is required")

        normalized: dict[str, object] = {
            "ts": timestamp,
            "type": event_name,
            "agent": agent,
            "detail": detail,
        }
        tier = payload.get("tier", _MISSING)
        if isinstance(tier, Enum):
            tier = tier.value
        if tier is not _MISSING:
            if not isinstance(tier, str) or not tier:
                raise ValueError("ledger tier is invalid")
            normalized["tier"] = tier
        return normalized

    @staticmethod
    def _validate_timestamp(value: str) -> None:
        if not _RFC3339_TIMESTAMP.fullmatch(value):
            raise ValueError("ledger timestamp is invalid")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("ledger timestamp is invalid") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("ledger timestamp must include a timezone")

    @staticmethod
    def _write_flags() -> int:
        flags = os.O_APPEND | os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    @staticmethod
    def _read_flags() -> int:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    @staticmethod
    def _verify_regular_private_file(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("ledger target is not a regular file")
        if metadata.st_nlink != 1:
            raise OSError("ledger target has unexpected links")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise OSError("ledger target has unexpected ownership")

    @staticmethod
    def _repair_incomplete_tail(descriptor: int) -> None:
        size = os.fstat(descriptor).st_size
        if size == 0 or os.pread(descriptor, 1, size - 1) == b"\n":
            return

        scan_size = min(size, MAX_ENTRY_BYTES)
        start = size - scan_size
        chunk = os.pread(descriptor, scan_size, start)
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            boundary = start + newline + 1
        elif start == 0:
            boundary = 0
        elif os.pread(descriptor, 1, start - 1) == b"\n":
            boundary = start
        else:
            raise OSError("ledger incomplete tail exceeds the recovery limit")
        os.ftruncate(descriptor, boundary)
        os.fsync(descriptor)

    @staticmethod
    def _rollback(descriptor: int, original_size: int) -> None:
        try:
            os.ftruncate(descriptor, original_size)
            os.fsync(descriptor)
        except OSError:
            # The caller still fails closed. A later append repairs an incomplete tail.
            pass

    @staticmethod
    def _fsync_parent(parent: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(parent, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _tail_lines(descriptor: int) -> list[bytes]:
        size = os.fstat(descriptor).st_size
        if size == 0:
            return []
        read_size = min(size, MAX_READ_BYTES)
        start = size - read_size
        data = os.pread(descriptor, read_size, start)

        if start > 0 and os.pread(descriptor, 1, start - 1) != b"\n":
            first_newline = data.find(b"\n")
            if first_newline < 0:
                return []
            data = data[first_newline + 1 :]
        if not data.endswith(b"\n"):
            last_newline = data.rfind(b"\n")
            if last_newline < 0:
                return []
            data = data[: last_newline + 1]
        return data.splitlines()

    @staticmethod
    def _write_all(descriptor: int, data: bytes) -> None:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("ledger append made no progress")
            remaining = remaining[written:]

    @staticmethod
    def _file_lock(descriptor: int, *, exclusive: bool) -> None:
        if fcntl is not None:
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(descriptor, operation)

    @staticmethod
    def _file_unlock(descriptor: int) -> None:
        if fcntl is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
