"""The deterministic endpoints must not reach the network.

``tests/harness/no-network.mts`` on the TypeScript side proves the *library*
never calls a model on the safety path. This proves the same thing one layer
out, at the HTTP boundary a deployment actually exposes: with outbound
connections severed process-wide, every deterministic route still answers
correctly.

The distinction matters because the failure this guards against is not someone
editing ``engine.py`` to call a model. It is a route handler enriching a
response with a model call before returning it, leaving the engine untouched
and the guarantee quietly false.
"""

from __future__ import annotations

import socket
import ssl

import pytest
from fastapi.testclient import TestClient

from brahmo.api import create_app
from brahmo.corpus import Corpus


class NetworkUsed(AssertionError):
    """Something tried to open an outbound connection."""


@pytest.fixture
def severed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cut every outbound path for the duration of a test.

    Socket *objects* still construct — httpx builds them while setting up its
    in-process ASGI transport — but nothing may connect, resolve a name or
    negotiate TLS.
    """

    def refuse(*args: object, **kwargs: object):
        raise NetworkUsed("the deterministic path attempted a network call")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", refuse)


@pytest.fixture
def client(api_corpus: Corpus) -> TestClient:
    return TestClient(create_app(corpus=api_corpus))


def test_safety_check_answers_with_the_network_severed(
    client: TestClient, severed: None
) -> None:
    response = client.post("/safety-check", json={"patient_id": 6})
    assert response.status_code == 200
    body = response.json()
    assert body["flags"], "expected the seeded HF + CKD patient to raise flags"
    assert body["computed"]["eGFR"] is not None


def test_compose_prompt_answers_with_the_network_severed(
    client: TestClient, severed: None
) -> None:
    response = client.post(
        "/compose-prompt", json={"patient_id": 2, "question": "Next step?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["optionC"].startswith("# CLINICAL CONSULT")
    assert body["meta"]["guidelines_count"] > 0


@pytest.mark.parametrize("patient_id", [1, 2, 3, 4, 5, 6])
def test_every_seeded_patient_is_checkable_offline(
    client: TestClient, severed: None, patient_id: int
) -> None:
    assert client.post("/safety-check", json={"patient_id": patient_id}).status_code == 200


def test_health_and_listing_answer_with_the_network_severed(
    client: TestClient, severed: None
) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/patients").json()) == 6


def test_consult_still_returns_the_verdict_with_no_model(
    client: TestClient, severed: None
) -> None:
    """The clinical content must not depend on the model answering."""
    response = client.post(
        "/consult", json={"patient_id": 6, "question": "Optimise her regimen?"}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["report"]["flags"], "the report is the point, model or no model"
    assert body["answers"]["model"] == "none"
    assert "error" in body["answers"]
    assert "grounded" not in body["answers"]


def test_the_guard_itself_works(severed: None) -> None:
    """A test that cannot fail proves nothing — check the fixture bites."""
    with pytest.raises(NetworkUsed):
        socket.create_connection(("example.invalid", 80))
    with pytest.raises(NetworkUsed):
        socket.getaddrinfo("example.invalid", 80)
