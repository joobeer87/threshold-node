"""THS-0043 — deterministic synthetic receipt and PNG fallback primitives.

This module does not subscribe to events, print, or choose an output path.  Callers
must explicitly build an allowlisted receipt and may then persist its deterministic
PNG representation to a private, write-once path.
"""

from __future__ import annotations

import binascii
import hashlib
import os
import re
import stat
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_WIDTH = 384
PNG_HEIGHT = 256

_MARGIN = 12
_FONT_SCALE = 2
_CHAR_ADVANCE = 6 * _FONT_SCALE
_LINE_ADVANCE = 8 * _FONT_SCALE
_MAX_COLUMNS = (PNG_WIDTH - (2 * _MARGIN)) // _CHAR_ADVANCE
_MAX_LINES = (PNG_HEIGHT - (2 * _MARGIN)) // _LINE_ADVANCE
_EVENT_TYPES = frozenset({"GRANT", "DENY", "ESTOP"})
_HEADER = "THRESHOLD / SYNTHETIC DEMO"
_FOOTER = ("SIMULATED SOFTWARE PATH", "NOT A SAFETY SYSTEM")
_LABEL = re.compile(r"[A-Z0-9][A-Z0-9 ._:/#-]*\Z")
_PRIVATE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,123}\.png\Z")
_SENSITIVE_TERMS = re.compile(
    r"(?:AUTHORIZATION|BEARER|CREDENTIAL|DIGEST|RAW[ _-]?PAYLOAD|SECRET|TOKEN)"
)

_SCOPE_LABELS = {
    "read:layout": "LAYOUT",
    "read:systems": "SYSTEMS",
    "read:inventory": "INVENTORY",
    "command:navigate": "NAV",
    "command:manipulate": "MANIP",
}
_TIERS = frozenset({"ADVISORY", "ENFORCED", "GATED"})
_DENY_REASONS = {
    "adapter-unavailable": "ADAPTER UNAVAILABLE",
    "grant-inactive": "GRANT INACTIVE",
    "invalid-policy": "POLICY UNAVAILABLE",
    "no-go": "NO-GO",
    "quiet-hours": "QUIET HOURS",
    "scope-denied": "SCOPE DENIED",
}

# Fixed 5x7 glyphs.  Each integer is one five-bit row, most-significant bit left.
# The table deliberately covers only the ASCII alphabet emitted by this module.
_FONT: dict[str, tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "#": (10, 31, 10, 10, 31, 10, 0),
    ",": (0, 0, 0, 0, 4, 4, 8),
    "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 4, 4),
    "/": (1, 2, 2, 4, 8, 8, 16),
    ":": (0, 4, 4, 0, 4, 4, 0),
    "_": (0, 0, 0, 0, 0, 0, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (14, 17, 1, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (15, 16, 16, 16, 16, 16, 15),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 14),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (31, 4, 4, 4, 4, 4, 31),
    "J": (1, 1, 1, 1, 17, 17, 14),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
}


class ReceiptValidationError(ValueError):
    """A sanitized receipt field failed the public synthetic template."""


class ReceiptStorageError(OSError):
    """The optional private receipt sink could not be used safely."""


_RECEIPT_FACTORY_SEAL = object()


def _validate_receipt_layout(event_type: object, lines: object) -> tuple[str, ...]:
    if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
        raise ReceiptValidationError("receipt event type is invalid")
    if (
        not isinstance(lines, tuple)
        or not lines
        or lines[0] != _HEADER
        or len(lines) > _MAX_LINES
    ):
        raise ReceiptValidationError("receipt layout is invalid")
    for line in lines:
        if (
            not isinstance(line, str)
            or len(line) > _MAX_COLUMNS
            or any(character not in _FONT for character in line)
            or _SENSITIVE_TERMS.search(line)
        ):
            raise ReceiptValidationError("receipt layout is invalid")
    return lines


def _receipt_integrity(event_type: str, lines: tuple[str, ...]) -> str:
    canonical = f"{event_type}\n" + "\n".join(lines) + "\n"
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass(frozen=True, init=False)
class SyntheticReceipt:
    """Factory-created synthetic receipt ready for text or bitmap output."""

    event_type: str
    lines: tuple[str, ...]
    _integrity_sha256: str = field(repr=False, compare=False)

    def __init__(
        self,
        event_type: str,
        lines: tuple[str, ...],
        *,
        _seal: object | None = None,
    ) -> None:
        if _seal is not _RECEIPT_FACTORY_SEAL:
            raise ReceiptValidationError("receipt construction is invalid")
        normalized = _validate_receipt_layout(event_type, lines)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "lines", normalized)
        object.__setattr__(
            self,
            "_integrity_sha256",
            _receipt_integrity(event_type, normalized),
        )

    def _validate_integrity(self) -> None:
        normalized = _validate_receipt_layout(self.event_type, self.lines)
        observed = getattr(self, "_integrity_sha256", None)
        if not isinstance(observed, str) or observed != _receipt_integrity(
            self.event_type,
            normalized,
        ):
            raise ReceiptValidationError("receipt integrity is invalid")

    @property
    def text(self) -> str:
        """Return canonical ASCII text with one final newline."""

        self._validate_integrity()
        return "\n".join(self.lines) + "\n"

    def text_bytes(self) -> bytes:
        return self.text.encode("ascii")


