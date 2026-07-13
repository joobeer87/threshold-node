"""Crash-recoverable authority for durable digest-only grant state.

The grant envelope and JSONL ledger are separate files, so the ledger append is
the explicit commit point. A revisioned pending envelope binds the exact ledger
bytes and offset. Recovery either proves that append, safely aborts an
uncommitted issue, or rolls a restrictive transition forward. Mismatches fail
closed instead of guessing.
"""

from __future__ import annotations

import copy
import secrets
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from hmac import compare_digest

from threshold.core.auth import is_valid_bearer_token, token_matches
from threshold.core.errors import ValidationError as ThresholdValidationError
from threshold.core.ledger import JsonlLedger, LedgerWitness, PreparedLedgerEvent
from threshold.core.types import Access, EventType, Grant, GrantStatus, Housefile
from threshold.grants.manager import GrantDecision, GrantManager, normalize_time
from threshold.grants.store import (
    GrantLedgerWitness,
    GrantMetadataStore,
    GrantStoreError,
    GrantStoreState,
    PendingGrantTransaction,
)


Observer = Callable[[str, dict[str, object]], None]


class GrantAuthorityUnavailable(OSError):
    """Sanitized fail-closed authority boundary."""


class GrantCredentialConflict(ThresholdValidationError):
    """A credential digest is already bound to another effective grant."""


class GrantAuthenticationFailed(Exception):
    """A supplied bearer credential does not authenticate the requested grant."""


