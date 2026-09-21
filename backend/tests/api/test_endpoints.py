"""Endpoint behaviour, and parity with the library underneath it.

The HTTP layer must add nothing clinical. Every response here is checked
against what :mod:`brahmo.engine` and :mod:`brahmo.composer` produce directly,
so a route that started massaging a report would fail rather than quietly
become the real implementation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from brahmo.api import create_app
from brahmo.corpus import Corpus
from brahmo.domain.patient import Patient
from brahmo.model import EchoModel


@pytest.fixture
def client(api_corpus: Corpus) -> TestClient:
    return TestClient(create_app(corpus=api_corpus))


@pytest.fixture
def client_with_model(api_corpus: Corpus) -> TestClient:
    return TestClient(create_app(corpus=api_corpus, model=EchoModel()))


INLINE_PATIENT = {
    "id": 900,
    "patient_label": "inline",
    "age": 62,
    "sex": "F",
    "bmi": 28.4,
    "conditions": ["T2DM", "CKD"],
    "medications": [{"drug": "Glimepiride", "dose": "2mg OD"}],
    "allergies": ["Sulfa drugs"],
    "labs": {"Cr": 1.6, "HbA1c": 9.2},
    "vitals": {},
    "insurance": {"provider": "NONE"},
    "income_context": "daily wage",
}


# -- validation -------------------------------------------------------------


def test_patient_id_and_patient_are_mutually_exclusive(client: TestClient) -> None:
    response = client.post("/safety-check", json={"patient_id": 1, "patient": INLINE_PATIENT})
    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]


def test_neither_patient_id_nor_patient_is_rejected(client: TestClient) -> None:
    response = client.post("/safety-check", json={})
    assert response.status_code == 422


def test_unknown_patient_is_404(client: TestClient) -> None:
    response = client.post("/safety-check", json={"patient_id": 9999})
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]


def test_unknown_field_is_rejected(client: TestClient) -> None:
    """Extra keys are a typo, not a courtesy."""
    response = client.post("/safety-check", json={"patient_id": 1, "patinet": 2})
    assert response.status_code == 422


def test_empty_question_is_rejected(client: TestClient) -> None:
    response = client.post("/compose-prompt", json={"patient_id": 1, "question": ""})
    assert response.status_code == 422


def test_get_unknown_patient_is_404(client: TestClient) -> None:
    assert client.get("/patients/9999").status_code == 404


# -- parity with the library ------------------------------------------------


@pytest.mark.parametrize("patient_id", [1, 2, 3, 4, 5, 6])
def test_safety_check_matches_the_engine(
    client: TestClient, api_corpus: Corpus, patient_id: int
) -> None:
    served = client.post("/safety-check", json={"patient_id": patient_id}).json()
    direct = api_corpus.engine.run(api_corpus.patient(patient_id)).to_dict()
    assert served == direct


def test_compose_prompt_matches_the_composer(client: TestClient, api_corpus: Corpus) -> None:
    question = "How should I adjust her regimen?"
    served = client.post(
        "/compose-prompt", json={"patient_id": 6, "question": question}
    ).json()

    patient = api_corpus.patient(6)
    report = api_corpus.engine.run(patient)
    composed = api_corpus.composer.compose(patient, report, question)

    assert served["optionC"] == composed.grounded
    assert served["generic"] == composed.generic
    assert served["meta"] == composed.meta.to_dict()
    assert served["report"] == report.to_dict()


def test_an_inline_patient_is_checked_the_same_way(
    client: TestClient, api_corpus: Corpus
) -> None:
    served = client.post("/safety-check", json={"patient": INLINE_PATIENT}).json()
    direct = api_corpus.engine.run(Patient.model_validate(INLINE_PATIENT)).to_dict()
    assert served == direct
    assert served["computed"]["eGFR_stage"] is not None


def test_inline_patient_flags_the_sulfa_cross_reactivity(client: TestClient) -> None:
    """A real check, not just a 200: this patient is on a sulfonylurea."""
    body = client.post("/safety-check", json={"patient": INLINE_PATIENT}).json()
    rules = {f["provenance"]["rule_id"] for f in body["flags"]}
    assert "allergy.sulfonamide_cross_reactivity" in rules


# -- listings ---------------------------------------------------------------


def test_patient_listing_summarises_every_seeded_patient(
    client: TestClient, api_corpus: Corpus
) -> None:
    listed = client.get("/patients").json()
    assert [p["id"] for p in listed] == [p.id for p in api_corpus.seeded_patients]
    assert all(p["patient_label"] for p in listed)


def test_patient_detail_round_trips(client: TestClient, api_corpus: Corpus) -> None:
    fetched = client.get("/patients/2").json()
    assert Patient.model_validate(fetched).id == 2


# -- model boundary ---------------------------------------------------------


def test_consult_uses_the_model_when_one_is_configured(
    client_with_model: TestClient,
) -> None:
    body = client_with_model.post(
        "/consult", json={"patient_id": 6, "question": "Next step?"}
    ).json()
    assert body["answers"]["model"] == "echo"
    assert body["answers"]["grounded"].startswith("[echo]")
    assert body["answers"]["generic"].startswith("[echo]")
    assert "error" not in body["answers"]


def test_consult_can_skip_the_generic_arm(client_with_model: TestClient) -> None:
    body = client_with_model.post(
        "/consult",
        json={"patient_id": 6, "question": "Next step?", "include_generic": False},
    ).json()
    assert "grounded" in body["answers"]
    assert "generic" not in body["answers"]


def test_the_report_is_identical_whether_or_not_a_model_answered(
    client: TestClient, client_with_model: TestClient
) -> None:
    """The model must not be able to change the clinical content."""
    payload = {"patient_id": 6, "question": "Next step?"}
    without = client.post("/consult", json=payload).json()
    with_model = client_with_model.post("/consult", json=payload).json()
    assert without["report"] == with_model["report"]
    assert without["meta"] == with_model["meta"]


def test_health_reports_the_configured_model(
    client: TestClient, client_with_model: TestClient
) -> None:
    assert client.get("/health").json()["model"] == "none"
    assert client_with_model.get("/health").json()["model"] == "echo"


def test_responses_carry_server_timing(client: TestClient) -> None:
    """The seam the query telemetry will hang off."""
    response = client.get("/health")
    assert response.headers["Server-Timing"].startswith("app;dur=")