def build_receipt(
    event_type: str | Enum,
    *,
    occurred_at: datetime,
    sequence: int,
    actor: str,
    scopes: Iterable[str | Enum] = (),
    zones: Iterable[str] = (),
    tier: str | Enum | None = None,
    reason: str | None = None,
) -> SyntheticReceipt:
    """Build one pure GRANT, DENY, or ESTOP synthetic receipt.

    The signature is the complete input allowlist.  It intentionally has no
    credential, digest, arbitrary detail, or raw-payload field.
    """

    kind = _enum_value(event_type)
    if not isinstance(kind, str) or kind not in _EVENT_TYPES:
        raise ReceiptValidationError("receipt event type is invalid")
    timestamp = _timestamp_label(occurred_at)
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not 1 <= sequence <= 999_999
    ):
        raise ReceiptValidationError("receipt sequence is invalid")
    actor_label = _safe_label(actor, field="actor", maximum=22)
    scope_labels = _normalize_scopes(scopes)
    zone_labels = _normalize_zones(zones)
    tier_label = _enum_value(tier) if tier is not None else None
    if tier_label is not None and not isinstance(tier_label, str):
        raise ReceiptValidationError("receipt tier is invalid")

    lines = [
        _HEADER,
        f"{timestamp} #{sequence:06d}",
        f"{kind}: {actor_label}",
    ]
    if kind == "GRANT":
        if (
            not scope_labels
            or not zone_labels
            or tier_label not in _TIERS
            or reason is not None
        ):
            raise ReceiptValidationError("grant receipt fields are invalid")
        lines.extend(_wrap_values("SCOPES", scope_labels))
        lines.extend(_wrap_values("ZONES", zone_labels))
        lines.append(f"TIER: {tier_label}")
    elif kind == "DENY":
        reason_label = _DENY_REASONS.get(reason) if isinstance(reason, str) else None
        if (
            scope_labels
            or len(zone_labels) > 1
            or tier_label is not None
            or reason_label is None
        ):
            raise ReceiptValidationError("deny receipt fields are invalid")
        if zone_labels:
            lines.append(f"ZONE: {zone_labels[0]}")
        lines.append(f"REASON: {reason_label}")
    else:
        if scope_labels or zone_labels or tier_label is not None or reason is not None:
            raise ReceiptValidationError("estop receipt fields are invalid")
        lines.extend(("STATE: TRIPPED", "GRANTS: SUSPENDED"))
    lines.extend(_FOOTER)
    return SyntheticReceipt(
        kind,
        tuple(lines),
        _seal=_RECEIPT_FACTORY_SEAL,
    )


def render_receipt_png(receipt: SyntheticReceipt) -> bytes:
    """Render a receipt to stable grayscale PNG bytes using the fixed font."""

    if not isinstance(receipt, SyntheticReceipt):
        raise ReceiptValidationError("receipt is invalid")
    receipt._validate_integrity()

    pixels = bytearray(b"\xff" * (PNG_WIDTH * PNG_HEIGHT))
    for line_index, line in enumerate(receipt.lines):
        origin_y = _MARGIN + (line_index * _LINE_ADVANCE)
        for character_index, character in enumerate(line):
            origin_x = _MARGIN + (character_index * _CHAR_ADVANCE)
            _draw_glyph(pixels, origin_x, origin_y, _FONT[character])

    scanlines = bytearray()
    for row in range(PNG_HEIGHT):
        scanlines.append(0)  # PNG filter type None.
        start = row * PNG_WIDTH
        scanlines.extend(pixels[start : start + PNG_WIDTH])

    header = struct.pack(
        "!IIBBBBB",
        PNG_WIDTH,
        PNG_HEIGHT,
        8,  # bit depth
        0,  # grayscale
        0,  # compression
        0,  # filter
        0,  # no interlace
    )
    compressed = zlib.compress(bytes(scanlines), level=9)
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", header),
            _png_chunk(b"IDAT", compressed),
            _png_chunk(b"IEND", b""),
        )
    )


