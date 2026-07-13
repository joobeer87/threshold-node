"""THS-0017 — private, durable storage for digest-only grant metadata."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from threshold.core.types import Grant, GrantStatus, Scope

try:  # The node's Linux targets provide process-safe advisory locks.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX hosts fail closed below
    fcntl = None  # type: ignore[assignment]


SCHEMA_VERSION = "ths/grant-metadata/0.2"
MAX_STORE_BYTES = 4 * 1024 * 1024
MAX_GRANTS = 1_024
MAX_ZONES_PER_GRANT = 64
MAX_NAME_LENGTH = 128
MAX_POLICY_LENGTH = 128

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TRANSACTION_ID = re.compile(r"tx-[0-9a-f]{32}\Z")
_GRANT_ID = re.compile(r"g-[A-Za-z0-9][A-Za-z0-9._-]{0,125}\Z")
_ZONE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_RFC3339_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_TOP_LEVEL_FIELDS = frozenset(
    {"schema", "revision", "grants", "ledger_witness", "pending"}
)
_GRANT_FIELDS = frozenset(
    {
        "id", "name", "kind", "scopes", "zones", "window", "expires",
        "status", "issued", "credential_digest",
    }
)
_KINDS = frozenset({"agent", "human", "humanoid"})
_TRANSACTION_KINDS = frozenset(
    {"issue", "demo_seed", "revoke", "expire", "suspend_all"}
)
_PENDING_FIELDS = frozenset(
    {
        "transaction",
        "kind",
        "base_revision",
        "target_revision",
        "ledger_offset",
        "ledger_tail_sha256",
        "target_sha256",
        "receipt_sha256",
        "event",
        "target_grants",
        "previous_statuses",
    }
)
_WITNESS_FIELDS = frozenset(
    {
        "transaction",
        "revision",
        "ledger_offset",
        "receipt_sha256",
        "target_sha256",
    }
)
_EVENT_FIELDS = frozenset(
    {"ts", "type", "agent", "detail", "transaction", "grant_revision"}
)
_EVENT_TYPES = frozenset({"GRANT", "DENY", "REVOKE", "ESTOP", "PROVISION"})


@dataclass(frozen=True)
class GrantLedgerWitness:
    """Opaque pointer to the exact ledger line committing a grant revision."""

    transaction: str
    revision: int
    ledger_offset: int
    receipt_sha256: str
    target_sha256: str


@dataclass(frozen=True)
class PendingGrantTransaction:
    """Recoverable cross-file transaction stored in the private envelope."""

    transaction: str
    kind: str
    base_revision: int
    target_revision: int
    ledger_offset: int
    ledger_tail_sha256: str
    target_sha256: str
    receipt_sha256: str
    event: dict[str, object]
    target_grants: dict[str, Grant]
    previous_statuses: dict[str, GrantStatus]


@dataclass(frozen=True)
class GrantStoreState:
    """Revisioned effective grants plus an optional recoverable transition."""

    revision: int
    grants: dict[str, Grant]
    ledger_witness: GrantLedgerWitness | None = None
    pending: PendingGrantTransaction | None = None

    @classmethod
    def empty(cls) -> "GrantStoreState":
        return cls(revision=0, grants={})


class GrantStoreError(OSError):
    """A sanitized, fail-closed grant-store boundary failure."""


class GrantMetadataStore:
    """Persist complete grant snapshots without retaining bearer credentials."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        candidate = Path(path)
        if not candidate.name or candidate.name in {".", ".."}:
            raise GrantStoreError("grant metadata store path is invalid")
        self.path = candidate.absolute()
        self._thread_lock = threading.RLock()

    def load(self) -> dict[str, Grant]:
        """Load only the effective fail-safe grant snapshot.

        A pending issue candidate is deliberately excluded. Pending restrictive
        transitions are already represented in the effective top-level grants.
        Transaction-aware callers must use :meth:`load_state`.
        """

        state = self.load_state()
        return {} if state is None else state.grants

    def load_state(self) -> GrantStoreState | None:
        """Load the revisioned envelope, distinguishing missing from empty."""

        with self._thread_lock:
            try:
                parent_fd = self._open_parent(create=False)
                if parent_fd is None:
                    return None
                try:
                    raw = self._read_target(parent_fd, missing_ok=True)
                finally:
                    os.close(parent_fd)
                return None if raw is None else self._decode_state(raw)
            except GrantStoreError:
                raise
            except (OSError, TypeError, ValueError, RecursionError):
                raise GrantStoreError("grant metadata store unavailable") from None

    def save(self, grants: Mapping[str, Grant] | Iterable[Grant]) -> None:
        """Persist a revision-zero primitive snapshot for isolated callers.

        The integrated node uses :meth:`save_state` through ``GrantAuthority``.
        This compatibility surface refuses to overwrite transaction history.
        """

        try:
            current = self.load_state()
            if current is not None and (
                current.revision != 0
                or current.ledger_witness is not None
                or current.pending is not None
            ):
                raise GrantStoreError("grant metadata transaction state is active")
            state = GrantStoreState(
                revision=0,
                grants=self._records_to_grants(self._normalize_outgoing(grants)),
            )
            encoded = self._encode_state(state)
        except GrantStoreError:
            raise
        except (TypeError, ValueError):
            raise GrantStoreError("grant metadata snapshot is invalid") from None

        with self._thread_lock:
            self._save_encoded(encoded)

    def save_state(self, state: GrantStoreState) -> None:
        """Atomically replace and fsync one validated revision envelope."""

        try:
            encoded = self._encode_state(state)
        except GrantStoreError:
            raise
        except (TypeError, ValueError, RecursionError):
            raise GrantStoreError("grant metadata snapshot is invalid") from None
        with self._thread_lock:
            self._save_encoded(encoded)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize a complete authority transaction across store instances.

        The stable private lock file covers reload/recovery, the pending store
        write, the exact ledger append, and finalization. Callers must hold this
        context for that entire sequence; individual atomic replacements are
        not a compare-and-swap boundary by themselves.
        """

        if fcntl is None:
            raise GrantStoreError("grant metadata transaction lock unavailable")
        with self._thread_lock:
            parent_fd: int | None = None
            descriptor: int | None = None
            locked = False
            try:
                parent_fd = self._open_parent(create=True)
                if parent_fd is None:  # pragma: no cover - create=True guarantees it
                    raise OSError("private directory was not created")
                name = f".{self.path.name}.lock"
                flags = os.O_RDWR | os.O_CREAT
                flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
                self._verify_private_file(descriptor)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                locked = True
                yield
            except GrantStoreError:
                raise
            except (OSError, TypeError, ValueError):
                raise GrantStoreError(
                    "grant metadata transaction lock unavailable"
                ) from None
            finally:
                if descriptor is not None:
                    if locked:
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_UN)
                        except OSError:
                            pass
                    os.close(descriptor)
                if parent_fd is not None:
                    os.close(parent_fd)

    def _save_encoded(self, encoded: bytes) -> None:
        parent_fd: int | None = None
        temporary_names: set[str] = set()
        try:
            parent_fd = self._open_parent(create=True)
            if parent_fd is None:  # pragma: no cover - create=True guarantees it
                raise OSError("private directory was not created")

            previous = self._read_target(parent_fd, missing_ok=True)
            if previous is not None:
                # Refuse to overwrite an unreadable or invalid security state.
                self._decode_state(previous)

            backup_name: str | None = None
            if previous is not None:
                backup_name = self._write_temporary(parent_fd, previous)
                temporary_names.add(backup_name)
            new_name = self._write_temporary(parent_fd, encoded)
            temporary_names.add(new_name)

            # Make rollback material durable before changing the live name.
            os.fsync(parent_fd)
            os.replace(
                new_name,
                self.path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temporary_names.discard(new_name)
            try:
                os.fsync(parent_fd)
            except OSError:
                self._rollback_replace(parent_fd, backup_name)
                if backup_name is not None:
                    temporary_names.discard(backup_name)
                raise

            if backup_name is not None:
                os.unlink(backup_name, dir_fd=parent_fd)
                temporary_names.discard(backup_name)
        except GrantStoreError:
            raise
        except (OSError, TypeError, ValueError, RecursionError):
            raise GrantStoreError("grant metadata store unavailable") from None
        finally:
            if parent_fd is not None:
                for name in temporary_names:
                    try:
                        os.unlink(name, dir_fd=parent_fd)
                    except OSError:
                        pass
                os.close(parent_fd)

    def _open_parent(self, *, create: bool) -> int | None:
        parent = self.path.parent
        self._reject_symlink_components(parent)
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            if not create:
                return None
            # Create only the private leaf. Missing ancestors are ambiguous and
            # rejected rather than recursively opened.
            try:
                parent.mkdir(mode=0o700)
                os.chmod(parent, 0o700, follow_symlinks=False)
                metadata = parent.lstat()
            except (FileExistsError, FileNotFoundError, OSError):
                raise GrantStoreError(
                    "grant metadata store directory is unsafe"
                ) from None

        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            raise GrantStoreError("grant metadata store directory is unsafe")

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(parent, flags)
        except OSError:
            raise GrantStoreError("grant metadata store directory is unsafe") from None
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
            or (hasattr(os, "geteuid") and opened.st_uid != os.geteuid())
        ):
            os.close(descriptor)
            raise GrantStoreError("grant metadata store directory is unsafe")
        return descriptor

    @staticmethod
    def _reject_symlink_components(path: Path) -> None:
        current = Path(path.anchor) if path.is_absolute() else Path()
        parts = path.parts[1:] if path.is_absolute() else path.parts
        for part in parts:
            current = current / part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    raise GrantStoreError(
                        "grant metadata store directory is unsafe"
                    )
            except FileNotFoundError:
                return

    def _read_target(self, parent_fd: int, *, missing_ok: bool) -> bytes | None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path.name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        try:
            self._verify_private_file(descriptor)
            size = os.fstat(descriptor).st_size
            if size <= 0 or size > MAX_STORE_BYTES:
                raise GrantStoreError("grant metadata store is invalid")
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise GrantStoreError("grant metadata store is invalid")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise GrantStoreError("grant metadata store is invalid")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    @staticmethod
    def _verify_private_file(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            raise GrantStoreError("grant metadata store file is unsafe")

    @staticmethod
    def _write_temporary(parent_fd: int, data: bytes) -> str:
        name = f".grants-{secrets.token_hex(16)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        try:
            os.fchmod(descriptor, 0o600)
            GrantMetadataStore._verify_private_file(descriptor)
            remaining = memoryview(data)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("grant metadata write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            try:
                os.unlink(name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
        os.close(descriptor)
        return name

    def _rollback_replace(self, parent_fd: int, backup_name: str | None) -> None:
        try:
            if backup_name is None:
                os.unlink(self.path.name, dir_fd=parent_fd)
            else:
                os.replace(
                    backup_name,
                    self.path.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
            os.fsync(parent_fd)
        except OSError:
            # The operation remains failed. Callers must treat the store as
            # unavailable until a later validated load establishes its state.
            pass

    @classmethod
    def _encode_state(cls, state: GrantStoreState) -> bytes:
        if not isinstance(state, GrantStoreState):
            raise GrantStoreError("grant metadata snapshot is invalid")
        grants = cls._normalize_outgoing(state.grants)
        witness: dict[str, object] | None = None
        if state.ledger_witness is not None:
            item = state.ledger_witness
            witness = {
                "transaction": item.transaction,
                "revision": item.revision,
                "ledger_offset": item.ledger_offset,
                "receipt_sha256": item.receipt_sha256,
                "target_sha256": item.target_sha256,
            }
        pending: dict[str, object] | None = None
        if state.pending is not None:
            item = state.pending
            pending = {
                "transaction": item.transaction,
                "kind": item.kind,
                "base_revision": item.base_revision,
                "target_revision": item.target_revision,
                "ledger_offset": item.ledger_offset,
                "ledger_tail_sha256": item.ledger_tail_sha256,
                "target_sha256": item.target_sha256,
                "receipt_sha256": item.receipt_sha256,
                "event": item.event,
                "target_grants": cls._normalize_outgoing(item.target_grants),
                "previous_statuses": {
                    grant_id: (
                        status.value if isinstance(status, GrantStatus) else status
                    )
                    for grant_id, status in sorted(item.previous_statuses.items())
                },
            }
        document = {
            "schema": SCHEMA_VERSION,
            "revision": state.revision,
            "grants": grants,
            "ledger_witness": witness,
            "pending": pending,
        }
        encoded = cls._canonical_json_line(document)
        if len(encoded) > MAX_STORE_BYTES:
            raise GrantStoreError(
                "grant metadata snapshot exceeds the local size limit"
            )
        # Validate the serialized form so dataclass callers cannot bypass the
        # same strict rules enforced during restart recovery.
        cls._decode_state(encoded)
        return encoded

    @staticmethod
    def _canonical_json_line(value: object) -> bytes:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )

    @classmethod
    def target_sha256(cls, grants: Mapping[str, Grant] | Iterable[Grant]) -> str:
        """Return a private binding for a complete target snapshot."""

        records = cls._normalize_outgoing(grants)
        return hashlib.sha256(cls._canonical_json_line(records)).hexdigest()

    @classmethod
    def _decode_state(cls, raw: bytes) -> GrantStoreState:
        def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        def reject_constant(_value: str) -> None:
            raise ValueError("non-finite JSON value")

        try:
            document = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=reject_duplicate,
                parse_constant=reject_constant,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            RecursionError,
        ):
            raise GrantStoreError("grant metadata store is invalid") from None
        if not isinstance(document, dict) or set(document) != _TOP_LEVEL_FIELDS:
            raise GrantStoreError("grant metadata store is invalid")
        if document["schema"] != SCHEMA_VERSION:
            raise GrantStoreError("grant metadata store is invalid")
        revision = document["revision"]
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 0
            or revision > 2**63 - 1
        ):
            raise GrantStoreError("grant metadata store is invalid")
        grants = cls._records_to_grants(document["grants"])
        witness = cls._decode_witness(document["ledger_witness"], revision)
        pending = cls._decode_pending(document["pending"], revision, grants)
        if revision == 0 and witness is not None:
            raise GrantStoreError("grant metadata store is invalid")
        if revision > 0 and witness is None:
            raise GrantStoreError("grant metadata store is invalid")
        return GrantStoreState(
            revision=revision,
            grants=grants,
            ledger_witness=witness,
            pending=pending,
        )

    @classmethod
    def _records_to_grants(cls, records: object) -> dict[str, Grant]:
        if not isinstance(records, list) or len(records) > MAX_GRANTS:
            raise GrantStoreError("grant metadata store is invalid")
        loaded: dict[str, Grant] = {}
        digests: set[str] = set()
        for record in records:
            normalized = cls._validate_record(record)
            grant_id = normalized["id"]
            digest = normalized["credential_digest"]
            if grant_id in loaded or digest in digests:
                raise GrantStoreError("grant metadata store is invalid")
            loaded[grant_id] = Grant(
                id=grant_id,
                name=normalized["name"],
                kind=normalized["kind"],
                scopes=tuple(Scope(scope) for scope in normalized["scopes"]),
                zones=tuple(normalized["zones"]),
                window=normalized["window"],
                expires=normalized["expires"],
                status=GrantStatus(normalized["status"]),
                issued=normalized["issued"],
                credential_digest=digest,
            )
            digests.add(digest)
        return loaded

    @classmethod
    def _decode_witness(
        cls,
        value: object,
        revision: int,
    ) -> GrantLedgerWitness | None:
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != _WITNESS_FIELDS:
            raise GrantStoreError("grant metadata store is invalid")
        transaction = value["transaction"]
        item_revision = value["revision"]
        ledger_offset = value["ledger_offset"]
        receipt_sha256 = value["receipt_sha256"]
        target_sha256 = value["target_sha256"]
        if not (
            isinstance(transaction, str)
            and _TRANSACTION_ID.fullmatch(transaction)
            and isinstance(item_revision, int)
            and not isinstance(item_revision, bool)
            and item_revision == revision
            and cls._valid_offset(ledger_offset)
            and isinstance(receipt_sha256, str)
            and _DIGEST.fullmatch(receipt_sha256)
            and isinstance(target_sha256, str)
            and _DIGEST.fullmatch(target_sha256)
        ):
            raise GrantStoreError("grant metadata store is invalid")
        return GrantLedgerWitness(
            transaction=transaction,
            revision=item_revision,
            ledger_offset=ledger_offset,
            receipt_sha256=receipt_sha256,
            target_sha256=target_sha256,
        )

    @classmethod
    def _decode_pending(
        cls,
        value: object,
        revision: int,
        effective_grants: dict[str, Grant],
    ) -> PendingGrantTransaction | None:
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != _PENDING_FIELDS:
            raise GrantStoreError("grant metadata store is invalid")
        transaction = value["transaction"]
        kind = value["kind"]
        base_revision = value["base_revision"]
        target_revision = value["target_revision"]
        ledger_offset = value["ledger_offset"]
        ledger_tail_sha256 = value["ledger_tail_sha256"]
        target_sha256 = value["target_sha256"]
        receipt_sha256 = value["receipt_sha256"]
        event = value["event"]
        previous_statuses = value["previous_statuses"]
        valid_header = (
            isinstance(transaction, str)
            and _TRANSACTION_ID.fullmatch(transaction) is not None
            and isinstance(kind, str)
            and kind in _TRANSACTION_KINDS
            and isinstance(base_revision, int)
            and not isinstance(base_revision, bool)
            and base_revision == revision
            and isinstance(target_revision, int)
            and not isinstance(target_revision, bool)
            and target_revision == base_revision + 1
            and cls._valid_offset(ledger_offset)
            and isinstance(ledger_tail_sha256, str)
            and _DIGEST.fullmatch(ledger_tail_sha256) is not None
            and isinstance(target_sha256, str)
            and _DIGEST.fullmatch(target_sha256) is not None
            and isinstance(receipt_sha256, str)
            and _DIGEST.fullmatch(receipt_sha256) is not None
        )
        if not valid_header:
            raise GrantStoreError("grant metadata store is invalid")
        normalized_event = cls._validate_event(event, transaction, target_revision)
        if hashlib.sha256(cls._canonical_json_line(normalized_event)).hexdigest() != receipt_sha256:
            raise GrantStoreError("grant metadata store is invalid")
        target_grants = cls._records_to_grants(value["target_grants"])
        if cls.target_sha256(target_grants) != target_sha256:
            raise GrantStoreError("grant metadata store is invalid")
        statuses = cls._decode_previous_statuses(previous_statuses)
        cls._validate_pending_semantics(
            kind,
            effective_grants,
            target_grants,
            statuses,
            normalized_event,
        )
        return PendingGrantTransaction(
            transaction=transaction,
            kind=kind,
            base_revision=base_revision,
            target_revision=target_revision,
            ledger_offset=ledger_offset,
            ledger_tail_sha256=ledger_tail_sha256,
            target_sha256=target_sha256,
            receipt_sha256=receipt_sha256,
            event=normalized_event,
            target_grants=target_grants,
            previous_statuses=statuses,
        )

    @classmethod
    def _validate_event(
        cls,
        event: object,
        transaction: str,
        revision: int,
    ) -> dict[str, object]:
        if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
            raise GrantStoreError("grant metadata store is invalid")
        timestamp = event["ts"]
        event_type = event["type"]
        agent = event["agent"]
        detail = event["detail"]
        if not (
            isinstance(timestamp, str)
            and cls._valid_timestamp(timestamp)
            and isinstance(event_type, str)
            and event_type in _EVENT_TYPES
            and cls._bounded_text(agent, MAX_NAME_LENGTH)
            and isinstance(detail, str)
            and len(detail) <= MAX_POLICY_LENGTH
            and all(character.isprintable() for character in detail)
            and event["transaction"] == transaction
            and event["grant_revision"] == revision
        ):
            raise GrantStoreError("grant metadata store is invalid")
        return dict(event)

    @staticmethod
    def _decode_previous_statuses(value: object) -> dict[str, GrantStatus]:
        if not isinstance(value, dict) or len(value) > MAX_GRANTS:
            raise GrantStoreError("grant metadata store is invalid")
        result: dict[str, GrantStatus] = {}
        for grant_id, status in value.items():
            if not (
                isinstance(grant_id, str)
                and _GRANT_ID.fullmatch(grant_id)
                and isinstance(status, str)
            ):
                raise GrantStoreError("grant metadata store is invalid")
            try:
                result[grant_id] = GrantStatus(status)
            except ValueError:
                raise GrantStoreError("grant metadata store is invalid") from None
        return result

    @classmethod
    def _validate_pending_semantics(
        cls,
        kind: str,
        effective: dict[str, Grant],
        target: dict[str, Grant],
        previous: dict[str, GrantStatus],
        event: dict[str, object],
    ) -> None:
        expected_event = {
            "issue": "GRANT",
            "demo_seed": "PROVISION",
            "revoke": "REVOKE",
            "expire": "DENY",
            "suspend_all": "ESTOP",
        }[kind]
        if event["type"] != expected_event:
            raise GrantStoreError("grant metadata store is invalid")
        if kind in {"issue", "demo_seed"}:
            if previous:
                raise GrantStoreError("grant metadata store is invalid")
            effective_records = cls._normalize_outgoing(effective)
            target_records = cls._normalize_outgoing(target)
            effective_map = {item["id"]: item for item in effective_records}
            target_map = {item["id"]: item for item in target_records}
            added = set(target_map) - set(effective_map)
            if (
                set(effective_map) - set(target_map)
                or any(target_map[key] != value for key, value in effective_map.items())
                or (kind == "issue" and len(added) != 1)
                or (kind == "demo_seed" and (effective_map or not added))
                or any(target_map[key]["status"] != GrantStatus.ACTIVE.value for key in added)
            ):
                raise GrantStoreError("grant metadata store is invalid")
            return

        if set(effective) != set(target) or cls.target_sha256(effective) != cls.target_sha256(target):
            raise GrantStoreError("grant metadata store is invalid")
        if not previous or set(previous) - set(target):
            raise GrantStoreError("grant metadata store is invalid")
        expected_to = {
            "revoke": GrantStatus.REVOKED,
            "expire": GrantStatus.EXPIRED,
            "suspend_all": GrantStatus.SUSPENDED,
        }[kind]
        allowed_from = {
            "revoke": {GrantStatus.ACTIVE, GrantStatus.SUSPENDED},
            "expire": {GrantStatus.ACTIVE},
            "suspend_all": {GrantStatus.ACTIVE},
        }[kind]
        if any(
            before not in allowed_from or target[grant_id].status != expected_to
            for grant_id, before in previous.items()
        ):
            raise GrantStoreError("grant metadata store is invalid")
        if kind in {"revoke", "expire"} and len(previous) != 1:
            raise GrantStoreError("grant metadata store is invalid")

    @staticmethod
    def _valid_offset(value: object) -> bool:
        return bool(
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= 2**63 - 1
        )

    @staticmethod
    def _normalize_outgoing(
        grants: Mapping[str, Grant] | Iterable[Grant],
    ) -> list[dict[str, object]]:
        if isinstance(grants, Mapping):
            items = list(grants.items())
            records = [grant for _key, grant in items]
            if any(
                not isinstance(key, str)
                or not isinstance(grant, Grant)
                or key != grant.id
                for key, grant in items
            ):
                raise GrantStoreError("grant metadata snapshot is invalid")
        else:
            if isinstance(grants, (str, bytes, bytearray)):
                raise GrantStoreError("grant metadata snapshot is invalid")
            records = list(grants)
        if len(records) > MAX_GRANTS or not all(
            isinstance(grant, Grant) for grant in records
        ):
            raise GrantStoreError("grant metadata snapshot is invalid")

        normalized: list[dict[str, object]] = []
        identifiers: set[str] = set()
        digests: set[str] = set()
        for grant in records:
            candidate: dict[str, object] = {
                "id": grant.id,
                "name": grant.name,
                "kind": grant.kind,
                "scopes": [
                    scope.value if isinstance(scope, Scope) else scope
                    for scope in grant.scopes
                ],
                "zones": list(grant.zones),
                "window": grant.window,
                "expires": grant.expires,
                "status": (
                    grant.status.value
                    if isinstance(grant.status, GrantStatus)
                    else grant.status
                ),
                "issued": grant.issued,
                "credential_digest": grant.credential_digest,
            }
            valid = GrantMetadataStore._validate_record(candidate)
            identifier = valid["id"]
            digest = valid["credential_digest"]
            if identifier in identifiers or digest in digests:
                raise GrantStoreError("grant metadata snapshot is invalid")
            identifiers.add(identifier)
            digests.add(digest)
            normalized.append(valid)
        return sorted(normalized, key=lambda record: record["id"])

    @staticmethod
    def _validate_record(record: object) -> dict[str, Any]:
        if not isinstance(record, dict) or set(record) != _GRANT_FIELDS:
            raise GrantStoreError("grant metadata store is invalid")

        grant_id = record["id"]
        name = record["name"]
        kind = record["kind"]
        scopes = record["scopes"]
        zones = record["zones"]
        window = record["window"]
        expires = record["expires"]
        status = record["status"]
        issued = record["issued"]
        digest = record["credential_digest"]
        allowed_scopes = {scope.value for scope in Scope}

        valid = (
            isinstance(grant_id, str)
            and _GRANT_ID.fullmatch(grant_id) is not None
            and GrantMetadataStore._bounded_text(name, MAX_NAME_LENGTH)
            and isinstance(kind, str)
            and kind in _KINDS
            and isinstance(scopes, list)
            and 1 <= len(scopes) <= len(allowed_scopes)
            and all(isinstance(scope, str) and scope in allowed_scopes for scope in scopes)
            and len(set(scopes)) == len(scopes)
            and isinstance(zones, list)
            and 1 <= len(zones) <= MAX_ZONES_PER_GRANT
            and all(
                isinstance(zone, str) and _ZONE_ID.fullmatch(zone) is not None
                for zone in zones
            )
            and len(set(zones)) == len(zones)
            and isinstance(window, str)
            and GrantMetadataStore._valid_window(window)
            and isinstance(expires, str)
            and (
                expires == "revocable"
                or GrantMetadataStore._valid_timestamp(expires)
            )
            and isinstance(status, str)
            and status in {item.value for item in GrantStatus}
            and isinstance(issued, str)
            and GrantMetadataStore._valid_timestamp(issued)
            and isinstance(digest, str)
            and _DIGEST.fullmatch(digest) is not None
        )
        if not valid:
            raise GrantStoreError("grant metadata store is invalid")

        return {
            "id": grant_id,
            "name": name,
            "kind": kind,
            "scopes": list(scopes),
            "zones": list(zones),
            "window": window,
            "expires": expires,
            "status": status,
            "issued": issued,
            "credential_digest": digest,
        }

    @staticmethod
    def _bounded_text(value: object, maximum: int) -> bool:
        return bool(
            isinstance(value, str)
            and 1 <= len(value) <= maximum
            and all(character.isprintable() for character in value)
        )

    @staticmethod
    def _valid_timestamp(value: str) -> bool:
        if len(value) > MAX_POLICY_LENGTH or not _RFC3339_TIMESTAMP.fullmatch(value):
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return parsed.tzinfo is not None and parsed.utcoffset() is not None

    @staticmethod
    def _valid_window(value: str) -> bool:
        if value == "standing":
            return True
        if len(value) > MAX_POLICY_LENGTH:
            return False
        parts = value.split("/")
        if len(parts) != 2 or not all(
            GrantMetadataStore._valid_timestamp(part) for part in parts
        ):
            return False
        start = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        end = datetime.fromisoformat(parts[1].replace("Z", "+00:00"))
        return start < end
