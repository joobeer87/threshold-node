"""Deterministic THS-0035 mock-agent contract and safety tests."""

from __future__ import annotations

import io
import json

import httpx
import pytest

from scripts import mock_robot


SYNTHETIC_CREDENTIAL = "synthetic-demo-credential-000000000001"


def scoped_payload(*, workshop_extra: dict[str, object] | None = None) -> dict[str, object]:
    workshop: dict[str, object] = {
        "id": "workshop",
        "access": "no-go",
        "boundary": [260, 100, 140, 100],
    }
    workshop.update(workshop_extra or {})
    return {
        "grant": {"id": "g-neo"},
        "capabilities": ["command:navigate"],
        "zones": [
            {
                "id": "kitchen",
                "name": "Kitchen",
                "access": "open",
                "boundary": [0, 0, 150, 100],
            },
            {
                "id": "living",
                "name": "Living Room",
                "access": "open",
                "boundary": [150, 0, 150, 100],
            },
            {
                "id": "utility",
                "name": "Utility",
                "access": "open",
                "boundary": [300, 0, 100, 100],
            },
            {"id": "studio", "disclosed": False},
            {
                "id": "office",
                "name": "Office",
                "access": "open",
                "boundary": [130, 100, 130, 100],
            },
            workshop,
            {"id": "backlawn", "disclosed": False},
            {
                "id": "garden",
                "access": "no-go",
                "boundary": [300, 200, 100, 120],
            },
        ],
    }


def allowed_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        503,
        json={
            "detail": {
                "policy_decision": "allowed",
                "relayed": False,
                "reason": "adapter_not_configured",
                "tier": "UNAVAILABLE",
            }
        },
        request=request,
    )


def denied_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        403,
        json={
            "detail": {
                "policy_decision": "denied",
                "relayed": False,
                "reason": "gate_refused",
            }
        },
        request=request,
    )


def records(output: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_three_step_flow_uses_fixed_safe_client_and_emits_only_receipts(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "127.0.0.1"
        assert request.url.port == 8471
        assert request.headers["X-Threshold-Grant-Token"] == SYNTHETIC_CREDENTIAL
        if len(requests) == 1:
            assert request.method == "GET"
            assert request.url.path == "/housefile"
            assert request.url.params.get("grant") == "g-neo"
            assert len(request.url.params) == 1
            return httpx.Response(200, json=scoped_payload(), request=request)
        body = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path == "/command"
        assert body["grant"] == "g-neo"
        assert body["verb"] == "navigate"
        if len(requests) == 2:
            assert body["zone"] == "kitchen"
            return allowed_response(request)
        assert body["zone"] == "workshop"
        return denied_response(request)

    client_options: dict[str, object] = {}
    original_client = mock_robot.httpx.Client

    def client_spy(*args, **kwargs):
        client_options.update(kwargs)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(mock_robot.httpx, "Client", client_spy)
    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_OK
    assert len(requests) == 3
    assert client_options["base_url"] == "http://127.0.0.1:8471"
    assert client_options["trust_env"] is False
    assert client_options["follow_redirects"] is False
    assert client_options["timeout"] == 3.0
    assert records(output) == [
        {"http_status": 200, "status": "passed", "step": "scoped_read"},
        {
            "http_status": 503,
            "policy_decision": "allowed",
            "relayed": False,
            "status": "passed",
            "step": "allowed_request",
        },
        {
            "http_status": 403,
            "policy_decision": "denied",
            "relayed": False,
            "status": "passed",
            "step": "no_go_denial",
        },
    ]
    assert SYNTHETIC_CREDENTIAL not in output.getvalue()
    assert "g-neo" not in output.getvalue()
    assert "kitchen" not in output.getvalue()
    assert "workshop" not in output.getvalue()


@pytest.mark.parametrize(
    ("argv", "environ"),
    [
        ([], {}),
        (["--grant"], {"THS_DEMO_GRANT_TOKEN": SYNTHETIC_CREDENTIAL}),
        (["--grant", "bad grant"], {"THS_DEMO_GRANT_TOKEN": SYNTHETIC_CREDENTIAL}),
    ],
)
def test_invalid_configuration_is_jsonl_and_never_opens_transport(argv, environ):
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request method: {request.method}")

    output = io.StringIO()
    exit_code = mock_robot.main(
        argv,
        environ=environ,
        transport=httpx.MockTransport(unexpected_request),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_CONFIG
    assert records(output) == [
        {
            "exit_code": 2,
            "failure": "invalid_demo_configuration",
            "status": "failed",
            "step": "configuration",
        }
    ]


def test_transport_failure_is_sanitized_and_distinct():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "synthetic private transport detail",
            request=request,
        )

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_TRANSPORT
    assert records(output) == [
        {
            "exit_code": 3,
            "failure": "loopback_unavailable",
            "status": "failed",
            "step": "transport",
        }
    ]
    assert "private transport detail" not in output.getvalue()
    assert mock_robot.BASE_URL not in output.getvalue()
    assert SYNTHETIC_CREDENTIAL not in output.getvalue()


def test_redirect_is_not_followed_and_fails_the_contract():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            307,
            headers={"Location": "http://127.0.0.1:8471/unexpected"},
            request=request,
        )

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_CONTRACT
    assert len(requests) == 1
    assert records(output)[0]["failure"] == "scoped_read_response"


def test_no_go_interior_overdisclosure_is_a_safety_failure():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=scoped_payload(workshop_extra={"name": "must not be disclosed"}),
            request=request,
        )

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert len(requests) == 1
    assert records(output)[0]["failure"] == "no_go_interior_disclosed"
    assert "must not be disclosed" not in output.getvalue()