def write_receipt_png(
    receipt: SyntheticReceipt,
    path: str | os.PathLike[str],
) -> Path:
    """Write one deterministic PNG to an explicit private, write-once path.

    The immediate parent is created only when its own parent already exists.
    Existing targets, links, non-private directories, and unexpected ownership
    fail closed.  No default path is selected and no artifact is written unless
    this function is called.
    """

    encoded = render_receipt_png(receipt)
    try:
        candidate = Path(path)
    except TypeError:
        raise ReceiptStorageError("receipt sink path is invalid") from None
    if not candidate.name or not _PRIVATE_FILENAME.fullmatch(candidate.name):
        raise ReceiptStorageError("receipt sink path is invalid")
    target = candidate.absolute()

    parent_fd: int | None = None
    descriptor: int | None = None
    created = False
    try:
        parent_fd = _open_private_parent(target.parent)
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ReceiptStorageError("receipt sink target is unsafe")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target.name, flags, 0o600, dir_fd=parent_fd)
        created = True
        os.fchmod(descriptor, 0o600)
        _verify_private_file(descriptor)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(parent_fd)
        return target
    except ReceiptStorageError:
        _remove_failed_target(parent_fd, target.name, created)
        raise
    except (OSError, TypeError, ValueError):
        _remove_failed_target(parent_fd, target.name, created)
        raise ReceiptStorageError("receipt sink unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def _timestamp_label(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ReceiptValidationError("receipt timestamp is invalid")
    try:
        if value.utcoffset() is None:
            raise ReceiptValidationError("receipt timestamp is invalid")
        normalized = value.astimezone(timezone.utc)
    except (OverflowError, TypeError, ValueError):
        raise ReceiptValidationError("receipt timestamp is invalid") from None
    return normalized.strftime("%Y-%m-%d %H:%M:%SZ")


def _safe_label(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ReceiptValidationError(f"receipt {field} is invalid")
    normalized = value.strip().upper()
    if (
        not normalized
        or len(normalized) > maximum
        or not _LABEL.fullmatch(normalized)
        or _SENSITIVE_TERMS.search(normalized)
    ):
        raise ReceiptValidationError(f"receipt {field} is invalid")
    return normalized


def _normalize_scopes(values: Iterable[str | Enum]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReceiptValidationError("receipt scopes are invalid")
    try:
        raw = tuple(values)
    except TypeError:
        raise ReceiptValidationError("receipt scopes are invalid") from None
    if len(raw) > len(_SCOPE_LABELS):
        raise ReceiptValidationError("receipt scopes are invalid")
    labels: list[str] = []
    for value in raw:
        scope = _enum_value(value)
        if not isinstance(scope, str):
            raise ReceiptValidationError("receipt scopes are invalid")
        label = _SCOPE_LABELS.get(scope)
        if label is None or label in labels:
            raise ReceiptValidationError("receipt scopes are invalid")
        labels.append(label)
    return tuple(sorted(labels))


def _normalize_zones(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReceiptValidationError("receipt zones are invalid")
    try:
        raw = tuple(values)
    except TypeError:
        raise ReceiptValidationError("receipt zones are invalid") from None
    if len(raw) > 4:
        raise ReceiptValidationError("receipt zones are invalid")
    labels = tuple(_safe_label(value, field="zone", maximum=12) for value in raw)
    if len(set(labels)) != len(labels):
        raise ReceiptValidationError("receipt zones are invalid")
    return tuple(sorted(labels))


def _wrap_values(label: str, values: tuple[str, ...]) -> tuple[str, ...]:
    prefix = f"{label}: "
    continuation = " " * len(prefix)
    lines: list[str] = []
    current = prefix
    for value in values:
        separator = "" if current in {prefix, continuation} else ","
        candidate = f"{current}{separator}{value}"
        if len(candidate) <= _MAX_COLUMNS:
            current = candidate
            continue
        if current in {prefix, continuation}:
            raise ReceiptValidationError("receipt layout is invalid")
        lines.append(current)
        current = f"{continuation}{value}"
    lines.append(current)
    return tuple(lines)


def _draw_glyph(
    pixels: bytearray,
    origin_x: int,
    origin_y: int,
    rows: tuple[int, ...],
) -> None:
    for glyph_y, row_bits in enumerate(rows):
        for glyph_x in range(5):
            if not row_bits & (1 << (4 - glyph_x)):
                continue
            for offset_y in range(_FONT_SCALE):
                row = origin_y + (glyph_y * _FONT_SCALE) + offset_y
                start = row * PNG_WIDTH
                for offset_x in range(_FONT_SCALE):
                    column = origin_x + (glyph_x * _FONT_SCALE) + offset_x
                    pixels[start + column] = 0


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
    return (
        struct.pack("!I", len(data))
        + chunk_type
        + data
        + struct.pack("!I", checksum)
    )


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ReceiptStorageError("receipt sink directory is unsafe")
        except FileNotFoundError:
            return


def _open_private_parent(parent: Path) -> int:
    _reject_symlink_components(parent)
    try:
        metadata = parent.lstat()
    except FileNotFoundError:
        try:
            parent.mkdir(mode=0o700)
            os.chmod(parent, 0o700, follow_symlinks=False)
            metadata = parent.lstat()
        except (FileExistsError, FileNotFoundError, OSError):
            raise ReceiptStorageError("receipt sink directory is unsafe") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
    ):
        raise ReceiptStorageError("receipt sink directory is unsafe")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError:
        raise ReceiptStorageError("receipt sink directory is unsafe") from None
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or (hasattr(os, "geteuid") and opened.st_uid != os.geteuid())
    ):
        os.close(descriptor)
        raise ReceiptStorageError("receipt sink directory is unsafe")
    return descriptor


def _verify_private_file(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
    ):
        raise ReceiptStorageError("receipt sink target is unsafe")


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("receipt write made no progress")
        remaining = remaining[written:]


def _remove_failed_target(parent_fd: int | None, name: str, created: bool) -> None:
    if parent_fd is None or not created:
        return
    try:
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError:
        pass
