from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from tests.differential.bridge import REPO_ROOT, TsBridge


def _node_available() -> bool:
    try:
        subprocess.run(["npx", "--version"], cwd=REPO_ROOT, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return (REPO_ROOT / "node_modules").is_dir()


@pytest.fixture(scope="session")
def ts() -> Iterator[TsBridge]:
    """The TypeScript implementation, live, for the whole session."""
    if not _node_available():
        pytest.skip("node_modules not installed — run `npm install` at the repo root")
    bridge = TsBridge()
    try:
        yield bridge
    finally:
        bridge.close()


# ---------------------------------------------------------------------------
# The engine, built from the exported seed fixtures.
# ---------------------------------------------------------------------------

import json  # noqa: E402

from brahmo.drugs import Formulary  # noqa: E402
from brahmo.engine import Engine  # noqa: E402
from brahmo.interactions import InteractionTable  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = REPO_ROOT / "tests" / "golden"


def _rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="session")
def engine() -> Engine:
    """The engine over the real seeded formulary."""
    return Engine(
        formulary=Formulary.from_rows(_rows("drugs.json")),
        interactions=InteractionTable.from_rows(_rows("drug_interactions.json")),
    )


@pytest.fixture(scope="session")
def golden_cases() -> list[dict]:
    """Every patient with the TypeScript engine's recorded report."""
    return [json.loads(p.read_text()) for p in sorted(GOLDEN.glob("patient-*.json"))]


@pytest.fixture(scope="session")
def composer() -> "Composer":
    """The composer over the real seeded corpus."""
    from brahmo import response_instructions
    from brahmo.composer import Composer
    from brahmo.retrieval import GuidelineLibrary, HospitalFormulary

    return Composer(
        formulary=Formulary.from_rows(_rows("drugs.json")),
        guidelines=GuidelineLibrary.from_rows(_rows("indian_guidelines.json")),
        stock=HospitalFormulary(_rows("hospital_formulary.json")),
        instructions=response_instructions(),
    )


@pytest.fixture(scope="session")
def api_corpus():
    """The corpus the HTTP tests run on, from the exported fixtures."""
    from brahmo.corpus import Corpus

    return Corpus.from_json_dir(FIXTURES)