def test_second_no_go_zone_overdisclosure_is_a_safety_failure():
    payload = scoped_payload()
    garden = next(zone for zone in payload["zones"] if zone["id"] == "garden")
    garden["note"] = "must remain private"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert records(output)[0]["failure"] == "no_go_interior_disclosed"
    assert "must remain private" not in output.getvalue()


def test_out_of_scope_zone_overdisclosure_is_a_safety_failure():
    payload = scoped_payload()
    studio = next(zone for zone in payload["zones"] if zone["id"] == "studio")
    studio.update(
        {
            "disclosed": True,
            "name": "must remain private",
            "access": "restricted",
            "boundary": [0, 100, 130, 100],
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert records(output)[0]["failure"] == "out_of_scope_zone_disclosed"
    assert "must remain private" not in output.getvalue()


def test_no_go_inventory_reference_is_a_safety_failure():
    payload = scoped_payload()
    payload["inventory"] = [
        {"name": "Synthetic hidden item", "zone": "workshop"}
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert records(output)[0]["failure"] == "no_go_interior_disclosed"
    assert "Synthetic hidden item" not in output.getvalue()


def test_unexpected_allowed_request_success_stops_before_no_go_step():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=scoped_payload(), request=request)
        return httpx.Response(200, json={"relayed": False}, request=request)

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert len(requests) == 2
    assert records(output)[-1]["failure"] == "unexpected_command_success"


def test_no_go_success_is_a_safety_failure():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=scoped_payload(), request=request)
        if len(requests) == 2:
            return allowed_response(request)
        return httpx.Response(200, json={"relayed": False}, request=request)

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_SAFETY
    assert len(requests) == 3
    assert records(output)[-1]["failure"] == "no_go_not_refused"


def test_malformed_policy_response_is_a_contract_failure():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=scoped_payload(), request=request)
        return httpx.Response(
            503,
            json={"detail": {"relayed": False}},
            request=request,
        )

    output = io.StringIO()
    exit_code = mock_robot.run_demo(
        "g-neo",
        SYNTHETIC_CREDENTIAL,
        transport=httpx.MockTransport(handler),
        output=output,
    )

    assert exit_code == mock_robot.EXIT_CONTRACT
    assert records(output)[-1]["failure"] == "allowed_response_contract"


def test_non_ascii_or_oversized_credentials_fail_before_transport():
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request method: {request.method}")

    for credential in ("x" * 32 + "é", "x" * 513):
        output = io.StringIO()
        exit_code = mock_robot.run_demo(
            "g-neo",
            credential,
            transport=httpx.MockTransport(unexpected_request),
            output=output,
        )
        assert exit_code == mock_robot.EXIT_CONFIG
        assert records(output)[0]["failure"] == "invalid_demo_configuration"
        assert credential not in output.getvalue()