class GrantAuthority:
    """Own grant mutations and recover their ledger/store commit protocol."""

    def __init__(
        self,
        housefile: Housefile,
        store: GrantMetadataStore,
        ledger: JsonlLedger,
        *,
        demo_mode: bool = False,
        demo_seeds: Iterable[Grant] = (),
        observer: Observer | None = None,
    ) -> None:
        self.housefile = housefile
        self.store = store
        self.ledger = ledger
        self.demo_mode = bool(demo_mode)
        self.demo_seeds = tuple(copy.deepcopy(tuple(demo_seeds)))
        self.observer = observer
        self._lock = threading.RLock()
        self._manager = GrantManager(housefile)
        self._state: GrantStoreState | None = None
        self._ready = False

    @property
    def grants(self) -> dict[str, Grant]:
        if not self._ready:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        return self._manager.grants

    @property
    def manager(self) -> GrantManager:
        """Stable manager reference retained for read-only compatibility."""

        return self._manager

    @property
    def revision(self) -> int:
        if not self._ready or self._state is None:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        return self._state.revision

    def ensure_ready(self, *, now: datetime | None = None) -> None:
        """Load, verify, and recover authority state before any grant use."""

        with self._exclusive(now=now):
            return

    def issue(self, grant: Grant, *, now: datetime) -> Grant:
        """Validate and commit one new grant without exposing it while pending."""

        with self._exclusive(now=now):
            if any(
                compare_digest(grant.credential_digest, existing.credential_digest)
                for existing in self.grants.values()
            ):
                raise GrantCredentialConflict("grant credential is already registered")
            target = self._copy_grants(self.grants)
            manager = GrantManager(self.housefile)
            manager.grants = target
            manager.issue(copy.deepcopy(grant), now=now)
            self._commit(
                kind="issue",
                target=manager.grants,
                previous_statuses={},
                event_type=EventType.GRANT,
                agent=grant.id,
                detail="grant issued",
                now=now,
            )
            return self.grants[grant.id]

    def revoke(self, grant_id: str, *, now: datetime) -> tuple[Grant, bool]:
        """Durably revoke an active or suspended grant without rollback."""

        with self._exclusive(now=now):
            current = self.grants[grant_id]
            if current.status in {GrantStatus.REVOKED, GrantStatus.EXPIRED}:
                return current, False
            previous = current.status
            target = self._copy_grants(self.grants)
            target[grant_id].status = GrantStatus.REVOKED
            self._commit(
                kind="revoke",
                target=target,
                previous_statuses={grant_id: previous},
                event_type=EventType.REVOKE,
                agent=grant_id,
                detail="grant revoked",
                now=now,
            )
            return self.grants[grant_id], True

    def decision(
        self,
        grant_id: str,
        *,
        now: datetime,
        action: str,
    ) -> tuple[Grant, GrantDecision]:
        """Evaluate a grant and persist an exact-boundary expiry before denial."""

        with self._exclusive(now=now):
            return self._decision_locked(grant_id, now=now, action=action)

    @contextmanager
    def authorized(
        self,
        grant_id: str,
        supplied_credential: str | None,
        *,
        now: datetime,
        action: str,
    ) -> Iterator[tuple[Grant, GrantDecision]]:
        """Hold authority through authentication, policy use, and its receipt.

        The caller performs disclosure or a future relay inside the yielded
        context. Concurrent revoke/suspend transitions therefore cannot land
        between an allowed decision and that protected action.
        """

        with self._exclusive(now=now):
            grant = self.grants.get(grant_id)
            if (
                grant is None
                or not is_valid_bearer_token(supplied_credential)
                or not token_matches(supplied_credential, grant.credential_digest)
            ):
                raise GrantAuthenticationFailed(
                    "grant authentication required"
                )
            yield self._decision_locked(
                grant_id,
                now=now,
                action=action,
            )

    def suspend_all(self, *, now: datetime) -> int:
        """Persist one ESTOP receipt and suspend every currently active grant."""

        with self._exclusive(now=now):
            affected = {
                grant_id: grant.status
                for grant_id, grant in self.grants.items()
                if grant.status == GrantStatus.ACTIVE
            }
            target = self._copy_grants(self.grants)
            for grant_id in affected:
                target[grant_id].status = GrantStatus.SUSPENDED
            self._commit(
                kind="suspend_all",
                target=target,
                previous_statuses=affected,
                event_type=EventType.ESTOP,
                agent="system",
                detail="simulated interlock tripped; active grants suspended",
                now=now,
            )
            return len(affected)

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Grant]:
        """Return an isolated effective snapshot for owner-safe projections."""

        with self._exclusive(now=now):
            return self._copy_grants(self.grants)

    @contextmanager
    def _exclusive(self, *, now: datetime | None) -> Iterator[None]:
        """Refresh and hold cross-instance authority ownership for one action."""

        with self._lock:
            try:
                with self.store.transaction():
                    self._reload(now=now)
                    yield
            except GrantAuthorityUnavailable:
                self._mark_unavailable()
                raise
            except (GrantStoreError, OSError, TypeError, ValueError):
                self._mark_unavailable()
                raise GrantAuthorityUnavailable("grant authority unavailable") from None

    def _reload(self, *, now: datetime | None) -> None:
        """Reload inside the shared file lock so cached instances cannot win."""

        state = self.store.load_state()
        if state is None:
            if self.ledger.has_history():
                raise GrantAuthorityUnavailable(
                    "grant authority history is ambiguous"
                )
            state = GrantStoreState.empty()
            self._install_state(state)
            if self.demo_mode and self.demo_seeds:
                self._bootstrap_demo(now=now)
            return

        if state.pending is not None:
            self._verify_pending_base_receipt(state)
            state = self._recover(state)
        else:
            self._verify_clean_state(state)
        self._install_state(state)

    def _bootstrap_demo(self, *, now: datetime | None) -> None:
        timestamp = normalize_time(now or datetime.now(timezone.utc), "current time")
        target: dict[str, Grant] = {}
        manager = GrantManager(self.housefile)
        for seed in self.demo_seeds:
            manager.grants = target
            manager.issue(copy.deepcopy(seed), now=timestamp)
            target = manager.grants
        self._commit(
            kind="demo_seed",
            target=target,
            previous_statuses={},
            event_type=EventType.PROVISION,
            agent="system",
            detail="synthetic demo grant provisioned",
            now=timestamp,
        )

    def _decision_locked(
        self,
        grant_id: str,
        *,
        now: datetime,
        action: str,
    ) -> tuple[Grant, GrantDecision]:
        grant = self.grants[grant_id]
        decision = self._manager.decision(grant, now=now)
        if decision.next_status == GrantStatus.EXPIRED:
            target = self._copy_grants(self.grants)
            target[grant_id].status = GrantStatus.EXPIRED
            self._commit(
                kind="expire",
                target=target,
                previous_statuses={grant_id: grant.status},
                event_type=EventType.DENY,
                agent=grant_id,
                detail=f"{action} refused: grant_expired",
                now=now,
            )
            grant = self.grants[grant_id]
        return grant, decision

    def _commit(
        self,
        *,
        kind: str,
        target: Mapping[str, Grant],
        previous_statuses: Mapping[str, GrantStatus],
        event_type: EventType,
        agent: str,
        detail: str,
        now: datetime,
    ) -> None:
        if self._state is None or self._state.pending is not None:
            self._mark_unavailable()
            raise GrantAuthorityUnavailable("grant authority unavailable")
        target_copy = self._copy_grants(target)
        self._validate_housefile_bindings(target_copy)
        transaction = f"tx-{secrets.token_hex(16)}"
        target_revision = self._state.revision + 1
        event = {
            "ts": self._timestamp(now),
            "type": event_type.value,
            "agent": agent,
            "detail": detail,
            "transaction": transaction,
            "grant_revision": target_revision,
        }
        try:
            prepared = self.ledger.prepare_event(event)
            pending = PendingGrantTransaction(
                transaction=transaction,
                kind=kind,
                base_revision=self._state.revision,
                target_revision=target_revision,
                ledger_offset=prepared.checkpoint.offset,
                ledger_tail_sha256=prepared.checkpoint.tail_sha256,
                target_sha256=self.store.target_sha256(target_copy),
                receipt_sha256=prepared.receipt_sha256,
                event=prepared.entry,
                target_grants=target_copy,
                previous_statuses=dict(previous_statuses),
            )
            effective = (
                self._copy_grants(self._state.grants)
                if kind in {"issue", "demo_seed"}
                else self._copy_grants(target_copy)
            )
            prepared_state = GrantStoreState(
                revision=self._state.revision,
                grants=effective,
                ledger_witness=self._state.ledger_witness,
                pending=pending,
            )
            self.store.save_state(prepared_state)
            self._state = prepared_state
            self._ready = False
            persisted = self.ledger.append_prepared(prepared)
            self._notify(persisted)
            final = self._final_state(prepared_state)
            self.store.save_state(final)
            self._install_state(final)
        except (GrantStoreError, OSError, TypeError, ValueError):
            self._mark_unavailable()
            raise GrantAuthorityUnavailable("grant authority unavailable") from None

    def _recover(self, state: GrantStoreState) -> GrantStoreState:
        pending = state.pending
        if pending is None:  # pragma: no cover - guarded by caller
            return state
        prepared = self.ledger.rebuild_prepared_event(
            pending.event,
            ledger_offset=pending.ledger_offset,
            ledger_tail_sha256=pending.ledger_tail_sha256,
            receipt_sha256=pending.receipt_sha256,
        )
        present = self.ledger.inspect_prepared(prepared)
        if not present and pending.kind == "issue":
            aborted = GrantStoreState(
                revision=state.revision,
                grants=self._copy_grants(state.grants),
                ledger_witness=state.ledger_witness,
            )
            self.store.save_state(aborted)
            self._verify_clean_state(aborted)
            return aborted
        if not present:
            persisted = self.ledger.append_prepared(prepared)
            self._notify(persisted)
        final = self._final_state(state)
        self.store.save_state(final)
        self._verify_clean_state(final)
        return final

    def _final_state(self, state: GrantStoreState) -> GrantStoreState:
        pending = state.pending
        if pending is None:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        return GrantStoreState(
            revision=pending.target_revision,
            grants=self._copy_grants(pending.target_grants),
            ledger_witness=GrantLedgerWitness(
                transaction=pending.transaction,
                revision=pending.target_revision,
                ledger_offset=pending.ledger_offset,
                receipt_sha256=pending.receipt_sha256,
                target_sha256=pending.target_sha256,
            ),
        )

    def _verify_clean_state(self, state: GrantStoreState) -> None:
        if state.pending is not None:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        if state.revision == 0:
            if state.grants or state.ledger_witness is not None:
                raise GrantAuthorityUnavailable("grant authority unavailable")
        else:
            witness = state.ledger_witness
            if witness is None:
                raise GrantAuthorityUnavailable("grant authority unavailable")
            if self.store.target_sha256(state.grants) != witness.target_sha256:
                raise GrantAuthorityUnavailable("grant authority unavailable")
            self.ledger.verify_witness(
                LedgerWitness(
                    transaction=witness.transaction,
                    grant_revision=witness.revision,
                    ledger_offset=witness.ledger_offset,
                    receipt_sha256=witness.receipt_sha256,
                )
            )
        self._validate_housefile_bindings(state.grants)

    def _verify_pending_base_receipt(self, state: GrantStoreState) -> None:
        """Verify the prior clean ledger revision before rolling forward."""

        pending = state.pending
        if pending is None or pending.base_revision != state.revision:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        self._validate_housefile_bindings(pending.target_grants)
        if state.revision == 0:
            if state.ledger_witness is not None:
                raise GrantAuthorityUnavailable("grant authority unavailable")
            return
        witness = state.ledger_witness
        if witness is None:
            raise GrantAuthorityUnavailable("grant authority unavailable")
        self.ledger.verify_witness(
            LedgerWitness(
                transaction=witness.transaction,
                grant_revision=witness.revision,
                ledger_offset=witness.ledger_offset,
                receipt_sha256=witness.receipt_sha256,
            )
        )

    def _install_state(self, state: GrantStoreState) -> None:
        self._verify_clean_state(state)
        self._manager.grants = self._copy_grants(state.grants)
        self._state = GrantStoreState(
            revision=state.revision,
            grants=self._copy_grants(state.grants),
            ledger_witness=state.ledger_witness,
        )
        self._ready = True

    def _mark_unavailable(self) -> None:
        self._ready = False
        self._manager.grants = {}

    def _validate_housefile_bindings(self, grants: Mapping[str, Grant]) -> None:
        for grant in grants.values():
            if not grant.scopes or not grant.zones or not grant.credential_digest:
                raise GrantAuthorityUnavailable("grant authority unavailable")
            for zone_id in grant.zones:
                zone = self.housefile.zone(zone_id)
                if zone is None or zone.access == Access.NO_GO:
                    raise GrantAuthorityUnavailable("grant authority unavailable")

    def _notify(self, event: dict[str, object]) -> None:
        if self.observer is None:
            return
        try:
            self.observer(str(event["type"]), dict(event))
        except Exception:
            # Durable state is authoritative; observers are best-effort only.
            return

    @staticmethod
    def _copy_grants(grants: Mapping[str, Grant]) -> dict[str, Grant]:
        return {grant_id: copy.deepcopy(grant) for grant_id, grant in grants.items()}

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return (
            normalize_time(value, "current time")
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
