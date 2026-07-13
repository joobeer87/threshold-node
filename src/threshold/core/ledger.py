"""THS-0016 — durable, append-only JSONL event ledger."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
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
CHECKPOINT_TAIL_BYTES = 64 * 1024
ALLOWED_EVENT_TYPES = frozenset(event_type.value for event_type in EventType)
_MISSING = object()
_TRANSACTION_ID = re.compile(r"tx-[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


@dataclass(frozen=True)
class LedgerCheckpoint:
    """Exact append precondition captured before a grant transaction."""

    offset: int
    tail_sha256: str


@dataclass(frozen=True)
class PreparedLedgerEvent:
    """Canonical event bytes bound to an exact ledger checkpoint."""

    entry: dict[str, object]
    encoded: bytes
    checkpoint: LedgerCheckpoint

    @property
    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.encoded).hexdigest()


@dataclass(frozen=True)
class LedgerWitness:
    """Minimum data needed to verify a committed grant revision."""

    transaction: str
    grant_revision: int
    ledger_offset: int
    receipt_sha256: str


class JsonlLedger:
    """Small local ledger with transactional appends and bounded tail reads.

    Event payloads are reduced to the THS-0.1 ledger fields. This prevents an
    unrelated event field from accidentally persisting credentials or raw
    adapter payloads. The format is durable but not tamper-evident.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).absolute()
        self._thread_lock = threading.RLock()

    def append(self, entry: Mapping[str, object]) -> dict[str, object]:
        """Append one canonical event and fsync it before returning.

        If a write or fsync fails, the ledger is truncated back to the
        pre-append boundary while the exclusive lock is held. Direct callers
        receive the failure so a policy boundary can fail closed.
        """

        event_type = entry.get("type")
        normalized = self._normalize(event_type, entry, strict=False)
        encoded = self._encode_entry(normalized)

        with self._thread_lock:
            parent = self.path.parent
            self._verify_private_parent(create=True)

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

    def prepare_event(self, entry: Mapping[str, object]) -> PreparedLedgerEvent:
        """Canonicalize one event and bind it to the current durable tail."""

        normalized = self._normalize(entry.get("type"), entry, strict=False)
        encoded = self._encode_entry(normalized)
        checkpoint = self._checkpoint()
        return PreparedLedgerEvent(normalized, encoded, checkpoint)

    def rebuild_prepared_event(
        self,
        entry: Mapping[str, object],
        *,
        ledger_offset: int,
        ledger_tail_sha256: str,
        receipt_sha256: str,
    ) -> PreparedLedgerEvent:
        """Reconstruct and validate a pending event during restart recovery."""

        normalized = self._normalize(entry.get("type"), entry, strict=True)
        encoded = self._encode_entry(normalized)
        if not (
            isinstance(ledger_offset, int)
            and not isinstance(ledger_offset, bool)
            and ledger_offset >= 0
            and isinstance(ledger_tail_sha256, str)
            and _DIGEST.fullmatch(ledger_tail_sha256)
            and isinstance(receipt_sha256, str)
            and _DIGEST.fullmatch(receipt_sha256)
            and hashlib.sha256(encoded).hexdigest() == receipt_sha256
        ):
            raise OSError("ledger transaction metadata is invalid")
        return PreparedLedgerEvent(
            normalized,
            encoded,
            LedgerCheckpoint(ledger_offset, ledger_tail_sha256),
        )

    def append_prepared(self, prepared: PreparedLedgerEvent) -> dict[str, object]:
        """Append exact bytes only when the durable tail still matches."""

        if not isinstance(prepared, PreparedLedgerEvent):
            raise OSError("ledger transaction metadata is invalid")
        normalized = self._normalize(
            prepared.entry.get("type"), prepared.entry, strict=True
        )
        if self._encode_entry(normalized) != prepared.encoded:
            raise OSError("ledger transaction metadata is invalid")

        with self._thread_lock:
            parent = self.path.parent
            self._verify_private_parent(create=True)
            descriptor = os.open(self.path, self._write_flags(), 0o600)
            original_size: int | None = None
            try:
                self._verify_regular_private_file(descriptor)
                os.fchmod(descriptor, 0o600)
                self._file_lock(descriptor, exclusive=True)
                self._repair_incomplete_tail(descriptor)
                original_size = os.fstat(descriptor).st_size
                if not self._checkpoint_matches(descriptor, prepared.checkpoint):
                    raise OSError("ledger transaction precondition changed")
                try:
                    self._write_all(descriptor, prepared.encoded)
                    os.fsync(descriptor)
                    self._fsync_parent(parent)
                except OSError:
                    self._rollback(descriptor, original_size)
                    raise
            finally:
                self._file_unlock(descriptor)
                os.close(descriptor)
        return normalized

    def inspect_prepared(self, prepared: PreparedLedgerEvent) -> bool:
        """Return exact-receipt presence; mismatches are ambiguous failures."""

        with self._thread_lock:
            descriptor: int | None = None
            try:
                self._verify_private_parent(create=False)
                descriptor = os.open(self.path, self._read_flags())
                self._verify_regular_private_file(descriptor)
                self._file_lock(descriptor, exclusive=False)
                size = os.fstat(descriptor).st_size
                checkpoint = prepared.checkpoint
                if size < checkpoint.offset:
                    raise OSError("ledger transaction history is unavailable")
                if self._checkpoint_digest(descriptor, checkpoint.offset) != (
                    checkpoint.tail_sha256
                ):
                    raise OSError("ledger transaction history is ambiguous")
                if size == checkpoint.offset:
                    return False
                observed = os.pread(
                    descriptor,
                    len(prepared.encoded),
                    checkpoint.offset,
                )
                if observed != prepared.encoded:
                    raise OSError("ledger transaction history is ambiguous")
                return True
            except FileNotFoundError:
                empty_digest = self._empty_checkpoint_digest()
                if (
                    prepared.checkpoint.offset == 0
                    and prepared.checkpoint.tail_sha256 == empty_digest
                ):
                    return False
                raise OSError("ledger transaction history is unavailable") from None
            finally:
                if descriptor is not None:
                    self._file_unlock(descriptor)
                    os.close(descriptor)

    def verify_witness(self, witness: LedgerWitness) -> None:
        """Verify the exact ledger line that committed a clean store revision."""

        if not (
            isinstance(witness, LedgerWitness)
            and _TRANSACTION_ID.fullmatch(witness.transaction)
            and isinstance(witness.grant_revision, int)
            and not isinstance(witness.grant_revision, bool)
            and witness.grant_revision > 0
            and isinstance(witness.ledger_offset, int)
            and not isinstance(witness.ledger_offset, bool)
            and witness.ledger_offset >= 0
            and _DIGEST.fullmatch(witness.receipt_sha256)
        ):
            raise OSError("ledger witness is invalid")
        with self._thread_lock:
            self._verify_private_parent(create=False)
            descriptor = os.open(self.path, self._read_flags())
            try:
                self._verify_regular_private_file(descriptor)
                self._file_lock(descriptor, exclusive=False)
                data = os.pread(
                    descriptor,
                    MAX_ENTRY_BYTES + 1,
                    witness.ledger_offset,
                )
                newline = data.find(b"\n")
                if newline < 0 or newline >= MAX_ENTRY_BYTES:
                    raise OSError("ledger witness is unavailable")
                encoded = data[: newline + 1]
                if hashlib.sha256(encoded).hexdigest() != witness.receipt_sha256:
                    raise OSError("ledger witness is invalid")
                try:
                    parsed = json.loads(encoded.decode("utf-8"))
                    normalized = self._normalize(
                        parsed.get("type") if isinstance(parsed, dict) else None,
                        parsed,
                        strict=True,
                    )
                except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    raise OSError("ledger witness is invalid") from None
                if (
                    normalized.get("transaction") != witness.transaction
                    or normalized.get("grant_revision") != witness.grant_revision
                    or self._encode_entry(normalized) != encoded
                ):
                    raise OSError("ledger witness is invalid")
            finally:
                self._file_unlock(descriptor)
                os.close(descriptor)

    def has_history(self) -> bool:
        """Return whether any durable ledger bytes predate a missing grant store."""

        with self._thread_lock:
            descriptor: int | None = None
            try:
                self._verify_private_parent(create=False)
                descriptor = os.open(self.path, self._read_flags())
                self._verify_regular_private_file(descriptor)
                return os.fstat(descriptor).st_size > 0
            except FileNotFoundError:
                return False
            finally:
                if descriptor is not None:
                    os.close(descriptor)

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
                self._verify_private_parent(create=False)
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
    def _encode_entry(entry: Mapping[str, object]) -> bytes:
        encoded = (
            json.dumps(
                entry,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        if len(encoded) > MAX_ENTRY_BYTES:
            raise ValueError("ledger entry exceeds the local size limit")
        return encoded

    def _checkpoint(self) -> LedgerCheckpoint:
        with self._thread_lock:
            parent = self.path.parent
            self._verify_private_parent(create=True)
            descriptor = os.open(self.path, self._write_flags(), 0o600)
            try:
                self._verify_regular_private_file(descriptor)
                os.fchmod(descriptor, 0o600)
                self._file_lock(descriptor, exclusive=True)
                self._repair_incomplete_tail(descriptor)
                os.fsync(descriptor)
                self._fsync_parent(parent)
                offset = os.fstat(descriptor).st_size
                return LedgerCheckpoint(
                    offset=offset,
                    tail_sha256=self._checkpoint_digest(descriptor, offset),
                )
            finally:
                self._file_unlock(descriptor)
                os.close(descriptor)

    @staticmethod
    def _empty_checkpoint_digest() -> str:
        return hashlib.sha256((0).to_bytes(8, "big")).hexdigest()

    @staticmethod
    def _checkpoint_digest(descriptor: int, offset: int) -> str:
        length = min(offset, CHECKPOINT_TAIL_BYTES)
        start = offset - length
        data = os.pread(descriptor, length, start) if length else b""
        return hashlib.sha256(offset.to_bytes(8, "big") + data).hexdigest()

    @classmethod
    def _checkpoint_matches(
        cls,
        descriptor: int,
        checkpoint: LedgerCheckpoint,
    ) -> bool:
        size = os.fstat(descriptor).st_size
        return bool(
            size == checkpoint.offset
            and cls._checkpoint_digest(descriptor, size) == checkpoint.tail_sha256
        )

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
        transaction = payload.get("transaction", _MISSING)
        grant_revision = payload.get("grant_revision", _MISSING)
        if (transaction is _MISSING) != (grant_revision is _MISSING):
            raise ValueError("ledger transaction metadata is incomplete")
        if transaction is not _MISSING:
            if not (
                isinstance(transaction, str)
                and _TRANSACTION_ID.fullmatch(transaction)
                and isinstance(grant_revision, int)
                and not isinstance(grant_revision, bool)
                and 0 < grant_revision <= 2**63 - 1
            ):
                raise ValueError("ledger transaction metadata is invalid")
            normalized["transaction"] = transaction
            normalized["grant_revision"] = grant_revision
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
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise OSError("ledger target permissions are not private")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise OSError("ledger target has unexpected ownership")

    def _verify_private_parent(self, *, create: bool) -> bool:
        parent = self.path.parent
        self._reject_symlink_components(parent)
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            if not create:
                return False
            try:
                parent.mkdir(mode=0o700)
                metadata = parent.lstat()
            except (FileExistsError, FileNotFoundError, OSError):
                raise OSError("ledger parent directory is unsafe") from None
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            raise OSError("ledger parent directory is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(parent, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or stat.S_IMODE(opened.st_mode) != 0o700
                or (hasattr(os, "geteuid") and opened.st_uid != os.geteuid())
            ):
                raise OSError("ledger parent directory is unsafe")
        finally:
            os.close(descriptor)
        return True

    @staticmethod
    def _reject_symlink_components(path: Path) -> None:
        current = Path(path.anchor) if path.is_absolute() else Path()
        parts = path.parts[1:] if path.is_absolute() else path.parts
        for part in parts:
            current = current / part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    raise OSError("ledger parent directory is unsafe")
            except FileNotFoundError:
                return

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
