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
