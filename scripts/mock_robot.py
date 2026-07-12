"""THS-0035 — safe mock-agent proof against the loopback demo API.

The script proves three API-boundary outcomes only. It never claims physical
movement, never prints a scoped housefile, and never echoes credentials or raw
server errors.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

import httpx

from threshold.core.auth import is_valid_bearer_token


BASE_URL = "http://127.0.0.1:8471"
DEFAULT_GRANT = "g-neo"
REQUEST_TIMEOUT_SECONDS = 3.0

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_TRANSPORT = 3
EXIT_CONTRACT = 4
EXIT_SAFETY = 5

_GRANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_BOUNDARY_ONLY_KEYS = {"id", "access", "boundary"}
_GRANTED_ZONE_IDS = {"kitchen", "living", "utility", "office"}
_WITHHELD_ZONE_IDS = {"studio", "backlawn"}
_EXPECTED_NO_GO_IDS = {"workshop", "garden"}
_EXPECTED_ZONE_IDS = _GRANTED_ZONE_IDS | _WITHHELD_ZONE_IDS | _EXPECTED_NO_GO_IDS


def _emit(output: TextIO, *, step: str, status: str, **fields: object) -> None:
    """Write one bounded, public-safe JSON Lines record."""
    record = {"step": step, "status": status, **fields}
    output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _fail(output: TextIO, *, step: str, exit_code: int, failure: str) -> int:
    _emit(output, step=step, status="failed", exit_code=exit_code, failure=failure)
    return exit_code


def _json_object(response: httpx.Response) -> Mapping[str, object] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _error_detail(response: httpx.Response) -> Mapping[str, object] | None:
    payload = _json_object(response)
    if payload is None:
        return None
    detail = payload.get("detail")
    return detail if isinstance(detail, Mapping) else None


def _find_zones(zones: object, zone_id: str) -> list[Mapping[str, object]]:
    if not isinstance(zones, list):
        return []
    return [
        zone
        for zone in zones
        if isinstance(zone, Mapping) and zone.get("id") == zone_id
    ]


def _identifier_count(value: object, identifier: str) -> int:
    """Count exact identifier references without retaining or printing payload data."""
    if isinstance(value, str):
        return int(value.casefold() == identifier.casefold())
    if isinstance(value, Mapping):
        return sum(
            _identifier_count(key, identifier) + _identifier_count(item, identifier)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(_identifier_count(item, identifier) for item in value)
    return 0


def _valid_boundary(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(point, (int, float)) and not isinstance(point, bool) for point in value)
    )


def _validate_scoped_read(payload: Mapping[str, object], grant_id: str) -> tuple[int, str] | None:
    grant = payload.get("grant")
    if not isinstance(grant, Mapping) or grant.get("id") != grant_id:
        return EXIT_CONTRACT, "scoped_grant_mismatch"

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or "command:navigate" not in capabilities:
        return EXIT_CONTRACT, "navigate_capability_missing"

    zones = payload.get("zones")
    if not isinstance(zones, list):
        return EXIT_CONTRACT, "no_go_boundary_missing"
    zone_maps = [zone for zone in zones if isinstance(zone, Mapping)]
    if len(zone_maps) != len(zones) or any(
        not isinstance(zone.get("id"), str) for zone in zone_maps
    ):
        return EXIT_CONTRACT, "zone_contract_invalid"
    zone_ids = [zone["id"] for zone in zone_maps]
    if len(zone_ids) != len(set(zone_ids)):
        return EXIT_SAFETY, "duplicate_zone_disclosure"
    unexpected = set(zone_ids) - _EXPECTED_ZONE_IDS
    if unexpected:
        return EXIT_SAFETY, "unexpected_zone_disclosed"
    if set(zone_ids) != _EXPECTED_ZONE_IDS:
        return EXIT_CONTRACT, "zone_contract_invalid"

    for granted_id in _GRANTED_ZONE_IDS:
        granted = _find_zones(zones, granted_id)[0]
        if (
            granted.get("disclosed") is False
            or not isinstance(granted.get("name"), str)
            or not granted.get("name")
            or granted.get("access") != "open"
            or not _valid_boundary(granted.get("boundary"))
        ):
            return EXIT_CONTRACT, "allowed_zone_not_disclosed"

    for withheld_id in _WITHHELD_ZONE_IDS:
        withheld = _find_zones(zones, withheld_id)[0]
        if withheld != {"id": withheld_id, "disclosed": False}:
            return EXIT_SAFETY, "out_of_scope_zone_disclosed"
        if _identifier_count(payload, withheld_id) != 1:
            return EXIT_SAFETY, "out_of_scope_zone_disclosed"

    no_go_zones = [
        zone for zone in zone_maps if zone.get("access") == "no-go"
    ]
    for no_go_zone in no_go_zones:
        if set(no_go_zone) != _BOUNDARY_ONLY_KEYS:
            return EXIT_SAFETY, "no_go_interior_disclosed"
        if not isinstance(no_go_zone.get("id"), str):
            return EXIT_CONTRACT, "no_go_boundary_invalid"
        if not _valid_boundary(no_go_zone.get("boundary")):
            return EXIT_CONTRACT, "no_go_boundary_invalid"

    no_go_ids = {zone.get("id") for zone in no_go_zones}
    if no_go_ids != _EXPECTED_NO_GO_IDS or len(no_go_zones) != len(_EXPECTED_NO_GO_IDS):
        return EXIT_CONTRACT, "no_go_boundary_missing"
    for no_go_id in _EXPECTED_NO_GO_IDS:
        if len(_find_zones(zones, no_go_id)) != 1:
            return EXIT_SAFETY, "no_go_interior_disclosed"
        if _identifier_count(payload, no_go_id) != 1:
            return EXIT_SAFETY, "no_go_interior_disclosed"
    return None


def _validate_allowed_response(response: httpx.Response) -> tuple[int, str] | None:
    detail = _error_detail(response)
    if response.is_success or (detail is not None and detail.get("relayed") is True):
        return EXIT_SAFETY, "unexpected_command_success"
    if response.status_code != 503 or detail is None:
        return EXIT_CONTRACT, "allowed_response_contract"
    if (
        detail.get("policy_decision") != "allowed"
        or detail.get("relayed") is not False
        or detail.get("reason") != "adapter_not_configured"
        or detail.get("tier") != "UNAVAILABLE"
    ):
        return EXIT_CONTRACT, "allowed_response_contract"
    return None


def _validate_no_go_response(response: httpx.Response) -> tuple[int, str] | None:
    detail = _error_detail(response)
    if response.is_success or (detail is not None and detail.get("relayed") is True):
        return EXIT_SAFETY, "no_go_not_refused"
    if response.status_code != 403 or detail is None:
        return EXIT_CONTRACT, "no_go_response_contract"
    if (
        detail.get("policy_decision") != "denied"
        or detail.get("relayed") is not False
        or detail.get("reason") != "gate_refused"
    ):
        return EXIT_CONTRACT, "no_go_response_contract"
    return None


def run_demo(
    grant_id: str,
    grant_token: str,
    *,
    transport: httpx.BaseTransport | None = None,
    output: TextIO = sys.stdout,
) -> int:
    """Run the three-step proof and return a stable process exit code."""
    if not _GRANT_ID.fullmatch(grant_id) or not is_valid_bearer_token(grant_token):
        return _fail(
            output,
            step="configuration",
            exit_code=EXIT_CONFIG,
            failure="invalid_demo_configuration",
        )
    headers = {"X-Threshold-Grant-Token": grant_token}
    try:
        with httpx.Client(
            base_url=BASE_URL,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            scoped = client.get("/housefile", params={"grant": grant_id})
            if scoped.status_code != 200:
                return _fail(
                    output,
                    step="scoped_read",
                    exit_code=EXIT_CONTRACT,
                    failure="scoped_read_response",
                )
            scoped_payload = _json_object(scoped)
            if scoped_payload is None:
                return _fail(
                    output,
                    step="scoped_read",
                    exit_code=EXIT_CONTRACT,
                    failure="scoped_read_response",
                )
            scoped_failure = _validate_scoped_read(scoped_payload, grant_id)
            if scoped_failure is not None:
                exit_code, failure = scoped_failure
                return _fail(
                    output,
                    step="scoped_read",
                    exit_code=exit_code,
                    failure=failure,
                )
            _emit(output, step="scoped_read", status="passed", http_status=200)

            allowed = client.post(
                "/command",
                json={"grant": grant_id, "verb": "navigate", "zone": "kitchen"},
            )
            allowed_failure = _validate_allowed_response(allowed)
            if allowed_failure is not None:
                exit_code, failure = allowed_failure
                return _fail(
                    output,
                    step="allowed_request",
                    exit_code=exit_code,
                    failure=failure,
                )
            _emit(
                output,
                step="allowed_request",
                status="passed",
                http_status=503,
                policy_decision="allowed",
                relayed=False,
            )

            denied = client.post(
                "/command",
                json={"grant": grant_id, "verb": "navigate", "zone": "workshop"},
            )
            denied_failure = _validate_no_go_response(denied)
            if denied_failure is not None:
                exit_code, failure = denied_failure
                return _fail(
                    output,
                    step="no_go_denial",
                    exit_code=exit_code,
                    failure=failure,
                )
            _emit(
                output,
                step="no_go_denial",
                status="passed",
                http_status=403,
                policy_decision="denied",
                relayed=False,
            )
    except httpx.TransportError:
        return _fail(
            output,
            step="transport",
            exit_code=EXIT_TRANSPORT,
            failure="loopback_unavailable",
        )
    return EXIT_OK


def _parse_grant(argv: Sequence[str]) -> str | None:
    if not argv:
        return DEFAULT_GRANT
    if len(argv) != 2 or argv[0] != "--grant":
        return None
    grant_id = argv[1]
    return grant_id if _GRANT_ID.fullmatch(grant_id) else None


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    output: TextIO = sys.stdout,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    values = os.environ if environ is None else environ
    grant_id = _parse_grant(args)
    grant_token = values.get("THS_DEMO_GRANT_TOKEN", "").strip()
    if grant_id is None or not is_valid_bearer_token(grant_token):
        return _fail(
            output,
            step="configuration",
            exit_code=EXIT_CONFIG,
            failure="invalid_demo_configuration",
        )
    return run_demo(grant_id, grant_token, transport=transport, output=output)


if __name__ == "__main__":
    raise SystemExit(main())
